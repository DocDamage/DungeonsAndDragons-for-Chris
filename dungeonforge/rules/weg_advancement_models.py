"""Saved study projects, instructors, and advancement requests for WEG 1992."""
import uuid
from typing import Literal
from pydantic import BaseModel, Field
from dungeonforge.rules.weg_dark_models import CorruptionState
from dungeonforge.rules.weg_reward_models import AdventureRewardRecord


def identity(prefix):
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


class D6Instructor(BaseModel):
    id: str = Field(default_factory=lambda: identity("teacher"))
    name: str = Field(min_length=1, max_length=120)
    attributes: dict[str, str] = Field(default_factory=dict)
    skills: dict[str, str] = Field(default_factory=dict)
    skill_attributes: dict[str, str] = Field(default_factory=dict)
    specialization_parents: dict[str, str] = Field(default_factory=dict)
    force_skills: dict[str, str] = Field(default_factory=dict)
    known_powers: list[str] = Field(default_factory=list)
    full_time: bool = False
    studying_with_master: bool = False
    dark_side_points: int = Field(0, ge=0)
    dark_side_consumed: bool = False
    character_points: int = Field(0, ge=0)
    force_points: int = Field(0, ge=0)
    corruption: CorruptionState = Field(default_factory=CorruptionState)
    notes: str = Field("", max_length=1000)


class D6TrainingRequest(BaseModel):
    actor_id: str | None = None
    kind: Literal["skill", "specialization", "advanced", "attribute", "force_skill", "force_power", "sensitivity", "move"]
    key: str = Field("", max_length=100)
    attribute: str | None = None
    parent_skill: str | None = None
    teacher_id: str | None = None
    days_saved: int = Field(0, ge=0, le=1000)
    power_days_saved: int = Field(0, ge=0, le=6)
    powers: list[str] = Field(default_factory=list, max_length=3)
    gm_study_days: int = Field(7, ge=1, le=3650)


class D6TrainingQuote(BaseModel):
    kind: str
    key: str
    old_code: str
    new_code: str
    attribute: str | None = None
    parent_skill: str | None = None
    cp_cost: int
    base_cp: int
    days: int
    teacher_id: str | None = None
    teacher_name: str | None = None
    powers: list[str] = Field(default_factory=list)
    power_slots: int = 0
    eligible_powers: list[str] = Field(default_factory=list)
    species_maximum: str | None = None
    notes: list[str] = Field(default_factory=list)
    source: str


class D6TrainingProject(BaseModel):
    id: str = Field(default_factory=lambda: identity("study"))
    request: D6TrainingRequest
    quote: D6TrainingQuote
    started_adventure: int
    finished_adventure: int | None = None
    days_completed: int = 0
    status: Literal["studying", "completed", "cancelled", "suspended", "released", "forfeited"] = "studying"
    teacher_dark_side_awarded: bool = False
    student_roll: dict | None = None
    maximum_roll: dict | None = None


class D6PowerGrant(BaseModel):
    id: str = Field(default_factory=lambda: identity("power_grant"))
    skill: str
    remaining: int
    teacher_id: str
    allowed_powers: list[str]
    project_id: str


class D6AdvancementState(BaseModel):
    project: D6TrainingProject | None = None
    history: list[D6TrainingProject] = Field(default_factory=list)
    improved: dict[str, int] = Field(default_factory=dict)
    power_grants: list[D6PowerGrant] = Field(default_factory=list)


class D6AdvancementCampaign(BaseModel):
    adventure: int = 1
    label: str = "Adventure 1"
    instructors: list[D6Instructor] = Field(default_factory=list)
    rewards: list[AdventureRewardRecord] = Field(default_factory=list)


class D6StudyRequest(BaseModel):
    actor_ids: list[str] = Field(default_factory=list, max_length=20)
    days: int = Field(1, ge=1, le=3650)


class D6AdvancementActorRequest(BaseModel):
    actor_id: str | None = None
    project_id: str | None = None


class D6PowerGrantRequest(BaseModel):
    actor_id: str | None = None
    grant_id: str
    power_id: str


class D6AwardRequest(BaseModel):
    actor_id: str | None = None
    points: int = Field(0, ge=0, le=100000)
    reason: str = Field(min_length=1, max_length=500)


class D6AdventureRequest(BaseModel):
    label: str = Field(min_length=1, max_length=120)
