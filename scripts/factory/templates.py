"""Load and fill the templates in ``templates/`` (T2.1).

A placeholder is ``{{name}}`` (lower-case letters and underscores). ``render`` replaces
every placeholder in a single pass, so a value that itself contains ``{{…}}`` (a story
about a template language, say) is inserted as it is and never expanded again.
"""

import re
from collections.abc import Mapping
from pathlib import Path

from factory.errors import FactoryError

TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "templates"
PLACEHOLDER = re.compile(r"\{\{([a-z_]+)\}\}")


class TemplateError(FactoryError):
    """A template could not be filled: a placeholder has no value, or a value is unused."""


def load(name: str) -> str:
    return (TEMPLATES_DIR / name).read_text(encoding="utf-8")


def placeholders(text: str) -> set[str]:
    return set(PLACEHOLDER.findall(text))


def render(text: str, values: Mapping[str, str]) -> str:
    """Fill every placeholder in ``text``. The keys of ``values`` must match exactly."""
    needed = placeholders(text)
    missing = sorted(needed - set(values))
    unused = sorted(set(values) - needed)
    if missing or unused:
        raise TemplateError(f"template values do not match its placeholders: "
                            f"missing {missing}, unused {unused}")
    return PLACEHOLDER.sub(lambda m: values[m[1]], text)
