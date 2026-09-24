"""Argument parsing and subcommand dispatch for ``scripts/factory.py``."""

import argparse
import json
import sys
from pathlib import Path

from factory import __version__, comments, doctor, labels, state, target
from factory.errors import FactoryError
from factory.gh import Gh
from factory.git import Git


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="factory.py",
        description="AI Software Factory state engine and helpers.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    # Each subcommand sets ``handler``. Commands that operate on the active target also
    # set ``needs_target=True``: the dispatcher then resolves the target and prints the
    # ``Target: <path> (<owner/repo>)`` banner before running them (rule T2).
    subparsers = parser.add_subparsers(title="subcommands", dest="command", metavar="<subcommand>")

    target_parser = subparsers.add_parser("target", help="select or show the active target repo")
    target_sub = target_parser.add_subparsers(dest="target_command", metavar="<action>")
    target_sub.required = True
    set_parser = target_sub.add_parser("set", help="validate <path> and make it the active target")
    set_parser.add_argument("path", help="local path of the target repository")
    set_parser.set_defaults(handler=_target_set)
    show_parser = target_sub.add_parser("show", help="print the active target")
    show_parser.add_argument("--json", action="store_true", help="machine-readable output")
    show_parser.set_defaults(handler=_target_show)

    doctor_parser = subparsers.add_parser(
        "doctor", help="check the target is ready for the factory")
    doctor_parser.add_argument("--json", action="store_true", help="machine-readable output")
    doctor_parser.set_defaults(handler=_doctor, needs_target=True)

    labels_parser = subparsers.add_parser("labels", help="manage the factory's GitHub labels")
    labels_sub = labels_parser.add_subparsers(dest="labels_command", metavar="<action>")
    labels_sub.required = True
    ensure_parser = labels_sub.add_parser(
        "ensure", help="create or update the factory labels on the target repo (idempotent)")
    ensure_parser.set_defaults(handler=_labels_ensure, needs_target=True)

    comment_parser = subparsers.add_parser(
        "comment", help="post a marked factory comment on an issue or PR (rule S14)",
        description="Post a comment carrying a factory marker. --kind reply adds a new "
                    "comment; --kind checkpoint edits the issue's single checkpoint comment "
                    "in place (or creates it).")
    where = comment_parser.add_mutually_exclusive_group(required=True)
    where.add_argument("--issue", type=_positive_int, metavar="N", help="issue number")
    where.add_argument("--pr", type=_positive_int, metavar="N", help="pull request number")
    comment_parser.add_argument("--kind", choices=("reply", "checkpoint"), required=True)
    comment_parser.add_argument(
        "--body-file", metavar="F",
        help="UTF-8 file with the comment text, or '-' for stdin. Required for reply; "
             "an optional note for checkpoint.")
    cp = comment_parser.add_argument_group("checkpoint options")
    cp.add_argument("--station", help="station just completed, e.g. S09")
    cp.add_argument("--next", dest="next_station", help="next station or gate, e.g. S10, GATE_B")
    cp.add_argument("--branch", help="story branch (default: the target's current branch)")
    cp.add_argument("--sha", help="pushed commit (default: the target's HEAD)")
    cp.add_argument("--fix-attempts", type=_non_negative_int, metavar="N",
                    help="default: carried over from the existing checkpoint, else 0")
    cp.add_argument("--review-round", type=_non_negative_int, metavar="N",
                    help="default: carried over from the existing checkpoint, else 0")
    comment_parser.set_defaults(handler=_comment, needs_target=True)

    guard_parser = subparsers.add_parser(
        "guard", help="PreToolUse hook: read a tool call on stdin; exit 2 to block it",
        description="Called by Claude Code before each Bash, PowerShell, Edit and Write "
                    "call (see .claude/settings.json). Not meant to be run by hand.")
    guard_parser.set_defaults(handler=_guard)

    state_parser = subparsers.add_parser(
        "state", help="work out the factory's current state from GitHub",
        description="Reads GitHub and prints exactly one state, the next station, the "
                    "commands allowed to act, and who the factory is waiting on.")
    state_parser.add_argument("--json", action="store_true",
                              help="machine-readable output (schema documented in state.py)")
    state_parser.set_defaults(handler=_state, needs_target=True)
    return parser


