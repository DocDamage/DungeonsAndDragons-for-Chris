from pydantic import BaseModel, Field, StrictInt
from dungeonforge.rules.weg_models import DieCode
from dungeonforge.rules.weg_custom_species_models import D6CustomSpecies


class D6SpecializationChoice(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    parent: str = Field(min_length=1, max_length=100)


class D6CreationRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    occupation: str = Field(min_length=1, max_length=120)
    species_id: str = "human"
    custom_species: D6CustomSpecies | None = None
    droid_model: str | None = None
    owner: str = Field("", max_length=120)
    attributes: dict[str, DieCode] = Field(default_factory=dict)
    skill_dice: dict[str, StrictInt] = Field(default_factory=dict)
    skill_attributes: dict[str, str] = Field(default_factory=dict)
    specializations: list[D6SpecializationChoice] = Field(default_factory=list, max_length=3)
    force_skills: list[str] = Field(default_factory=list, max_length=3)
    force_sensitive: bool = False
    powers: list[str] = Field(default_factory=list, max_length=22)
    force_background: str = Field("", max_length=2000)
    background: str = Field("", max_length=4000)
    gm_approval: str = Field(min_length=1, max_length=2000)
    equipment: list[str] = Field(default_factory=list, max_length=30)
    credits: int = Field(250, ge=0, le=1000000)
    include_medic: bool = True
    expected_updated_at: float | None = None
