"""FastAPI dependencies: authentication and project-level authorization (RBAC)."""
from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db.models import Project, ProjectMember, Task, User
from .db.session import get_db
from .security import decode_access_token

bearer = HTTPBearer(auto_error=False)


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    uid = decode_access_token(creds.credentials)
    user = db.get(User, uid) if uid else None
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")
    return user


@dataclass
class ProjectAccess:
    project: Project
    membership: ProjectMember
    user: User

    @property
    def is_manager(self) -> bool:
        return self.membership.role == "manager"

    def require_manager(self) -> None:
        if not self.is_manager:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Only project managers can do this")

    def can_edit_task(self, task: Task) -> bool:
        return self.is_manager or task.assignee_id == self.user.id or task.created_by == self.user.id


def project_access(db: Session, project_id: int, user: User) -> ProjectAccess:
    project = db.get(Project, project_id)
    # Same 404 for "does not exist" and "not a member": do not leak project existence.
    if project is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")
    m = db.scalar(select(ProjectMember).where(ProjectMember.project_id == project_id, ProjectMember.user_id == user.id))
    if m is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")
    return ProjectAccess(project, m, user)


def get_project_access(
    project_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> ProjectAccess:
    return project_access(db, project_id, user)


def task_access(db: Session, task_id: int, user: User) -> tuple[Task, ProjectAccess]:
    task = db.get(Task, task_id)
    if task is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Task not found")
    return task, project_access(db, task.project_id, user)
