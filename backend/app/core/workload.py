"""Team workload intelligence (rule-based, no ML needed).

Load is measured in open story points, because that is the effort estimate the
team itself provides. A member is:
  * OVERLOADED      if load > 1.5 x team median AND load > their capacity, or load > 1.5 x capacity
  * UNDERUTILISED   if load < 0.5 x team median (and the team median is meaningful)
Also reported: high-priority share and near-deadline pressure (open points due in <= 3 days).
"""
from __future__ import annotations

import statistics
from dataclasses import asdict, dataclass

from .state import ProjectState, as_aware, days_between

OVERLOAD_RATIO = 1.5
UNDERUSE_RATIO = 0.5
PRESSURE_DAYS = 3.0


@dataclass
class MemberLoad:
    member_id: int
    name: str
    open_tasks: int
    open_points: float
    capacity_points: float
    utilisation: float           # open_points / capacity
    ratio_to_median: float       # open_points / team median
    high_priority_open: int
    points_due_soon: float       # open points with deadline within PRESSURE_DAYS
    overdue: int
    status: str                  # "overloaded" | "balanced" | "underutilised"
    reasons: list[str]


@dataclass
class WorkloadReport:
    members: list[MemberLoad]
    team_median_points: float
    team_mean_points: float
    imbalance_ratio: float       # max load / median load
    unassigned_open: int

    def as_dict(self) -> dict:
        return {
            "members": [asdict(m) for m in self.members],
            "team_median_points": self.team_median_points,
            "team_mean_points": self.team_mean_points,
            "imbalance_ratio": self.imbalance_ratio,
            "unassigned_open": self.unassigned_open,
        }

    def by_id(self, member_id: int) -> MemberLoad | None:
        return next((m for m in self.members if m.member_id == member_id), None)


def compute_workload(state: ProjectState) -> WorkloadReport:
    now = as_aware(state.now)
    raw = []
    for m in state.members.values():
        tasks = state.tasks_of(m.id)
        pts = float(sum(t.story_points or 0 for t in tasks))
        due_soon = float(sum(
            (t.story_points or 0) for t in tasks
            if t.deadline is not None and 0 <= days_between(now, t.deadline) <= PRESSURE_DAYS
        ))
        raw.append((m, tasks, pts, due_soon))

    loads = [r[2] for r in raw]
    median = float(statistics.median(loads)) if loads else 0.0
    mean = float(statistics.mean(loads)) if loads else 0.0

    members = []
    for m, tasks, pts, due_soon in raw:
        ratio = pts / median if median > 0 else (0.0 if pts == 0 else float("inf"))
        util = pts / m.capacity_points if m.capacity_points else 0.0
        reasons = []
        status = "balanced"
        if (ratio > OVERLOAD_RATIO and util > 1.0) or util > OVERLOAD_RATIO:
            status = "overloaded"
            reasons.append(f"{pts:g} open points vs team median {median:g} ({ratio:.1f}x)")
            if util > 1.0:
                reasons.append(f"{round(util * 100)}% of capacity ({m.capacity_points:g} pts)")
        elif median >= 3 and ratio < UNDERUSE_RATIO:
            status = "underutilised"
            reasons.append(f"only {pts:g} open points vs team median {median:g}")
        if due_soon > 0.6 * m.capacity_points:
            reasons.append(f"{due_soon:g} points due within {PRESSURE_DAYS:g} days")
        members.append(MemberLoad(
            member_id=m.id, name=m.name, open_tasks=len(tasks), open_points=pts,
            capacity_points=m.capacity_points, utilisation=round(util, 3),
            ratio_to_median=round(ratio, 3) if ratio != float("inf") else 99.0,
            high_priority_open=sum(1 for t in tasks if t.priority in ("high", "critical")),
            points_due_soon=due_soon, overdue=sum(1 for t in tasks if state.is_overdue(t)),
            status=status, reasons=reasons,
        ))
    members.sort(key=lambda x: -x.open_points)
    imbalance = (max(loads) / median) if loads and median > 0 else 1.0
    return WorkloadReport(
        members=members, team_median_points=median, team_mean_points=round(mean, 2),
        imbalance_ratio=round(imbalance, 2),
        unassigned_open=sum(1 for t in state.open_tasks() if t.assignee_id is None),
    )
