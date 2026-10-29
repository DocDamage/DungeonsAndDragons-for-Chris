"""Saved organic treatment and natural recovery, WEG40055 (1992) p.67."""
import uuid
from typing import Literal

from pydantic import BaseModel, Field


class MedicalRequest(BaseModel):
    patient_id: str
    reason: str = Field(min_length=1, max_length=1000)
    expected_updated_at: float


class BactaStart(MedicalRequest):
    operator_id: str
    setup_minutes: int = Field(ge=1, le=1440)
    facility: str = Field(min_length=1, max_length=300)
    tank_confirmed: bool = False
    legal_basis: Literal["licensed", "gm_exception"] = "licensed"
    permission_confirmed: bool = False
    untrained_skill: Literal["first_aid", "technical"] = "first_aid"
    difficulty: int | None = Field(None, ge=1, le=1000)
    character_points: int = Field(0, ge=0, le=2)
    force_point: bool = False
    medicine_item_id: str | None = None
    medicine_quantity: int = Field(1, ge=1, le=999)
    medicine_confirmed: bool = False
    medicine_bonus_dice: int = Field(0, ge=0, le=10)
    medicine_facts: str = Field("", max_length=1000)


class NaturalCareStart(MedicalRequest):
    mode: Literal["rest", "easy", "work"] = "rest"
    medicine_item_id: str | None = None
    medicine_quantity: int = Field(1, ge=1, le=999)
    medicine_confirmed: bool = False
    medicine_bonus_dice: int = Field(0, ge=0, le=10)
    medicine_time_factor: float = Field(1, ge=0.01, le=1)
    strong_medicine_confirmed: bool = False
    medicine_facts: str = Field("", max_length=1000)


class MedicalAdvance(BaseModel):
    rounds: int = Field(ge=1, le=6_307_200)
    reason: str = Field(min_length=1, max_length=1000)
    expected_updated_at: float


class MedicalProjectRequest(BaseModel):
    project_id: str
    reason: str = Field(min_length=1, max_length=1000)
    expected_updated_at: float


class MedicalProject(BaseModel):
    id: str = Field(default_factory=lambda: f"medical_{uuid.uuid4().hex[:12]}")
    kind: Literal["bacta", "natural"]
    patient_id: str
    initial_wound: Literal["wounded", "incapacitated", "mortally_wounded"]
    status: Literal["active", "ready", "completed", "failed", "interrupted", "cancelled"] = "active"
    reason: str
    required_rounds: int = Field(0, ge=0)
    elapsed_rounds: int = Field(0, ge=0)
    remaining_rounds: int = Field(0, ge=0)
    operator_id: str | None = None
    facility: str = ""
    tank_confirmed: bool = False
    legal_basis: str = ""
    permission_confirmed: bool = False
    skill: str | None = None
    difficulty: int | None = None
    trained: bool = False
    character_points: int = 0
    force_point: bool = False
    setup_minutes: int = 0
    treatment_roll: dict | None = None
    duration_roll: dict | None = None
    care_mode: Literal["rest", "easy", "work"] | None = None
    medicine: dict = Field(default_factory=dict)
    observed_injury: dict = Field(default_factory=dict)
    outcome: str = ""
    history: list[dict] = Field(default_factory=list)
    source: str = "WEG40055 (1992), printed p.67."


class D6MedicalState(BaseModel):
    projects: list[MedicalProject] = Field(default_factory=list)
    history: list[dict] = Field(default_factory=list)
