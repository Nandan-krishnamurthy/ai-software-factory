"""AI Software Factory command-line entry point.

Usage: python scripts/factory.py <subcommand> [options]

Subcommands are registered in ``factory.cli`` and added task by task
(see docs/03-factory-plan.md). This file only bootstraps the import path.
"""

import sys
from pathlib import Path

# Make the ``factory`` package (scripts/factory/) importable when this file is
# run directly, regardless of the current working directory.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from factory.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
