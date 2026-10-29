"""Serializable Force activation, upkeep, and special recovery state (WEG 1992)."""

import uuid
from typing import Any, Literal

from pydantic import BaseModel, Field

from dungeonforge.rules.dice import RollResult


ForceSkill = Literal["control", "sense", "alter"]
Relationship = Literal["close_relative", "close_friend", "friend", "acquaintance", "slight_acquaintance", "met_once", "reputation", "stranger", "alien_stranger"]
Proximity = Literal["touching", "line_of_sight", "hidden_nearby", "nearby_km", "regional", "same_planet", "same_system", "different_system"]


class ForceSkillRoll(BaseModel):
    skill: str
    difficulty: int
    success: bool
    roll: RollResult
    character_points: int = 0
    opposition: RollResult | None = None


class ForceEffect(BaseModel):
    id: str = Field(default_factory=lambda: f"force_{uuid.uuid4().hex[:12]}")
    power_id: str
    source_id: str
    target_id: str | None = None
    skills: list[ForceSkill] = Field(default_factory=list)
    maintained: bool = False
    recipient: bool = False
    activation_round: bool = True
    ready_in_rounds: int = 0
    rounds_remaining: int | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)


class ForceAttempt(BaseModel):
    id: str = Field(default_factory=lambda: f"activation_{uuid.uuid4().hex[:12]}")
    power_id: str
    source_id: str
    target_id: str | None = None
    skills: list[ForceSkill]
    parameters: dict[str, Any] = Field(default_factory=dict)
    rolls: list[ForceSkillRoll] = Field(default_factory=list)
    preparation_remaining: int = 0
    preparation_committed: bool = False
    failed: bool = False
    dark_side_awarded: bool = False


class ForceState(BaseModel):
    known_powers: list[str] = Field(default_factory=list)
    effects: list[ForceEffect] = Field(default_factory=list)
    attempt: ForceAttempt | None = None
    saber_locked: bool = False
    reduce_injury_available: bool = False
    remain_pending: bool = False
    remain_actions: int | None = None
    elapsed_rounds: int = 0
    healing_day: int = -1
    healing_rolls_remaining: int = 0
    healing_rolls_used: int = 0
    permanent_injuries: list[str] = Field(default_factory=list)
    heroic_force_returns: int = 0
    dark_side_consumed: bool = False


class ForcePowerRequest(BaseModel):
    actor_id: str | None = None
    power_id: str
    target_id: str | None = None
    keep_up: bool = False
    same_round: bool = True
    actions: int = Field(1, ge=1, le=10)
    force_point: bool = False
    character_points: int = Field(0, ge=0, le=5)
    mishap: Literal["penalty", "complication"] = "penalty"
    base_difficulties: dict[ForceSkill, int] = Field(default_factory=dict)
    tyia_alter_difficulty: int | None = Field(None, ge=1, le=1000)
    relationship: Relationship = "stranger"
    proximity: Proximity = "line_of_sight"
    willing: bool = True
    resistance_total: int | None = Field(None, ge=0, le=10000)
    resistance_skill: Literal["auto", "control", "perception"] = "auto"
    target_is_droid: bool = False
    profile: str = ""
    mass_kg: float = Field(1, gt=0, le=100000)
    speed_m_per_round: float = Field(10, ge=0, le=10000)
    maneuver_modifier: int = Field(0, ge=0, le=1000)
    in_sight: bool = True
    quiet: bool = False
    quiet_modifier: int = Field(5, ge=5, le=10)
    description: str = Field("", max_length=2000)
    duration_rounds: int = Field(12, ge=1, le=725760)
    permanent_injury: str = Field("", max_length=240)
    distance_m: float = Field(10, ge=0, le=1000000)


class ForceContinueRequest(BaseModel):
    actor_id: str | None = None
    character_points: int = Field(0, ge=0, le=5)
    mishap: Literal["penalty", "complication"] = "penalty"
    actions: int = Field(1, ge=1, le=10)
    force_point: bool = False


class ForceManageRequest(BaseModel):
    actor_id: str | None = None
    effect_id: str | None = None
    action: Literal["cancel", "drop", "wake", "leave_emptiness", "heal", "advance"]
    rounds: int = Field(1, ge=1, le=725760)
    character_points: int = Field(0, ge=0, le=2)
    stimulus: bool = False


class ForceReactionRequest(BaseModel):
    actor_id: str | None = None
    action: Literal["absorb_energy", "redirect_blaster"]
    attacker_id: str | None = None
    target_id: str | None = None
    range_band: Literal["point_blank", "short", "medium", "long"] = "short"
    difficulty: int | None = Field(None, ge=1, le=1000)
    character_points: int = Field(0, ge=0, le=5)
    mishap: Literal["penalty", "complication"] = "penalty"


class ForceBoostWindow(BaseModel):
    actor_id: str
    turn_id: str
    attempt_id: str
    points_spent: int
    limit: int = 2
    force_used: bool = False


class ForceTargetRequest(BaseModel):
    actor_id: str | None = None
    target_id: str
    effect_id: str | None = None
    character_points: int = Field(0, ge=0, le=2)
    mishap: Literal["penalty", "complication"] = "penalty"
