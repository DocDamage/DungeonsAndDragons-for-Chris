"""Source catalog transactions, actual personal loadouts and paid equipment work."""
import uuid
from typing import Literal

from pydantic import BaseModel, Field


class EquipmentPurchaseRequest(BaseModel):
    catalog_id: str
    actor_id: str | None = None
    quantity: int = Field(1, ge=1, le=99)
    unit_price: int | None = Field(None, ge=0, le=1_000_000_000_000)
    availability_confirmed: bool = False
    legal_basis: Literal["ordinary", "licensed", "authorized", "black_market"] = "ordinary"
    permit_confirmed: bool = False
    special_acquisition_confirmed: bool = False
    reason: str = Field(min_length=1, max_length=1000)
    expected_updated_at: float | None = None


class EquipmentPurchaseQuote(BaseModel):
    catalog_id: str
    name: str
    quantity: int
    unit_price: int
    total: int
    availability: str
    notes: list[str] = Field(default_factory=list)
    source: str


class EquipmentPurchaseRecord(BaseModel):
    id: str = Field(default_factory=lambda: f"purchase_{uuid.uuid4().hex[:12]}")
    actor_id: str
    quote: EquipmentPurchaseQuote
    inventory_ids: list[str]
    legal_basis: str
    reason: str


class EquipmentLoadoutRequest(BaseModel):
    actor_id: str | None = None
    weapon_id: str | None
    armor_ids: list[str] = Field(max_length=20)
    use_legacy_armor: bool | None = None
    generator_connected: bool | None = None
    reason: str = Field(min_length=1, max_length=1000)
    expected_updated_at: float | None = None


class EquipmentReloadRequest(BaseModel):
    actor_id: str | None = None
    item_id: str
    primary: bool = True
    power: bool = False
    reason: str = Field(min_length=1, max_length=1000)


class EquipmentWorkRequest(BaseModel):
    item_id: str
    operation: Literal["repair", "improve"] = "repair"
    armor_profile: Literal["energy", "physical"] | None = None
    target_pips: int = Field(0, ge=0, le=5)
    asset_value: int | None = Field(None, gt=0, le=1_000_000_000_000)
    gm_difficulty: int | None = Field(None, ge=1, le=1000)
    reason: str = Field(min_length=1, max_length=1000)
    expected_updated_at: float | None = None


class EquipmentWorkQuote(BaseModel):
    item_id: str
    item_name: str
    operation: str
    skill: str
    difficulty: int
    parts_cost: int
    percent: int
    fingerprint: str
    old_value: str | None = None
    new_value: str | None = None
    notes: list[str] = Field(default_factory=list)
    source: str


class EquipmentWorkProject(BaseModel):
    id: str = Field(default_factory=lambda: f"gearwork_{uuid.uuid4().hex[:12]}")
    request: EquipmentWorkRequest
    quote: EquipmentWorkQuote
    paid_credits: int
    status: Literal["pending", "completed", "cancelled"] = "pending"
    attempts: list[dict] = Field(default_factory=list)
    cancellation_reason: str | None = None


class EquipmentWorkAttempt(BaseModel):
    project_id: str
    actor_id: str | None = None
    character_points: int = Field(0, ge=0, le=2)
    force_point: bool = False
    minutes: int | None = Field(None, ge=1, le=525600)
    timing_reason: str = Field("", max_length=1000)


class EquipmentWorkCancel(BaseModel):
    project_id: str
    reason: str = Field(min_length=1, max_length=1000)


class EquipmentArmorBaseline(BaseModel):
    armor_energy: str = "0D"
    armor_physical: str = "0D"
    dexterity_penalty: int = 0


class D6EquipmentState(BaseModel):
    purchases: list[EquipmentPurchaseRecord] = Field(default_factory=list)
    work_projects: list[EquipmentWorkProject] = Field(default_factory=list)
    armor_baselines: dict[str, EquipmentArmorBaseline] = Field(default_factory=dict)
