"""Orchestration: one call that turns a ProjectState into the full picture,
plus what-if simulation and the recommendation engine.

Recommendations are generated from templates filled with *actual* project data.
Where a recommendation proposes an action (e.g. reassignment), the action is
first simulated with the same model so the recommendation can state the
expected effect ("risk of #142 drops from 78% to 41%"). Nothing is invented:
every number comes from the database or the model.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from .flow import compute_flow
from .health import HealthReport, compute_health, diff_health
from .state import ProjectState, as_aware, days_between
from .workload import WorkloadReport, compute_workload

PRIORITY_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}


@dataclass
class Analysis:
    risks: dict  # task_id -> RiskResult
    workload: WorkloadReport
    health: HealthReport

    def risk_levels(self) -> dict[int, str]:
        return {tid: r.level for tid, r in self.risks.items()}


def analyze(state: ProjectState, predictor, explain: bool = True) -> Analysis:
    risks = predictor.predict_state(state, explain=explain) if predictor else {}
    workload = compute_workload(state)
    health = compute_health(state, workload, {tid: r.level for tid, r in risks.items()})
    return Analysis(risks, workload, health)


# ---------------------------------------------------------------------------
# What-if simulation
# ---------------------------------------------------------------------------

@dataclass
class Change:
    task_id: int
    assignee_id: Optional[int] = None
    unassign: bool = False
    deadline: Optional[datetime] = None
    story_points: Optional[float] = None
    status: Optional[str] = None


def apply_change(state: ProjectState, change: Change) -> ProjectState:
    s = state.clone()
    t = s.tasks[change.task_id]
    if change.unassign:
        t.assignee_id = None
        t.reassign_count += 1
    elif change.assignee_id is not None and change.assignee_id != t.assignee_id:
        t.assignee_id = change.assignee_id
        t.reassign_count += 1
    if change.deadline is not None:
        t.deadline = change.deadline
    if change.story_points is not None:
        t.story_points = change.story_points
    if change.status is not None:
        t.status = change.status
        if change.status == "done":
            t.completed_at = s.now
    return s


def simulate(state: ProjectState, change: Change, predictor, before: Optional[Analysis] = None) -> dict:
    before = before or analyze(state, predictor, explain=False)
    after_state = apply_change(state, change)
    after = analyze(after_state, predictor, explain=True)
    changed = []
    for tid in set(before.risks) | set(after.risks):
        pb = before.risks[tid].probability if tid in before.risks else None
        pa = after.risks[tid].probability if tid in after.risks else None
        if pb is None or pa is None or abs(pa - pb) >= 0.01:
            changed.append({
                "task_id": tid, "title": state.tasks[tid].title,
                "before": None if pb is None else round(pb, 3),
                "after": None if pa is None else round(pa, 3),
                "level_after": after.risks[tid].level if tid in after.risks else None,
            })
    changed.sort(key=lambda c: -abs((c["after"] or 0) - (c["before"] or 0)))
    target = after.risks.get(change.task_id)
    return {
        "task": {
            "task_id": change.task_id,
            "before": before.risks[change.task_id].as_dict() if change.task_id in before.risks else None,
            "after": target.as_dict() if target else None,
        },
        "changed_tasks": changed,
        "health_before": before.health.as_dict(),
        "health_after": after.health.as_dict(),
        "health_explanation": diff_health(before.health, after.health),
        "workload_after": after.workload.as_dict(),
    }


# ---------------------------------------------------------------------------
# Recommendation engine
# ---------------------------------------------------------------------------

ACTION_BY_FACTOR = {
    "open_blockers": "Unblock it first: finish or re-plan its prerequisite tasks.",
    "assignee_open_points": "Reduce the assignee's load or move this task to someone with capacity.",
    "assignee_open_count": "Reduce the assignee's parallel work (limit WIP).",
    "story_points": "Split it into smaller tasks that can be finished independently.",
    "elapsed_frac": "Most of its window is used: check in today and agree a recovery plan.",
    "days_to_deadline": "Deadline is close: swarm on it or renegotiate the deadline now.",
    "is_unassigned": "Assign an owner today.",
    "assignee_hist_late_rate": "Schedule an early check-in or pair on it.",
    "reassign_count": "Stop the ownership churn: fix one owner.",
    "is_bug": "Time-box investigation and escalate if the root cause is unclear.",
    "window_days": "Plan intermediate milestones inside this long window.",
}


def _rec(key, kind, severity, title, detail, evidence, task_ids=(), member_ids=(), action=None):
    return {"id": key, "kind": kind, "severity": severity, "title": title, "detail": detail,
            "evidence": list(evidence), "task_ids": list(task_ids), "member_ids": list(member_ids),
            "action": action}


def recommend(state: ProjectState, analysis: Analysis, predictor, max_items: int = 8) -> list[dict]:
    recs: list[dict] = []
    now = as_aware(state.now)
    risks = analysis.risks
    covered: set[int] = set()

    # 1) Rebalance overloaded members - evaluated with the model.
    receivers = [m for m in analysis.workload.members if m.status != "overloaded"]
    receivers.sort(key=lambda m: m.open_points)
    for over in [m for m in analysis.workload.members if m.status == "overloaded"]:
        movable = [
            t for t in state.tasks_of(over.member_id)
            if t.status == "todo" and not state.open_blockers(t)
        ]
        movable.sort(key=lambda t: (PRIORITY_ORDER.get(t.priority, 1), -(t.story_points or 0)))
        best = None
        for t in movable[:4]:
            for r in receivers[:3]:
                sim_state = apply_change(state, Change(task_id=t.id, assignee_id=r.member_id))
                after = predictor.predict_state(sim_state, explain=False) if predictor else {}
                affected = [x.id for x in state.tasks_of(over.member_id)] + [x.id for x in state.tasks_of(r.member_id)]
                before_sum = sum(risks[i].probability for i in affected if i in risks)
                after_sum = sum(after[i].probability for i in affected if i in after)
                gain = before_sum - after_sum
                if best is None or gain > best[0]:
                    best = (gain, t, r, after)
        if best and best[0] > 0.02:
            gain, t, r, after = best
            pb = risks[t.id].probability if t.id in risks else None
            pa = after[t.id].probability if t.id in after else None
            effect = f" Predicted risk of this task: {pb:.0%} → {pa:.0%}." if pb is not None and pa is not None else ""
            recs.append(_rec(
                f"rebalance-{over.member_id}-{t.id}", "rebalance", "high",
                f"Move “{t.title}” from {over.name} to {r.name}",
                f"{over.name} carries {over.open_points:g} open points across {over.open_tasks} tasks "
                f"(team median {analysis.workload.team_median_points:g}); {r.name} has {r.open_points:g}.{effect} "
                f"Combined delay risk on both members' tasks drops by {gain * 100:.0f} percentage points.",
                over.reasons, [t.id], [over.member_id, r.member_id],
                {"type": "reassign", "task_id": t.id, "to_member_id": r.member_id},
            ))
            covered.add(t.id)

    # 2) Bottlenecks: late or risky tasks that block others.
    for t in state.open_tasks():
        deps = state.transitive_dependents(t.id)
        if len(deps) < 2:
            continue
        lvl = risks[t.id].level if t.id in risks else None
        if not (state.is_overdue(t) or lvl in ("high", "medium")):
            continue
        why = "is overdue" if state.is_overdue(t) else f"has {lvl} delay risk ({risks[t.id].probability:.0%})"
        recs.append(_rec(
            f"bottleneck-{t.id}", "bottleneck", "high" if state.is_overdue(t) or lvl == "high" else "medium",
            f"Prioritise “{t.title}”: it blocks {len(deps)} tasks",
            f"#{t.id} {why} and {len(deps)} downstream tasks cannot finish until it does "
            f"({', '.join('#' + str(d.id) for d in deps[:5])}). Owner: {state.member_name(t.assignee_id)}.",
            [f"blocks #{d.id} {d.title}" for d in deps[:5]], [t.id] + [d.id for d in deps],
        ))
        covered.add(t.id)

    # 3) High-risk tasks with a factor-specific action.
    for tid, r in sorted(risks.items(), key=lambda kv: -kv[1].probability):
        if r.level != "high" or tid in covered:
            continue
        t = state.tasks[tid]
        top = r.factors[0].feature if r.factors else None
        action = ACTION_BY_FACTOR.get(top, "Review scope and ownership with the team.")
        recs.append(_rec(
            f"risk-{tid}", "delay_risk", "high",
            f"“{t.title}” is likely to miss its deadline ({r.probability:.0%})",
            action, [f.label for f in r.factors[:3]], [tid], [t.assignee_id] if t.assignee_id else [],
        ))

    # 3b) Overdue tasks not already covered as bottlenecks.
    for t in state.open_tasks():
        if state.is_overdue(t) and t.id not in covered:
            late = days_between(t.deadline, now)
            recs.append(_rec(
                f"overdue-{t.id}", "overdue", "high",
                f"“{t.title}” is {late:.1f} days overdue",
                f"Owner: {state.member_name(t.assignee_id)}. Agree a new realistic date or re-scope it today.",
                [], [t.id], [t.assignee_id] if t.assignee_id else [],
            ))

    # 4) Urgent work not started.
    for t in state.open_tasks():
        if t.status == "todo" and t.priority in ("high", "critical") and t.deadline is not None:
            left = days_between(now, t.deadline)
            if 0 <= left <= 2 and t.id not in covered:
                recs.append(_rec(
                    f"urgent-{t.id}", "not_started", "medium",
                    f"“{t.title}” is due in {left * 24:.0f} h and has not started",
                    f"{t.priority.capitalize()} priority, owner {state.member_name(t.assignee_id)}. Start it today or move the deadline.",
                    [], [t.id], [t.assignee_id] if t.assignee_id else [],
                ))

    # 5) Unassigned work with a deadline in the next week.
    unassigned = [t for t in state.open_tasks() if t.assignee_id is None and t.deadline is not None
                  and days_between(now, t.deadline) <= 7]
    if unassigned:
        lightest = receivers[0] if receivers else None
        recs.append(_rec(
            "unassigned", "unassigned", "medium",
            f"{len(unassigned)} task{'s' if len(unassigned) != 1 else ''} due this week "
            f"{'have' if len(unassigned) != 1 else 'has'} no owner",
            ", ".join(f"#{t.id} {t.title}" for t in unassigned[:4])
            + (f". {lightest.name} currently has the most capacity." if lightest else ""),
            [], [t.id for t in unassigned],
            action={"type": "reassign", "task_id": unassigned[0].id, "to_member_id": lightest.member_id} if lightest else None,
        ))

    order = {"high": 0, "medium": 1, "low": 2}
    recs.sort(key=lambda r: order[r["severity"]])
    return recs[:max_items]
