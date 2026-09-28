"""Relational schema (PostgreSQL in production, SQLite for quick local runs).

Tables and why each exists (see docs/DATABASE.md for the ER diagram):
  users                    accounts (bcrypt password hash)
  projects                 a project with a planned start/end
  project_members          who is on the project, their ROLE (RBAC) and CAPACITY
                           (this is the "team": a separate teams table would add
                            nothing for this scope)
  tasks                    work items (the Kanban cards)
  task_dependencies        "task X cannot finish before task Y" (many-to-many)
  task_updates             append-only history: status/assignee/deadline changes
                           and comments. Feeds cycle time and the reassignment feature.
  predictions              model outputs over time (audit trail + risk trend)
  health_snapshots         project health over time (explains changes)
  recommendation_feedback  applied / dismissed recommendations -> measurable usefulness
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import (JSON, CheckConstraint, DateTime, Float, ForeignKey, Index, Integer, String, Text,
                        UniqueConstraint, func)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .session import Base

TASK_STATUSES = ("todo", "in_progress", "review", "done")
PRIORITIES = ("low", "medium", "high", "critical")
TASK_TYPES = ("feature", "bug", "chore")
ROLES = ("manager", "member")


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class User(TimestampMixin, Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)


class Project(TimestampMixin, Base):
    __tablename__ = "projects"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    start_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    end_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    is_demo: Mapped[bool] = mapped_column(default=False, nullable=False)

    members: Mapped[list["ProjectMember"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    tasks: Mapped[list["Task"]] = relationship(back_populates="project", cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint("end_date IS NULL OR start_date IS NULL OR end_date > start_date", name="ck_project_dates"),
    )


class ProjectMember(Base):
    __tablename__ = "project_members"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role: Mapped[str] = mapped_column(String(16), default="member", nullable=False)
    capacity_points: Mapped[float] = mapped_column(Float, default=13.0, nullable=False)
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    project: Mapped[Project] = relationship(back_populates="members")
    user: Mapped[User] = relationship()

    __table_args__ = (
        UniqueConstraint("project_id", "user_id", name="uq_member"),
        CheckConstraint("role IN ('manager','member')", name="ck_member_role"),
        CheckConstraint("capacity_points > 0", name="ck_member_capacity"),
        Index("ix_member_user", "user_id"),
    )


class Task(TimestampMixin, Base):
    __tablename__ = "tasks"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    task_type: Mapped[str] = mapped_column(String(16), default="feature", nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="todo", nullable=False)
    priority: Mapped[str] = mapped_column(String(16), default="medium", nullable=False)
    story_points: Mapped[Optional[float]] = mapped_column(Float)
    assignee_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    start_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    deadline: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), onupdate=func.now())

    project: Mapped[Project] = relationship(back_populates="tasks")
    assignee: Mapped[Optional[User]] = relationship(foreign_keys=[assignee_id])
    blocked_by: Mapped[list["TaskDependency"]] = relationship(
        foreign_keys="TaskDependency.task_id", cascade="all, delete-orphan", back_populates="task")

    __table_args__ = (
        CheckConstraint("status IN ('todo','in_progress','review','done')", name="ck_task_status"),
        CheckConstraint("priority IN ('low','medium','high','critical')", name="ck_task_priority"),
        CheckConstraint("task_type IN ('feature','bug','chore')", name="ck_task_type"),
        CheckConstraint("story_points IS NULL OR story_points >= 0", name="ck_task_points"),
        Index("ix_task_project_status", "project_id", "status"),
        Index("ix_task_assignee", "assignee_id"),
        Index("ix_task_deadline", "deadline"),
    )


class TaskDependency(Base):
    __tablename__ = "task_dependencies"
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True)
    depends_on_id: Mapped[int] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True)

    task: Mapped[Task] = relationship(foreign_keys=[task_id], back_populates="blocked_by")
    depends_on: Mapped[Task] = relationship(foreign_keys=[depends_on_id])

    __table_args__ = (
        CheckConstraint("task_id <> depends_on_id", name="ck_dep_not_self"),
        Index("ix_dep_depends_on", "depends_on_id"),
    )


class TaskUpdate(TimestampMixin, Base):
    __tablename__ = "task_updates"
    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    kind: Mapped[str] = mapped_column(String(16), nullable=False)  # created|status|assignee|deadline|estimate|comment
    from_value: Mapped[Optional[str]] = mapped_column(String(200))
    to_value: Mapped[Optional[str]] = mapped_column(String(200))
    comment: Mapped[Optional[str]] = mapped_column(Text)

    user: Mapped[Optional[User]] = relationship()

    __table_args__ = (Index("ix_update_task_time", "task_id", "created_at"),)


class Prediction(TimestampMixin, Base):
    __tablename__ = "predictions"
    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False)
    probability: Mapped[float] = mapped_column(Float, nullable=False)
    level: Mapped[str] = mapped_column(String(16), nullable=False)
    factors: Mapped[list] = mapped_column(JSON, default=list)
    model_version: Mapped[str] = mapped_column(String(64), nullable=False)

    __table_args__ = (
        CheckConstraint("probability >= 0 AND probability <= 1", name="ck_pred_prob"),
        Index("ix_pred_task_time", "task_id", "created_at"),
    )


class HealthSnapshot(TimestampMixin, Base):
    __tablename__ = "health_snapshots"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    signals: Mapped[list] = mapped_column(JSON, default=list)

    __table_args__ = (Index("ix_health_project_time", "project_id", "created_at"),)


class RecommendationFeedback(TimestampMixin, Base):
    __tablename__ = "recommendation_feedback"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    rec_key: Mapped[str] = mapped_column(String(120), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    action: Mapped[str] = mapped_column(String(16), nullable=False)  # applied | dismissed
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

    __table_args__ = (
        CheckConstraint("action IN ('applied','dismissed')", name="ck_feedback_action"),
        Index("ix_feedback_project", "project_id", "rec_key"),
    )
