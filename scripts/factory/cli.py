"""Argument parsing and subcommand dispatch for ``scripts/factory.py``."""

import argparse
import json
import sys
from pathlib import Path

from factory import (
    __version__,
    commands,
    comments,
    doctor,
    increments,
    issues,
    labels,
    pick,
    signals,
    state,
    target,
    verdict,
)
from factory.config import load_config
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

    inc_parser = subparsers.add_parser(
        "increment", help="the current increment, the next one, and the next REQ/STORY IDs")
    inc_sub = inc_parser.add_subparsers(dest="increment_command", metavar="<action>")
    inc_sub.required = True
    inc_show = inc_sub.add_parser(
        "show", help="report the current increment and the next free REQ/STORY IDs")
    inc_show.add_argument("--json", action="store_true", help="machine-readable output")
    inc_show.set_defaults(handler=_increment, needs_target=True, allocate=False, slug=None)
    inc_next = inc_sub.add_parser(
        "next", help="allocate the next increment NNN-slug, or explain why not yet",
        description="Prints the next increment name and the next free REQ/STORY IDs. "
                    "Refuses (exit 1) while the current increment is still in planning, "
                    "has stories without issues, or has open, unblocked stories. Changes "
                    "nothing: the station creates the folder.")
    inc_next.add_argument("--slug", help="short name, e.g. add-due-dates (free text is "
                                         "slugified). Optional for the first increment "
                                         f"(default {increments.FIRST_SLUG!r})")
    inc_next.add_argument("--json", action="store_true", help="machine-readable output")
    inc_next.set_defaults(handler=_increment, needs_target=True, allocate=True)

    issues_parser = subparsers.add_parser("issues", help="manage the story issues")
    issues_sub = issues_parser.add_subparsers(dest="issues_command", metavar="<action>")
    issues_sub.required = True
    sync_parser = issues_sub.add_parser(
        "sync", help="create the missing story issues from 05-stories.md (idempotent)",
        description="Parse the increment's 05-stories.md, validate it against the story "
                    "contract, and create one issue per story that has none yet. A real run "
                    "needs the increment's Planning PR to be merged (Gate A) and reads the "
                    "file from the default branch on GitHub. --dry-run reads the local file "
                    "and prints the exact plan without changing anything.")
    sync_parser.add_argument("--dry-run", action="store_true",
                             help="print the plan; create nothing")
    sync_parser.add_argument("--increment", metavar="NNN-slug",
                             help="default: the highest increment folder in the target")
    sync_parser.set_defaults(handler=_issues_sync, needs_target=True)

    pick_parser = subparsers.add_parser(
        "pick", help="start the next unblocked story (only /factory-continue may)",
        description="Applies the unblocked rule (lowest milestone, then lowest issue "
                    "number, among open status:ready stories whose blockers are all "
                    "closed), assigns the issue and labels it status:in-progress. Refuses "
                    "without --authorized-by-continue (rule S2) and while another story is "
                    "in progress, in review or has changes requested.")
    pick_parser.add_argument("--authorized-by-continue", action="store_true",
                             help="passed only by /factory-continue (station S06)")
    pick_parser.add_argument("--json", action="store_true", help="machine-readable output")
    pick_parser.set_defaults(handler=_pick, needs_target=True)

    label_parser = subparsers.add_parser(
        "label", help="give a story issue exactly one status:* label",
        description="Adds status:<STATUS> and removes every other status:* label from the "
                    "story issue. Changes nothing if it is already the only one.")
    label_parser.add_argument("--issue", type=_positive_int, required=True, metavar="N")
    label_parser.add_argument("--status", required=True, choices=pick.STATUSES)
    label_parser.set_defaults(handler=_label, needs_target=True)

    verdict_parser = subparsers.add_parser(
        "verdict", help="check the AC verifier's per-AC verdict for a story")
    verdict_sub = verdict_parser.add_subparsers(dest="verdict_command", metavar="<action>")
    verdict_sub.required = True
    vcheck = verdict_sub.add_parser(
        "check", help="validate a verdict against the story's acceptance criteria",
        description="Checks that the verdict has one line per acceptance criterion of the "
                    "issue, each with evidence, and a Suite line. Exit 0: valid and nothing "
                    "failed. Exit 1: invalid, or an AC or the suite failed (S11 must not "
                    "open a ready PR). Reads --file, or else the note of the issue's "
                    "checkpoint comment, where S10 stores the verdict. Read-only.")
    vcheck.add_argument("--issue", type=_positive_int, required=True, metavar="N")
    vcheck.add_argument("--file", metavar="F", help="UTF-8 file with the verdict (default: "
                                                   "the checkpoint comment's note)")
    vcheck.set_defaults(handler=_verdict_check, needs_target=True)

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

    route_parser = subparsers.add_parser(
        "route", help="which station a /factory-* command runs next, or why it stops",
        description="Used by the command files: reads the state and prints whether the "
                    "command should run a station (and which file) or stop. Read-only.")
    route_parser.add_argument(
        "--command", required=True, type=_command_name, metavar="NAME",
        help="the running command, without its slash (Git Bash rewrites /…): "
             + ", ".join(sorted(c[1:] for c in commands.COMMANDS)))
    route_parser.add_argument("--continuing", action="store_true",
                              help="a station of this command has just run")
    route_parser.add_argument("--after", metavar="SXX",
                              help="the station that has just run (with --continuing)")
    route_parser.add_argument("--json", action="store_true", help="machine-readable output")
    route_parser.set_defaults(handler=_route, needs_target=True)

    feedback_parser = subparsers.add_parser(
        "feedback", help="list the human feedback on a PR in the current review round",
        description="Reads a PR and prints its verdict and every human feedback item in the "
                    "current review round (architecture §9.2): comments from config.reviewers "
                    "without a factory marker, posted after the factory's last push or reply. "
                    "Read-only. Stations answer each item with `factory.py comment`.")
    feedback_parser.add_argument("--pr", type=_positive_int, required=True, metavar="N")
    feedback_parser.add_argument("--json", action="store_true", help="machine-readable output")
    feedback_parser.set_defaults(handler=_feedback, needs_target=True)

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


