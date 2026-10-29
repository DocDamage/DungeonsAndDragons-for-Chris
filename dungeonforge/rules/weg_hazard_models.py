"""Saved personal hazards from the 1992 corebook, printed pp.79, 86, 97."""
from typing import Literal
from pydantic import BaseModel, Field


class D6Drowning(BaseModel):
    round: int = 0
    initial_difficulty: int
    rescue_difficulty: int
    attempted_round: int = -1
    declared_round: int = -1


class D6HazardState(BaseModel):
    fatigue_failures: int = 0
    fatigued: bool = False
    exhausted: bool = False
    willpower_driven: bool = False
    exertion_rounds: int = 0
    rest_rounds: int = 0
    drowning: D6Drowning | None = None
    swim_round: int = -1
    history: list[dict] = Field(default_factory=list)


class HazardActor(BaseModel):
    actor_id: str | None = None
    reason: str = Field(min_length=1, max_length=1000)


class HazardPoints(HazardActor):
    character_points: int = Field(0, ge=0, le=2)
    force_point: bool = False


class HazardFall(HazardActor):
    meters: float = Field(gt=0, le=100000)
    standard_gravity: bool = True
    damage_code: str | None = None
    resistance_character_points: int = Field(0, ge=0, le=5)


class HazardExertion(HazardPoints):
    rounds: int = Field(720, ge=1, le=6307200)
    difficulty: int = Field(15, ge=1, le=1000)
    push_with_willpower: bool = False
    willpower_character_points: int = Field(0, ge=0, le=2)
    willpower_difficulty: int | None = Field(None, ge=1, le=1000)
    failure_damage_margin: int | None = Field(None, ge=0, le=1000)
    gamorrean_retry: bool = False
    retry_character_points: int = Field(0, ge=0, le=2)


class HazardRest(HazardActor):
    rounds: int = Field(720, ge=1, le=6307200)


class HazardSwim(HazardPoints):
    difficulty: int = Field(10, ge=1, le=1000)
    actions: int = Field(1, ge=1, le=10)
    breathing_risk: bool = True
    rescue_difficulty: int | None = Field(None, ge=1, le=1000)


class HazardDrowningAction(HazardPoints):
    action: Literal["swim", "other", "pass", "rescued"]
    skill: str = "search"
    difficulty: int = Field(10, ge=1, le=1000)
    actions: int = Field(1, ge=1, le=10)


class HazardNext(BaseModel):
    reason: str = Field(min_length=1, max_length=1000)
