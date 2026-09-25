"""T4.4: resume robustness — idempotent branches and PRs, and crash replay.

A session can end after any step of a station. The state engine then names the same
station again (its checkpoint was not written), so ``/factory-resume`` runs it **from
the start**. The crash-replay tests run a station's steps, stop after step *k* (for
every *k*), run the whole station again, and compare the result with a run that never
crashed: the same single branch, PR and checkpoint, never a second one.

The branch tests use real git (a bare ``origin`` and a clone in a temp directory); the
PR, comment and label calls go to an in-memory GitHub.
"""

import json
import re
import shutil
import tempfile
import unittest
from pathlib import Path

from factory import comments, ensure, pick
from factory.gh import Gh, ProcessResult
from factory.git import Git
from factory.markers import CheckpointMarker, PlanningMarker, PrMarker, StoryMarker, build, find

REPO = "owner/app"
STORY_BODY = build(PrMarker("STORY-012")) + "\nCloses #12\n\n## Summary\n- adds a task"
PLAN_BODY = build(PlanningMarker("001-initial")) + "\n## Summary\n- the plan"
IDENTITY = ["-c", "user.name=factory", "-c", "user.email=factory@example.invalid"]


class FakeGitHub:
    """PRs, issue comments and labels, served through the gh transport interface."""

    def __init__(self):
        self.prs: list[dict] = []
        self.comments: dict[int, list[dict]] = {}
        self.issues = {12: {"number": 12, "labels": [{"name": "factory:story"},
                                                     {"name": "status:in-progress"}],
                            "body": build(StoryMarker("STORY-012", "001-initial"))}}
        self.next_id = 100

    def __call__(self, argv, *, timeout, cwd=None, env=None, input=None):
        args = list(argv[1:])
        if args[:2] == ["pr", "list"]:
            head = args[args.index("--head") + 1]
            return self.ok([{"number": p["number"], "url": p["url"], "isDraft": p["draft"],
                             "baseRefName": p["base"]}
                            for p in self.prs if p["head"] == head and p["state"] == "OPEN"])
        if args[:2] == ["pr", "create"]:
            number = 20 + len(self.prs)
            labels = [args[i + 1] for i, a in enumerate(args) if a == "--label"]
            self.prs.append({"number": number, "state": "OPEN", "draft": "--draft" in args,
                             "head": args[args.index("--head") + 1],
                             "base": args[args.index("--base") + 1],
                             "title": args[args.index("--title") + 1], "body": input,
                             "labels": labels, "url": f"https://github.com/{REPO}/pull/{number}"})
            return ProcessResult([], 0, f"https://github.com/{REPO}/pull/{number}\n", "")
        if args[:2] == ["pr", "edit"]:
            pr = next(p for p in self.prs if p["number"] == int(args[2]))
            if "--title" in args:
                pr["title"], pr["body"] = args[args.index("--title") + 1], input
            if "--add-label" in args and args[args.index("--add-label") + 1] not in pr["labels"]:
                pr["labels"].append(args[args.index("--add-label") + 1])
            return ProcessResult([], 0, pr["url"] + "\n", "")
        assert args[0] == "api", args
        endpoint, method = args[1], args[args.index("--method") + 1]
        if m := re.fullmatch(rf"repos/{REPO}/issues/(\d+)/comments", endpoint):
            number = int(m[1])
            if method == "GET":
                return self.ok([list(self.comments.get(number, []))])
            self.next_id += 1
            comment = {"id": self.next_id, "body": json.loads(input)["body"], "html_url": "u"}
            self.comments.setdefault(number, []).append(comment)
            return self.ok(comment)
        if m := re.fullmatch(rf"repos/{REPO}/issues/comments/(\d+)", endpoint):
            for comment in (c for cs in self.comments.values() for c in cs):
                if comment["id"] == int(m[1]):
                    comment["body"] = json.loads(input)["body"]
                    return self.ok(comment)
        if m := re.fullmatch(rf"repos/{REPO}/issues/(\d+)", endpoint):
            return self.ok(self.issues[int(m[1])])
        if m := re.fullmatch(rf"repos/{REPO}/issues/(\d+)/labels(?:/(.+))?", endpoint):
            issue = self.issues[int(m[1])]
            if method == "POST":
                issue["labels"] += [{"name": x} for x in json.loads(input)["labels"]]
            else:
                name = m[2].replace("%3A", ":")
                issue["labels"] = [x for x in issue["labels"] if x["name"] != name]
            return self.ok(issue["labels"])
        raise AssertionError(f"unexpected call {args}")

    @staticmethod
    def ok(data):
        return ProcessResult([], 0, json.dumps(data), "")

    def open_prs(self, head):
        return [p for p in self.prs if p["head"] == head and p["state"] == "OPEN"]

    def checkpoints(self, number=12):
        return [c for c in self.comments.get(number, []) if c["body"].startswith(
            "<!-- factory:checkpoint")]


