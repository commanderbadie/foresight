"""Feature definitions shared by offline training (TAWOS) and live inference (app DB).

There is exactly ONE implementation of every feature, used by both
`ml/build_tawos_snapshots.py` and the FastAPI predictor. This removes
train/serve skew and is easy to defend: "the model sees the same numbers
in training and in production".

Every feature is computable from information available *at the snapshot
time* (no future information) -- see docs/ML.md, section "Leakage".
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

from .state import ProjectState, TaskState, as_aware, days_between

FEATURE_NAMES: list[str] = [
    "story_points",           # estimated effort (Jira story points / app story points)
    "priority_rank",          # 1=low .. 4=critical
    "is_bug",                 # 1 if the task is a bug
    "days_to_deadline",       # days left until the deadline (negative = overdue)
    "window_days",            # planned length of the task window (start -> deadline)
    "elapsed_frac",           # fraction of the window already used
    "assignee_open_points",   # story points of the assignee's OTHER open tasks
    "assignee_open_count",    # number of the assignee's OTHER open tasks
    "open_blockers",          # prerequisite tasks not finished yet
    "assignee_hist_late_rate",  # smoothed historical late rate of the assignee
    "project_hist_late_rate",   # smoothed historical late rate of the project
    "age_days",               # days since the task was created
    "reassign_count",         # reassignments before the snapshot
    "desc_len_log",           # log(1 + description length)
    "is_unassigned",          # 1 if nobody owns the task
]

PRIORITY_RANK = {"low": 1, "medium": 2, "high": 3, "critical": 4}

# Mapping of Jira priority names (TAWOS) onto the app's 4-level scale.
JIRA_PRIORITY_RANK = {
    "trivial": 1, "lowest": 1, "low": 1, "minor": 1,
    "medium": 2, "major": 2, "normal": 2,
    "high": 3, "critical": 3,
    "highest": 4, "blocker": 4, "urgent": 4,
}

SMOOTHING_WEIGHT = 5.0  # pseudo-observations pulled towards the global prior
DEFAULT_GLOBAL_LATE_RATE = 0.3


def smoothed_rate(late: float, total: float, prior: float, weight: float = SMOOTHING_WEIGHT) -> float:
    """Bayesian-smoothed rate so that a member with 1 late task out of 1 is not '100% late'."""
    return (late + weight * prior) / (total + weight)


@dataclass
class HistoryStats:
    """Outcome history known *before* the snapshot (late count, total count)."""

    by_assignee: dict[object, list[float]] = field(default_factory=dict)
    project: list[float] = field(default_factory=lambda: [0.0, 0.0])
    global_prior: float = DEFAULT_GLOBAL_LATE_RATE

    def assignee_rate(self, assignee_key) -> float:
        late, total = self.by_assignee.get(assignee_key, [0.0, 0.0])
        return smoothed_rate(late, total, self.global_prior)

    def project_rate(self) -> float:
        late, total = self.project
        return smoothed_rate(late, total, self.global_prior)

    def record(self, assignee_key, late: bool) -> None:
        rec = self.by_assignee.setdefault(assignee_key, [0.0, 0.0])
        rec[0] += float(late)
        rec[1] += 1.0
        self.project[0] += float(late)
        self.project[1] += 1.0

    @classmethod
    def from_state(cls, state: ProjectState, global_prior: float = DEFAULT_GLOBAL_LATE_RATE) -> "HistoryStats":
        """Live app: history = tasks whose outcome is already known at `state.now`."""
        h = cls(global_prior=global_prior)
        for t in state.tasks.values():
            outcome = state.was_late(t)
            if outcome is None:
                continue
            # Open-and-overdue tasks count as late, but must not leak into their
            # OWN feature -- compute_features() subtracts them again.
            h.record(t.assignee_id, outcome)
        return h


def compute_features(
    state: ProjectState,
    task: TaskState,
    history: Optional[HistoryStats] = None,
    exclude_self_from_history: bool = True,
) -> dict[str, float]:
    """Compute the model's feature vector for one open task at `state.now`."""
    history = history or HistoryStats.from_state(state)
    now = as_aware(state.now)

    sp = task.story_points
    story_points = float(sp) if sp is not None and sp >= 0 else math.nan

    if task.deadline is not None:
        dl = as_aware(task.deadline)
        days_to_deadline = days_between(now, dl)
        window_days = max(days_between(task.window_start, dl), 0.5)
        elapsed = days_between(task.window_start, now)
        elapsed_frac = min(max(elapsed / window_days, 0.0), 2.0)
    else:
        days_to_deadline, window_days, elapsed_frac = math.nan, math.nan, math.nan

    others = [
        t for t in state.tasks.values()
        if t.id != task.id and not t.is_done
        and task.assignee_id is not None and t.assignee_id == task.assignee_id
    ]
    assignee_open_points = float(sum((t.story_points or 0.0) for t in others))

    # History rates, removing this task's own outcome if it is already counted
    # (an overdue open task is 'late' in history; using that for itself is leakage).
    a_late, a_total = history.by_assignee.get(task.assignee_id, [0.0, 0.0])
    p_late, p_total = history.project
    if exclude_self_from_history:
        own = state.was_late(task)
        if own is not None:
            a_late, a_total = a_late - float(own), a_total - 1.0
            p_late, p_total = p_late - float(own), p_total - 1.0
    assignee_rate = smoothed_rate(max(a_late, 0), max(a_total, 0), history.global_prior)
    project_rate = smoothed_rate(max(p_late, 0), max(p_total, 0), history.global_prior)

    return {
        "story_points": story_points,
        "priority_rank": float(PRIORITY_RANK.get(task.priority, 2)),
        "is_bug": 1.0 if task.task_type == "bug" else 0.0,
        "days_to_deadline": days_to_deadline,
        "window_days": window_days,
        "elapsed_frac": elapsed_frac,
        "assignee_open_points": assignee_open_points,
        "assignee_open_count": float(len(others)),
        "open_blockers": float(len(state.open_blockers(task))),
        "assignee_hist_late_rate": assignee_rate,
        "project_hist_late_rate": project_rate,
        "age_days": max(days_between(task.created_at, now), 0.0),
        "reassign_count": float(task.reassign_count),
        "desc_len_log": math.log1p(max(task.description_len, 0)),
        "is_unassigned": 1.0 if task.assignee_id is None else 0.0,
    }


