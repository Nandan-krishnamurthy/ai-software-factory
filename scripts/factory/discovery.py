"""Codebase discovery for station S01 (T5.1): the commands a repo declares, with evidence.

Rule H4: the factory never guesses a command. ``discover`` proposes a command only when the
repository itself declares it, and names the file and entry that do:

* a script in ``package.json`` (run with the package manager its lockfile or
  ``packageManager`` field names, or npm when none is named);
* a target in the ``Makefile`` (``build``, ``lint``, ``typecheck``/``type-check``, ``test``;
  never ``make install``, which usually installs onto the system);
* a Python tool configured in ``pyproject.toml``, ``setup.cfg``, ``tox.ini``,
  ``pytest.ini``, ``ruff.toml``, ``.flake8`` or ``mypy.ini`` (pytest, ruff, flake8, and mypy
  only when its ``files`` setting makes it runnable without arguments), and
  ``requirements.txt`` for the install;
* the manifest of a toolchain whose standard commands they are: ``go.mod`` and
  ``Cargo.toml``.

Where several sources declare the same command, the first one in that order is proposed and
the others are listed as ``alternatives``. Anything not declared is ``None`` and listed in
``missing``; other stacks it recognises (Maven, Gradle, .NET, Ruby, PHP) are reported in
``notes`` without commands. It also lists the ``run:`` lines of GitHub Actions workflows and
the project's own documents as **hints** for S01 to read: they are not proposals.

Only the repository root is scanned (plus ``.github/workflows``). Read-only: it never runs
anything. S01 runs every command before it writes it to ``.factory/config.json``.
"""

import configparser
import json
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from factory.config import COMMAND_NAMES

SCHEMA_VERSION = 1
_MAX_BYTES = 1_000_000  # a manifest larger than this is not read
_DOCS = ("README.md", "README", "CLAUDE.md", "CONTRIBUTING.md", "docs/CONTRIBUTING.md")
_NPM_PLACEHOLDER = "no test specified"  # the test script `npm init` writes
_SCRIPT_NAMES = {
    "build": ("build",),
    "lint": ("lint",),
    "typecheck": ("typecheck", "type-check"),
    "test": ("test",),
}
_MAKE_TARGET = re.compile(r"^([A-Za-z0-9][A-Za-z0-9_.-]*)\s*:(?!=)")
_OTHER_STACKS = (  # recognised, but discovery proposes no commands for them
    ("pom.xml", "Maven"), ("build.gradle", "Gradle"), ("build.gradle.kts", "Gradle"),
    ("Gemfile", "Ruby (Bundler)"), ("composer.json", "PHP (Composer)"),
)


@dataclass(frozen=True)
class Candidate:
    command: str
    evidence: str  # the file and entry that declare it

    def to_dict(self) -> dict[str, str]:
        return {"command": self.command, "evidence": self.evidence}


@dataclass(frozen=True)
class Hint:
    file: str
    line: int
    text: str

    def to_dict(self) -> dict[str, Any]:
        return {"file": self.file, "line": self.line, "text": self.text}


@dataclass
class Discovery:
    stacks: list[tuple[str, str]] = field(default_factory=list)  # (name, evidence)
    found: dict[str, list[Candidate]] = field(
        default_factory=lambda: {name: [] for name in COMMAND_NAMES})
    hints: list[Hint] = field(default_factory=list)
    docs: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def commands(self) -> dict[str, Candidate | None]:
        return {name: (found[0] if found else None) for name, found in self.found.items()}

    @property
    def missing(self) -> list[str]:
        return [name for name, found in self.found.items() if not found]

    def add(self, name: str, command: str, evidence: str) -> None:
        if all(c.command != command for c in self.found[name]):
            self.found[name].append(Candidate(command, evidence))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": SCHEMA_VERSION,
            "stacks": [{"name": n, "evidence": e} for n, e in self.stacks],
            "commands": {n: (c.to_dict() if c else None) for n, c in self.commands.items()},
            "alternatives": {n: [c.to_dict() for c in found[1:]]
                             for n, found in self.found.items() if len(found) > 1},
            "missing": self.missing,
            "hints": [h.to_dict() for h in self.hints],
            "docs": list(self.docs),
            "notes": list(self.notes),
        }


def discover(root: Path) -> Discovery:
    """The commands ``root`` declares, in the precedence order of the module docstring."""
    result = Discovery()
    _make(root, result)
    _node(root, result)
    _python(root, result)
    _toolchains(root, result)
    for name, stack in _OTHER_STACKS:
        if (root / name).is_file():
            result.stacks.append((stack, name))
            result.notes.append(f"{stack} project ({name}): discovery proposes no commands for "
                                "it; take them from the project's docs or CI, or leave them null.")
    if any(root.glob("*.sln")) or any(root.glob("*.csproj")):
        result.stacks.append((".NET", "*.sln / *.csproj"))
        result.notes.append(".NET project: discovery proposes no commands for it; take them "
                            "from the project's docs or CI, or leave them null.")
    result.hints = _workflow_hints(root)
    result.docs = [d for d in _DOCS if (root / d).is_file()]
    if not result.stacks:
        result.notes.append("No known manifest at the repository root.")
    return result


