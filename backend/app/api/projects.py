from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db.models import HealthSnapshot, Project, ProjectMember, Task, User
from ..db.session import get_db
from ..deps import ProjectAccess, get_current_user, get_project_access
from ..schemas import MemberIn, MemberOut, MemberPatch, ProjectIn, ProjectListItem, ProjectOut, ProjectPatch

router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.get("", response_model=list[ProjectListItem])
def list_projects(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.execute(
        select(Project, ProjectMember.role).join(ProjectMember, ProjectMember.project_id == Project.id)
        .where(ProjectMember.user_id == user.id).order_by(Project.created_at.desc())
    ).all()
    out = []
    for project, role in rows:
        open_tasks = db.scalar(select(func.count()).select_from(Task)
                               .where(Task.project_id == project.id, Task.status != "done")) or 0
        members = db.scalar(select(func.count()).select_from(ProjectMember)
                            .where(ProjectMember.project_id == project.id)) or 0
        snap = db.scalar(select(HealthSnapshot).where(HealthSnapshot.project_id == project.id)
                         .order_by(HealthSnapshot.created_at.desc()).limit(1))
        out.append(ProjectListItem(
            **ProjectOut.model_validate(project).model_dump(), role=role, open_tasks=open_tasks,
            member_count=members, health_score=snap.score if snap else None,
            health_status=snap.status if snap else None,
        ))
    return out


@router.post("", response_model=ProjectOut, status_code=201)
def create_project(body: ProjectIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    project = Project(**body.model_dump(), created_by=user.id)
    project.members.append(ProjectMember(user_id=user.id, role="manager"))
    db.add(project)
    db.commit()
    db.refresh(project)  # load server defaults (created_at) before serialising
    return project


@router.get("/{project_id}", response_model=ProjectOut)
def get_project(acc: ProjectAccess = Depends(get_project_access)):
    return acc.project


@router.patch("/{project_id}", response_model=ProjectOut)
def update_project(body: ProjectPatch, acc: ProjectAccess = Depends(get_project_access), db: Session = Depends(get_db)):
    acc.require_manager()
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(acc.project, k, v)
    p = acc.project
    if p.start_date and p.end_date and p.end_date <= p.start_date:
        raise HTTPException(422, "end_date must be after start_date")
    db.commit()
    return p


@router.delete("/{project_id}", status_code=204)
def delete_project(acc: ProjectAccess = Depends(get_project_access), db: Session = Depends(get_db)):
    acc.require_manager()
    db.delete(acc.project)
    db.commit()
    return Response(status_code=204)


# ---------------- members ----------------
def _member_out(m: ProjectMember) -> MemberOut:
    return MemberOut(user_id=m.user_id, name=m.user.name, email=m.user.email, role=m.role,
                     capacity_points=m.capacity_points)


@router.get("/{project_id}/members", response_model=list[MemberOut])
def list_members(acc: ProjectAccess = Depends(get_project_access), db: Session = Depends(get_db)):
    ms = db.scalars(select(ProjectMember).where(ProjectMember.project_id == acc.project.id)).all()
    return [_member_out(m) for m in sorted(ms, key=lambda m: m.user.name)]


@router.post("/{project_id}/members", response_model=MemberOut, status_code=201)
def add_member(body: MemberIn, acc: ProjectAccess = Depends(get_project_access), db: Session = Depends(get_db)):
    acc.require_manager()
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    if user is None:
        raise HTTPException(404, "No registered user with that email. Ask them to sign up first.")
    exists = db.scalar(select(ProjectMember).where(ProjectMember.project_id == acc.project.id,
                                                   ProjectMember.user_id == user.id))
    if exists:
        raise HTTPException(status.HTTP_409_CONFLICT, "Already a member")
    m = ProjectMember(project_id=acc.project.id, user_id=user.id, role=body.role, capacity_points=body.capacity_points)
    db.add(m)
    db.commit()
    db.refresh(m)
    return _member_out(m)


@router.patch("/{project_id}/members/{user_id}", response_model=MemberOut)
def update_member(user_id: int, body: MemberPatch, acc: ProjectAccess = Depends(get_project_access),
                  db: Session = Depends(get_db)):
    acc.require_manager()
    m = db.scalar(select(ProjectMember).where(ProjectMember.project_id == acc.project.id,
                                              ProjectMember.user_id == user_id))
    if m is None:
        raise HTTPException(404, "Member not found")
    if body.role == "member" and m.role == "manager":
        managers = db.scalar(select(func.count()).select_from(ProjectMember).where(
            ProjectMember.project_id == acc.project.id, ProjectMember.role == "manager"))
        if managers <= 1:
            raise HTTPException(409, "A project needs at least one manager")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(m, k, v)
    db.commit()
    return _member_out(m)


@router.delete("/{project_id}/members/{user_id}", status_code=204)
def remove_member(user_id: int, acc: ProjectAccess = Depends(get_project_access), db: Session = Depends(get_db)):
    acc.require_manager()
    m = db.scalar(select(ProjectMember).where(ProjectMember.project_id == acc.project.id,
                                              ProjectMember.user_id == user_id))
    if m is None:
        raise HTTPException(404, "Member not found")
    if m.role == "manager":
        managers = db.scalar(select(func.count()).select_from(ProjectMember).where(
            ProjectMember.project_id == acc.project.id, ProjectMember.role == "manager"))
        if managers <= 1:
            raise HTTPException(409, "A project needs at least one manager")
    # Unassign their open tasks so nothing silently disappears.
    for t in db.scalars(select(Task).where(Task.project_id == acc.project.id, Task.assignee_id == user_id,
                                           Task.status != "done")).all():
        t.assignee_id = None
    db.delete(m)
    db.commit()
    return Response(status_code=204)
