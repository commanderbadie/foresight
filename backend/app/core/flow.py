"""Team-level flow metrics (descriptive analytics, no ML).

We deliberately measure the FLOW of work rather than scoring individuals:
throughput, cycle time, deadline adherence and WIP are standard, defensible
delivery metrics; per-person "productivity scores" are not (see docs/ANALYSIS.md).
"""
from __future__ import annotations

import statistics
from datetime import timedelta

from .state import ProjectState, as_aware, days_between


def compute_flow(state: ProjectState, weeks: int = 8) -> dict:
    now = as_aware(state.now)
    done = [t for t in state.done_tasks() if t.completed_at is not None]

    # Weekly buckets ending today (oldest first)
    buckets = []
    for w in range(weeks - 1, -1, -1):
        end = now - timedelta(days=7 * w)
        start = end - timedelta(days=7)
        in_week = [t for t in done if start < as_aware(t.completed_at) <= end]
        with_dl = [t for t in in_week if t.deadline is not None]
        on_time = [t for t in with_dl if as_aware(t.completed_at) <= as_aware(t.deadline)]
        buckets.append({
            "week_ending": end.date().isoformat(),
            "completed": len(in_week),
            "points": float(sum(t.story_points or 0 for t in in_week)),
            "on_time_pct": round(100 * len(on_time) / len(with_dl), 1) if with_dl else None,
        })

    cycle = [days_between(t.started_at, t.completed_at) for t in done if t.started_at]
    lead = [days_between(t.created_at, t.completed_at) for t in done]
    with_dl = [t for t in done if t.deadline is not None]
    on_time = [t for t in with_dl if as_aware(t.completed_at) <= as_aware(t.deadline)]
    open_with_dl = [t for t in state.open_tasks() if t.deadline is not None]
    overdue = [t for t in open_with_dl if state.is_overdue(t)]

    return {
        "weekly": buckets,
        "completed_total": len(done),
        "open_total": len(state.open_tasks()),
        "wip": sum(1 for t in state.tasks.values() if t.status in ("in_progress", "review")),
        "median_cycle_time_days": round(statistics.median(cycle), 1) if cycle else None,
        "median_lead_time_days": round(statistics.median(lead), 1) if lead else None,
        "deadline_adherence_pct": round(100 * len(on_time) / len(with_dl), 1) if with_dl else None,
        "overdue_rate_pct": round(100 * len(overdue) / len(open_with_dl), 1) if open_with_dl else None,
    }