# ---------------------------------------------------------------------------
# Human-readable phrasing used by the explainer and recommendation engine.
# ---------------------------------------------------------------------------

def describe_feature(name: str, value: float, reference: float) -> str:
    def f1(x):
        return f"{x:.1f}".rstrip("0").rstrip(".")

    if value is None or (isinstance(value, float) and math.isnan(value)):
        return {
            "story_points": "no effort estimate",
            "days_to_deadline": "no deadline set",
        }.get(name, f"{name} unknown")
    table = {
        "story_points": lambda: f"large estimate: {f1(value)} story points (typical {f1(reference)})",
        "priority_rank": lambda: "priority is " + {1: "low", 2: "medium", 3: "high", 4: "critical"}.get(int(value), "?"),
        "is_bug": lambda: "it is a bug (bugs are harder to schedule)" if value else "it is not a bug",
        "days_to_deadline": lambda: (f"overdue by {f1(-value)} days" if value < 0 else f"deadline in {f1(value)} days"),
        "window_days": lambda: f"planned window of {f1(value)} days (typical {f1(reference)})",
        "elapsed_frac": lambda: f"{round(value * 100)}% of the planned window already used",
        "assignee_open_points": lambda: f"assignee carries {f1(value)} other open points (typical {f1(reference)})",
        "assignee_open_count": lambda: f"assignee has {int(value)} other open tasks (typical {f1(reference)})",
        "open_blockers": lambda: f"{int(value)} unfinished prerequisite task{'s' if value != 1 else ''}",
        "assignee_hist_late_rate": lambda: f"assignee's past late rate is {round(value * 100)}% (typical {round(reference * 100)}%)",
        "project_hist_late_rate": lambda: f"project's past late rate is {round(value * 100)}%",
        "age_days": lambda: f"task has been open {f1(value)} days",
        "reassign_count": lambda: f"reassigned {int(value)} time{'s' if value != 1 else ''}",
        "desc_len_log": lambda: ("very short description" if value < reference else "long description"),
        "is_unassigned": lambda: "nobody is assigned" if value else "task has an owner",
    }
    return table.get(name, lambda: f"{name} = {value}")()
