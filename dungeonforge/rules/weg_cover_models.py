"""Saved physical cover objects and explicit GM battlefield facts (1992 p.63)."""
import uuid
from typing import Literal
from pydantic import BaseModel, Field
from dungeonforge.rules.weg_models import DieCode


class D6CoverObject(BaseModel):
    id: str = Field(default_factory=lambda: f"cover_{uuid.uuid4().hex[:12]}")
    name: str = Field(min_length=1, max_length=120)
    body: DieCode
    damage_state: Literal["intact", "lightly_damaged", "heavily_damaged", "severely_damaged", "destroyed"] = "intact"
    reason: str = Field(min_length=1, max_length=2000)


class D6CoverFacts(BaseModel):
    target_id: str
    concealment_dice: Literal[0, 1, 2, 4] = 0
    fraction: Literal["none", "quarter", "half", "three_quarters", "full"] = "none"
    object_id: str | None = None
    new_name: str | None = Field(None, min_length=1, max_length=120)
    new_body: DieCode | None = None
    reason: str = Field(min_length=1, max_length=2000)
    expected_updated_at: float
