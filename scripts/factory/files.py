"""``safe_write``: the one way the factory's own writers write a file (SR1.1, N1).

The guard checks the path options of ``factory.py`` before a command runs. This is the
second line: whatever path reaches a writer, from an option or a default, the writer
refuses the folders that hold the factory's controls, in either mode:

* the factory's ``scripts/`` (the guard's own code) and ``.claude/`` (settings and hooks);
* the factory's ``.factory-local/`` (the target pointer, set only by the human; D-10);
* ``~/.claude/`` (Claude Code's user settings and project memory, which load into every
  later session; N22).

The pointer itself, the settings that ``target set`` updates and the headless runner's
log are written by commands only the human runs (``target set``, ``run``); those do not
use this helper.
"""

import os
from pathlib import Path

from factory import target as target_mod
from factory.errors import FactoryError


class UnsafeWriteError(FactoryError):
    """A factory writer was asked to write inside a protected folder."""


def protected_roots(factory_root: Path | None = None,
                    home: Path | None = None) -> tuple[tuple[Path, str], ...]:
    factory_root = factory_root or target_mod.FACTORY_ROOT
    home = home or Path.home()
    return (
        (factory_root / "scripts", "the factory's scripts/ (the guard's own code)"),
        (factory_root / ".claude", "the factory's .claude/ (settings and hooks)"),
        (factory_root / ".factory-local", "the factory's .factory-local/ (the target pointer)"),
        (home / ".claude", "~/.claude/ (Claude Code's settings and memory)"),
    )


def _real(path: Path) -> str:
    return os.path.normcase(os.path.realpath(os.path.abspath(path)))


def _inside(real: str, root: Path) -> bool:
    base = _real(root)
    return real == base or real.startswith(base.rstrip("\\/") + os.sep)


def check_writable(path: Path, factory_root: Path | None = None,
                   home: Path | None = None) -> None:
    """Raise ``UnsafeWriteError`` if ``path`` is inside a protected folder. Symlinks and
    junctions are resolved, so a link into a protected folder is refused too."""
    real = _real(path)
    for root, label in protected_roots(factory_root, home):
        if _inside(real, root):
            raise UnsafeWriteError(f"refusing to write {path}: it is inside {label} (SR1.1)")


def safe_write(path: Path, content: str | bytes, *, encoding: str = "utf-8",
               factory_root: Path | None = None, home: Path | None = None) -> Path:
    """Write ``content`` to ``path``, creating its folder, unless the path is protected.
    ``str`` is written as text in ``encoding`` (with the platform's newline translation,
    as ``Path.write_text``); ``bytes`` are written as they are."""
    path = Path(path)
    check_writable(path, factory_root, home)
    path.parent.mkdir(parents=True, exist_ok=True)
    check_writable(path, factory_root, home)  # again: the folder may be a link created meanwhile
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        path.write_text(content, encoding=encoding)
    return path
