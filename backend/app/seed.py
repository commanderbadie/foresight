"""Seed the SYNTHETIC demo project and demo users.

    python -m app.seed            # create if missing
    python -m app.seed --reset    # delete the demo project and recreate it (fresh dates)

Demo logins (password for all: demo1234):
    priya@demo.foresight  (manager)   rahul@demo.foresight   aisha@demo.foresight
    karan@demo.foresight              meera@demo.foresight   dev@demo.foresight
"""
from __future__ import annotations

import argparse
from datetime import timedelta

from sqlalchemy import select

from .core.demo_data import build_demo_spec
from .db import models  # noqa: F401
from .db.models import Project, ProjectMember, Task, TaskDependency, TaskUpdate, User
from .db.session import Base, SessionLocal, engine
from .security import hash_password

DEMO_PASSWORD = "demo1234"


def seed(reset: bool = False) -> int:
    Base.metadata.create_all(engine)
    db = SessionLocal()
    try:
        existing = db.scalar(select(Project).where(Project.is_demo.is_(True)))
        if existing and not reset:
            print(f"Demo project already exists (id={existing.id}). Use --reset to recreate it.")
            return existing.id
        if existing:
            db.delete(existing)
            db.commit()

        spec = build_demo_spec()
        users = {}
        pw = hash_password(DEMO_PASSWORD)
        for m in spec["members"]:
            u = db.scalar(select(User).where(User.email == m["email"]))
            if u is None:
                u = User(email=m["email"], name=m["name"], password_hash=pw)
                db.add(u)
                db.flush()
            users[m["key"]] = u

        p = spec["project"]
        project = Project(name=p["name"], description=p["description"], start_date=p["start_date"],
                          end_date=p["end_date"], created_by=users["priya"].id, is_demo=True,
                          created_at=p["start_date"])
        db.add(project)
        db.flush()
        for m in spec["members"]:
            db.add(ProjectMember(project_id=project.id, user_id=users[m["key"]].id, role=m["role"],
                                 capacity_points=m["capacity_points"]))

        ids = {}
        order = {"todo": 0, "in_progress": 0, "review": 0, "done": 0}
        for t in spec["tasks"]:
            assignee = users[t["assignee"]].id if t["assignee"] else None
            task = Task(project_id=project.id, title=t["title"], description=t["description"],
                        task_type=t["task_type"], status=t["status"], priority=t["priority"],
                        story_points=t["story_points"], assignee_id=assignee, created_by=users["priya"].id,
                        start_date=t["start_date"], deadline=t["deadline"], started_at=t["started_at"],
                        completed_at=t["completed_at"], created_at=t["created_at"], position=order[t["status"]])
            order[t["status"]] += 1
            db.add(task)
            db.flush()
            ids[t["key"]] = task.id
            db.add(TaskUpdate(task_id=task.id, user_id=users["priya"].id, kind="created", to_value=t["title"],
                              created_at=t["created_at"]))
            if t["started_at"]:
                db.add(TaskUpdate(task_id=task.id, user_id=assignee, kind="status", from_value="todo",
                                  to_value="in_progress", created_at=t["started_at"]))
            if t["completed_at"]:
                db.add(TaskUpdate(task_id=task.id, user_id=assignee, kind="status", from_value="in_progress",
                                  to_value="done", created_at=t["completed_at"]))
            for i in range(t["reassign_count"]):
                db.add(TaskUpdate(task_id=task.id, user_id=users["priya"].id, kind="assignee",
                                  from_value=str(users["meera"].id), to_value=str(assignee),
                                  created_at=t["created_at"] + timedelta(hours=6 + i)))
        for t in spec["tasks"]:
            for b in t["blocked_by"]:
                db.add(TaskDependency(task_id=ids[t["key"]], depends_on_id=ids[b]))
        db.commit()
        print(f"Seeded demo project '{project.name}' (id={project.id}) with {len(spec['tasks'])} tasks.")
        print(f"Log in as priya@demo.foresight / {DEMO_PASSWORD}")
        return project.id
    finally:
        db.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--reset", action="store_true")
    seed(ap.parse_args().reset)
