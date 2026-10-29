"""Persistent, paid native craft repair projects (WEG40055 pp.87–91)."""
import uuid
from typing import Literal
from pydantic import BaseModel, Field


class D6CraftRepairRequest(BaseModel):
    craft_id: str
    system: Literal["maneuverability", "moves", "shields", "drives", "hyperdrive", "generator", "controls", "weapon", "weapons", "nav_computer", "escape_pods"]
    weapon_id: str | None = None
    asset_value: int = Field(0, ge=0, le=1000000000000)
    assessed_damage: Literal["lightly_damaged", "heavily_damaged", "severely_damaged", "destroyed"] = "lightly_damaged"
    replacement: bool = False
    gm_difficulty: int | None = Field(None, ge=1, le=1000)
    gm_cost: int | None = Field(None, ge=0, le=1000000000000)
    parts_item: str | None = None
    reason: str = Field(min_length=1, max_length=1000)
    expected_updated_at: float | None = None


class D6CraftRepairQuote(BaseModel):
    craft_id: str
    key: str
    skill: str
    difficulty: int
    parts_cost: int
    percent: int | None = None
    fingerprint: str
    notes: list[str] = Field(default_factory=list)
    source: str = "WEG40055 (1992), printed pp.87–91; repair modifiers are GM rulings."


class D6CraftRepairProject(BaseModel):
    id: str = Field(default_factory=lambda: f"repair_{uuid.uuid4().hex[:12]}")
    request: D6CraftRepairRequest
    quote: D6CraftRepairQuote
    paid_credits: int = 0
    parts_source: str = "credits"
    status: Literal["pending", "completed", "cancelled"] = "pending"
    attempts: list[dict] = Field(default_factory=list)


class D6CraftRepairAttempt(BaseModel):
    project_id: str
    actor_id: str | None = None
    minutes: int | None = Field(None, ge=1, le=525600)
    timing_reason: str = Field("", max_length=1000)
    character_points: int = Field(0, ge=0, le=2)
    force_point: bool = False


class D6CraftRepairManage(BaseModel):
    project_id: str
    reason: str = Field(min_length=1, max_length=1000)
