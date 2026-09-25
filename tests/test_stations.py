"""Station lint (T2.4): every station file is structurally valid and safe.

Checked for each ``stations/S*.md``:

* frontmatter ``id``/``name``/``allowed_from``/``next``, with ``id`` matching the file name;
* the eight required sections, in order, none empty; the file requires ``_rules.md``;
* an objective Done check: checklist items, at least one command, and the state that
  ``state --json`` must report afterwards;
* output paths that exist in architecture §5.1, and the planning document that
  ``state.py`` expects from that station;
* every command it names: ``factory.py`` commands parse with the real CLI parser, ``gh``
  commands are pre-approved or read-only, ``git`` runs as ``git -C <T>`` (rule T3), and
  every ``gh``/``git`` command is **allowed by the real guard**. No merge step, no push to
  the default branch, no force-push, no direct comment, no story pick;
* the ``allowed_from``/``next`` graph across all stations.

The helpers are module-level so the command-file lint (T2.5) can reuse them.
"""

import contextlib
import io
import json
import re
import shlex
import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path

from factory import cli, guard, state
from tests import REPO_ROOT

STATIONS_DIR = REPO_ROOT / "stations"
SECTIONS = ["Purpose", "Preconditions", "Inputs", "Steps", "Outputs", "Checkpoint",
            "Stop conditions", "Done check"]
FRONTMATTER_KEYS = ["id", "name", "allowed_from", "next"]
GATES = {"GATE_A", "GATE_B", "GATE_C"}
ENTRY_POINTS = {"START"}  # /factory-start
# Stations that other stations may already name, before they are built.
PENDING = {"S01": "T5.1 (M5)"}
# The stations built by T2.4. Later tasks add more; these must always exist.
PLANNING_STATIONS = {"S00-intake.md", "S02-requirements.md", "S03-architecture.md",
                     "S04-plan.md", "S05-stories.md", "S05b-issues.md"}
# Target-repo paths from architecture §5.1 (<INC> is the increment folder).
ALLOWED_OUTPUTS = {
    ".factory/config.json",
    ".factory/log.md",
    "docs/factory/traceability.md",
    *(f"docs/factory/increments/<INC>/{name}" for _, name in state.PLAN_DOCS),
}
# Commands never allowed anywhere in a station file (D1, S1, S2, S4, S14).
FORBIDDEN = [
    (r"\bgh\s+pr\s+merge\b", "merges a PR (D1, rule S1)"),
    (r"\bgh\s+pr\s+review\b", "reviews a PR"),
    (r"\bgh\s+(?:pr|issue)\s+comment\b", "comments without a marker (rule S14)"),
    (r"mergePullRequest|enablePullRequestAutoMerge|mergeBranch", "merges via GraphQL (D1)"),
    (r"/pulls/[^\s/`]+/merge\b|/merges\b", "merges via the REST API (D1)"),
    (r"--auto\b", "enables auto-merge (D1)"),
    (r"\bgit\b[^`\n]*\bmerge\b", "runs git merge"),
    (r"--force\b|--force-with-lease\b|\bpush\s+-f\b", "force-pushes (rule S4)"),
    (r"--authorized-by-continue", "picks a story; only S06, run by /factory-continue, may "
                                  "(rule S2)"),
    (r"\bgit\b[^`\n]*\breset\s+--hard\b", "discards work"),
]
GH_APPROVED = {  # .claude/settings.json permissions.allow
    ("issue", "create"), ("issue", "view"), ("issue", "edit"), ("issue", "list"),
    ("pr", "create"), ("pr", "view"), ("pr", "edit"), ("pr", "list"),
}
GH_READ_ONLY = {("repo", "view"), ("api", "user"), ("auth", "status"), ("pr", "checks")}
# S06 is the one station that starts a story, and only /factory-continue runs it
# (test_commands checks that no other command has S06 in its scope).
PICK_STATION = "S06"
PLACEHOLDERS = {"<T>": "/work/target", "<R>": "owner/app", "<D>": "main",
                "<INC>": "001-initial", "<N>": "7", "<k>": "1", "<SCRATCH>": "/tmp/factory",
                "<I>": "12", "<B>": "story/12-add-task", "<P>": "21"}
