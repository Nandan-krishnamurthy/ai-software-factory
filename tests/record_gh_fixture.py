"""Developer tool: run real ``gh`` commands and save them as a replayable cassette.

Usage (from the repo root)::

    python tests/record_gh_fixture.py tests/fixtures/gh/NAME.json -- repo view o/r --json name
    python tests/record_gh_fixture.py NAME.json --append -- issue list --repo o/r --json number

Each ``--`` group is one gh call. Non-zero exits are recorded too (useful for error
fixtures). Tokens are redacted before saving. Only read-only commands should be recorded.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from factory.errors import GhError  # noqa: E402
from factory.gh import Gh  # noqa: E402
from factory.gh_fixtures import RecordingTransport, load_cassette  # noqa: E402


def main(argv: list[str]) -> int:
    if "--" not in argv:
        print(__doc__)
        return 2
    split = argv.index("--")
    parser = argparse.ArgumentParser(prog="record_gh_fixture.py")
    parser.add_argument("cassette", type=Path)
    parser.add_argument("--append", action="store_true", help="add to an existing cassette")
    opts = parser.parse_args(argv[:split])

    calls, current = [], []
    for token in argv[split + 1 :] + ["--"]:
        if token == "--":
            if current:
                calls.append(current)
            current = []
        else:
            current.append(token)

    recorder = RecordingTransport(opts.cassette)
    if opts.append and opts.cassette.exists():
        recorder.interactions = load_cassette(opts.cassette)
    gh = Gh(transport=recorder)
    for call in calls:
        try:
            gh.run(call)
            print(f"recorded (exit 0): gh {' '.join(call)}")
        except GhError as err:
            print(f"recorded (exit {err.returncode}): gh {' '.join(call)}")
    print(f"saved {recorder.save()}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
