"""Argument parsing and subcommand dispatch for ``scripts/factory.py``."""

import argparse

from factory import __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="factory.py",
        description="AI Software Factory state engine and helpers.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    # Each later task registers its subcommand here, e.g.
    #   sub = subparsers.add_parser("doctor", help="...")
    #   sub.set_defaults(handler=doctor.run)
    parser.add_subparsers(
        title="subcommands",
        dest="command",
        metavar="<subcommand>",
        description="none implemented yet (added from T1.1 onwards)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    handler = getattr(args, "handler", None)
    if handler is None:
        parser.print_help()
        return 0
    return handler(args)