# The story loop built by T3.3, S06 (pick) to S11 (PR), ending at Gate B.
STORY_STATIONS = ("S06", "S07", "S08", "S09", "S10", "S11")
_SPAN = re.compile(r"`([^`\n]+)`")


@dataclass
class Station:
    path: Path
    frontmatter: dict
    intro: str
    sections: dict[str, str]
    order: list[str]
    text: str

    @property
    def id(self) -> str:
        return self.frontmatter.get("id", "")

    @property
    def next(self) -> str:
        return self.frontmatter.get("next", "")

    @property
    def allowed_from(self) -> list[str]:
        value = self.frontmatter.get("allowed_from", [])
        return value if isinstance(value, list) else []


def parse_frontmatter(text: str) -> tuple[dict, str]:
    """A tiny YAML subset: ``key: value`` and ``key: [a, b]`` between ``---`` lines."""
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---\n", 4)
    if end < 0:
        return {}, text
    data: dict = {}
    for line in text[4:end].splitlines():
        if not line.strip():
            continue
        key, _, value = line.partition(":")
        value = value.strip()
        if value.startswith("[") and value.endswith("]"):
            data[key.strip()] = [v.strip() for v in value[1:-1].split(",") if v.strip()]
        else:
            data[key.strip()] = value
    return data, text[end + 5:]


def parse_station(path: Path) -> Station:
    text = path.read_text(encoding="utf-8")
    frontmatter, body = parse_frontmatter(text)
    sections: dict[str, str] = {}
    order: list[str] = []
    intro: list[str] = []
    current: list[str] | None = None
    fenced = False
    for line in body.splitlines():
        if line.startswith("```"):
            fenced = not fenced
        if not fenced and line.startswith("## "):
            name = line[3:].strip()
            order.append(name)
            current = []
            sections[name] = ""
            continue
        if current is None:
            intro.append(line)
        else:
            sections[order[-1]] += line + "\n"
    return Station(path, frontmatter, "\n".join(intro), sections, order, text)


def substitute(command: str) -> str:
    for placeholder, value in PLACEHOLDERS.items():
        command = command.replace(placeholder, value)
    return re.sub(r"<[^>\s]+(?: [^>]+)?>", "x", command)  # any other placeholder


def commands(text: str) -> list[str]:
    """Every backticked span that is a ``python scripts/factory.py``, ``gh`` or ``git`` command."""
    return [span for span in _SPAN.findall(text)
            if span.startswith(("python scripts/factory.py", "gh ", "git "))]


def guard_context(scratch: Path) -> guard.GuardContext:
    return guard.GuardContext(factory_root=REPO_ROOT, target_root=Path("/work/target"),
                              cwd=REPO_ROOT, default_branch="main", scratch_dirs=(scratch,))


def lint_command(command: str, ctx: guard.GuardContext) -> list[str]:
    """Problems with one command named in a station (or a command file)."""
    problems = []
    try:
        raw = shlex.split(command)
    except ValueError:
        raw = []
    for token in raw[1:]:
        if token.startswith("/") and not token.startswith("//"):
            problems.append(f"`{command}`: argument {token!r} starts with '/', which Git Bash "
                            "on Windows rewrites into a Windows path; drop the slash")
    concrete = substitute(command)
    try:
        argv = shlex.split(concrete)
    except ValueError as err:
        return [f"`{command}`: cannot be parsed ({err})"]
    if argv[:2] == ["python", "scripts/factory.py"]:
        err = io.StringIO()
        try:
            with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
                cli.build_parser().parse_args(argv[2:])
        except SystemExit as exc:
            if exc.code:
                problems.append(f"`{command}`: not a valid factory.py command: "
                                f"{err.getvalue().strip().splitlines()[-1]}")
    elif argv[0] == "gh":
        if tuple(argv[1:3]) not in GH_APPROVED | GH_READ_ONLY:
            problems.append(f"`{command}`: `gh {' '.join(argv[1:3])}` is neither pre-approved "
                            "in .claude/settings.json nor read-only")
    elif argv[0] == "git" and argv[1:2] != ["-C"]:
        problems.append(f"`{command}`: run git as `git -C <T> …` (rule T3)")
    if argv[0] in ("gh", "git"):
        decision = guard.decide("Bash", {"command": concrete}, ctx)
        if not decision.allowed:
            problems.append(f"`{command}`: blocked by the guard: {decision.reason}")
    return problems


