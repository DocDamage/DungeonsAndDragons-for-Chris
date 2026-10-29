"""Explicit Reloaded milestone reviews; legacy saves start with unknown progress."""
import time
import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from dungeonforge.rules.strahd_children_models import DurstChildrenState


class DeathHouseActor(BaseModel):
    actor_id: str
    name: str


class DeathHouseEvent(BaseModel):
    id: str
    action: str
    reason: str
    actors: list[DeathHouseActor]
    status_before: str
    status_after: str
    pips_before: int
    pips_after: int
    requested_pips: int = 0
    floor: str | None = None
    room: str | None = None
    skill: str | None = None
    early_trigger: str | None = None
    chimes: list[str] = Field(default_factory=list)
    reminders: list[str] = Field(default_factory=list)
    source_path: str
    created_at: float = Field(default_factory=time.time)


class DeathHouseState(BaseModel):
    status: Literal["unstarted", "exploring", "hunting", "awakened_early", "escaping", "escaped"] = "unstarted"
    remaining_pips: int = Field(18, ge=0, le=18)
    visited_floors: list[str] = Field(default_factory=list)
    events: list[DeathHouseEvent] = Field(default_factory=list)


class DeathHouseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_id: str = Field(min_length=1, max_length=120, pattern=r"^[A-Za-z0-9_-]+$")
    action: Literal["start", "new_floor", "room_search", "short_rest", "awakens_early", "mound_destroyed", "escaped"]
    actual_event_confirmed: bool = False
    actor_ids: list[str] = Field(min_length=1, max_length=100)
    reason: str = Field(min_length=1, max_length=2000)
    floor: str | None = None
    room: str | None = None
    skill: Literal["perception", "investigation"] | None = None
    early_trigger: Literal["mound_attacked", "tendrils_damaged"] | None = None
    expected_updated_at: float | None = None


class StrahdMilestone(BaseModel):
    id: str
    title: str
    arcs: list[str]
    xp_per_pc: int | None = None
    variants: dict[str, int] = Field(default_factory=dict)
    trigger: str
    source_path: str
    prerequisite_ids: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class StrahdXPAccount(BaseModel):
    actor_id: str
    name: str
    baseline_xp: int = Field(ge=0, le=1000000000)
    baseline_reason: str
    awarded_xp: int = Field(0, ge=0, le=1000000000)


class StrahdRecipientReview(BaseModel):
    actor_id: str
    eligible: bool
    reason: str = Field(min_length=1, max_length=1000)


class StrahdXPAllocation(BaseModel):
    actor_id: str
    name: str
    xp: int
    total_xp: int
    sheet_level: int
    xp_level: int
    level_up_pending: bool


class StrahdMilestoneAward(BaseModel):
    id: str = Field(default_factory=lambda: f"strahd_award_{uuid.uuid4().hex[:12]}")
    milestone_id: str
    title: str
    variant: str | None = None
    xp_per_pc: int
    reason: str
    source_path: str
    trigger: str
    reviews: list[StrahdRecipientReview]
    allocations: list[StrahdXPAllocation]
    created_at: float = Field(default_factory=time.time)


class StrahdArcReview(BaseModel):
    id: str = Field(default_factory=lambda: f"strahd_arc_{uuid.uuid4().hex[:12]}")
    arc: str
    status: Literal["unreviewed", "active", "completed", "failed"]
    reason: str
    created_at: float = Field(default_factory=time.time)


class StrahdProgressState(BaseModel):
    accounts: list[StrahdXPAccount] = Field(default_factory=list)
    awards: list[StrahdMilestoneAward] = Field(default_factory=list)
    arc_reviews: list[StrahdArcReview] = Field(default_factory=list)
    death_house: DeathHouseState = Field(default_factory=DeathHouseState)
    children: DurstChildrenState = Field(default_factory=DurstChildrenState)


class StrahdXPEnrollment(BaseModel):
    actor_id: str
    baseline_xp: int = Field(ge=0, le=1000000000)
    reason: str = Field(min_length=1, max_length=1000)
    pc_confirmed: bool = False


class StrahdRegisterRequest(BaseModel):
    actors: list[StrahdXPEnrollment] = Field(min_length=1, max_length=100)
    expected_updated_at: float | None = None


class StrahdMilestoneRequest(BaseModel):
    milestone_id: str
    variant: str | None = None
    completion_confirmed: bool = False
    reason: str = Field(min_length=1, max_length=2000)
    reviews: list[StrahdRecipientReview] = Field(min_length=1, max_length=100)
    expected_updated_at: float | None = None


class StrahdArcRequest(BaseModel):
    arc: str
    status: Literal["unreviewed", "active", "completed", "failed"]
    reason: str = Field(min_length=1, max_length=1000)
    expected_updated_at: float | None = None
