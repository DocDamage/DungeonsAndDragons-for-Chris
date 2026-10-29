"""Saved actual grenade positions, scatter, timers and three-action tosses."""
import uuid
from typing import Literal

from pydantic import BaseModel, Field, model_validator
from dungeonforge.rules.dice import RollResult


Location = Literal["head", "torso", "left_arm", "right_arm", "left_leg", "right_leg"]


class D6BlastPoint(BaseModel):
    model_config = {"extra": "forbid", "allow_inf_nan": False}
    x: float = Field(ge=-1_000_000, le=1_000_000)
    y: float = Field(ge=-1_000_000, le=1_000_000)


class D6BlastPosition(BaseModel):
    model_config = {"extra": "forbid"}
    actor_id: str
    point: D6BlastPoint
    hit_location: Location | None = None
    side: Literal["front", "back"]
    resistance_character_points: int = Field(0, ge=0, le=5)


class ExplosiveRequest(BaseModel):
    model_config = {"extra": "forbid"}
    reason: str = Field(min_length=1, max_length=1500)
    expected_updated_at: float


class D6BlastPositionsRequest(ExplosiveRequest):
    positions: list[D6BlastPosition] = Field(min_length=1, max_length=200)
    all_scene_actors_confirmed: bool = False
    same_plane_unobstructed_confirmed: bool = False
    independent_damage_rolls_confirmed: bool = False
    distance_rounding: Literal["up", "down"]


class D6GrenadeThrowRequest(ExplosiveRequest):
    actor_id: str
    item_id: str
    target: D6BlastPoint
    heading: D6BlastPoint | None = None
    trigger: Literal["contact", "timer"]
    timer_seconds: float | None = Field(None, gt=0, le=86400)
    timer_rounding_confirmed: bool = False
    visible_landing: bool = True
    unseen_modifier: int | None = Field(None, ge=5, le=10)
    character_points: int = Field(0, ge=0, le=5)
    mishap: Literal["penalty", "complication"] = "penalty"

    @model_validator(mode="after")
    def actual_fuse(self):
        if self.trigger == "timer" and (self.timer_seconds is None or not self.timer_rounding_confirmed):
            raise ValueError("Record actual timer seconds and confirm the saved five-second round-boundary convention.")
        if self.trigger == "contact" and self.timer_seconds is not None:
            raise ValueError("A contact grenade detonates immediately; it has no saved timer.")
        return self


class D6GrenadeIntentRequest(ExplosiveRequest):
    actor_id: str


class D6GrenadeStepRequest(ExplosiveRequest):
    actor_id: str
    grenade_id: str
    clear_path_confirmed: bool = False


class D6GrenadeRethrowRequest(D6GrenadeStepRequest):
    target: D6BlastPoint
    heading: D6BlastPoint | None = None
    visible_landing: bool = True
    unseen_modifier: int | None = Field(None, ge=5, le=10)
    character_points: int = Field(0, ge=0, le=5)
    mishap: Literal["penalty", "complication"] = "penalty"
    throw_as_far: bool = False
    lowered_difficulty: int | None = Field(None, ge=1, le=1000)
    far_throw_ruling: str = Field("", max_length=1000)


class D6GrenadeThrowRecord(BaseModel):
    actor_id: str
    name: str
    round: int
    origin: D6BlastPoint
    target: D6BlastPoint
    distance: float
    range_band: str
    difficulty: int
    roll: RollResult
    success: bool
    character_points: int = 0
    force_point_active: bool = False
    scatter_direction: RollResult | None = None
    scatter_distance: RollResult | None = None
    landing: D6BlastPoint
    rethrow: bool = False
    reason: str
    positions: dict[str, D6BlastPosition] = Field(default_factory=dict)


class D6BlastVictim(BaseModel):
    actor_id: str
    name: str
    point: D6BlastPoint
    distance: float
    blast_distance: int
    affected: bool
    damage_code: str | None = None
    damage_roll: RollResult | None = None
    resistance_roll: RollResult | None = None
    character_points: int = 0
    point_note: str = ""
    hit_location: Location | None = None
    side: str
    margin: int | None = None
    before: str
    after: str
    injury: str | None = None
    armor_damage: dict | None = None


class D6GrenadeRecord(BaseModel):
    id: str = Field(default_factory=lambda: f"grenade_{uuid.uuid4().hex[:12]}")
    item_id: str
    catalog_id: Literal["fragmentation_grenade", "thermal_detonator"]
    name: str
    source: str
    created_round: int
    trigger: Literal["contact", "timer"]
    timer_seconds: float | None = None
    due_round: int
    position: D6BlastPoint
    holder_id: str | None = None
    status: Literal["armed", "resolved"] = "armed"
    item_snapshot: dict
    throws: list[D6GrenadeThrowRecord] = Field(default_factory=list)
    victims: list[D6BlastVictim] = Field(default_factory=list)
    resolved_round: int | None = None
    reason: str
    distance_rounding: Literal["up", "down"] = "up"
    position_reason: str = ""


class D6GrenadeIntent(BaseModel):
    actor_id: str
    declared_round: int
    stage: Literal["declared", "approached", "grabbed", "thrown"] = "declared"
    grenade_id: str | None = None
    actions: list[dict] = Field(default_factory=list)
    reason: str


class D6ExplosivesState(BaseModel):
    positions: dict[str, D6BlastPosition] = Field(default_factory=dict)
    position_round: int = 0
    position_reason: str = ""
    all_scene_actors_confirmed: bool = False
    same_plane_unobstructed_confirmed: bool = False
    independent_damage_rolls_confirmed: bool = False
    distance_rounding: Literal["up", "down"] = "up"
    grenades: list[D6GrenadeRecord] = Field(default_factory=list)
    intents: list[D6GrenadeIntent] = Field(default_factory=list)
    history: list[dict] = Field(default_factory=list)