def lint_station(station: Station, ctx: guard.GuardContext) -> list[str]:
    """Every problem with one station file, as readable strings. [] when it is valid."""
    problems: list[str] = []
    name = station.path.name
    match = re.fullmatch(r"(S\d{2}b?)-[a-z0-9]+(?:-[a-z0-9]+)*\.md", name)
    if match is None:
        problems.append(f"{name}: file name must look like S05-stories.md")
    if list(station.frontmatter) != FRONTMATTER_KEYS:
        problems.append(f"{name}: frontmatter keys must be {FRONTMATTER_KEYS}, got "
                        f"{list(station.frontmatter)}")
    if match and station.id != match[1]:
        problems.append(f"{name}: id {station.id!r} does not match the file name")
    if not station.frontmatter.get("name"):
        problems.append(f"{name}: frontmatter needs a name")
    if not isinstance(station.frontmatter.get("allowed_from"), list) \
            or not station.allowed_from:
        problems.append(f"{name}: allowed_from must be a non-empty [list]")
    if "_rules.md" not in station.intro:
        problems.append(f"{name}: must require stations/_rules.md before its sections")
    if station.order != SECTIONS:
        problems.append(f"{name}: sections must be exactly {SECTIONS}, got {station.order}")
    for section in SECTIONS:
        if not station.sections.get(section, "").strip():
            problems.append(f"{name}: section {section!r} is empty or missing")

    pre = station.sections.get("Preconditions", "")
    if "python scripts/factory.py state --json" not in pre:
        problems.append(f"{name}: Preconditions must check `python scripts/factory.py "
                        "state --json`")

    done = station.sections.get("Done check", "")
    items = [line for line in done.splitlines() if line.strip()]
    if not items or any(not line.startswith("- [ ] ") for line in items):
        problems.append(f"{name}: Done check must be a list of `- [ ] ` items")
    if not commands(done):
        problems.append(f"{name}: Done check must name at least one command to run")
    if "state --json" not in done or not any(f"`{s}`" in done for s in state.STATES):
        problems.append(f"{name}: Done check must say which state `state --json` reports")

    stops = station.sections.get("Stop conditions", "")
    if not any(line.startswith("- ") for line in stops.splitlines()):
        problems.append(f"{name}: Stop conditions must be a list")

    outputs = station.sections.get("Outputs", "")
    for path in re.findall(r"(?:\.factory|docs/factory)/[A-Za-z0-9_./<>-]*[A-Za-z0-9>]",
                           outputs):
        if path not in ALLOWED_OUTPUTS:
            problems.append(f"{name}: output {path!r} is not a target path in "
                            "architecture §5.1")

    for pattern, why in FORBIDDEN:
        if pattern == "--authorized-by-continue" and station.id == PICK_STATION:
            continue
        for found in re.finditer(pattern, station.text):
            line = station.text[:found.start()].count("\n") + 1
            problems.append(f"{name}:{line}: {why}: {found.group(0)!r}")
    for line in station.sections.get("Steps", "").splitlines():
        if re.search(r"\bmerge\b", line, re.I) and not re.search(
                r"human|never|yourself|\bnot\b", line, re.I):
            problems.append(f"{name}: a step mentions merging: {line.strip()!r} "
                            "(only the human merges, D1)")

    for command in commands(station.text):
        problems += [f"{name}: {p}" for p in lint_command(command, ctx)]
    return problems


