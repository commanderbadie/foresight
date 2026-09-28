"""Tests for the intelligence engine (no database or web framework needed)."""
from datetime import timedelta
from pathlib import Path

import pytest

from app.core.demo_data import build_demo_state
from app.core.features import FEATURE_NAMES, HistoryStats, compute_features, smoothed_rate
from app.core.health import compute_health, diff_health
from app.core.intelligence import Change, analyze, apply_change, recommend, simulate
from app.core.state import MemberState, ProjectState, TaskState, utcnow
from app.core.workload import compute_workload
from app.ml.predictor import load_predictor

MODEL = Path(__file__).resolve().parents[1] / "models" / "demo" / "model.joblib"


@pytest.fixture(scope="module")
def predictor():
    if not MODEL.exists():
        from app.ml.demo_model import build_demo_model
        build_demo_model(MODEL)
    return load_predictor(MODEL)


def tiny_state():
    now = utcnow()
    members = {1: MemberState(1, "A", 10), 2: MemberState(2, "B", 10)}
    t = lambda i, **k: TaskState(id=i, title=f"t{i}", status=k.get("status", "todo"), priority=k.get("priority", "medium"),
                                 task_type="feature", story_points=k.get("sp", 3), assignee_id=k.get("a", 1),
                                 created_at=now - timedelta(days=5), deadline=now + timedelta(days=k.get("d", 5)),
                                 completed_at=k.get("completed"), blocked_by=k.get("blocked", []))
    tasks = {1: t(1, d=-1), 2: t(2, blocked=[1]), 3: t(3, a=2, status="done", completed=now - timedelta(days=1)),
             4: t(4, sp=8), 5: t(5, sp=8), 6: t(6, sp=8)}
    return ProjectState(1, "p", now, members, tasks)


def test_feature_vector_complete_and_ordered():
    s = tiny_state()
    f = compute_features(s, s.tasks[2])
    assert list(f) == FEATURE_NAMES
    assert f["open_blockers"] == 1
    assert f["assignee_open_count"] == 4          # tasks 1,4,5,6 (not itself, not done)
    assert f["assignee_open_points"] == 3 + 8 * 3


def test_history_excludes_own_outcome():
    """An overdue task must not use its own 'late' outcome in its history feature (leakage)."""
    s = tiny_state()
    h = HistoryStats.from_state(s)
    f = compute_features(s, s.tasks[1], h)
    assert f["assignee_hist_late_rate"] == pytest.approx(smoothed_rate(0, 0, h.global_prior))


def test_smoothing_pulls_towards_prior():
    assert smoothed_rate(1, 1, 0.3) < 0.5
    assert smoothed_rate(0, 0, 0.3) == pytest.approx(0.3)


def test_workload_flags_overload():
    w = compute_workload(tiny_state())
    a = w.by_id(1)
    assert a.status == "overloaded" and a.open_points == 30


def test_health_is_documented_sum_of_penalties():
    s = tiny_state()
    h = compute_health(s, compute_workload(s), {})
    assert h.score == pytest.approx(100 - sum(sig.penalty for sig in h.signals))
    keys = {sig.key for sig in h.signals}
    assert {"overdue", "blocked", "workload"} <= keys


def test_health_diff_explains_change():
    s = tiny_state()
    before = compute_health(s, compute_workload(s), {})
    s2 = apply_change(s, Change(task_id=1, status="done"))
    after = compute_health(s2, compute_workload(s2), {})
    assert after.score > before.score
    assert any("resolved" in line for line in diff_health(before, after))


def test_predictions_valid_and_explained(predictor):
    s = build_demo_state()
    risks = predictor.predict_state(s)
    assert risks
    for r in risks.values():
        assert 0.0 <= r.probability <= 1.0
        assert r.level in ("low", "medium", "high", "overdue")
    worst = max((r for r in risks.values() if r.level != "overdue"), key=lambda r: r.probability)
    assert worst.factors, "high-risk task should have explaining factors"


def test_overdue_tasks_are_not_predicted(predictor):
    s = build_demo_state()
    risks = predictor.predict_state(s)
    for tid, r in risks.items():
        if s.is_overdue(s.tasks[tid]):
            assert r.level == "overdue"


def test_what_if_reassignment_reduces_risk(predictor):
    s = build_demo_state()
    pay = next(t for t in s.tasks.values() if t.title.startswith("Payment"))
    light = min(s.members.values(), key=lambda m: sum(t.story_points or 0 for t in s.tasks_of(m.id)))
    res = simulate(s, Change(task_id=pay.id, assignee_id=light.id), predictor)
    assert res["task"]["after"]["probability"] < res["task"]["before"]["probability"]
    assert s.tasks[pay.id].assignee_id != light.id, "simulation must not mutate the real state"


def test_recommendations_grounded_in_data(predictor):
    s = build_demo_state()
    recs = recommend(s, analyze(s, predictor), predictor)
    assert recs
    for r in recs:
        for tid in r["task_ids"]:
            assert tid in s.tasks, "recommendations may only reference real tasks"
    assert any(r["kind"] == "rebalance" for r in recs)
    assert any(r["kind"] == "bottleneck" for r in recs)