def render(result: Discovery) -> str:
    lines = ["Stacks: " + (", ".join(f"{n} ({e})" for n, e in result.stacks) or "none found")]
    for name, candidate in result.commands.items():
        shown = f"{candidate.command}    <- {candidate.evidence}" if candidate else "null"
        lines.append(f"  {name:<10} {shown}")
        for alt in result.found[name][1:]:
            lines.append(f"  {'':<10} also: {alt.command}    <- {alt.evidence}")
    if result.missing:
        lines.append("Not declared (null): " + ", ".join(result.missing))
    for hint in result.hints:
        lines.append(f"Hint: {hint.file}:{hint.line}: {hint.text}")
    if result.docs:
        lines.append("Docs to read: " + ", ".join(result.docs))
    lines.extend(f"Note: {note}" for note in result.notes)
    return "\n".join(lines)


# ----------------------------------------------------------------------------- sources


def _read(path: Path) -> str | None:
    try:
        if not path.is_file() or path.stat().st_size > _MAX_BYTES:
            return None
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _make(root: Path, result: Discovery) -> None:
    # Compare real names: on a case-insensitive file system "makefile" also opens "Makefile",
    # and the evidence must name the file that exists.
    present = {p.name for p in root.iterdir()} if root.is_dir() else set()
    for name in ("GNUmakefile", "makefile", "Makefile"):  # the order make looks for them
        text = _read(root / name) if name in present else None
        if text is not None:
            break
    else:
        return
    result.stacks.append(("Make", name))
    targets = {m.group(1) for line in text.splitlines() if (m := _MAKE_TARGET.match(line))}
    for command, names in _SCRIPT_NAMES.items():
        for target in names:
            if target in targets:
                result.add(command, f"make {target}", f"{name}: target `{target}`")
                break


def _node(root: Path, result: Discovery) -> None:
    text = _read(root / "package.json")
    if text is None:
        return
    result.stacks.append(("Node.js", "package.json"))
    try:
        data = json.loads(text)
    except ValueError as err:
        result.notes.append(f"package.json is not valid JSON ({err}): no commands taken from it.")
        return
    if not isinstance(data, dict):
        result.notes.append("package.json is not a JSON object: no commands taken from it.")
        return
    manager, why = _package_manager(root, data)
    if manager is None:
        result.notes.append("package.json has no lockfile and no packageManager field: the "
                            "install command is not determined.")
    else:
        install = {"npm": "npm ci", "yarn": "yarn install", "pnpm": "pnpm install"}[manager]
        result.add("install", install, why)
    runner = manager or "npm"
    scripts = data.get("scripts")
    scripts = scripts if isinstance(scripts, dict) else {}
    for command, names in _SCRIPT_NAMES.items():
        for script in names:
            body = scripts.get(script)
            if not isinstance(body, str) or not body.strip():
                continue
            if script == "test" and _NPM_PLACEHOLDER in body:
                result.notes.append("package.json scripts.test is npm's placeholder "
                                    "(\"no test specified\"): not a test command.")
                break
            how = "" if manager else " (run with npm: no other package manager is declared)"
            result.add(command, _run_script(runner, script),
                       f"package.json: scripts.{script}{how}")
            break


def _package_manager(root: Path, data: dict) -> tuple[str | None, str]:
    declared = data.get("packageManager")
    if isinstance(declared, str):
        name = declared.split("@", 1)[0].strip()
        if name in ("npm", "yarn", "pnpm"):
            return name, f"package.json: packageManager `{declared}`"
    for lockfile, name in (("pnpm-lock.yaml", "pnpm"), ("yarn.lock", "yarn"),
                           ("package-lock.json", "npm"), ("npm-shrinkwrap.json", "npm")):
        if (root / lockfile).is_file():
            return name, f"{lockfile} ({name} lockfile)"
    return None, ""


def _run_script(manager: str, script: str) -> str:
    if manager == "yarn":
        return f"yarn {script}"
    if script == "test":
        return f"{manager} test"
    return f"{manager} run {script}"


