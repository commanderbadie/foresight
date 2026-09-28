from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.state import as_aware, utcnow
from ..db.models import ProjectMember, Task, TaskDependency, TaskUpdate, User
from ..db.session import get_db
from ..deps import ProjectAccess, get_current_user, get_project_access, task_access
from ..schemas import CommentIn, DependencyIn, TaskIn, TaskOut, TaskPatch, UpdateOut
from ..services import load_state, member_names, predictor, task_out, would_create_cycle

router = APIRouter(tags=["tasks"])


def _check_assignee(db: Session, project_id: int, assignee_id: Optional[int]) -> None:
    if assignee_id is None:
        return
    ok = db.scalar(select(ProjectMember).where(ProjectMember.project_id == project_id,
                                               ProjectMember.user_id == assignee_id))
    if not ok:
        raise HTTPException(422, "Assignee must be a member of the project")


def _log(db: Session, task: Task, user: User, kind: str, old=None, new=None, comment=None):
    db.add(TaskUpdate(task_id=task.id, user_id=user.id, kind=kind,
                      from_value=None if old is None else str(old)[:200],
                      to_value=None if new is None else str(new)[:200], comment=comment))


def _apply_status(task: Task, new_status: str) -> None:
    now = utcnow()
    if new_status in ("in_progress", "review") and task.started_at is None:
        task.started_at = now
    if new_status == "done":
        task.completed_at = now
        if task.started_at is None:
            task.started_at = now
    elif task.status == "done":
        task.completed_at = None  # reopened
    task.status = new_status


@router.get("/api/projects/{project_id}/tasks", response_model=list[TaskOut])
def list_tasks(status: Optional[str] = None, assignee_id: Optional[int] = None, overdue: bool = False,
               with_risk: bool = True, acc: ProjectAccess = Depends(get_project_access), db: Session = Depends(get_db)):
    tasks = db.scalars(select(Task).where(Task.project_id == acc.project.id)
                       .order_by(Task.status, Task.position, Task.id)).all()
    state = load_state(db, acc.project)
    risks = predictor().predict_state(state, explain=True) if with_risk else None
    names = member_names(db, acc.project.id)
    out = []
    for t in tasks:
        if status and t.status != status:
            continue
        if assignee_id is not None and t.assignee_id != assignee_id:
            continue
        item = task_out(t, state, risks, names)
        if overdue and not item["is_overdue"]:
            continue
        out.append(item)
    return out


@router.post("/api/projects/{project_id}/tasks", response_model=TaskOut, status_code=201)
def create_task(body: TaskIn, acc: ProjectAccess = Depends(get_project_access), db: Session = Depends(get_db)):
    _check_assignee(db, acc.project.id, body.assignee_id)
    data = body.model_dump(exclude={"depends_on", "status"})
    task = Task(**data, project_id=acc.project.id, created_by=acc.user.id)
    _apply_status(task, body.status)
    db.add(task)
    db.flush()
    for dep in set(body.depends_on):
        other = db.get(Task, dep)
        if other is None or other.project_id != acc.project.id:
            raise HTTPException(422, f"Dependency #{dep} is not a task in this project")
        db.add(TaskDependency(task_id=task.id, depends_on_id=dep))
    _log(db, task, acc.user, "created", new=task.title)
    db.commit()
    return task_out(task, load_state(db, acc.project), None, member_names(db, acc.project.id))