def lint_graph(stations: list[Station]) -> list[str]:
    """The ``allowed_from``/``next`` graph across all stations."""
    problems: list[str] = []
    ids = {s.id for s in stations}
    by_id = {s.id: s for s in stations}
    if len(ids) != len(stations):
        problems.append("two stations share an id")
    for s in stations:
        if s.next not in ids | GATES | set(PENDING):
            problems.append(f"{s.id}: next {s.next!r} is not a station or a gate")
        for source in s.allowed_from:
            if source not in ids | GATES | ENTRY_POINTS | set(PENDING):
                problems.append(f"{s.id}: allowed_from {source!r} is not a station, gate "
                                "or entry point")
            elif source in by_id and by_id[source].next != s.id:
                problems.append(f"{s.id}: allowed_from {source}, but {source}.next is "
                                f"{by_id[source].next!r}")
        if s.next in by_id and s.id not in by_id[s.next].allowed_from:
            problems.append(f"{s.id}: next is {s.next}, but {s.next}.allowed_from does not "
                            f"list {s.id}")
    # Everything is reachable from an entry point. Transitions: an entry point or a gate
    # leads to every station that lists it in allowed_from; a station leads to its next.
    reached, frontier = set(), set(ENTRY_POINTS)
    while frontier:
        node = frontier.pop()
        reached.add(node)
        if node in by_id:
            targets = {by_id[node].next} & (GATES | ids)
        else:
            targets = {s.id for s in stations if node in s.allowed_from}
        frontier |= targets - reached
    for s in stations:
        if s.id not in reached:
            problems.append(f"{s.id}: not reachable from {sorted(ENTRY_POINTS)}")
    return problems


def load_stations() -> list[Station]:
    return [parse_station(p) for p in sorted(STATIONS_DIR.glob("S*.md"))]


# ----------------------------------------------------------------------------- tests


class StationFilesTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.ctx = guard_context(Path(tmp.name))
        self.stations = load_stations()

    def test_planning_stations_exist(self):
        names = {s.path.name for s in self.stations}
        self.assertLessEqual(PLANNING_STATIONS, names)

    def test_every_station_passes_the_lint(self):
        for station in self.stations:
            with self.subTest(station=station.path.name):
                self.assertEqual(lint_station(station, self.ctx), [])

    def test_graph(self):
        self.assertEqual(lint_graph(self.stations), [])

    def test_planning_flow(self):
        by_id = {s.id: s for s in self.stations}
        self.assertEqual([by_id[i].next for i in ("S00", "S02", "S03", "S04", "S05", "S05b")],
                         ["S02", "S03", "S04", "S05", "GATE_A", "GATE_C"])
        self.assertEqual(by_id["S00"].allowed_from, ["START"])
        self.assertIn("GATE_A", by_id["S05"].allowed_from)  # revision mode (GATE_A_CHANGES)
        self.assertEqual(by_id["S05b"].allowed_from, ["GATE_A"])

    def test_every_station_the_state_engine_names_exists(self):
        ids = {s.id for s in self.stations}
        named = {station for station, _ in state.PLAN_DOCS} | {"S05b"}
        self.assertEqual(named - ids, set(PENDING))

    def test_each_planning_station_outputs_the_document_the_state_engine_expects(self):
        by_id = {s.id: s for s in self.stations}
        for station_id, doc in state.PLAN_DOCS:
            if station_id in PENDING:
                continue
            with self.subTest(station=station_id):
                self.assertIn(f"docs/factory/increments/<INC>/{doc}",
                              by_id[station_id].sections["Outputs"])
        self.assertIn(".factory/config.json", by_id["S00"].sections["Outputs"])

    def test_allowed_outputs_are_in_architecture_5_1(self):
        arch = (REPO_ROOT / "docs" / "02-factory-architecture.md").read_text(encoding="utf-8")
        tree = arch[arch.index("### 5.1"):arch.index("### 5.2")]
        for path in ALLOWED_OUTPUTS:
            with self.subTest(path=path):
                self.assertIn(path.rsplit("/", 1)[-1], tree)

    def test_planning_commits_carry_the_station_trailer(self):
        # state.py checks invariant 4 with this trailer.
        for station in self.stations:
            if station.id in ("S00", "S02", "S03", "S04", "S05"):
                with self.subTest(station=station.id):
                    self.assertIn(f'-m "{state.FACTORY_COMMIT_TRAILER}: {station.id}"',
                                  station.sections["Checkpoint"])

    def test_planning_pr_is_opened_idempotently_with_its_marker(self):
        s05 = {s.id: s for s in self.stations}["S05"]
        steps = s05.sections["Steps"]
        self.assertIn("gh pr list --repo <R> --head factory/plan-<INC> --state open", steps)
        self.assertLess(steps.index("gh pr list"), steps.index("gh pr create"))
        self.assertIn("--label factory:planning", steps)
        self.assertIn("issues sync --dry-run", steps)
        self.assertIn("<!-- factory:planning increment=<INC> -->", steps)

    def test_revision_mode_replies_to_every_item_through_factory_comment(self):
        s05 = {s.id: s for s in self.stations}["S05"]
        steps = s05.sections["Steps"]
        self.assertIn("python scripts/factory.py feedback --pr <N>", steps)
        self.assertIn("python scripts/factory.py comment --pr <N> --kind reply", steps)


