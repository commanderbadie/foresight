"""In-memory snapshot of a project.

Every intelligence component (features, health, workload, recommendations,
what-if simulation) works on this plain-Python structure instead of on ORM
objects. That keeps the logic:
  * testable without a database,
  * reusable by the offline ML pipeline,
  * safe to mutate for what-if simulations (we copy, never touch the DB).
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

DONE = "done"
OPEN_STATUSES = ("todo", "in_progress", "review")
ALL_STATUSES = ("todo", "in_progress", "review", "done")
PRIORITIES = ("low", "medium", "high", "critical")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def as_aware(dt: Optional[datetime]) -> Optional[datetime]:
    """SQLite returns naive datetimes; treat them as UTC."""
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def days_between(a: datetime, b: datetime) -> float:
    return (as_aware(b) - as_aware(a)).total_seconds() / 86400.0


@dataclass
class MemberState:
    id: int
    name: str
    capacity_points: float = 13.0  # story points a member can carry comfortably


@dataclass
class TaskState:
    id: int
    title: str
    status: str
    priority: str
    task_type: str  # "feature" | "bug" | "chore"
    story_points: Optional[float]
    assignee_id: Optional[int]
    created_at: datetime
    deadline: Optional[datetime]
    start_date: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    description_len: int = 0
    reassign_count: int = 0
    blocked_by: list[int] = field(default_factory=list)  # ids of prerequisite tasks

    @property
    def is_done(self) -> bool:
        return self.status == DONE

    @property
    def window_start(self) -> datetime:
        return as_aware(self.start_date or self.created_at)


@dataclass
class ProjectState:
    project_id: int
    name: str
    now: datetime
    members: dict[int, MemberState]
    tasks: dict[int, TaskState]
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None

    # ---------- convenience queries ----------
    def open_tasks(self) -> list[TaskState]:
        return [t for t in self.tasks.values() if not t.is_done]

    def done_tasks(self) -> list[TaskState]:
        return [t for t in self.tasks.values() if t.is_done]

    def tasks_of(self, member_id: int, open_only: bool = True) -> list[TaskState]:
        return [
            t for t in self.tasks.values()
            if t.assignee_id == member_id and (not open_only or not t.is_done)
        ]

    def is_overdue(self, t: TaskState) -> bool:
        return (not t.is_done) and t.deadline is not None and as_aware(t.deadline) < as_aware(self.now)

    def was_late(self, t: TaskState) -> Optional[bool]:
        """Outcome label for a task whose deadline has passed or that is done.

        Returns None when the outcome is not known yet (open and not past due).
        This is the same definition the ML label uses: not finished by deadline.
        """
        if t.deadline is None:
            return None
        dl = as_aware(t.deadline)
        if t.is_done and t.completed_at is not None:
            return as_aware(t.completed_at) > dl
        if dl < as_aware(self.now):
            return True
        return None

    def open_blockers(self, t: TaskState) -> list[TaskState]:
        return [self.tasks[b] for b in t.blocked_by if b in self.tasks and not self.tasks[b].is_done]

    def dependents_of(self, task_id: int) -> list[TaskState]:
        return [t for t in self.tasks.values() if task_id in t.blocked_by and not t.is_done]

    def transitive_dependents(self, task_id: int) -> list[TaskState]:
        seen: set[int] = set()
        stack = [task_id]
        out: list[TaskState] = []
        while stack:
            cur = stack.pop()
            for d in self.dependents_of(cur):
                if d.id not in seen:
                    seen.add(d.id)
                    out.append(d)
                    stack.append(d.id)
        return out

    def member_name(self, member_id: Optional[int]) -> str:
        if member_id is None or member_id not in self.members:
            return "Unassigned"
        return self.members[member_id].name

    def clone(self) -> "ProjectState":
        return copy.deepcopy(self)