@router.get("/api/tasks/{task_id}", response_model=TaskOut)
def get_task(task_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    task, acc = task_access(db, task_id, user)
    state = load_state(db, acc.project)
    return task_out(task, state, predictor().predict_state(state), member_names(db, acc.project.id))


@router.patch("/api/tasks/{task_id}", response_model=TaskOut)
def update_task(task_id: int, body: TaskPatch, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    task, acc = task_access(db, task_id, user)
    changes = body.model_dump(exclude_unset=True)
    only_status_or_position = set(changes) <= {"status", "position"}
    if not acc.can_edit_task(task) and not (only_status_or_position and task.assignee_id is None):
        raise HTTPException(403, "Only the assignee, the creator or a manager can edit this task")

    if body.unassign:
        if task.assignee_id is not None:
            _log(db, task, user, "assignee", task.assignee_id, None)
        task.assignee_id = None
    elif "assignee_id" in changes and changes["assignee_id"] != task.assignee_id:
        _check_assignee(db, task.project_id, changes["assignee_id"])
        _log(db, task, user, "assignee", task.assignee_id, changes["assignee_id"])
        task.assignee_id = changes["assignee_id"]
    if "status" in changes and changes["status"] != task.status:
        _log(db, task, user, "status", task.status, changes["status"])
        _apply_status(task, changes["status"])
    if "deadline" in changes and as_aware(changes["deadline"]) != as_aware(task.deadline):
        _log(db, task, user, "deadline", task.deadline, changes["deadline"])
        task.deadline = changes["deadline"]
    if "story_points" in changes and changes["story_points"] != task.story_points:
        _log(db, task, user, "estimate", task.story_points, changes["story_points"])
        task.story_points = changes["story_points"]
    for k in ("title", "description", "task_type", "priority", "start_date", "position"):
        if k in changes and changes[k] is not None:
            setattr(task, k, changes[k])
    db.commit()
    state = load_state(db, acc.project)
    return task_out(task, state, predictor().predict_state(state), member_names(db, acc.project.id))


@router.delete("/api/tasks/{task_id}", status_code=204)
def delete_task(task_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    task, acc = task_access(db, task_id, user)
    if not (acc.is_manager or task.created_by == user.id):
        raise HTTPException(403, "Only a manager or the creator can delete a task")
    db.delete(task)
    db.commit()
    return Response(status_code=204)


@router.post("/api/tasks/{task_id}/dependencies", status_code=201)
def add_dependency(task_id: int, body: DependencyIn, user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    task, acc = task_access(db, task_id, user)
    if not acc.can_edit_task(task):
        raise HTTPException(403, "Not allowed")
    other = db.get(Task, body.depends_on_id)
    if other is None or other.project_id != task.project_id:
        raise HTTPException(422, "Dependency must be a task in the same project")
    if other.id == task.id:
        raise HTTPException(422, "A task cannot depend on itself")
    if db.get(TaskDependency, (task.id, other.id)):
        raise HTTPException(409, "Dependency already exists")
    if would_create_cycle(load_state(db, acc.project), task.id, other.id):
        raise HTTPException(422, "This dependency would create a cycle")
    db.add(TaskDependency(task_id=task.id, depends_on_id=other.id))
    _log(db, task, user, "dependency", None, f"#{other.id}")
    db.commit()
    return {"task_id": task.id, "depends_on_id": other.id}


@router.delete("/api/tasks/{task_id}/dependencies/{depends_on_id}", status_code=204)
def remove_dependency(task_id: int, depends_on_id: int, user: User = Depends(get_current_user),
                      db: Session = Depends(get_db)):
    task, acc = task_access(db, task_id, user)
    if not acc.can_edit_task(task):
        raise HTTPException(403, "Not allowed")
    dep = db.get(TaskDependency, (task_id, depends_on_id))
    if dep is None:
        raise HTTPException(404, "Dependency not found")
    db.delete(dep)
    db.commit()
    return Response(status_code=204)


@router.get("/api/tasks/{task_id}/updates", response_model=list[UpdateOut])
def list_updates(task_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    task_access(db, task_id, user)
    ups = db.scalars(select(TaskUpdate).where(TaskUpdate.task_id == task_id)
                     .order_by(TaskUpdate.created_at.desc(), TaskUpdate.id.desc()).limit(100)).all()
    return [UpdateOut(id=u.id, kind=u.kind, from_value=u.from_value, to_value=u.to_value, comment=u.comment,
                      user_name=u.user.name if u.user else None, created_at=as_aware(u.created_at)) for u in ups]


@router.post("/api/tasks/{task_id}/updates", response_model=UpdateOut, status_code=201)
def add_comment(task_id: int, body: CommentIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    task, _ = task_access(db, task_id, user)
    u = TaskUpdate(task_id=task.id, user_id=user.id, kind="comment", comment=body.comment)
    db.add(u)
    db.commit()
    return UpdateOut(id=u.id, kind=u.kind, from_value=None, to_value=None, comment=u.comment, user_name=user.name,
                     created_at=as_aware(u.created_at) or utcnow())
