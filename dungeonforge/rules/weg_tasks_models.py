"""Saved 1992 scene tasks, declared workers, Command rolls and required stages."""
import uuid
from typing import Literal

from pydantic import BaseModel, Field


class D6TaskStep(BaseModel):
    skill: str = Field(min_length=1, max_length=120)
    difficulty: int = Field(15, ge=1, le=1000)
    rounds: int = Field(1, ge=1, le=6307200)
    mode: Literal["normal", "prepared", "rushed"] = "normal"
    reason: str = Field(min_length=1, max_length=1000)
    rush_rounding: Literal["down", "up"] | None = None
    rounding_reason: str = Field("", max_length=1000)


class D6TaskRequest(BaseModel):
    actor_id: str
    label: str = Field(min_length=1, max_length=120)
    reason: str = Field(min_length=1, max_length=1000)
    exclusive: bool = False
    steps: list[D6TaskStep] = Field(min_length=1, max_length=20)
    participant_ids: list[str] = Field(default_factory=list, max_length=1500)
    commander_id: str | None = None
    commander_participates: bool = False
    contact_confirmed: bool = False
    target_visible: bool = False
    same_range: bool = False
    participant_limit: int | None = Field(None, ge=2, le=1500)
    command_difficulty: int | None = Field(None, ge=1, le=1000)
    command_character_points: int = Field(0, ge=0, le=5)
    command_force_point: bool = False
    expected_updated_at: float | None = None


class D6TaskStepQuote(BaseModel):
    skill: str
    mode: str
    difficulty: int
    base_rounds: int
    preparation_rounds: int
    work_rounds: int
    total_rounds: int


class D6TaskQuote(BaseModel):
    steps: list[D6TaskStepQuote]
    combined: bool
    average_skill: int | None = None
    command_band: str | None = None
    command_difficulty: int | None = None
    declared_count: int = 1
    table_count: int = 1
    participants: list[dict] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    source: str = "WEG40055 (1992), printed pp.30, 55, 58, 65, 68–70."


class D6TaskProject(BaseModel):
    id: str = Field(default_factory=lambda: f"task_{uuid.uuid4().hex[:12]}")
    label: str
    reason: str
    request: D6TaskRequest
    quote: D6TaskQuote
    status: Literal["pending", "completed", "failed", "interrupted", "cancelled"] = "pending"
    current_step: int = 0
    work_rounds: int = 0
    elapsed_rounds: int = 0
    declarations: list[dict] = Field(default_factory=list)
    command: dict | None = None
    results: list[dict] = Field(default_factory=list)
    work_log: list[dict] = Field(default_factory=list)
    actor_clocks: dict[str, int] = Field(default_factory=dict)


class D6TaskState(BaseModel):
    projects: list[D6TaskProject] = Field(default_factory=list)


class D6TaskAdvance(BaseModel):
    project_id: str
    rounds: int = Field(1, ge=1, le=6307200)
    reason: str = Field(min_length=1, max_length=1000)


class D6TaskResolve(BaseModel):
    project_id: str
    character_points: int = Field(0, ge=0, le=5)
    force_point: bool = False


class D6TaskManage(BaseModel):
    project_id: str
    reason: str = Field(min_length=1, max_length=1000)
