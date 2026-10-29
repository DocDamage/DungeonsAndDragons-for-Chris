"""Species traits, creation provenance and Droid identity saved with native sheets."""
from typing import Literal
from pydantic import BaseModel, Field
from dungeonforge.rules.weg_custom_species_models import D6CustomSpecies


class D6SpeciesContext(BaseModel):
    environment: Literal["neutral", "moist", "dry"] = "neutral"
    scent_tracking: bool = False
    climbing_claws: bool = False
    enhanced_senses: bool = False
    familiar_destination: bool = False
    berserk: bool = False
    heavy_grasper: bool = False
    long_range_sensor: bool = False
    moving_target_sensor: bool = False
    target_distance_m: float = Field(0, ge=0, le=1000000)
    visited_locations: list[str] = Field(default_factory=list)


class D6DroidState(BaseModel):
    model: str
    owner: str = ""
    degree: int = Field(ge=1, le=5)
    equipment: list[str] = Field(default_factory=list)
    hardwired_skills: dict[str, str] = Field(default_factory=dict)
    hardwired_specializations: dict[str, str] = Field(default_factory=dict)
    tasks: list[str] = Field(default_factory=list)
    memory_wipes: int = 0
    destroyed: bool = False
    repair_attempts: int = 0
    work_history: list[dict] = Field(default_factory=list)
    route_memory: list[dict] = Field(default_factory=list)


class D6Origin(BaseModel):
    starting_force_skills: list[Literal["control", "sense", "alter"]] = Field(default_factory=list, max_length=3)
    custom_species: D6CustomSpecies | None = None
    template_id: str = ""
    force_tradition: Literal["standard", "tyia"] = "standard"
    method: str = "GM sheet"
    species_id: str = ""
    attribute_budget: int = 0
    skill_budget: int = 0
    skill_dice: dict[str, int] = Field(default_factory=dict)
    specializations: dict[str, str] = Field(default_factory=dict)
    background: str = ""
    gm_approval: str = ""
    source: str = ""
