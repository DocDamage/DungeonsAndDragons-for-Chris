"""Default-off physical gear facts; authoritative runtime objects never serialize."""
from typing import Any, Literal
import uuid

from pydantic import BaseModel, Field, PrivateAttr

Damage = Literal["intact", "lightly_damaged", "heavily_damaged", "severely_damaged", "destroyed"]


class MacroPreparation(BaseModel):
    actor_id: str = ""
    nonce: str = Field(default_factory=lambda: uuid.uuid4().hex)
    history_index: int = Field(0, ge=0)
    macro_item_id: str
    weapon_id: str
    target_id: str
    encounter_id: str | None = None
    round_number: int | None = None
    completed_elapsed_round: int


class GearFacts(BaseModel):
    powersuit_id: str | None = None
    powersuit_functional: bool = False
    mftas_id: str | None = None
    mftas_functional: bool = False
    macro_item_id: str | None = None
    macro_functional: bool = False
    macro_mode: Literal["off", "view", "linked"] = "off"
    macro_model_range_m: float = Field(1000, gt=0, le=1_000_000)
    visual_task_confirmed: bool = False
    visual_skill: str = "search"
    visibility_obscured: bool = False
    target_id: str = Field("", max_length=300)
    view_distance_m: float | None = Field(None, ge=0, le=1_000_000)
    target_movement_m: float = Field(0, ge=0, le=1_000_000)
    linked_weapon_id: str | None = None
    software_confirmed: bool = False
    software_facts: str = Field("", max_length=1000)
    steady_rest: bool = False
    position_maintained: bool = False
    reason: str = Field("", max_length=1000)


class D6GearContext(GearFacts):
    powersuit_reviewed_damage: Damage | None = None
    mftas_reviewed_damage: Damage | None = None
    macro_reviewed_damage: Damage | None = None
    observed_history_index: int | None = None
    observed_encounter_id: str | None = None
    observed_round: int | None = None
    preparation: MacroPreparation | None = None
    history: list[dict] = Field(default_factory=list)
    _inventory: list[Any] = PrivateAttr(default_factory=list)
    _actor_id: str = PrivateAttr("")
    _session_id: str = PrivateAttr("")
    _weapon_id: str | None = PrivateAttr(None)
    _encounter_id: str | None = PrivateAttr(None)
    _round: int | None = PrivateAttr(None)
    _history_index: int = PrivateAttr(-1)
    _scope: dict | None = PrivateAttr(None)
    _preparation_verified: bool = PrivateAttr(False)


class GearFactsRequest(GearFacts):
    actor_id: str
    expected_updated_at: float


class GearPrepareRequest(BaseModel):
    actor_id: str
    target_id: str
    reason: str = Field(min_length=1, max_length=1000)
    expected_updated_at: float
