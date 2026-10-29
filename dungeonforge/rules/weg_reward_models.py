"""Saved adventure-end accounting for the 1992 corebook, printed pp.54–57."""
import uuid
from typing import Literal
from pydantic import BaseModel, Field


ForceRuling = Literal["unheroic", "heroic", "heroic_climax", "evil", "evil_climax"]


class ForceExpenditure(BaseModel):
    id: str = Field(default_factory=lambda: f"fp_{uuid.uuid4().hex[:12]}")
    adventure: int | None = None
    source: str
    consumed: bool = False
    guaranteed_heroic: bool = False
    forfeited: bool = False
    ruling: ForceRuling | None = None
    reason: str = ""
    corruption_event_id: str | None = None
    returned: int = 0


class D6Rewards(BaseModel):
    baseline_known: bool = True
    starting_force_points: int | None = None
    expenditures: list[ForceExpenditure] = Field(default_factory=list)


class ForceReview(BaseModel):
    expenditure_id: str
    ruling: ForceRuling
    reason: str = Field(min_length=1, max_length=500)
    corruption_event_id: str | None = None


class AdventureActorReward(BaseModel):
    actor_id: str
    character_points: int = Field(0, ge=0, le=100000)
    zero_point_heroism: bool = False
    reason: str = Field(min_length=1, max_length=500)
    reviews: list[ForceReview] = Field(default_factory=list, max_length=10000)


class AdventureRewardRequest(BaseModel):
    adventure: int = Field(ge=1)
    expected_updated_at: float
    next_label: str = Field(min_length=1, max_length=120)
    actors: list[AdventureActorReward] = Field(min_length=1, max_length=100)


class AdventureRewardRecord(BaseModel):
    adventure: int
    label: str
    actors: list[dict] = Field(default_factory=list)
