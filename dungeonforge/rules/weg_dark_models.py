"""Persistent WEG 1992 corruption, atonement, calls and redemption."""
import uuid
from typing import Literal
from pydantic import BaseModel, Field
from dungeonforge.rules.dice import RollResult
from dungeonforge.rules.weg_favor_models import DarkSideFavor


class CorruptionEvent(BaseModel):
    id: str = Field(default_factory=lambda: f"dark_{uuid.uuid4().hex[:12]}")
    source: str
    reason: str
    before: int
    after: int
    fall_die: int | None = None
    fell: bool = False
    cp_awarded: int = 0
    adventure: int | None = None
    reported: bool = False


class AtonementReview(BaseModel):
    adventure: int
    approved: bool
    reason: str


class AtonementCycle(BaseModel):
    started_adventure: int
    next_review: int
    consecutive: int = 0
    status: Literal["active", "completed", "failed", "abandoned"] = "active"
    intention: str
    reviews: list[AtonementReview] = Field(default_factory=list)


class DarkDemand(BaseModel):
    cp_loss: int
    roll: RollResult


class CorruptionState(BaseModel):
    favors: list[DarkSideFavor] = Field(default_factory=list)
    events: list[CorruptionEvent] = Field(default_factory=list)
    atonement: AtonementCycle | None = None
    atonement_history: list[AtonementCycle] = Field(default_factory=list)
    calls_adventure: int = 0
    calls: int = 0
    pending_demand: DarkDemand | None = None
    refuses_force: bool = False
    control_mode: Literal["player", "gm", "redemption"] = "player"
    fallen_adventure: int | None = None
    redemption_deadline: int | None = None
    npc_permanent: bool = False
    moment_keys: list[str] = Field(default_factory=list)
    dead: bool = False


class DarkAwardRequest(BaseModel):
    actor_id: str | None = None
    cause: Literal["evil_act", "evil_force_point", "inaction", "temptation"] = "evil_act"
    reason: str = Field(min_length=1, max_length=1000)
    player_warned: bool = False


class DarkCallRequest(BaseModel):
    actor_id: str | None = None
    actions: int = Field(2, ge=1, le=10)
    force_point: bool = False
    harmful: bool = True
    skill: Literal["auto", "control", "perception"] = "auto"
    difficulty: int | None = Field(None, ge=1, le=1000)
    intention: str = Field(min_length=1, max_length=1000)
    mishap: Literal["penalty", "complication"] = "penalty"


class DarkDemandRequest(BaseModel):
    actor_id: str | None = None
    method: Literal["character_points", "attribute", "force_skill"]
    key: str = ""


class AtonementRequest(BaseModel):
    actor_id: str | None = None
    action: Literal["begin", "approve", "reject", "abandon"]
    reason: str = Field(min_length=1, max_length=1000)
    adventure: int | None = Field(None, ge=1)


class DarkRedemptionRequest(BaseModel):
    actor_id: str | None = None
    action: Literal["allow_arc", "moment_of_doubt", "heroic_sacrifice"]
    light_jedi_id: str | None = None
    reason: str = Field(min_length=1, max_length=1000)
    confrontation_key: str = Field("", max_length=120)
    adventures: int = Field(3, ge=1, le=3)
    died: bool = False


class DarkCorrectionRequest(BaseModel):
    actor_id: str | None = None
    points: int = Field(ge=0, le=1000000)
    consumed: bool
    reason: str = Field(min_length=1, max_length=1000)


class DarkBeliefRequest(BaseModel):
    actor_id: str | None = None
    refuses_force: bool