def _command_name(text: str) -> str:
    name = commands.normalize_command(text)
    if name is None:
        raise argparse.ArgumentTypeError(
            f"{text!r} is not one of: " + ", ".join(sorted(c[1:] for c in commands.COMMANDS)))
    return name


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
            # With --json the banner goes to stderr, so stdout stays pure JSON. Flushed so
            # it still comes first when stdout is a pipe and an error goes to stderr (T2).
            print(args.target.banner(), file=sys.stderr if getattr(args, "json", False)
                  else sys.stdout, flush=True)
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


def _increment(args: argparse.Namespace) -> int:
    try:
        result = increments.assess_target(Gh(), args.target.path, args.target.repo, args.slug)
    except ValueError as err:
        raise increments.IncrementError([str(err)]) from None
    print(json.dumps(result.to_dict(), indent=2) if args.json
          else increments.render(result, allocating=args.allocate))
    if not args.allocate:
        return 0
    if result.reasons:
        return 1
    if result.next_increment is None:
        raise increments.IncrementError(
            [f"--slug is needed: increment {result.current} already exists"])
    return 0


def _issues_sync(args: argparse.Namespace) -> int:
    result = issues.sync(Gh(), args.target.path, args.target.repo,
                         increment=args.increment, dry_run=args.dry_run)
    print(issues.render(result))
    return 0


def _pick(args: argparse.Namespace) -> int:
    choice, login = pick.pick(Gh(), args.target.repo,
                              authorized_by_continue=args.authorized_by_continue)
    print(json.dumps(pick.pick_to_dict(choice, login), indent=2) if args.json
          else pick.render_pick(choice, login))
    return 0


def _label(args: argparse.Namespace) -> int:
    add, remove = pick.set_status(Gh(), args.target.repo, args.issue, args.status)
    if not add and not remove:
        print(f"#{args.issue} already has only status:{args.status}; nothing changed")
    else:
        changes = [f"+{name}" for name in add] + [f"-{name}" for name in remove]
        print(f"#{args.issue}: " + ", ".join(changes))
    return 0


def _verdict_check(args: argparse.Namespace) -> int:
    gh = Gh()
    issue = gh.api(f"repos/{args.target.repo}/issues/{args.issue}")
    if args.file:
        try:
            text = Path(args.file).read_text(encoding="utf-8")
        except OSError as err:
            raise verdict.VerdictError(f"cannot read --file {args.file}: {err}") from None
    else:
        text = verdict.checkpoint_note(gh, args.target.repo, args.issue)
    result = verdict.parse(text, verdict.issue_acs(issue.get("body") or ""))
    print(verdict.render(result))
    return 0 if result.ok else 1


def _route(args: argparse.Namespace) -> int:
    result = state.derive_state(state.collect_snapshot(Gh(), args.target.repo)).to_dict()
    decision = commands.route(args.command, result, continuing=args.continuing,
                              after=args.after)
    print(json.dumps(decision.to_dict(), indent=2) if args.json else commands.render(decision))
    return 0


def _feedback(args: argparse.Namespace) -> int:
    config = load_config(args.target.path)
    gate = signals.signals_for(config)
    pr = signals.fetch_pr(Gh(), args.target.repo, args.pr)
    verdict = gate.verdict(pr).value
    items = gate.feedback(pr)
    if args.json:
        print(json.dumps({"pr": pr.number, "verdict": verdict, "items": [
            {"id": f.comment.id, "kind": f.comment.kind, "author": f.comment.author,
             "created_at": f.comment.created_at.isoformat(), "url": f.comment.url,
             "path": f.comment.path, "line": f.comment.line, "is_trigger": f.is_trigger,
             "text": f.text} for f in items]}, indent=2))
        return 0
    print(f"PR #{pr.number}: {verdict}, {len(items)} feedback item(s) in this round")
    for number, f in enumerate(items, 1):
        where = f" {f.comment.path}:{f.comment.line}" if f.comment.path else ""
        tag = " (/changes)" if f.is_trigger else ""
        print(f"\n[{number}] {f.comment.kind}{where} by {f.comment.author}{tag} "
              f"{f.comment.url}".rstrip())
        print(f.text or "(no text)")
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
