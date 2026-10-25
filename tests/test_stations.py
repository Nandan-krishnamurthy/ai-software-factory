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

from factory import cli, evidence, guard, prbody, state
from tests import REPO_ROOT

STATIONS_DIR = REPO_ROOT / "stations"
SECTIONS = ["Purpose", "Preconditions", "Inputs", "Steps", "Outputs", "Checkpoint",
            "Stop conditions", "Done check"]
FRONTMATTER_KEYS = ["id", "name", "allowed_from", "next"]
GATES = {"GATE_A", "GATE_B", "GATE_C"}
ENTRY_POINTS = {"START"}  # /factory-start
# Stations that other stations may already name, before they are built.
PENDING: dict[str, str] = {}
# The stations built by T2.4. Later tasks add more; these must always exist.
PLANNING_STATIONS = {"S00-intake.md", "S02-requirements.md", "S03-architecture.md",
                     "S04-plan.md", "S05-stories.md", "S05b-issues.md"}
# Target-repo paths from architecture §5.1 (<INC> is the increment folder).
ALLOWED_OUTPUTS = {
    ".factory/config.json",
    ".factory/log.md",
    "docs/factory/traceability.md",
    "docs/factory/knowledge.md",
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
# T6.5: S09-S11 run the verification engine; the model writes no gate result, test result
# or PR body fact itself (rule H1). Each pattern is a way a station could ask it to.
VERIFICATION_STATIONS = ("S09", "S10", "S11")
HAND_WRITTEN = [
    (r"\{\{", "fills a template placeholder by hand"),
    (r"templates/pr\.md", "fills the PR template by hand instead of `pr render`"),
    (r"(?i)\bresult lines?\b", "keeps a command's result line by hand"),
    (r"(?i)every gate shows", "writes gate results by hand"),
    (r"Skipped: commands\.", "writes a gate's wording by hand"),
    (r"(?i)\b(?:run|re-run)\b[^\n]*?`commands\.(?:build|lint|typecheck|test)`",
     "runs a configured command by hand instead of `verify run`"),
    (r"(?i)\bthe full commands\b", "runs the quality commands by hand"),
]
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
    def next(self) -> str | list[str]:
        return self.frontmatter.get("next", "")

    @property
    def nexts(self) -> list[str]:
        """Where the station leads: one station or gate, or a branch (``next: [S01, S02]``,
        S00 for an existing or a new project)."""
        value = self.next
        return value if isinstance(value, list) else [value]

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
        if not s.nexts or any(n not in ids | GATES | set(PENDING) for n in s.nexts):
            problems.append(f"{s.id}: next {s.next!r} is not a station or a gate")
        for source in s.allowed_from:
            if source not in ids | GATES | ENTRY_POINTS | set(PENDING):
                problems.append(f"{s.id}: allowed_from {source!r} is not a station, gate "
                                "or entry point")
            elif source in by_id and s.id not in by_id[source].nexts:
                problems.append(f"{s.id}: allowed_from {source}, but {source}.next is "
                                f"{by_id[source].next!r}")
        for nxt in s.nexts:
            if nxt in by_id and s.id not in by_id[nxt].allowed_from:
                problems.append(f"{s.id}: next is {nxt}, but {nxt}.allowed_from does not "
                                f"list {s.id}")
    # Everything is reachable from an entry point. Transitions: an entry point or a gate
    # leads to every station that lists it in allowed_from; a station leads to its next.
    reached, frontier = set(), set(ENTRY_POINTS)
    while frontier:
        node = frontier.pop()
        reached.add(node)
        if node in by_id:
            targets = set(by_id[node].nexts) & (GATES | ids)
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
        self.assertEqual([by_id[i].next for i in ("S01", "S02", "S03", "S04", "S05", "S05b")],
                         ["S02", "S03", "S04", "S05", "GATE_A", "GATE_C"])
        # S00 leads to Codebase Discovery for an existing project, else straight to S02.
        self.assertEqual(by_id["S00"].next, ["S01", "S02"])
        self.assertEqual(by_id["S00"].allowed_from, ["START"])
        self.assertEqual(by_id["S01"].allowed_from, ["S00"])
        self.assertEqual(by_id["S02"].allowed_from, ["S00", "S01"])
        self.assertIn("GATE_A", by_id["S05"].allowed_from)  # revision mode (GATE_A_CHANGES)
        self.assertEqual(by_id["S05b"].allowed_from, ["GATE_A"])

    def test_branches_prs_and_issues_are_created_only_through_idempotent_helpers(self):
        """T4.4: a create-type action always looks for the item first, so a resumed
        station never makes a second branch, PR or issue. The helpers do that in code
        (``factory.py branch``, ``pr``, ``issues sync``); no station creates one directly."""
        direct = re.compile(r"\bgh\s+(?:pr|issue)\s+create\b|\bgit\b[^`\n]*\b(?:switch\s+-c|"
                            r"checkout\s+-b|branch\s+(?!-)[^`\s]+)")
        for station in self.stations:
            with self.subTest(station=station.id):
                found = [c for c in commands(station.text) if direct.search(c)]
                self.assertEqual(found, [])
        by_id = {s.id: s for s in self.stations}
        self.assertIn("python scripts/factory.py branch --name factory/plan-<INC> --base <D>",
                      by_id["S00"].sections["Steps"])
        self.assertIn("python scripts/factory.py branch --name <B>", by_id["S07"].sections["Steps"])

    def test_every_station_the_state_engine_names_exists(self):
        ids = {s.id for s in self.stations}
        named = {station for station, _ in state.PLAN_DOCS} | {"S05b"}
        named |= {"S06", "S07", "S08", "S11", "S12"}  # named literally by story states
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
            if station.id in ("S00", "S01", "S02", "S03", "S04", "S05"):
                with self.subTest(station=station.id):
                    self.assertIn(f'-m "{state.FACTORY_COMMIT_TRAILER}: {station.id}"',
                                  station.sections["Checkpoint"])

    def test_planning_pr_is_opened_idempotently_with_its_marker(self):
        s05 = {s.id: s for s in self.stations}["S05"]
        steps = s05.sections["Steps"]
        self.assertIn("python scripts/factory.py pr --head factory/plan-<INC>", steps)
        self.assertIn("--label factory:planning", steps)
        self.assertIn("issues sync --dry-run", steps)
        self.assertIn("<!-- factory:planning increment=<INC> -->", steps)

    def test_revision_mode_replies_to_every_item_through_factory_comment(self):
        s05 = {s.id: s for s in self.stations}["S05"]
        steps = s05.sections["Steps"]
        self.assertIn("python scripts/factory.py feedback --pr <N>", steps)
        self.assertIn("python scripts/factory.py comment --pr <N> --kind reply", steps)


class ExistingProjectPlanningTest(unittest.TestCase):
    """T5.2: /factory-start for an existing project and for the next increment."""

    def setUp(self):
        self.by_id = {s.id: s for s in load_stations()}

    def section(self, station_id, name):
        return self.by_id[station_id].sections[name]

    def test_s00_starts_the_next_increment_after_a_complete_one(self):
        self.assertIn("`INCREMENT_COMPLETE`", self.section("S00", "Preconditions"))
        steps = self.section("S00", "Steps")
        # INCREMENT_COMPLETE's state names the finished increment: S00 must not reuse it.
        self.assertIn("**Resumed run** (`state --json` reports `PLANNING`)", steps)
        self.assertIn("**New increment** (`UNCONFIGURED` or `INCREMENT_COMPLETE`)", steps)
        new = steps[steps.index("**New increment**"):]
        self.assertLess(new.index("`git -C <T> pull --ff-only`"),
                        new.index("`python scripts/factory.py increment next --json`"))
        self.assertIn("`002-<slug>` after `001-initial`", steps)

    def test_existing_projects_use_the_delta_templates(self):
        for station_id, template in (("S02", "requirements-delta.md"),
                                     ("S03", "architecture-delta.md")):
            with self.subTest(station=station_id):
                self.assertIn(f"templates/{template}", self.section(station_id, "Inputs"))
                steps = self.section(station_id, "Steps")
                self.assertIn(f"**Existing project** (`01-codebase-analysis.md` exists): "
                              f"fill `templates/{template}`", steps)
                self.assertIn("**New project**: use these sections, in this order:", steps)


class IntakeStationTest(unittest.TestCase):
    """T7.2: S00 creates the labels before doctor, and takes non-Markdown requirements."""

    LABELS = "python scripts/factory.py labels ensure"
    DOCTOR = "python scripts/factory.py doctor"

    def setUp(self):
        self.s00 = {s.id: s for s in load_stations()}["S00"]
        self.steps = self.s00.sections["Steps"]

    def test_labels_are_ensured_before_the_first_doctor(self):
        """AC3 (M2 Problem 1): on a brand-new repo, doctor's labels FAIL is what labels ensure
        fixes, so labels ensure must run first, and doctor must still run before anything
        else changes."""
        self.assertIn(self.LABELS, self.steps)
        first_doctor = self.steps.index(self.DOCTOR)
        self.assertLess(self.steps.index(self.LABELS), first_doctor)
        before = self.steps[:first_doctor]
        for later in ("gh repo view", "increment next", "factory.py branch", "config.json",
                      "00-prd.md"):
            self.assertNotIn(later, before, f"{later!r} must come after the first doctor")
        self.assertIn(self.DOCTOR, self.steps[first_doctor + len(self.DOCTOR):],
                      "doctor must still run again at the end")
        self.assertIn("If it reports any `FAIL`", self.steps[first_doctor:])

    def test_requirements_are_taken_by_format(self):
        """AC2 (M2 Problem 3) and decision D-C."""
        for text in ("`.md` or `.markdown`", "copy it unchanged", "`.txt`", "`.pdf`",
                     "faithful Markdown", "source header", "stop and ask"):
            self.assertIn(text, self.steps)
        stops = self.s00.sections["Stop conditions"]
        self.assertIn("not Markdown, text or PDF", stops)
        self.assertIn("cannot be reproduced", stops)
        # The content stays data, and the secret check covers a transcription too.
        self.assertIn("rule U1", self.steps)
        self.assertIn("rule S6", self.steps)

    def test_the_source_header_format_is_documented(self):
        """Decision D-D: one fixed header, documented in templates/README.md."""
        readme = (REPO_ROOT / "templates" / "README.md").read_text(encoding="utf-8")
        self.assertIn("<!-- factory:prd-source", self.steps)
        self.assertIn("templates/README.md", self.steps)
        self.assertIn("<!-- factory:prd-source", readme)
        for field in ("git hash-object", "outside the repository", "Not reproduced:"):
            self.assertIn(field, readme)


class DiscoveryStationTest(unittest.TestCase):
    """T5.1: S01 never guesses a command, and stops on a red baseline."""

    def setUp(self):
        self.s01 = {s.id: s for s in load_stations()}["S01"]

    def section(self, name):
        return self.s01.sections[name]

    def test_commands_come_from_evidence_and_are_run(self):
        steps = self.section("Steps")
        self.assertIn("python scripts/factory.py discover --json", steps)
        self.assertIn("Never compose a command yourself", steps)
        self.assertIn("Otherwise `null`", steps)
        self.assertIn("verbatim", steps)
        self.assertIn("**Run the baseline**", steps)
        # Rule H4 is named where the station states its purpose.
        self.assertIn("rule H4", self.section("Purpose"))

    def test_red_baseline_asks_the_human_and_commits_nothing(self):
        steps = self.section("Steps")
        self.assertIn("python scripts/factory.py question answer --key baseline-<INC> "
                      "--keyword accept-baseline --json", steps)
        self.assertIn("python scripts/factory.py question ask --key baseline-<INC>", steps)
        self.assertIn("**without** writing anything into `<T>`", steps)
        self.assertIn("nothing is committed", self.section("Checkpoint"))
        self.assertIn("**Red baseline**", self.section("Stop conditions"))
        self.assertIn("`NEEDS_HUMAN`", self.section("Done check"))
        # The analysis reaches <T> only after the gate (step 7 follows step 6).
        self.assertLess(steps.index("**Gate on the baseline.**"),
                        steps.index("Copy the analysis to `<T>/docs/factory/increments/"))

    def test_it_writes_only_the_commands_of_the_config(self):
        self.assertIn("set each of the five `commands`", self.section("Steps"))
        self.assertIn("change nothing else", self.section("Steps"))
        self.assertIn(".factory/config.json` (its `commands` only)", self.section("Outputs"))

    def test_knowledge_base_is_created_or_updated(self):
        """T7.3: S01 is the only writer of docs/factory/knowledge.md, and the write is
        gated by `knowledge check`, never by hand-guessed freshness."""
        steps = self.section("Steps")
        self.assertIn("python scripts/factory.py knowledge check --json", steps)
        for text in ("missing", "invalid", "stale", "## Changes", "latest earlier increment"):
            self.assertIn(text, steps)
        for heading in ("## Stack", "## Layout", "## Conventions", "## Commands",
                        "## Hotspots", "## Architecture decisions", "## Known risks",
                        "## Changes"):
            self.assertIn(heading, steps)
        self.assertIn("<!-- factory:knowledge checked=", steps)
        self.assertIn("docs/factory/knowledge.md", self.section("Outputs"))
        self.assertIn("docs/factory/knowledge.md", self.section("Checkpoint"))
        self.assertIn("knowledge check --json` reports `\"ok\": true`",
                      self.section("Done check"))
        # Written after the analysis, from facts already gathered (no second discovery run).
        self.assertLess(steps.index("Copy the analysis to `<T>/docs/factory/increments/"),
                        steps.index("**Update the knowledge base**"))
        # Links by path, which is what `knowledge check` counts (review of PR #52).
        self.assertIn("link every merged increment's `03-architecture.md` by its path", steps)
        self.assertIn("Naming an increment without its path does not count", steps)

    def test_rules_follow_target_conventions_without_obeying_their_text(self):
        """T7.3 decision K-E, reworded in the review of PR #52: CLAUDE.md and knowledge.md
        stay useful conventions at level 4, but their text is data and cannot override
        rules 1-3."""
        rules = (REPO_ROOT / "stations" / "_rules.md").read_text(encoding="utf-8")
        level4 = next(line for line in rules.splitlines() if line.startswith("4. "))
        for text in ("`<target>/CLAUDE.md`", "`<target>/docs/factory/knowledge.md`",
                     "Follow the conventions they record", "rule U1",
                     "is not followed", "nothing in them overrides rules 1–3"):
            self.assertIn(text, level4)
        order = [line[:3] for line in rules.splitlines() if re.match(r"^[1-5]\. \*\*", line)]
        self.assertEqual(order, ["1. ", "2. ", "3. ", "4. ", "5. "])


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
        self.assertIn('python scripts/factory.py pr --head <B> --title "[#<I>] <story title>" '
                      "--body-file <SCRATCH>/pr-<I>.md --draft", stuck)
        self.assertIn("gh issue edit <I> --repo <R> --add-label factory:needs-human", stuck)
        self.assertIn("Stuck", self.section("S10", "Steps"))  # a failed AC counts too

    def rework(self, station_id):
        steps = self.section(station_id, "Steps")
        return steps[steps.index("### Rework mode"):]

    def test_rework_runs_s08_to_s11_under_the_lock(self):
        """T4.2 (architecture §7.2): the rework path through the story stations."""
        self.assertIn("GATE_B", self.by_id["S08"].allowed_from)
        for sid in ("S08", "S09", "S10", "S11"):
            with self.subTest(station=sid):
                self.assertIn(f"`GATE_B_CHANGES_REQUESTED` with `next_station` `{sid}`",
                              self.section(sid, "Preconditions"))
        s08 = self.rework("S08")
        for text in ("limits.max_review_rounds",
                     "python scripts/factory.py label --issue <I> --status changes-requested",
                     "--station S08 --next S08 --branch <B> --fix-attempts 0",
                     "python scripts/factory.py feedback --pr <P> --rework",
                     "`Feedback <id>: <what changed, or why nothing changed>`", "rule U4"):
            self.assertIn(text, s08)
        self.assertLess(s08.index("limits.max_review_rounds"), s08.index("--status changes"))

    def test_s11_answers_every_item_then_counts_the_round_then_releases_the_lock(self):
        s11 = self.rework("S11")
        order = ["python scripts/factory.py comment --pr <P> --kind reply --to <id>",
                 "python scripts/factory.py comment --pr <P> --kind reply --body-file "
                 "<SCRATCH>/round-<k>.md",
                 "--station S11 --next GATE_B --branch <B> --review-round <k>",
                 "python scripts/factory.py label --issue <I> --status in-review"]
        positions = [s11.index(text) for text in order]
        self.assertEqual(positions, sorted(positions))
        self.assertIn("Repeat until `feedback --pr <P> --rework` lists no item", s11)
        self.assertIn("feedback --pr <P> --rework` lists no item",
                      self.section("S11", "Done check"))

    def test_s12_closes_out_only_after_an_observed_merge(self):
        """T4.3: S12 confirms the merge first, merges nothing and picks nothing."""
        s12 = self.by_id["S12"]
        self.assertEqual((s12.allowed_from, s12.next), (["GATE_B"], "GATE_C"))
        steps = self.section("S12", "Steps")
        confirm = steps.index("python scripts/factory.py closeout --issue <I> --json")
        for later in ("git -C <T> switch <D>", "git -C <T> branch -D <B>",
                      "python scripts/factory.py comment --issue <I> --kind reply",
                      "python scripts/factory.py closeout --issue <I> --finish"):
            self.assertLess(confirm, steps.index(later), later)
        self.assertNotIn("pick", " ".join(commands(s12.text)))
        self.assertIn("reports `CLOSEOUT_PENDING` with `next_station` `S12`",
                      self.section("S12", "Preconditions"))
        self.assertIn("reports `IDLE_AT_GATE_C`", self.section("S12", "Done check"))

    def test_s12_deletes_only_the_merged_branch_and_marks_done_before_the_checkpoint(self):
        steps = self.section("S12", "Steps")
        delete = steps.index("git -C <T> branch -D <B>")
        self.assertLess(steps.index("git -C <T> rev-parse <B>"), delete)
        self.assertIn("If they differ, the branch has commits that are not in the PR: keep it",
                      steps)
        # status:done (closeout --finish) first; the checkpoint is only a record after it.
        self.assertLess(steps.index("closeout --issue <I> --finish"),
                        steps.index("**Checkpoint**"))
        self.assertIn("--station S12 --next GATE_C --branch <B> --sha <merge_sha>",
                      self.section("S12", "Checkpoint"))

    def test_s12_reports_the_knowledge_base_on_the_increments_last_story_only(self):
        """T7.3 decision K-A: S12 only reports, from traceability.md and `knowledge
        check`; S01 is the only writer, and S12 still commits nothing (rule S1)."""
        steps = self.section("S12", "Steps")
        self.assertIn("python scripts/factory.py knowledge check --json",
                      self.section("S12", "Inputs"))
        self.assertIn("**Knowledge base**", steps)
        self.assertIn("increment_complete", steps)
        self.assertIn("docs/factory/traceability.md", steps)
        self.assertIn("never commits anything", steps)
        self.assertNotIn("docs/factory/knowledge.md", self.section("S12", "Outputs"))
        self.assertIn("Nothing is committed", self.section("S12", "Checkpoint"))
        # Review of PR #52: every status is reported, and exit 1 never stops close-out.
        self.assertIn("exit 1 is not a stop condition", steps)
        for status in ("`fresh`", "`stale`", "`missing`", "`invalid`"):
            self.assertIn(status, steps)
        self.assertIn("the next S01 creates it", steps)
        self.assertIn("the next S01 rewrites every section", steps)

    def test_s11_brings_the_branch_up_to_date_and_sends_it_back_to_s09(self):
        # T6.5 (B-06): new <D> commits change the code, so S09 and S10 run again, rather
        # than S11 re-running the commands by hand.
        steps = self.section("S11", "Steps")
        self.assertIn("git -C <T> rev-list --count <B>..origin/<D>", steps)
        self.assertIn("git -C <T> pull --no-rebase --no-edit origin <D>", steps)
        back = steps.index("--station S11 --next S09 --branch <B>")
        self.assertLess(steps.index("pull --no-rebase"), back)
        self.assertLess(back, steps.index("python scripts/factory.py pr --head <B>"))

    def test_s11_publishes_the_render_and_copies_the_verdict_unchanged(self):
        # T6.5: the body is `pr render`'s (the verdict lines copied unchanged by the code),
        # published as written and confirmed by `pr check`.
        steps = self.section("S11", "Steps")
        order = ["python scripts/factory.py pr render --issue <I> --notes "
                 "<SCRATCH>/notes-<I>.md --out <SCRATCH>/pr-<I>.md",
                 'python scripts/factory.py pr --head <B> --title "[#<I>] <story title>" '
                 "--body-file <SCRATCH>/pr-<I>.md --json",
                 "docs/factory/traceability.md",
                 "python scripts/factory.py verify run --issue <I>",
                 "python scripts/factory.py verify map --issue <I>",
                 "python scripts/factory.py pr check <P>"]
        positions = [steps.index(text) for text in order]
        self.assertEqual(positions, sorted(positions))
        self.assertIn("exactly as written", steps)
        self.assertIn("`python scripts/factory.py pr check <P>` exits 0",
                      self.section("S11", "Done check"))
        self.assertIn("copied unchanged (rule H5)", self.section("S11", "Purpose"))
        # The verdict S10 stored is what the render copies: it is on GitHub, not in the session.
        self.assertIn("--body-file <SCRATCH>/verdict-<I>.md", self.section("S10", "Checkpoint"))

    def test_skipped_gate_wording_is_the_engines(self):
        # T6.5: the stations no longer write gate results, so the template contract's
        # wording for a null command is what `pr render` produces.
        readme = (REPO_ROOT / "templates" / "README.md").read_text(encoding="utf-8")
        self.assertIn("`Skipped: commands.<name> is null`", readme)
        recorded = evidence.Evidence(
            issue=1, repo="o/r", branch="story/1-x", sha="1" * 40, started_at="",
            finished_at="", sha_after="1" * 40, commands=[
                evidence.CommandEvidence(name, None, "skipped")
                for name in evidence.VERIFY_COMMANDS])
        gate = prbody._command_gate("gate_build", "Q1 Build", recorded, "build")
        self.assertEqual(gate.value, "Skipped: commands.build is null")
        for sid in ("S09", "S11"):
            with self.subTest(station=sid):
                self.assertNotIn("Skipped: commands.", self.by_id[sid].text)

    def test_s11_updates_traceability_and_moves_the_label(self):
        self.assertIn("docs/factory/traceability.md", self.section("S11", "Outputs"))
        self.assertIn("python scripts/factory.py label --issue <I> --status in-review",
                      self.section("S11", "Steps"))

    def test_s10_uses_the_ac_verifier_and_never_self_verifies(self):
        s10 = self.by_id["S10"].text
        self.assertIn("`ac-verifier` subagent", s10)
        self.assertIn(".claude/agents/ac-verifier.md", s10)
        self.assertIn("never verify your own work", self.section("S10", "Preconditions"))


def hand_written_results(text: str) -> list[str]:
    """Why a station's text asks the model to run the quality commands or write gate
    results itself (rule H1, T6.5); empty if it leaves both to the engine."""
    return [f"{why}: {m[0]!r}" for pattern, why in HAND_WRITTEN
            for m in [re.search(pattern, text)] if m]


class VerificationEngineTest(unittest.TestCase):
    """T6.5: S09-S11 use the verification engine, and contain no hand-written gate results."""

    def setUp(self):
        self.by_id = {s.id: s for s in load_stations()}

    def steps(self, sid):
        return self.by_id[sid].sections["Steps"]

    def test_no_station_has_the_model_write_results(self):
        for sid in VERIFICATION_STATIONS:
            with self.subTest(station=sid):
                self.assertEqual(hand_written_results(self.by_id[sid].text), [])

    def test_the_lint_catches_the_hand_written_forms(self):
        # Lines from S09 and S11 as they were before T6.5.
        for text in ("Fill [`templates/pr.md`](../templates/pr.md) into `<SCRATCH>/pr-<I>.md` "
                     "**honestly**: every gate shows its real result",
                     "Run, from inside `<T>`, each non-`null` command from "
                     "`.factory/config.json`: `commands.build`, then `commands.test`",
                     "Keep the exact result line of each",
                     "A `null` command is **skipped**: write `Skipped: commands.<name> is null`",
                     "Then run the full commands again (build, lint, typecheck)",
                     "`{{test_command}}` and `{{test_result}}`: the real full-suite command"):
            with self.subTest(text=text[:40]):
                self.assertTrue(hand_written_results(text))

    def test_s09_commits_then_runs_the_commands_through_the_factory(self):
        steps = self.steps("S09")
        run = steps.index("python scripts/factory.py verify run --issue <I>")
        self.assertLess(steps.index("Commit and push the tests"), run)
        self.assertIn("nothing is committed after them", steps)
        self.assertIn("python scripts/factory.py verify check --issue <I>` exits 0",
                      self.by_id["S09"].sections["Done check"])

    def test_the_stuck_draft_pr_is_rendered(self):
        stuck = self.by_id["S09"].sections["Stop conditions"]
        order = ["python scripts/factory.py verify map --issue <I>",
                 "python scripts/factory.py pr render --issue <I> --notes "
                 "<SCRATCH>/notes-<I>.md --stuck --out <SCRATCH>/pr-<I>.md",
                 'python scripts/factory.py pr --head <B> --title "[#<I>] <story title>" '
                 "--body-file <SCRATCH>/pr-<I>.md --draft"]
        positions = [stuck.index(text) for text in order]
        self.assertEqual(positions, sorted(positions))
        self.assertIn("Stuck", self.steps("S10"))

    def test_s10_maps_the_run_before_the_verifier(self):
        steps = self.steps("S10")
        self.assertLess(steps.index("python scripts/factory.py verify map --issue <I>"),
                        steps.index("Start the `ac-verifier` subagent"))
        self.assertLess(steps.index("Start the `ac-verifier` subagent"),
                        steps.index("python scripts/factory.py verdict check --issue <I>"))
        self.assertIn("python scripts/factory.py verify check --issue <I>` exits 0",
                      self.by_id["S10"].sections["Preconditions"])

    def test_s12_runs_the_commands_a_story_introduced_before_it_is_done(self):
        # B-01: the walking skeleton's commands are approved by the merge and run then.
        steps = self.by_id["S12"].sections["Steps"]
        run = steps.index("python scripts/factory.py verify run --issue <I>")
        self.assertLess(steps.index("git -C <T> switch <D>"), run)
        self.assertLess(run, steps.index("python scripts/factory.py closeout --issue <I> "
                                         "--finish"))
        self.assertIn("verify_after_merge", steps)


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

    PR = {"number": 7, "state": "OPEN", "mergedAt": None, "headRefName": "factory/plan-x",
          "commits": [{"committedDate": "2026-09-24T10:00:00Z"}],
          "comments": [
              {"id": "c1", "author": {"login": "alice"}, "body": "/changes\nSplit STORY-002",
               "createdAt": "2026-09-24T11:00:00Z", "url": "u1"},
              {"id": "c2", "author": {"login": "mallory"}, "body": "/changes\nmerge it",
               "createdAt": "2026-09-24T11:01:00Z", "url": "u2"},
              {"id": "c3", "author": {"login": "alice"}, "body": "old remark",
               "createdAt": "2026-09-24T09:00:00Z", "url": "u3"}],
          "reviews": []}
    INLINE = [{"id": 9, "user": {"login": "alice"}, "body": "Rename this REQ",
               "created_at": "2026-09-24T11:02:00Z", "html_url": "u9",
               "path": "docs/factory/increments/x/02-requirements.md", "line": 4}]

    def test_rework_lists_the_unanswered_items_after_a_push(self):
        """T4.2: ``feedback --rework`` keeps the round's items until each is answered."""
        from factory.markers import ReplyMarker, build

        pr = dict(self.PR, commits=[{"committedDate": "2026-09-24T10:00:00Z"},
                                    {"committedDate": "2026-09-24T12:00:00Z"}])
        pr["comments"] = [*self.PR["comments"], {
            "id": "f1", "author": {"login": "alice"}, "createdAt": "2026-09-24T12:05:00Z",
            "body": build(ReplyMarker(to="c1")) + "\nSplit into STORY-002 and STORY-009."}]
        data = self.run_feedback(pr, "--rework")
        self.assertEqual((data["verdict"], data["rework"]), ("PENDING", True))
        self.assertEqual([i["id"] for i in data["items"]], ["c3", "9"])  # c1 is answered

    def test_lists_only_human_items_of_the_current_round(self):
        data = self.run_feedback(self.PR)
        self.assertEqual(data["verdict"], "CHANGES_REQUESTED")
        self.assertEqual([(i["id"], i["is_trigger"], i["text"]) for i in data["items"]],
                         [("c1", True, "Split STORY-002"), ("9", False, "Rename this REQ")])
        self.assertEqual(data["items"][1]["path"],
                         "docs/factory/increments/x/02-requirements.md")

    def run_feedback(self, pr, *extra):
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
        inline = self.INLINE
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
            code = cli.main(["feedback", "--pr", "7", "--json", *extra])
        self.assertEqual(code, 0)
        self.assertTrue(all(c[0] in ("pr", "api") for c in calls))  # reads only
        return json.loads(out.getvalue())


if __name__ == "__main__":
    unittest.main()