def _python(root: Path, result: Discovery) -> None:
    pyproject: dict[str, Any] = {}
    text = _read(root / "pyproject.toml")
    if text is not None:
        try:
            pyproject = tomllib.loads(text)
        except tomllib.TOMLDecodeError as err:
            result.notes.append(f"pyproject.toml is not valid TOML ({err}): no commands taken "
                                "from it.")
    tool = pyproject.get("tool") if isinstance(pyproject.get("tool"), dict) else {}
    setup_cfg = _ini(root / "setup.cfg", result)
    tox = _ini(root / "tox.ini", result)
    markers = [m for m in ("pyproject.toml", "setup.py", "setup.cfg", "requirements.txt")
               if (root / m).is_file()]
    if not markers:
        return
    result.stacks.append(("Python", ", ".join(markers)))

    if (root / "requirements.txt").is_file():
        result.add("install", "python -m pip install -r requirements.txt", "requirements.txt")

    pytest_evidence = (
        ("pyproject.toml: [tool.pytest.ini_options]" if "pytest" in tool else None)
        or ("pytest.ini" if (root / "pytest.ini").is_file() else None)
        or ("setup.cfg: [tool:pytest]" if setup_cfg.has_section("tool:pytest") else None)
        or ("tox.ini: [pytest]" if tox.has_section("pytest") else None)
        or ("conftest.py" if (root / "conftest.py").is_file() else None))
    if pytest_evidence:
        result.add("test", "python -m pytest", pytest_evidence)

    ruff_evidence = (("pyproject.toml: [tool.ruff]" if "ruff" in tool else None)
                     or next((f for f in ("ruff.toml", ".ruff.toml") if (root / f).is_file()),
                             None))
    if ruff_evidence:
        result.add("lint", "python -m ruff check", ruff_evidence)
    flake8_evidence = ((".flake8" if (root / ".flake8").is_file() else None)
                       or ("setup.cfg: [flake8]" if setup_cfg.has_section("flake8") else None)
                       or ("tox.ini: [flake8]" if tox.has_section("flake8") else None))
    if flake8_evidence:
        result.add("lint", "python -m flake8", flake8_evidence)

    mypy_ini = _ini(root / "mypy.ini", result)
    mypy = tool.get("mypy") if isinstance(tool.get("mypy"), dict) else None
    sources = [("pyproject.toml: [tool.mypy]", mypy is not None, bool(mypy and mypy.get("files"))),
               ("mypy.ini: [mypy]", mypy_ini.has_section("mypy"),
                mypy_ini.has_option("mypy", "files") if mypy_ini.has_section("mypy") else False),
               ("setup.cfg: [mypy]", setup_cfg.has_section("mypy"),
                setup_cfg.has_option("mypy", "files") if setup_cfg.has_section("mypy") else False)]
    for where, configured, has_files in sources:
        if configured and has_files:
            result.add("typecheck", "python -m mypy", f"{where} with `files`")
            break
        if configured:
            result.notes.append(f"mypy is configured ({where}) without `files`: it needs paths "
                                "on the command line, so no typecheck command is proposed.")
            break

    if not result.found["test"]:
        result.notes.append("Python project without a test runner configuration (pytest): no "
                            "test command is proposed from the manifests.")


def _ini(path: Path, result: Discovery) -> configparser.ConfigParser:
    parser = configparser.ConfigParser(interpolation=None)
    text = _read(path)
    if text is not None:
        try:
            parser.read_string(text, source=path.name)
        except configparser.Error as err:
            result.notes.append(f"{path.name} could not be read ({err.__class__.__name__}): no "
                                "commands taken from it.")
            return configparser.ConfigParser(interpolation=None)
    return parser


def _toolchains(root: Path, result: Discovery) -> None:
    if (root / "go.mod").is_file():
        result.stacks.append(("Go", "go.mod"))
        for name, command in (("build", "go build ./..."), ("lint", "go vet ./..."),
                              ("test", "go test ./...")):
            result.add(name, command, "go.mod (the Go toolchain's standard command)")
    if (root / "Cargo.toml").is_file():
        result.stacks.append(("Rust", "Cargo.toml"))
        for name, command in (("build", "cargo build"), ("test", "cargo test")):
            result.add(name, command, "Cargo.toml (Cargo's standard command)")


def _workflow_hints(root: Path) -> list[Hint]:
    """The ``run:`` lines of GitHub Actions workflows, including ``run: |`` blocks."""
    hints: list[Hint] = []
    folder = root / ".github" / "workflows"
    if not folder.is_dir():
        return hints
    for path in sorted([*folder.glob("*.yml"), *folder.glob("*.yaml")]):
        text = _read(path)
        if text is None:
            continue
        name = path.relative_to(root).as_posix()
        block_indent: int | None = None
        for number, line in enumerate(text.splitlines(), start=1):
            indent = len(line) - len(line.lstrip())
            if block_indent is not None:
                if line.strip() and indent > block_indent:
                    hints.append(Hint(name, number, line.strip()))
                    continue
                if line.strip():
                    block_indent = None
            match = re.match(r"^\s*(?:-\s+)?run:\s*(.*)$", line)
            if not match:
                continue
            value = match.group(1).strip()
            if value in ("|", ">", "|-", ">-", "|+", ">+"):
                block_indent = indent
            elif value:
                hints.append(Hint(name, number, value.strip("'\"")))
    return hints
