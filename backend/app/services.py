"""Glue between the database and the framework-independent intelligence engine."""
from __future__ import annotations

from collections import defaultdict
from datetime import timedelta
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .config import get_settings
from .core.intelligence import Analysis, analyze, recommend
from .core.state import MemberState, ProjectState, TaskState, as_aware, utcnow
from .db.models import (HealthSnapshot, Prediction, Project, ProjectMember, RecommendationFeedback, Task,
                        TaskDependency, TaskUpdate, User)
from .ml.predictor import Predictor, get_predictor

HEALTH_SNAPSHOT_EVERY = timedelta(hours=1)
PREDICTION_CHANGE_TO_STORE = 0.02


def predictor() -> Predictor:
    s = get_settings()
    return get_predictor(s.model_path, s.demo_model_path)


def load_state(db: Session, project: Project) -> ProjectState:
    members = {
        m.user_id: MemberState(m.user_id, m.user.name, m.capacity_points)
        for m in db.scalars(select(ProjectMember).where(ProjectMember.project_id == project.id)).all()
    }
    tasks = db.scalars(select(Task).where(Task.project_id == project.id)).all()
    ids = [t.id for t in tasks]
    deps = defaultdict(list)
    reassigns: dict[int, int] = {}
    if ids:
        for d in db.scalars(select(TaskDependency).where(TaskDependency.task_id.in_(ids))).all():
            deps[d.task_id].append(d.depends_on_id)
        reassigns = dict(db.execute(
            select(TaskUpdate.task_id, func.count()).where(TaskUpdate.task_id.in_(ids), TaskUpdate.kind == "assignee")
            .group_by(TaskUpdate.task_id)
        ).all())
    state_tasks = {
        t.id: TaskState(
            id=t.id, title=t.title, status=t.status, priority=t.priority, task_type=t.task_type,
            story_points=t.story_points, assignee_id=t.assignee_id, created_at=as_aware(t.created_at),
            deadline=as_aware(t.deadline), start_date=as_aware(t.start_date), started_at=as_aware(t.started_at),
            completed_at=as_aware(t.completed_at), description_len=len(t.description or ""),
            reassign_count=int(reassigns.get(t.id, 0)), blocked_by=deps.get(t.id, []),
        )
        for t in tasks
    }
    return ProjectState(project.id, project.name, utcnow(), members, state_tasks,
                        as_aware(project.start_date), as_aware(project.end_date))


def run_analysis(db: Session, project: Project, with_recs: bool = True, persist: bool = True):
    state = load_state(db, project)
    p = predictor()
    analysis = analyze(state, p)
    recs = recommend(state, analysis, p) if with_recs else []
    if with_recs:
        dismissed = set(db.scalars(select(RecommendationFeedback.rec_key).where(
            RecommendationFeedback.project_id == project.id,
            RecommendationFeedback.created_at >= utcnow() - timedelta(days=2))).all())
        recs = [r for r in recs if r["id"] not in dismissed]
    if persist:
        _persist(db, project, analysis, p)
    return state, analysis, recs


def _persist(db: Session, project: Project, analysis: Analysis, p: Predictor) -> None:
    """Store prediction history (only when it changed) and hourly health snapshots."""
    if analysis.risks:
        latest = {}
        sub = select(Prediction.task_id, func.max(Prediction.id).label("mid")).where(
            Prediction.task_id.in_(list(analysis.risks))).group_by(Prediction.task_id).subquery()
        for pred in db.scalars(select(Prediction).join(sub, Prediction.id == sub.c.mid)).all():
            latest[pred.task_id] = pred
        for tid, r in analysis.risks.items():
            prev = latest.get(tid)
            if prev is None or abs(prev.probability - r.probability) >= PREDICTION_CHANGE_TO_STORE \
                    or prev.model_version != p.version:
                db.add(Prediction(task_id=tid, probability=round(r.probability, 4), level=r.level,
                                  factors=[f.as_dict() for f in r.factors], model_version=p.version))
    last = db.scalar(select(HealthSnapshot).where(HealthSnapshot.project_id == project.id)
                     .order_by(HealthSnapshot.created_at.desc()).limit(1))
    h = analysis.health
    if last is None or utcnow() - as_aware(last.created_at) >= HEALTH_SNAPSHOT_EVERY or abs(last.score - h.score) >= 5:
        db.add(HealthSnapshot(project_id=project.id, score=h.score, status=h.status,
                              signals=[s["label"] for s in h.as_dict()["signals"]]))
    db.commit()


def task_out(task: Task, state: Optional[ProjectState] = None, risks: Optional[dict] = None,
             names: Optional[dict[int, str]] = None) -> dict:
    blocked_by, blocks, overdue = [], [], False
    if state is not None and task.id in state.tasks:
        ts = state.tasks[task.id]
        blocked_by = list(ts.blocked_by)
        blocks = [d.id for d in state.tasks.values() if task.id in d.blocked_by]
        overdue = state.is_overdue(ts)
    risk = risks[task.id].as_dict() if risks and task.id in risks else None
    return {
        "id": task.id, "project_id": task.project_id, "title": task.title, "description": task.description,
        "task_type": task.task_type, "status": task.status, "priority": task.priority,
        "story_points": task.story_points, "assignee_id": task.assignee_id,
        "assignee_name": (names or {}).get(task.assignee_id) if task.assignee_id else None,
        "start_date": as_aware(task.start_date), "deadline": as_aware(task.deadline),
        "started_at": as_aware(task.started_at), "completed_at": as_aware(task.completed_at),
        "created_at": as_aware(task.created_at), "position": task.position,
        "blocked_by": blocked_by, "blocks": blocks, "is_overdue": overdue, "risk": risk,
    }


def member_names(db: Session, project_id: int) -> dict[int, str]:
    rows = db.execute(select(User.id, User.name).join(ProjectMember, ProjectMember.user_id == User.id)
                      .where(ProjectMember.project_id == project_id)).all()
    return {uid: name for uid, name in rows}


def would_create_cycle(state: ProjectState, task_id: int, depends_on_id: int) -> bool:
    """Adding task -> depends_on creates a cycle if task is already (transitively) a prerequisite of depends_on."""
    stack, seen = [depends_on_id], set()
    while stack:
        cur = stack.pop()
        if cur == task_id:
            return True
        if cur in seen or cur not in state.tasks:
            continue
        seen.add(cur)
        stack.extend(state.tasks[cur].blocked_by)
    return False