class StoryStationsTest(unittest.TestCase):
    """T3.3: the story loop S06-S11, as in architecture §7.1."""

    def setUp(self):
        self.by_id = {s.id: s for s in load_stations()}

    def section(self, station_id, name):
        return self.by_id[station_id].sections[name]

    def test_flow_from_gate_c_to_gate_b(self):
        self.assertEqual([self.by_id[i].next for i in STORY_STATIONS],
                         ["S07", "S08", "S09", "S10", "S11", "GATE_B"])
        self.assertEqual(self.by_id["S06"].allowed_from, ["GATE_C"])
        self.assertEqual(self.by_id["S05b"].next, "GATE_C")

    def test_only_s06_picks_a_story(self):
        for station in self.by_id.values():
            with self.subTest(station=station.id):
                if station.id == PICK_STATION:
                    self.assertIn("python scripts/factory.py pick --authorized-by-continue",
                                  station.sections["Steps"])
                else:
                    self.assertNotIn("pick --authorized-by-continue", station.text)

    def test_s06_writes_no_checkpoint_so_the_state_engine_names_s07(self):
        s06 = self.by_id["S06"].text
        self.assertNotIn("--kind checkpoint", s06)
        self.assertIn("reports `STORY_IN_PROGRESS` with `next_station` `S07`",
                      self.section("S06", "Done check"))

    def test_every_station_pushes_and_checkpoints(self):
        # A push and a checkpoint after every station (architecture §7.1): at most one
        # station's work is lost if the session dies.
        for sid, nxt in (("S07", "S08"), ("S08", "S09"), ("S09", "S10"), ("S10", "S11"),
                         ("S11", "GATE_B")):
            with self.subTest(station=sid):
                checkpoint = self.section(sid, "Checkpoint")
                self.assertIn(f"python scripts/factory.py comment --issue <I> --kind checkpoint "
                              f"--station {sid} --next {nxt} --branch <B>", checkpoint)
                if sid != "S10":  # S10 changes no code
                    self.assertIn("git -C <T> push", checkpoint)
                    self.assertIn(f'-m "{state.FACTORY_COMMIT_TRAILER}: {sid}"', checkpoint)

    def test_done_checks_match_the_state_engine(self):
        for sid, nxt in (("S07", "S08"), ("S08", "S09"), ("S09", "S10"), ("S10", "S11")):
            with self.subTest(station=sid):
                self.assertIn(f"reports `STORY_IN_PROGRESS` with `next_station` `{nxt}`",
                              self.section(sid, "Done check"))
        self.assertIn("reports `GATE_B_WAITING_REVIEW`", self.section("S11", "Done check"))

    def test_story_stations_read_the_state_and_the_targets_claude_md(self):
        for sid in STORY_STATIONS[1:]:
            with self.subTest(station=sid):
                self.assertIn("`STORY_IN_PROGRESS` with `next_station` `" + sid + "`",
                              self.section(sid, "Preconditions"))
        for sid in ("S08", "S09"):
            self.assertIn("<T>/CLAUDE.md", self.section(sid, "Inputs"))

    def test_fix_attempts_then_a_draft_pr_and_needs_human(self):
        s09 = self.by_id["S09"].text
        self.assertIn("limits.max_fix_attempts", s09)
        self.assertIn("--fix-attempts <k>", s09)
        stuck = self.section("S09", "Stop conditions")
        self.assertIn("gh pr create --draft", stuck)
        self.assertIn("gh issue edit <I> --repo <R> --add-label factory:needs-human", stuck)
        self.assertLess(stuck.index("gh pr list --repo <R> --head <B>"),
                        stuck.index("gh pr create --draft"))
        self.assertIn("Stuck", self.section("S10", "Steps"))  # a failed AC counts too

    def test_s11_brings_the_branch_up_to_date_and_re_tests_before_the_pr(self):
        steps = self.section("S11", "Steps")
        self.assertIn("git -C <T> rev-list --count <B>..origin/<D>", steps)
        self.assertIn("git -C <T> pull --no-rebase --no-edit origin <D>", steps)
        self.assertIn("run the full commands again", steps)
        self.assertLess(steps.index("pull --no-rebase"), steps.index("gh pr create"))

    def test_s11_pr_follows_the_template_and_copies_the_verdict_unchanged(self):
        steps = self.section("S11", "Steps")
        self.assertIn("templates/pr.md", steps)
        self.assertIn("**copied unchanged** (rule H5)", steps)
        self.assertIn("`<!-- factory:pr story=<STORY-###> -->`", steps)
        self.assertLess(steps.index("gh pr list --repo <R> --head <B>"),
                        steps.index("gh pr create"))
        self.assertIn('--title "[#<I>] <story title>"', steps)
        self.assertIn("every heading of `templates/pr.md` in order, no `{{`",
                      self.section("S11", "Done check"))
        # The verdict S10 stored is what S11 copies: it is on GitHub, not in the session.
        self.assertIn("--body-file <SCRATCH>/verdict-<I>.md", self.section("S10", "Checkpoint"))

    def test_skipped_gate_wording_matches_the_template_contract(self):
        readme = (REPO_ROOT / "templates" / "README.md").read_text(encoding="utf-8")
        self.assertIn("`Skipped: commands.<name> is null`", readme)
        for sid in ("S09", "S11"):
            with self.subTest(station=sid):
                self.assertIn("`Skipped: commands.<name> is null`", self.by_id[sid].text)

    def test_s11_updates_traceability_and_moves_the_label(self):
        self.assertIn("docs/factory/traceability.md", self.section("S11", "Outputs"))
        self.assertIn("python scripts/factory.py label --issue <I> --status in-review",
                      self.section("S11", "Steps"))

    def test_s10_uses_the_ac_verifier_and_never_self_verifies(self):
        s10 = self.by_id["S10"].text
        self.assertIn("`ac-verifier` subagent", s10)
        self.assertIn(".claude/agents/ac-verifier.md", s10)
        self.assertIn("never verify your own work", self.section("S10", "Preconditions"))


