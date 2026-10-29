"""The rare free Dark Side offers in WEG40055 (1992), printed p.57."""
import time
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class DarkSideFavor(BaseModel):
    id: str
    actor_id: str
    actor_name: str
    moment_key: str
    eligibility: Literal["very_powerful_evil", "desperately_recruited"]
    gm_rare_offer_confirmed: bool
    offer_reason: str
    adventure: int
    scope_kind: Literal["scene", "personal", "vehicle"]
    scope_id: str
    status: Literal["offered", "used", "declined", "withdrawn"] = "offered"
    offered_at: float = Field(default_factory=time.time)
    resolution_reason: str | None = None
    resolved_at: float | None = None
    current_moment_confirmed: bool = False
    consequence_accepted: bool = False
    used_clock: int | None = None
    used_round: int | None = None
    actions_declared: int | None = None
    normal_force_point_spent: bool = False
    corruption_event_id: str | None = None
    expenditure_id: str | None = None
    source: str = "WEG40055 (1992), PDF p.54 / printed p.57, Favors."


class FavorOfferRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    offer_id: str = Field(min_length=1, max_length=120, pattern=r"^[A-Za-z0-9_-]+$")
    actor_id: str
    moment_key: str = Field(min_length=1, max_length=160)
    eligibility: Literal["very_powerful_evil", "desperately_recruited"]
    gm_rare_offer_confirmed: bool = False
    reason: str = Field(min_length=1, max_length=2000)
    expected_updated_at: float


class FavorResolveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    actor_id: str
    offer_id: str
    action: Literal["use", "decline", "withdraw"]
    reason: str = Field(min_length=1, max_length=2000)
    current_moment_confirmed: bool = False
    consequence_accepted: bool = False
    actions: int = Field(1, ge=1, le=10)
    force_point: bool = False
    expected_updated_at: float