def _positive_int(text: str) -> int:
    value = int(text)
    if value < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return value


def _non_negative_int(text: str) -> int:
    value = int(text)
    if value < 0:
        raise argparse.ArgumentTypeError("must be zero or more")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    handler = getattr(args, "handler", None)
    if handler is None:
        parser.print_help()
        return 0
    try:
        if getattr(args, "needs_target", False):
            args.target = target.get_target()
            # With --json the banner goes to stderr, so stdout stays pure JSON.
            print(args.target.banner(), file=sys.stderr if getattr(args, "json", False)
                  else sys.stdout)
        return handler(args)
    except FactoryError as err:
        print(f"error: {err}", file=sys.stderr)
        return 1


def _target_set(args: argparse.Namespace) -> int:
    active = target.set_target(args.path)
    print(active.banner())
    print("Active target recorded; Claude Code may now access this directory.")
    return 0


def _doctor(args: argparse.Namespace) -> int:
    checks = doctor.run_doctor(args.target, Gh())
    print(doctor.to_json(checks) if args.json else doctor.render(checks))
    return doctor.exit_code(checks)


def _labels_ensure(args: argparse.Namespace) -> int:
    plan = labels.ensure_labels(Gh(), args.target.repo)
    for spec in plan.create:
        print(f"  created    {spec.name}")
    for current, spec in plan.update:
        renamed = f" (was {current})" if current != spec.name else ""
        print(f"  updated    {spec.name}{renamed}")
    for spec in plan.unchanged:
        print(f"  unchanged  {spec.name}")
    print(f"Labels: {len(plan.create)} created, {len(plan.update)} updated, "
          f"{len(plan.unchanged)} unchanged.")
    return 0


def _state(args: argparse.Namespace) -> int:
    snapshot = state.collect_snapshot(Gh(), args.target.repo)
    result = state.derive_state(snapshot)
    print(json.dumps(result.to_dict(), indent=2) if args.json else state.render(result))
    return 0


def _guard(args: argparse.Namespace) -> int:
    from factory import guard_hook  # imported lazily: only the hook needs it

    return guard_hook.main()


def _comment(args: argparse.Namespace) -> int:
    repo = args.target.repo
    number = args.issue or args.pr
    text = _read_body(args.body_file)
    gh = Gh()
    if args.kind == "reply":
        if args.station or args.next_station:
            raise comments.CommentError("--station/--next are only for --kind checkpoint")
        if not text.strip():
            raise comments.CommentError("--kind reply needs --body-file with some text")
        comments.check_target_kind(gh, repo, number, expect_pr=args.pr is not None)
        posted = comments.post_reply(gh, repo, number, text)
    else:
        if args.pr is not None:
            raise comments.CommentError("checkpoints live on the story issue; use --issue N")
        if not args.station or not args.next_station:
            raise comments.CommentError("--kind checkpoint needs --station and --next")
        git = Git(args.target.path)
        branch = args.branch or git.current_branch()
        if not branch:
            raise comments.CommentError("the target has no current branch; pass --branch")
        try:
            sha = args.sha or git.rev_parse("HEAD")
        except FactoryError:
            raise comments.CommentError("the target has no commits; pass --sha") from None
        comments.check_target_kind(gh, repo, number, expect_pr=False)
        posted = comments.upsert_checkpoint(
            gh, repo, number, station=args.station, next_station=args.next_station,
            branch=branch, sha=sha, fix_attempts=args.fix_attempts,
            review_round=args.review_round, note=text)
    print(f"{posted.action} {args.kind} comment on #{number}: {posted.url}")
    return 0


def _read_body(body_file: str | None) -> str:
    if body_file is None:
        return ""
    if body_file == "-":
        # Decode explicitly: on Windows sys.stdin may use the console code page.
        return sys.stdin.buffer.read().decode("utf-8")
    try:
        return Path(body_file).read_text(encoding="utf-8")
    except OSError as err:
        raise comments.CommentError(f"cannot read --body-file {body_file}: {err}") from None


def _target_show(args: argparse.Namespace) -> int:
    active = target.get_target()
    if args.json:
        print(json.dumps({"path": str(active.path), "repo": active.repo}))
    else:
        print(active.banner())
    return 0