class LintCatchesProblemsTest(unittest.TestCase):
    """The lint itself: a station that breaks a rule must be reported."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        self.ctx = guard_context(self.dir)
        self.good = (STATIONS_DIR / "S03-architecture.md").read_text(encoding="utf-8")

    def lint(self, text, name="S03-architecture.md"):
        path = self.dir / name
        path.write_text(text, encoding="utf-8")
        return "\n".join(lint_station(parse_station(path), self.ctx))

    def test_good_station_is_clean(self):
        self.assertEqual(self.lint(self.good), "")

    def test_each_problem_is_caught(self):
        steps_end = "6. Commit and push. See Checkpoint.\n"
        cases = {
            "merge command": ("6. Commit and push.", "6. Run `gh pr merge <N> --squash`.",
                              "merges a PR"),
            "push to main": (steps_end, steps_end + "7. Run `git -C <T> push origin <D>`.\n",
                             "blocked by the guard"),
            "force push": (steps_end, steps_end + "7. Run `git -C <T> push -f origin x`.\n",
                           "force-pushes"),
            "direct comment": (steps_end, steps_end + "7. Run `gh issue comment 1 -b hi`.\n",
                               "without a marker"),
            "story pick": (steps_end, steps_end + "7. Run `python scripts/factory.py pick "
                           "--authorized-by-continue`.\n", "picks a story"),
            "unknown factory.py command": (
                steps_end, steps_end + "7. Run `python scripts/factory.py plan --now`.\n",
                "not a valid factory.py command"),
            "bad flag": (steps_end, steps_end + "7. Run `python scripts/factory.py issues sync "
                         "--dryrun`.\n", "not a valid factory.py command"),
            "unapproved gh": (steps_end, steps_end + "7. Run `gh repo delete <R>`.\n",
                              "neither pre-approved"),
            "git without -C": (steps_end, steps_end + "7. Run `git status`.\n", "git -C"),
            "merge step in prose": (steps_end, steps_end + "7. Merge the PR when green.\n",
                                    "mentions merging"),
            "missing section": ("## Stop conditions", "## Stops", "sections must be"),
            "vague done check": ("- [ ] Every `REQ-###`", "Looks complete. Every `REQ-###`",
                                 "list of `- [ ] ` items"),
            "done check without state": (
                "reports `PLANNING` with `next_station` `S04`", "is fine",
                "which state"),
            "output outside §5.1": ("- `docs/factory/increments/<INC>/03-architecture.md`",
                                    "- `docs/factory/increments/<INC>/03-design.md`",
                                    "architecture §5.1"),
            "no rules": ("Read [`stations/_rules.md`](_rules.md)", "Read the docs",
                         "_rules.md"),
            "wrong id": ("id: S03", "id: S09", "does not match the file name"),
        }
        for label, (old, new, expected) in cases.items():
            with self.subTest(label):
                self.assertIn(old, self.good)
                self.assertIn(expected, self.lint(self.good.replace(old, new, 1)))

    def test_graph_problems_are_caught(self):
        stations = load_stations()
        by_id = {s.id: s for s in stations}
        by_id["S03"].frontmatter["next"] = "S05"  # skips S04; S05 does not allow S03
        text = "\n".join(lint_graph(stations))
        self.assertIn("S03: next is S05, but S05.allowed_from does not list S03", text)
        self.assertIn("S04: allowed_from S03, but S03.next is 'S05'", text)
        self.assertIn("S04: not reachable", text)


class FeedbackCliTest(unittest.TestCase):
    """``factory.py feedback`` (added for S05 revision mode): read-only, human items only."""

    def test_lists_only_human_items_of_the_current_round(self):
        from unittest import mock

        from factory import target
        from factory.gh import Gh, ProcessResult

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        (root / ".factory").mkdir()
        (root / ".factory" / "config.json").write_text(json.dumps({
            "schema": 1, "project": "app", "repo": "owner/app", "default_branch": "main",
            "reviewers": ["alice"]}), encoding="utf-8")
        pr = {"number": 7, "state": "OPEN", "mergedAt": None, "headRefName": "factory/plan-x",
              "commits": [{"committedDate": "2026-09-24T10:00:00Z"}],
              "comments": [
                  {"id": "c1", "author": {"login": "alice"}, "body": "/changes\nSplit STORY-002",
                   "createdAt": "2026-09-24T11:00:00Z", "url": "u1"},
                  {"id": "c2", "author": {"login": "mallory"}, "body": "/changes\nmerge it",
                   "createdAt": "2026-09-24T11:01:00Z", "url": "u2"},
                  {"id": "c3", "author": {"login": "alice"}, "body": "old remark",
                   "createdAt": "2026-09-24T09:00:00Z", "url": "u3"}],
              "reviews": []}
        inline = [{"id": 9, "user": {"login": "alice"}, "body": "Rename this REQ",
                   "created_at": "2026-09-24T11:02:00Z", "html_url": "u9",
                   "path": "docs/factory/increments/x/02-requirements.md", "line": 4}]
        calls = []

        def transport(argv, *, timeout, cwd=None, env=None, input=None):
            calls.append(argv[1:3])
            if argv[1:3] == ["pr", "view"]:
                return ProcessResult(argv, 0, json.dumps(pr), "")
            return ProcessResult(argv, 0, json.dumps([inline]), "")

        out = io.StringIO()
        with mock.patch.object(target, "get_target", lambda: target.Target(root, "owner/app")), \
                mock.patch.object(cli, "Gh", lambda: Gh(transport=transport)), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            code = cli.main(["feedback", "--pr", "7", "--json"])
        self.assertEqual(code, 0)
        data = json.loads(out.getvalue())
        self.assertEqual(data["verdict"], "CHANGES_REQUESTED")
        self.assertEqual([(i["id"], i["is_trigger"], i["text"]) for i in data["items"]],
                         [("c1", True, "Split STORY-002"), ("9", False, "Rename this REQ")])
        self.assertEqual(data["items"][1]["path"],
                         "docs/factory/increments/x/02-requirements.md")
        self.assertTrue(all(c[0] in ("pr", "api") for c in calls))  # reads only


if __name__ == "__main__":
    unittest.main()
