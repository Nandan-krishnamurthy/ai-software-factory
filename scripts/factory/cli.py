"""Argument parsing and subcommand dispatch for ``scripts/factory.py``."""

import argparse
import json
import sys

from factory import __version__, doctor, labels, target
from factory.errors import FactoryError
from factory.gh import Gh


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
    return parser


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
            print(args.target.banner())
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


def _target_show(args: argparse.Namespace) -> int:
    active = target.get_target()
    if args.json:
        print(json.dumps({"path": str(active.path), "repo": active.repo}))
    else:
        print(active.banner())
    return 0
