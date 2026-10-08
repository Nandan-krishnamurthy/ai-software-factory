"""Dependency manifests and lockfiles, for the deterministic PR body (T6.3).

``pr render`` lists every dependency a story adds and cross-checks it against the
``New dependency: <name> — <reason>`` lines of the commit bodies (rule S9). A new
dependency is a name that a manifest the branch changes declares at the story's head and
did not declare at its base. The manifests read, by file name:

* Node.js ``package.json`` and PHP ``composer.json``: the dependency sections;
* Python ``requirements*.txt`` / ``requirements*.in``, ``pyproject.toml`` (PEP 621
  ``project``, PEP 735 ``dependency-groups``, Poetry) and ``Pipfile``;
* Go ``go.mod``: direct requirements (``// indirect`` ones are not new dependencies);
* Rust ``Cargo.toml``: every ``*dependencies`` table, per target too;
* Ruby ``Gemfile``: ``gem`` lines.

A Makefile declares no dependencies, so it is never a manifest. Lockfiles are not
manifests either: they are what a package manager wrote, and gate Q7 leaves them out of
a story's size.
"""

import json
import re
import tomllib
from pathlib import PurePosixPath

# Lockfiles of the package managers above (and a few more); excluded from the Q7 size.
LOCKFILES = frozenset({
    "package-lock.json", "npm-shrinkwrap.json", "yarn.lock", "pnpm-lock.yaml", "bun.lockb",
    "bun.lock", "composer.lock", "poetry.lock", "Pipfile.lock", "pdm.lock", "uv.lock",
    "go.sum", "Cargo.lock", "Gemfile.lock", "packages.lock.json", "Podfile.lock",
    "pubspec.lock", "mix.lock", "gradle.lockfile", "flake.lock",
})
_REQUIREMENTS = re.compile(r"^requirements[\w.-]*\.(?:txt|in)$", re.I)
_PEP508_NAME = re.compile(r"^\s*([A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?)")


class ManifestError(ValueError):
    """A manifest could not be read."""


def is_lockfile(path: str) -> bool:
    return PurePosixPath(path).name in LOCKFILES


def is_manifest(path: str) -> bool:
    name = PurePosixPath(path).name
    return name in ("package.json", "composer.json", "pyproject.toml", "Pipfile", "go.mod",
                    "Cargo.toml", "Gemfile") or bool(_REQUIREMENTS.match(name))


def dependencies(path: str, text: str | None) -> set[str]:
    """The dependency names ``text`` (the manifest at ``path``) declares; empty for no
    file. Raises ``ManifestError`` when it cannot be read."""
    if text is None:
        return set()
    name = PurePosixPath(path).name
    try:
        if name in ("package.json", "composer.json"):
            return _json_deps(text, name)
        if name == "pyproject.toml":
            return _pyproject_deps(tomllib.loads(text))
        if name == "Pipfile":
            data = tomllib.loads(text)
            return {_py(n) for key in ("packages", "dev-packages")
                    for n in _table(data.get(key))}
        if name == "Cargo.toml":
            return _cargo_deps(tomllib.loads(text))
        if name == "go.mod":
            return _go_deps(text)
        if name == "Gemfile":
            return set(re.findall(r"""^\s*gem\s+['"]([^'"]+)['"]""", text, re.M))
        if _REQUIREMENTS.match(name):
            return _requirements_deps(text)
    except (ValueError, tomllib.TOMLDecodeError) as err:
        raise ManifestError(f"{path} cannot be read: {err}") from None
    return set()


def normalize(name: str) -> str:
    """How names are compared: case-insensitive, and ``_``/``.`` as ``-`` (as PyPI does)."""
    return re.sub(r"[-_.]+", "-", name.strip().strip("`'\"")).lower()


def _json_deps(text: str, name: str) -> set[str]:
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("not a JSON object")
    keys = (("dependencies", "devDependencies", "peerDependencies", "optionalDependencies")
            if name == "package.json" else ("require", "require-dev"))
    return {n for key in keys for n in _table(data.get(key))}


def _table(value) -> list[str]:
    return list(value) if isinstance(value, dict) else []


def _py(requirement: str) -> str:
    m = _PEP508_NAME.match(requirement)
    return m[1] if m else requirement.strip()


def _pyproject_deps(data: dict) -> set[str]:
    found: set[str] = set()
    project = data.get("project") if isinstance(data.get("project"), dict) else {}
    found |= {_py(r) for r in project.get("dependencies") or [] if isinstance(r, str)}
    for group in _table(project.get("optional-dependencies")):
        found |= {_py(r) for r in project["optional-dependencies"][group] or []
                  if isinstance(r, str)}
    groups = data.get("dependency-groups") if isinstance(data.get("dependency-groups"),
                                                         dict) else {}
    for entries in groups.values():
        found |= {_py(r) for r in entries or [] if isinstance(r, str)}
    tool = data.get("tool") if isinstance(data.get("tool"), dict) else {}
    poetry = tool.get("poetry") if isinstance(tool.get("poetry"), dict) else {}
    tables = [poetry.get("dependencies"), poetry.get("dev-dependencies")]
    for group in (poetry.get("group") or {}).values():
        if isinstance(group, dict):
            tables.append(group.get("dependencies"))
    found |= {n for table in tables for n in _table(table) if n.lower() != "python"}
    return found


def _cargo_deps(data: dict) -> set[str]:
    keys = ("dependencies", "dev-dependencies", "build-dependencies")
    found = {n for key in keys for n in _table(data.get(key))}
    for target in _table(data.get("target")):
        spec = data["target"][target]
        if isinstance(spec, dict):
            found |= {n for key in keys for n in _table(spec.get(key))}
    workspace = data.get("workspace") if isinstance(data.get("workspace"), dict) else {}
    return found | set(_table(workspace.get("dependencies")))


def _go_deps(text: str) -> set[str]:
    found, block = set(), False
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("require ("):
            block = True
            continue
        if block and line == ")":
            block = False
            continue
        entry = line[len("require "):].strip() if line.startswith("require ") else (
            line if block else "")
        if entry and not entry.startswith("//") and "// indirect" not in entry:
            found.add(entry.split()[0])
    return found


def _requirements_deps(text: str) -> set[str]:
    found = set()
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or line.startswith("-"):
            continue  # an option such as -r, -e or --index-url
        if m := _PEP508_NAME.match(line):
            found.add(m[1])
    return found
