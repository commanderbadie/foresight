"""Request/response validation (Pydantic v2)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Literal, Optional

from pydantic import AfterValidator, BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator


def _to_utc(v: Optional[datetime]) -> Optional[datetime]:
    """Store every timestamp in UTC (the browser may send +05:30 etc.; naive = UTC)."""
    if v is None:
        return None
    return v.replace(tzinfo=timezone.utc) if v.tzinfo is None else v.astimezone(timezone.utc)


UTCDateTime = Annotated[datetime, AfterValidator(_to_utc)]

Status = Literal["todo", "in_progress", "review", "done"]
Priority = Literal["low", "medium", "high", "critical"]
TaskType = Literal["feature", "bug", "chore"]
Role = Literal["manager", "member"]


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------- auth ----------
class RegisterIn(BaseModel):
    email: EmailStr
    name: str = Field(min_length=2, max_length=120)
    password: str = Field(min_length=8, max_length=72)


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=72)


class UserOut(ORM):
    id: int
    email: str
    name: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


# ---------- projects ----------
class ProjectIn(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    description: str = Field(default="", max_length=5000)
    start_date: Optional[UTCDateTime] = None
    end_date: Optional[UTCDateTime] = None

    @model_validator(mode="after")
    def _dates(self):
        if self.start_date and self.end_date and self.end_date <= self.start_date:
            raise ValueError("end_date must be after start_date")
        return self


class ProjectPatch(BaseModel):
    name: Optional[str] = Field(default=None, min_length=2, max_length=160)
    description: Optional[str] = Field(default=None, max_length=5000)
    start_date: Optional[UTCDateTime] = None
    end_date: Optional[UTCDateTime] = None


class ProjectOut(ORM):
    id: int
    name: str
    description: str
    start_date: Optional[datetime]
    end_date: Optional[datetime]
    is_demo: bool
    created_at: datetime


class ProjectListItem(ProjectOut):
    role: Role
    open_tasks: int
    member_count: int
    health_score: Optional[float] = None
    health_status: Optional[str] = None


class MemberIn(BaseModel):
    email: EmailStr
    role: Role = "member"
    capacity_points: float = Field(default=13, gt=0, le=200)


class MemberPatch(BaseModel):
    role: Optional[Role] = None
    capacity_points: Optional[float] = Field(default=None, gt=0, le=200)


class MemberOut(BaseModel):
    user_id: int
    name: str
    email: str
    role: Role
    capacity_points: float


# ---------- tasks ----------
class TaskIn(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    description: str = Field(default="", max_length=20000)
    task_type: TaskType = "feature"
    status: Status = "todo"
    priority: Priority = "medium"
    story_points: Optional[float] = Field(default=None, ge=0, le=100)
    assignee_id: Optional[int] = None
    start_date: Optional[UTCDateTime] = None
    deadline: Optional[UTCDateTime] = None
    depends_on: list[int] = Field(default_factory=list)


class TaskPatch(BaseModel):
    title: Optional[str] = Field(default=None, min_length=2, max_length=200)
    description: Optional[str] = Field(default=None, max_length=20000)
    task_type: Optional[TaskType] = None
    status: Optional[Status] = None
    priority: Optional[Priority] = None
    story_points: Optional[float] = Field(default=None, ge=0, le=100)
    assignee_id: Optional[int] = None
    unassign: bool = False
    start_date: Optional[UTCDateTime] = None
    deadline: Optional[UTCDateTime] = None
    position: Optional[int] = None


class TaskOut(ORM):
    id: int
    project_id: int
    title: str
    description: str
    task_type: TaskType
    status: Status
    priority: Priority
    story_points: Optional[float]
    assignee_id: Optional[int]
    assignee_name: Optional[str] = None
    start_date: Optional[datetime]
    deadline: Optional[datetime]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    created_at: datetime
    position: int
    blocked_by: list[int] = []
    blocks: list[int] = []
    is_overdue: bool = False
    risk: Optional[dict] = None


class DependencyIn(BaseModel):
    depends_on_id: int


class CommentIn(BaseModel):
    comment: str = Field(min_length=1, max_length=5000)


class UpdateOut(BaseModel):
    id: int
    kind: str
    from_value: Optional[str]
    to_value: Optional[str]
    comment: Optional[str]
    user_name: Optional[str]
    created_at: datetime


# ---------- intelligence ----------
class WhatIfIn(BaseModel):
    task_id: int
    assignee_id: Optional[int] = None
    unassign: bool = False
    deadline: Optional[UTCDateTime] = None
    story_points: Optional[float] = Field(default=None, ge=0, le=100)
    status: Optional[Status] = None


class FeedbackIn(BaseModel):
    kind: str = Field(max_length=32)
    action: Literal["applied", "dismissed"]


class AskIn(BaseModel):
    question: str = Field(min_length=2, max_length=1000)

    @field_validator("question")
    @classmethod
    def _strip(cls, v: str) -> str:
        return v.strip()
