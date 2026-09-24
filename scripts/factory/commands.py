"""Which station a slash command may run next (architecture §4.2).

Every station-running command file (``.claude/commands/factory-*.md``) loops::

    python scripts/factory.py route --command factory-resume              # first time
    … run the station it names …
    python scripts/factory.py route --command factory-resume --continuing --after S05

The name is passed **without** its leading slash: Git Bash on Windows (the shell Claude
Code uses there) rewrites an argument like ``/factory-start`` into a Windows path such as
``C:/Program Files/Git/factory-start``. ``normalize_command`` accepts all three spellings.

``route()`` is pure. It answers **run** (a station and its file) or **stop** (a reason
for the human), so the command's control flow is decided by code, not interpreted
from prose:

* **Entry.** The first call requires the command to be in the state engine's
  ``allowed_commands`` for the current state.
* **Continuing.** After a station, the command goes on only while the factory is the
  one waiting (``waiting_on == "factory"``). A gate, or anything that needs the human,
  stops it.
* **Scope.** The next station must be in the command's scope. ``/factory-resume`` never
  runs S06 (Pick): only ``/factory-continue`` may start a story (D2, rule S2).
* **Progress.** If the state engine names the same station that just ran, that station
  did not complete, so the command stops instead of looping.
* **Entry station.** Where nothing is in motion yet, the state engine names no station
  (e.g. ``UNCONFIGURED``). A command may then name its own first station:
  ``/factory-start`` begins with S00.
* **Availability.** A station whose file does not exist yet (e.g. S01 before M5) stops
  the command with an explanation.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from factory import state as state_mod

STATIONS_DIR = Path(__file__).resolve().parents[2] / "stations"


@dataclass(frozen=True)
class Command:
    name: str
    stations: tuple[str, ...]  # the stations this command may run
    purpose: str
    entry: tuple[tuple[str, str], ...] = ()  # (state, station) when state names no station


# Commands that run stations. /factory-target and /factory-status never do.
# /factory-continue (T3.5) and the story stations (M3/M4) are added later.
COMMANDS: dict[str, Command] = {
    "/factory-start": Command(
        "/factory-start", ("S00", "S01", "S02", "S03", "S04", "S05"),
        "begin a new increment and plan it, up to Gate A",
        entry=((state_mod.UNCONFIGURED, "S00"),)),
    "/factory-resume": Command(
        "/factory-resume", ("S00", "S01", "S02", "S03", "S04", "S05", "S05b"),
        "finish what is in motion, up to the next gate; never starts a story"),
}


@dataclass(frozen=True)
class Route:
    action: str  # "run" | "stop"
    state: str
    message: str
    station: str | None = None
    station_file: str | None = None  # relative to the factory repo

    def to_dict(self) -> dict[str, Any]:
        return {"action": self.action, "state": self.state, "station": self.station,
                "station_file": self.station_file, "message": self.message}


def normalize_command(text: str) -> str | None:
    """``factory-start``, ``/factory-start`` or a Git Bash-mangled ``C:/…/factory-start``
    → ``/factory-start``; ``None`` if it names no station-running command."""
    name = "/" + text.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1].strip()
    return name if name in COMMANDS else None


def station_file(station: str, stations_dir: Path = STATIONS_DIR) -> str | None:
    """``stations/S05b-issues.md`` for ``S05b``, or ``None`` if there is no such file."""
    matches = sorted(stations_dir.glob(f"{station}-*.md"))
    return f"stations/{matches[0].name}" if matches else None


def route(command: str, result: dict[str, Any], *, continuing: bool = False,
          after: str | None = None, stations_dir: Path = STATIONS_DIR) -> Route:
    """Pure (apart from checking which station files exist): run the next station, or stop.

    ``result`` is the ``state --json`` object.
    """
    spec = COMMANDS.get(command)
    current = result["state"]
    message = result["details"]["message"]
    if spec is None:
        return Route("stop", current, f"{command} does not run stations.")

    def stop(reason: str) -> Route:
        return Route("stop", current, reason)

    if current in (state_mod.INCONSISTENT, state_mod.NEEDS_HUMAN):
        return stop(f"{current}: {message}")
    if not continuing and command not in result["allowed_commands"]:
        return stop(f"{command} cannot act in state {current}. {message} Allowed now: "
                    + ", ".join(result["allowed_commands"]) + ".")
    if continuing and result["waiting_on"] != "factory":
        return stop(f"Stopped at {current}. {message}")
    station = result["next_station"]
    if station is None and not continuing:
        station = dict(spec.entry).get(current)
    if station is None:
        return stop(f"Nothing for {command} to run in state {current}. {message}")
    if station not in spec.stations:
        why = (" Only /factory-continue may start a story (rule S2)." if station == "S06"
               else "")
        return stop(f"{current}: the next station is {station}, which {command} does not "
                    f"run.{why} {message}")
    if continuing and after == station:
        return stop(f"{station} ran but the state engine still names it as the next "
                    f"station, so it did not complete. {message} Check its Done check, "
                    "fix the cause, then run the command again.")
    path = station_file(station, stations_dir)
    if path is None:
        return stop(f"{current}: the next station is {station}, which is not available "
                    f"yet (no stations/{station}-*.md). {message}")
    return Route("run", current, f"Run {station} ({path}). {message}", station, path)


def render(route_: Route) -> str:
    if route_.action == "run":
        return f"Run {route_.station}: read and follow {route_.station_file}\n{route_.message}"
    return f"Stop: {route_.message}"
