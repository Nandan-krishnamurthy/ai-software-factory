"""Record real ``gh`` responses as fixtures ("cassettes") and replay them offline.

Cassette format (JSON)::

    {"version": 1,
     "interactions": [{"args": ["repo", "view", ...], "input": null,
                       "returncode": 0, "stdout": "...", "stderr": ""}]}

``args`` excludes the leading ``gh``. Environment variables are never recorded,
and anything that looks like a GitHub token is redacted before saving (rule S6).

Record::

    rec = RecordingTransport("tests/fixtures/gh/x.json")
    Gh(transport=rec).json(["repo", "view", "o/r"], fields=["name"])
    rec.save()

Replay::

    gh = FakeGh.from_file("tests/fixtures/gh/x.json")
    gh.json(["repo", "view", "o/r"], fields=["name"])
"""

import json
import re
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from factory.errors import FactoryError
from factory.gh import Gh, ProcessResult, Transport, run_process

CASSETTE_VERSION = 1
_TOKEN = re.compile(r"\b(gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})\b")


class UnexpectedCall(FactoryError):
    """FakeGh received a call that is not in its cassette (or was already used up)."""


def redact(text: str | None) -> str | None:
    return _TOKEN.sub("<redacted-token>", text) if text else text


def _strip_gh(argv: Sequence[str]) -> list[str]:
    argv = list(argv)
    return argv[1:] if argv and argv[0] == "gh" else argv


def load_cassette(path: str | Path) -> list[dict[str, Any]]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("version") != CASSETTE_VERSION:
        raise ValueError(f"{path}: unsupported cassette version {data.get('version')!r}")
    return data["interactions"]


class RecordingTransport:
    """Runs real commands through ``inner`` and remembers each gh interaction."""

    def __init__(self, path: str | Path, inner: Transport = run_process):
        self.path = Path(path)
        self.inner = inner
        self.interactions: list[dict[str, Any]] = []

    def __call__(self, argv, *, timeout, cwd=None, env=None, input=None) -> ProcessResult:
        result = self.inner(argv, timeout=timeout, cwd=cwd, env=env, input=input)
        self.interactions.append(
            {
                "args": _strip_gh(argv),
                "input": redact(input),
                "returncode": result.returncode,
                "stdout": redact(result.stdout),
                "stderr": redact(result.stderr),
            }
        )
        return result

    def save(self) -> Path:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        body = {"version": CASSETTE_VERSION, "interactions": self.interactions}
        self.path.write_text(json.dumps(body, indent=2) + "\n", encoding="utf-8")
        return self.path


class ReplayTransport:
    """Answers each call with the first unused recorded interaction whose args match."""

    def __init__(self, interactions: Sequence[dict[str, Any]]):
        self.interactions = [dict(i) for i in interactions]
        self.used = [False] * len(self.interactions)
        self.calls: list[dict[str, Any]] = []

    def __call__(self, argv, *, timeout, cwd=None, env=None, input=None) -> ProcessResult:
        if timeout is None or timeout <= 0:
            raise ValueError("every external command needs a positive timeout")
        args = _strip_gh(argv)
        self.calls.append({"args": args, "timeout": timeout, "env": env, "input": input})
        for index, interaction in enumerate(self.interactions):
            if self.used[index]:
                continue
            if interaction["args"] == args and interaction.get("input") == input:
                self.used[index] = True
                return ProcessResult(
                    ["gh", *args],
                    interaction["returncode"],
                    interaction.get("stdout") or "",
                    interaction.get("stderr") or "",
                )
        raise UnexpectedCall(f"no unused recorded interaction for: gh {' '.join(args)}")

    def unused(self) -> list[list[str]]:
        return [i["args"] for i, used in zip(self.interactions, self.used, strict=True) if not used]


class FakeGh(Gh):
    """A ``Gh`` that replays recorded interactions instead of running ``gh``."""

    def __init__(self, interactions: Sequence[dict[str, Any]], **kwargs):
        self.replay = ReplayTransport(interactions)
        super().__init__(transport=self.replay, **kwargs)

    @classmethod
    def from_file(cls, path: str | Path, **kwargs) -> "FakeGh":
        return cls(load_cassette(path), **kwargs)

    def assert_all_used(self) -> None:
        leftover = self.replay.unused()
        if leftover:
            raise AssertionError(f"recorded interactions never used: {leftover}")