_TEMPLATE: tempfile.TemporaryDirectory | None = None


def template() -> Path:
    """A bare ``origin`` with one commit on ``main``, and a clone of it. Built once and
    copied for every world, because starting git processes is slow on Windows."""
    global _TEMPLATE
    if _TEMPLATE is None:
        _TEMPLATE = tempfile.TemporaryDirectory()
        root = Path(_TEMPLATE.name)
        origin, seed = root / "origin.git", root / "seed"
        Git(root).run(["init", "-q", "--bare", "-b", "main", str(origin)])
        Git(root).run(["clone", "-q", str(origin), str(seed)])
        (seed / "README.md").write_text("# app\n", encoding="utf-8")
        Git(seed).run(["add", "README.md"])
        Git(seed).run([*IDENTITY, "commit", "-qm", "initial"])
        Git(seed).run(["push", "-q", "origin", "HEAD:main"])
        Git(root).run(["clone", "-q", str(origin), str(root / "target")])
    return Path(_TEMPLATE.name)


def tearDownModule():
    if _TEMPLATE is not None:
        _TEMPLATE.cleanup()


class World:
    """A target clone with a real ``origin`` (a bare repo), and an in-memory GitHub."""

    def __init__(self, test: unittest.TestCase):
        tmp = tempfile.TemporaryDirectory()
        test.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        for name in ("origin.git", "target"):
            shutil.copytree(template() / name, root / name)
        self.path = root / "target"
        self.git = Git(self.path)
        self.git.run(["remote", "set-url", "origin", str(root / "origin.git")])
        self.fake = FakeGitHub()
        self.gh = Gh(transport=self.fake)

    def remote_heads(self, prefix: str) -> list[str]:
        out = self.git.run(["ls-remote", "--heads", "origin"])
        return sorted(line.split("refs/heads/")[1] for line in out.splitlines()
                      if line.split("refs/heads/")[1].startswith(prefix))

    def commit_and_push(self, path: str, line: str, station: str) -> None:
        with open(self.path / path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
        self.git.run(["add", path])
        self.git.run([*IDENTITY, "commit", "-qm", f"{station} step",
                      "-m", f"Factory-Station: {station}"])
        self.git.run(["push", "-q", "-u", "origin", self.git.current_branch()])

    def checkpoint(self, station: str, nxt: str) -> None:
        comments.upsert_checkpoint(self.gh, REPO, 12, station=station, next_station=nxt,
                                   branch=self.git.current_branch(),
                                   sha=self.git.rev_parse("HEAD"))


# ----------------------------------------------------------------------------- branches


class EnsureBranchTest(unittest.TestCase):
    def test_creates_the_branch_from_the_default_branch(self):
        w = World(self)
        result = ensure.ensure_branch(w.git, "story/12-add-task", "main")
        self.assertEqual((result.name, result.action), ("story/12-add-task", "created"))
        self.assertEqual(w.git.current_branch(), "story/12-add-task")
        self.assertEqual(w.git.rev_parse("HEAD"), w.git.rev_parse("origin/main"))

    def test_reuses_a_pushed_branch_even_with_another_slug(self):
        w = World(self)
        ensure.ensure_branch(w.git, "story/12-add-task", "main")
        w.commit_and_push("log.md", "S07", "S07")
        w.git.run(["switch", "-q", "main"])
        w.git.run(["branch", "-q", "-D", "story/12-add-task"])  # e.g. a fresh clone
        result = ensure.ensure_branch(w.git, "story/12-add-a-task", "main")
        self.assertEqual((result.name, result.action), ("story/12-add-task", "reused-remote"))
        self.assertEqual(w.remote_heads("story/12-"), ["story/12-add-task"])
        self.assertIn("S07", (w.path / "log.md").read_text(encoding="utf-8"))

    def test_reuses_a_local_branch_that_was_never_pushed(self):
        w = World(self)
        ensure.ensure_branch(w.git, "story/12-add-task", "main")
        w.git.run(["switch", "-q", "main"])
        result = ensure.ensure_branch(w.git, "story/12-other-slug", "main")
        self.assertEqual((result.name, result.action), ("story/12-add-task", "reused-local"))

    def test_another_storys_branch_is_not_reused(self):
        w = World(self)
        ensure.ensure_branch(w.git, "story/1-first", "main")
        w.commit_and_push("log.md", "x", "S07")
        w.git.run(["switch", "-q", "main"])
        # story/12-… must not match story/1-… (nor story/120-…)
        self.assertEqual(ensure.ensure_branch(w.git, "story/12-add", "main").action, "created")

    def test_refuses_when_two_branches_match(self):
        w = World(self)
        for name in ("story/12-a", "story/12-b"):
            w.git.run(["switch", "-q", "-c", name, "origin/main"])
            w.git.run(["push", "-q", "origin", name])
        w.git.run(["switch", "-q", "main"])
        with self.assertRaises(ensure.EnsureError) as ctx:
            ensure.ensure_branch(w.git, "story/12-c", "main")
        self.assertIn("story/12-a, story/12-b", str(ctx.exception))

    def test_uncommitted_changes_are_reported_and_kept(self):
        """A session killed during S08 leaves its unfinished work: never discarded."""
        w = World(self)
        ensure.ensure_branch(w.git, "story/12-add-task", "main")
        (w.path / "src.ts").write_text("half done", encoding="utf-8")
        with self.assertRaises(ensure.EnsureError) as ctx:
            ensure.ensure_branch(w.git, "story/12-add-task", "main")
        self.assertIn("?? src.ts", str(ctx.exception))
        self.assertIn("never discards", str(ctx.exception))
        self.assertEqual((w.path / "src.ts").read_text(encoding="utf-8"), "half done")
        self.assertEqual(w.git.current_branch(), "story/12-add-task")

    def test_the_planning_branch_is_matched_exactly(self):
        w = World(self)
        name = "factory/plan-001-initial"
        self.assertEqual(ensure.ensure_branch(w.git, name, "main").action, "created")
        w.commit_and_push("log.md", "S00", "S00")
        self.assertEqual(ensure.ensure_branch(w.git, name, "main").action, "reused-remote")
        self.assertEqual(w.remote_heads("factory/plan-"), [name])

    def test_family(self):
        self.assertEqual(ensure.family("story/12-add-task"), "story/12-")
        self.assertEqual(ensure.family("factory/plan-001-initial"), "factory/plan-001-initial")
        with self.assertRaises(ensure.EnsureError):
            ensure.ensure_branch(Git("."), "story/add-task", "main")  # no issue number


# ----------------------------------------------------------------------------- PRs


class EnsurePrTest(unittest.TestCase):
    def setUp(self):
        self.fake = FakeGitHub()
        self.gh = Gh(transport=self.fake)

    def ensure(self, **kw):
        args = dict(head="story/12-add-task", base="main", title="[#12] Add a task",
                    body=STORY_BODY)
        return ensure.ensure_pr(self.gh, REPO, **{**args, **kw})

    def test_creates_once_then_updates_the_same_pr(self):
        first = self.ensure()
        second = self.ensure(title="[#12] Add a task (v2)", body=STORY_BODY + "\nmore")
        self.assertEqual((first.action, second.action), ("created", "updated"))
        self.assertEqual(first.number, second.number)
        (pr,) = self.fake.open_prs("story/12-add-task")
        self.assertEqual((pr["title"], pr["body"].endswith("more")),
                         ("[#12] Add a task (v2)", True))

    def test_a_stuck_draft_is_later_updated_not_duplicated(self):
        draft = self.ensure(draft=True)
        ready = self.ensure()
        self.assertEqual((draft.number, ready.number, ready.is_draft), (20, 20, True))
        self.assertEqual(len(self.fake.prs), 1)

    def test_labels_are_added_once(self):
        head = "factory/plan-001-initial"
        for _ in range(2):
            self.ensure(head=head, body=PLAN_BODY, labels=("factory:planning",))
        (pr,) = self.fake.open_prs(head)
        self.assertEqual(pr["labels"], ["factory:planning"])

    def test_refusals(self):
        with self.assertRaises(ensure.EnsureError) as ctx:
            self.ensure(body="no marker")
        self.assertIn("marker", str(ctx.exception))
        self.fake.prs = [{"number": n, "state": "OPEN", "draft": False,
                          "head": "story/12-add-task", "base": "main", "labels": [],
                          "url": f"u/{n}"} for n in (20, 21)]
        with self.assertRaises(ensure.EnsureError) as ctx:
            self.ensure()
        self.assertIn("#20, #21", str(ctx.exception))
        self.fake.prs = [dict(self.fake.prs[0], base="develop")]
        with self.assertRaises(ensure.EnsureError) as ctx:
            self.ensure()
        self.assertIn("targets 'develop'", str(ctx.exception))


# ----------------------------------------------------------------------------- replay


class CrashReplayTest(unittest.TestCase):
    """Stop a station after each step, run it again from the start, compare."""

    def replay(self, setup, steps, observe):
        reference = World(self)
        setup(reference)
        for step in steps:
            step(reference)
        expected = observe(reference)
        for k in range(len(steps) + 1):
            with self.subTest(crash_after_step=k):
                w = World(self)
                setup(w)
                for step in steps[:k]:
                    step(w)  # … and the session ends here
                for step in steps:  # the resumed station starts over
                    step(w)
                self.assertEqual(observe(w), expected)
        return expected

    def test_s07_branch(self):
        steps = [
            lambda w: ensure.ensure_branch(w.git, "story/12-add-task", "main"),
            lambda w: w.commit_and_push(".factory-log.md", "S07 branch", "S07"),
            lambda w: w.checkpoint("S07", "S08"),
        ]

        def observe(w):
            marker = find(w.fake.checkpoints()[0]["body"], CheckpointMarker)
            return {"branches": w.remote_heads("story/12-"),
                    "checkpoints": len(w.fake.checkpoints()),
                    "checkpoint": (marker.station, marker.next, marker.branch),
                    "current": w.git.current_branch()}

        expected = self.replay(lambda w: None, steps, observe)
        self.assertEqual(expected, {"branches": ["story/12-add-task"], "checkpoints": 1,
                                    "checkpoint": ("S07", "S08", "story/12-add-task"),
                                    "current": "story/12-add-task"})

    def test_s11_pr(self):
        def setup(w):  # S07-S10 are done: the branch is pushed, the story in progress
            ensure.ensure_branch(w.git, "story/12-add-task", "main")
            w.commit_and_push("src.ts", "code", "S08")
            w.checkpoint("S10", "S11")

        steps = [
            lambda w: ensure.ensure_pr(w.gh, REPO, head="story/12-add-task", base="main",
                                       title="[#12] Add a task", body=STORY_BODY),
            lambda w: w.commit_and_push("traceability.md", "REQ-001 #20", "S11"),
            lambda w: pick.set_status(w.gh, REPO, 12, "in-review"),
            lambda w: w.checkpoint("S11", "GATE_B"),
        ]

        def observe(w):
            return {"prs": [(p["number"], p["draft"]) for p in w.fake.prs],
                    "checkpoints": len(w.fake.checkpoints()),
                    "status": sorted(x["name"] for x in w.fake.issues[12]["labels"]
                                     if x["name"].startswith("status:")),
                    "branches": w.remote_heads("story/12-")}

        expected = self.replay(setup, steps, observe)
        self.assertEqual(expected, {"prs": [(20, False)], "checkpoints": 1,
                                    "status": ["status:in-review"],
                                    "branches": ["story/12-add-task"]})

    def test_s00_and_s05_planning_branch_and_pr(self):
        head = "factory/plan-001-initial"
        steps = [
            lambda w: ensure.ensure_branch(w.git, head, "main"),
            lambda w: w.commit_and_push("00-prd.md", "PRD", "S00"),
            lambda w: w.commit_and_push("05-stories.md", "stories", "S05"),
            lambda w: ensure.ensure_pr(w.gh, REPO, head=head, base="main",
                                       title="[Planning] 001-initial", body=PLAN_BODY,
                                       labels=("factory:planning",)),
        ]

        def observe(w):
            return {"branches": w.remote_heads("factory/plan-"),
                    "prs": [(p["number"], p["labels"]) for p in w.fake.prs]}

        expected = self.replay(lambda w: None, steps, observe)
        self.assertEqual(expected, {"branches": [head],
                                    "prs": [(20, ["factory:planning"])]})


if __name__ == "__main__":
    unittest.main()
