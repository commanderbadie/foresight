from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..core.flow import compute_flow
from ..core.intelligence import Change, simulate
from ..db.models import HealthSnapshot, Prediction, RecommendationFeedback, Task, User
from ..db.session import get_db
from ..deps import ProjectAccess, get_current_user, get_project_access, task_access
from ..schemas import FeedbackIn, WhatIfIn
from ..services import load_state, member_names, predictor, run_analysis, task_out

router = APIRouter(tags=["intelligence"])


def model_badge() -> dict:
    p = predictor()
    card = p.card
    return {
        "version": p.version,
        "data_source": card.get("data_source"),
        "is_synthetic": bool(card.get("is_synthetic", False)),
        "algorithm": card.get("algorithm"),
        "warning": card.get("warning"),
        "thresholds": p.thresholds,
    }


@router.get("/api/projects/{project_id}/overview")
def overview(acc: ProjectAccess = Depends(get_project_access), db: Session = Depends(get_db)):
    """Everything the dashboard needs in one round trip."""
    state, analysis, recs = run_analysis(db, acc.project)
    names = member_names(db, acc.project.id)
    tasks = {t.id: t for t in db.scalars(select(Task).where(Task.project_id == acc.project.id)).all()}
    ranked = sorted(analysis.risks.values(), key=lambda r: -r.probability)
    top = [task_out(tasks[r.task_id], state, analysis.risks, names) for r in ranked[:8] if r.task_id in tasks]
    upcoming = sorted(
        [t for t in state.open_tasks() if t.deadline and not state.is_overdue(t)], key=lambda t: t.deadline
    )[:6]
    prev = db.scalars(select(HealthSnapshot).where(HealthSnapshot.project_id == acc.project.id)
                      .order_by(HealthSnapshot.created_at.desc()).limit(2)).all()
    return {
        "project": {"id": acc.project.id, "name": acc.project.name, "is_demo": acc.project.is_demo,
                    "start_date": state.start_date, "end_date": state.end_date},
        "role": acc.membership.role,
        "health": analysis.health.as_dict(),
        "health_previous": prev[1].score if len(prev) > 1 else None,
        "workload": analysis.workload.as_dict(),
        "flow": compute_flow(state),
        "top_risks": top,
        "risk_counts": {lvl: sum(1 for r in analysis.risks.values() if r.level == lvl)
                        for lvl in ("overdue", "high", "medium", "low")},
        "upcoming": [task_out(tasks[t.id], state, analysis.risks, names) for t in upcoming],
        "recommendations": recs,
        "model": model_badge(),
    }


@router.get("/api/projects/{project_id}/workload")
def workload(acc: ProjectAccess = Depends(get_project_access), db: Session = Depends(get_db)):
    state, analysis, _ = run_analysis(db, acc.project, with_recs=False, persist=False)
    names = member_names(db, acc.project.id)
    tasks = {t.id: t for t in db.scalars(select(Task).where(Task.project_id == acc.project.id)).all()}
    members = []
    for m in analysis.workload.as_dict()["members"]:
        mine = [task_out(tasks[t.id], state, analysis.risks, names) for t in state.tasks_of(m["member_id"])]
        members.append({**m, "tasks": sorted(mine, key=lambda x: (x["deadline"] is None, x["deadline"] or 0))})
    return {**analysis.workload.as_dict(), "members": members}


@router.post("/api/projects/{project_id}/what-if")
def what_if(body: WhatIfIn, acc: ProjectAccess = Depends(get_project_access), db: Session = Depends(get_db)):
    """Simulate a change WITHOUT saving it: before/after risk and health, with explanation."""
    state = load_state(db, acc.project)
    if body.task_id not in state.tasks:
        raise HTTPException(404, "Task not in this project")
    if body.assignee_id is not None and body.assignee_id not in state.members:
        raise HTTPException(422, "Assignee must be a project member")
    result = simulate(state, Change(task_id=body.task_id, assignee_id=body.assignee_id, unassign=body.unassign,
                                    deadline=body.deadline, story_points=body.story_points, status=body.status),
                      predictor())
    return result


@router.get("/api/tasks/{task_id}/risk")
def task_risk(task_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    task, acc = task_access(db, task_id, user)
    state = load_state(db, acc.project)
    p = predictor()
    risks = p.predict_state(state)
    history = db.scalars(select(Prediction).where(Prediction.task_id == task_id)
                         .order_by(Prediction.created_at).limit(200)).all()
    blocks = state.transitive_dependents(task_id)
    return {
        "risk": risks[task_id].as_dict() if task_id in risks else None,
        "features": ({k: (None if v != v else round(v, 4)) for k, v in risks[task_id].features.items()}
                     if task_id in risks else None),
        "history": [{"at": h.created_at, "probability": h.probability, "level": h.level} for h in history],
        "blocks": [{"id": d.id, "title": d.title} for d in blocks],
        "blocked_by": [{"id": b.id, "title": b.title, "status": b.status} for b in
                       (state.tasks[x] for x in state.tasks[task_id].blocked_by if x in state.tasks)],
        "model": model_badge(),
    }


@router.post("/api/projects/{project_id}/recommendations/{rec_key}/feedback", status_code=201)
def recommendation_feedback(rec_key: str, body: FeedbackIn, acc: ProjectAccess = Depends(get_project_access),
                            db: Session = Depends(get_db)):
    db.add(RecommendationFeedback(project_id=acc.project.id, rec_key=rec_key[:120], kind=body.kind,
                                  action=body.action, user_id=acc.user.id))
    db.commit()
    return {"ok": True}


@router.get("/api/projects/{project_id}/recommendations/stats")
def recommendation_stats(acc: ProjectAccess = Depends(get_project_access), db: Session = Depends(get_db)):
    """Measurable usefulness: how often managers act on each kind of recommendation."""
    rows = db.execute(select(RecommendationFeedback.kind, RecommendationFeedback.action, func.count())
                      .where(RecommendationFeedback.project_id == acc.project.id)
                      .group_by(RecommendationFeedback.kind, RecommendationFeedback.action)).all()
    stats: dict[str, dict] = {}
    for kind, action, n in rows:
        stats.setdefault(kind, {"applied": 0, "dismissed": 0})[action] = n
    for s in stats.values():
        total = s["applied"] + s["dismissed"]
        s["acceptance_rate"] = round(s["applied"] / total, 3) if total else None
    return stats


@router.get("/api/projects/{project_id}/health/history")
def health_history(acc: ProjectAccess = Depends(get_project_access), db: Session = Depends(get_db)):
    snaps = db.scalars(select(HealthSnapshot).where(HealthSnapshot.project_id == acc.project.id)
                       .order_by(HealthSnapshot.created_at).limit(500)).all()
    return [{"at": s.created_at, "score": s.score, "status": s.status, "signals": s.signals} for s in snaps]


@router.get("/api/model")
def model_info(user: User = Depends(get_current_user)):
    p = predictor()
    return {"card": p.card, "metrics": p.metrics, "thresholds": p.thresholds, "features": p.feature_names,
            "reference": p.reference}
