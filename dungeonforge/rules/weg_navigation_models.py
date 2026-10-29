"""Saved hyperspace calculations, mishaps and exposed-crew emergencies."""
import uuid
from typing import Literal
from pydantic import BaseModel, Field


class D6NavigationRequest(BaseModel):
    craft_id: str
    actor_id: str | None = None
    origin: str = Field(min_length=1, max_length=120)
    destination: str = Field(min_length=1, max_length=120)
    base_hours: float | None = Field(None, gt=0, le=100000)
    base_difficulty: int = Field(15, ge=1, le=1000)
    route_type: Literal["major", "common", "light", "infrequent", "old", "unexplored"] = "major"
    backup: bool = False
    hasty: bool = False
    obstacles: int = Field(0, ge=0, le=1000)
    extra_hours: int = Field(0, ge=-100000, le=100000)
    clearance_units: float = Field(50, ge=0, le=1000000)
    boarding_confirmed: bool = False
    plotting_rounds: int = Field(1, ge=1, le=172800)
    astromech_id: str | None = None
    destination_visited: bool = False
    character_points: int = Field(0, ge=0, le=2)
    force_point: bool = False
    reason: str = Field(min_length=1, max_length=1000)
    expected_updated_at: float | None = None


class D6NavigationQuote(BaseModel):
    difficulty: int
    hours: float
    rounds: int
    has_navigation: bool
    multiplier: float
    notes: list[str] = Field(default_factory=list)


class D6Journey(BaseModel):
    id: str = Field(default_factory=lambda: f"journey_{uuid.uuid4().hex[:12]}")
    request: D6NavigationRequest
    quote: D6NavigationQuote
    status: str = "travelling"
    remaining_rounds: int
    elapsed_rounds: int = 0
    roll: dict
    miss: int = 0
    mishap: int | None = None
    auxiliary_rolls: list[dict] = Field(default_factory=list)
    travellers: list[str] = Field(default_factory=list)
    crew_exposure: dict[str, dict] = Field(default_factory=dict)
    emergency_round: int = 0
    resolution: list[str] = Field(default_factory=list)


class D6NavigationState(BaseModel):
    journeys: list[D6Journey] = Field(default_factory=list)


class D6NavigationAdvance(BaseModel):
    rounds: int = Field(720, ge=1, le=6307200)


class D6NavigationResolve(BaseModel):
    journey_id: str
    action: Literal["abort", "roll_mishap", "location", "close_call", "exposure", "next_round"]
    location: str = Field("", max_length=120)
    system: Literal["drives", "nav_computer", "weapons", "escape_pods"] = "nav_computer"
    actor_ids: list[str] = Field(default_factory=list, max_length=100)
    reason: str = Field(min_length=1, max_length=1000)


class D6NavigationSuit(BaseModel):
    journey_id: str
    actor_id: str
    method: Literal["suit", "breathe", "rescue", "wait"]
    suit_name: str = ""
    rescuer_id: str | None = None
    character_points: int = Field(0, ge=0, le=2)
    force_point: bool = False
    gamorrean_retry: bool = False
    retry_character_points: int = Field(0, ge=0, le=2)
    actions: int = Field(1, ge=1, le=2)
    reason: str = Field(min_length=1, max_length=1000)


class D6NavigationMemory(BaseModel):
    actor_id: str
    origin: str = Field(min_length=1, max_length=120)
    destination: str = Field(min_length=1, max_length=120)
    reason: str = Field(min_length=1, max_length=1000)
