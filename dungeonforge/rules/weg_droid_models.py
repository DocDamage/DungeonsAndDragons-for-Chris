from typing import Literal
from pydantic import BaseModel, Field


class D6DroidWork(BaseModel):
    actor_id: str | None = None
    programmer_id: str | None = None
    operation: Literal["learn", "refine", "task", "wipe", "cartridge", "repair", "attachment"]
    skill: str = ""
    parent_skill: str | None = None
    attribute: str | None = None
    minutes: int = Field(15, ge=15, le=525600)
    reason: str = Field(min_length=1, max_length=1000)
    difficulty: int = Field(20, ge=1, le=1000)
    difficulty_modifier: int = Field(0, ge=0, le=1000)
    roll_bonus: int = Field(0, ge=0, le=1000)
    character_points: int = Field(0, ge=0, le=2)
    force_point: bool = False
    computer_connected: bool = False
    software_available: bool = False
    hardwire: bool = False
    credits: int = Field(0, ge=0, le=1000000)
    cartridge_rating: str = ""
    task: str = Field("", max_length=1000)
    parts_item: str = Field("", max_length=120)
    parts_quantity: int = Field(1, ge=1, le=10000)
    attachment: str = Field("", max_length=300)
