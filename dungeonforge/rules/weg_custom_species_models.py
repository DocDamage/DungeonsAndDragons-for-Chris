"""GM-authored species records; numeric limits are explicit, never inferred from prose."""
import re
import uuid

from pydantic import BaseModel, Field, StrictInt, field_validator, model_validator


ATTRIBUTES = ("dexterity", "knowledge", "mechanical", "perception", "strength", "technical")
SOURCE = "WEG40055 (1992), printed pp.15–17 / PDF pp.16–18: Designing Your Own Template; New Alien Species."


def code_pips(value):
    match = re.fullmatch(r"(\d{1,2})D(?:\+([12]))?", value)
    return int(match[1]) * 3 + int(match[2] or 0)


class D6CustomSpecies(BaseModel):
    model_config = {"extra": "forbid"}
    id: str = Field(default_factory=lambda: f"custom_{uuid.uuid4().hex[:12]}", pattern=r"^custom_[a-z0-9_]{1,64}$")
    name: str = Field(min_length=1, max_length=120)
    average_attribute_dice: StrictInt = Field(ge=0)
    minimums: dict[str, str]
    maximums: dict[str, str]
    move: StrictInt = Field(ge=1, le=1000)
    move_maximum: StrictInt = Field(ge=1, le=1000)
    concept: str = Field(min_length=1, max_length=2000)
    biology: str = Field(min_length=1, max_length=2000)
    breathing_needs: str = Field(min_length=1, max_length=2000)
    culture: str = Field(min_length=1, max_length=2000)
    special_abilities: str = Field(min_length=1, max_length=2000)
    disadvantages: str = Field(min_length=1, max_length=2000)
    story_factors: str = Field(min_length=1, max_length=2000)
    gm_rationale: str = Field(min_length=1, max_length=2000)
    source: str = Field(min_length=1, max_length=1000)

    @field_validator("name", "concept", "biology", "breathing_needs", "culture", "special_abilities", "disadvantages", "story_factors", "gm_rationale", "source")
    @classmethod
    def actual_text(cls, value):
        if not value.strip():
            raise ValueError("Record the actual species details and GM balance ruling; explicitly state when none apply.")
        return value.strip()

    @field_validator("minimums", "maximums")
    @classmethod
    def six_bounds(cls, values):
        if set(values) != set(ATTRIBUTES):
            raise ValueError("Record exactly all six species attribute limits.")
        normalized = {}
        for key, value in values.items():
            value = re.sub(r"\s+", "", value.upper())
            if not re.fullmatch(r"\d{1,2}D(?:\+[12])?", value) or int(value.split("D")[0]) > 50:
                raise ValueError("Species limits must use native 0D to 50D codes with zero, one or two pips.")
            normalized[key] = value
        return normalized

    @model_validator(mode="after")
    def coherent_limits(self):
        if any(code_pips(self.minimums[key]) > code_pips(self.maximums[key]) for key in ATTRIBUTES):
            raise ValueError("Each species minimum must be at most its maximum.")
        budget = (self.average_attribute_dice + 6) * 3
        if not sum(map(code_pips, self.minimums.values())) <= budget <= sum(map(code_pips, self.maximums.values())):
            raise ValueError("The six species bounds must fit the exact average + 6D player attribute budget.")
        if self.move > self.move_maximum:
            raise ValueError("Starting Move cannot exceed the species maximum Move.")
        return self
