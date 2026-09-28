"""Explainable project health score (rule-based and fully documented).

    score = 100 - sum(penalties)            (clamped to 0..100)

| Signal                  | Penalty                                   | Cap |
|-------------------------|-------------------------------------------|-----|
| Overdue open tasks      | 8 per task                                | 30  |
| High/critical due <48h  | 5 per task not yet in review/done         | 15  |
| Blocked tasks           | 4 per open task with unfinished blockers  | 15  |
| High ML delay risk      | 5 per open task at HIGH risk              | 20  |
| Workload imbalance      | 8 per overloaded member                   | 15  |
| Behind schedule         | 1 per % point completion lags time used   | 15  |
|   (only counted when the lag is > 10 points)                           |     |

Status: score >= 75 ON TRACK, 50..74 AT RISK, < 50 CRITICAL.
Every penalty carries a human-readable reason and the ids of the tasks /
members that caused it, so the UI can link from the reason to the evidence.
The same function is used for "before vs after" in what-if simulations, which is
how the system explains *changes* in health.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Optional

from .state import ProjectState, as_aware, days_between
from .workload import WorkloadReport

ON_TRACK, AT_RISK, CRITICAL = "on_track", "at_risk", "critical"


@dataclass
class Signal:
    key: str
    label: str
    penalty: float
    task_ids: list[int] = field(default_factory=list)
    member_ids: list[int] = field(default_factory=list)


@dataclass
class HealthReport:
    score: float
    status: str
    signals: list[Signal]
    completion_pct: float
    time_elapsed_pct: Optional[float]

    def as_dict(self) -> dict:
        return {
            "score": self.score,
            "status": self.status,
            "signals": [asdict(s) for s in self.signals],
            "completion_pct": self.completion_pct,
            "time_elapsed_pct": self.time_elapsed_pct,
        }


def _status(score: float) -> str:
    return ON_TRACK if score >= 75 else AT_RISK if score >= 50 else CRITICAL


def compute_health(
    state: ProjectState,
    workload: WorkloadReport,
    risk_levels: Optional[dict[int, str]] = None,
) -> HealthReport:
    risk_levels = risk_levels or {}
    now = as_aware(state.now)
    signals: list[Signal] = []
    open_tasks = state.open_tasks()

    overdue = [t for t in open_tasks if state.is_overdue(t)]
    if overdue:
        signals.append(Signal("overdue", f"{len(overdue)} task{'s are' if len(overdue) != 1 else ' is'} overdue",
                              min(8 * len(overdue), 30), [t.id for t in overdue]))

    urgent = [
        t for t in open_tasks
        if t.priority in ("high", "critical") and t.status not in ("review",)
        and t.deadline is not None and 0 <= days_between(now, t.deadline) <= 2
    ]
    if urgent:
        signals.append(Signal("urgent", f"{len(urgent)} high-priority task{'s have' if len(urgent) != 1 else ' has'} "
                                        f"less than 48 hours left", min(5 * len(urgent), 15), [t.id for t in urgent]))

    blocked = [t for t in open_tasks if state.open_blockers(t)]
    if blocked:
        signals.append(Signal("blocked", f"{len(blocked)} task{'s are' if len(blocked) != 1 else ' is'} waiting on "
                                         f"unfinished prerequisites", min(4 * len(blocked), 15), [t.id for t in blocked]))

    high_risk = [tid for tid, lvl in risk_levels.items() if lvl == "high" and tid in state.tasks]
    if high_risk:
        signals.append(Signal("ml_risk", f"{len(high_risk)} task{'s have' if len(high_risk) != 1 else ' has'} a HIGH "
                                         f"predicted delay risk", min(5 * len(high_risk), 20), high_risk))

    over = [m for m in workload.members if m.status == "overloaded"]
    if over:
        names = ", ".join(m.name for m in over)
        signals.append(Signal("workload", f"{names} {'is' if len(over) == 1 else 'are'} overloaded",
                              min(8 * len(over), 15), member_ids=[m.member_id for m in over]))

    total_pts = sum((t.story_points or 1) for t in state.tasks.values())
    done_pts = sum((t.story_points or 1) for t in state.done_tasks())
    completion = 100.0 * done_pts / total_pts if total_pts else 0.0
    elapsed_pct = None
    if state.start_date and state.end_date:
        span = days_between(state.start_date, state.end_date)
        if span > 0:
            elapsed_pct = max(0.0, min(100.0, 100.0 * days_between(state.start_date, now) / span))
            lag = elapsed_pct - completion
            if lag > 10:
                signals.append(Signal("schedule", f"completion ({completion:.0f}%) trails time used "
                                                  f"({elapsed_pct:.0f}%) by {lag:.0f} points", min(lag, 15)))

    signals.sort(key=lambda s: -s.penalty)
    score = max(0.0, min(100.0, 100.0 - sum(s.penalty for s in signals)))
    return HealthReport(round(score, 1), _status(score), signals, round(completion, 1),
                        None if elapsed_pct is None else round(elapsed_pct, 1))


def diff_health(before: HealthReport, after: HealthReport) -> list[str]:
    """Plain-language explanation of why the health score changed."""
    b = {s.key: s for s in before.signals}
    a = {s.key: s for s in after.signals}
    out = []
    for key in sorted(set(b) | set(a)):
        pb, pa = (b[key].penalty if key in b else 0), (a[key].penalty if key in a else 0)
        if abs(pb - pa) < 0.5:
            continue
        if key in b and key not in a:
            out.append(f"resolved: {b[key].label} (+{pb:g})")
        elif key in a and key not in b:
            out.append(f"new: {a[key].label} (-{pa:g})")
        else:
            out.append(f"{'improved' if pa < pb else 'worsened'}: {a[key].label} ({pb - pa:+g})")
    return out
