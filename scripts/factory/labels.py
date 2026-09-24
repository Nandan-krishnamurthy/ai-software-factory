"""The factory's GitHub labels (requirements §4) and ``labels ensure``.

``ensure_labels`` is idempotent: it creates missing labels, updates ones whose colour or
description differ, and leaves everything else alone. It never deletes a label, including
labels the factory does not own.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field

from factory.gh import Gh


@dataclass(frozen=True)
class LabelSpec:
    name: str
    color: str  # 6-digit hex, lowercase, no '#'
    description: str


REQUIRED_LABELS: tuple[LabelSpec, ...] = (
    LabelSpec("factory:story", "5319e7", "Story managed by the AI Software Factory"),
    LabelSpec("factory:planning", "1d76db", "Planning PR for a factory increment"),
    LabelSpec("factory:needs-human", "b60205", "The factory is stopped until a human decides"),
    LabelSpec("status:ready", "0e8a16", "Approved; can be picked once its dependencies are done"),
    LabelSpec("status:blocked", "d93f0b", "Has open dependencies or is waiting on a human answer"),
    LabelSpec("status:in-progress", "fbca04", "Being implemented by the factory (acts as a lock)"),
    LabelSpec("status:in-review", "0052cc", "PR open, waiting for human review (Gate B)"),
    LabelSpec("status:changes-requested", "e99695", "A reviewer asked for changes (/changes)"),
    LabelSpec("status:done", "6f42c1", "PR merged by the human; close-out complete"),
)


@dataclass
class LabelPlan:
    create: list[LabelSpec] = field(default_factory=list)
    update: list[tuple[str, LabelSpec]] = field(default_factory=list)  # (current name, spec)
    unchanged: list[LabelSpec] = field(default_factory=list)

    @property
    def is_noop(self) -> bool:
        return not self.create and not self.update


def list_labels(gh: Gh, repo: str) -> list[dict]:
    return gh.json(
        ["label", "list", "--repo", repo, "--limit", "1000"],
        fields=["name", "color", "description"],
    )


def plan_labels(
    existing: Sequence[dict], required: Sequence[LabelSpec] = REQUIRED_LABELS
) -> LabelPlan:
    """Pure: what must change so every required label exists exactly as specified.

    GitHub label names are case-insensitive, so ``Status:Done`` counts as existing and is
    renamed to the canonical spelling.
    """
    by_lower = {label["name"].lower(): label for label in existing}
    plan = LabelPlan()
    for spec in required:
        current = by_lower.get(spec.name.lower())
        if current is None:
            plan.create.append(spec)
        elif (
            current["name"] != spec.name
            or (current.get("color") or "").lower() != spec.color
            or (current.get("description") or "") != spec.description
        ):
            plan.update.append((current["name"], spec))
        else:
            plan.unchanged.append(spec)
    return plan


def ensure_labels(gh: Gh, repo: str) -> LabelPlan:
    """Create or update the required labels. Returns what was done."""
    plan = plan_labels(list_labels(gh, repo))
    for spec in plan.create:
        gh.run(["label", "create", spec.name, "--repo", repo,
                "--color", spec.color, "--description", spec.description])
    for current_name, spec in plan.update:
        args = ["label", "edit", current_name, "--repo", repo,
                "--color", spec.color, "--description", spec.description]
        if current_name != spec.name:
            args += ["--name", spec.name]
        gh.run(args)
    return plan
