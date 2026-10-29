"""Native 1992 WEG craft, crew stations, and persistent system damage."""

import uuid
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from dungeonforge.rules.dice import RollResult
from dungeonforge.rules.weg_models import D6Character, DieCode
from dungeonforge.rules.weg_engineering_models import D6CraftRepairProject


Scale = Literal["character", "speeder", "walker", "starfighter", "capital", "death_star"]
Arc = Literal["front", "back", "left", "right"]
CraftDamage = Literal["intact", "lightly_damaged", "heavily_damaged", "severely_damaged", "destroyed"]


class D6Crew(BaseModel):
    id: str
    name: str
    character_id: str | None = None
    stations: list[Literal["pilot", "gunner", "shields", "engineer"]] = Field(default_factory=list)
    d6: D6Character = Field(default_factory=D6Character)
    control_penalty: int = Field(0, ge=0)
    next_control_penalty: int = Field(0, ge=0)
    evacuated: bool = False


class D6VehicleWeapon(BaseModel):
    id: str
    name: str
    system: str = "laser"
    skill: str = "starship_gunnery"
    scale: Scale | None = None
    arcs: list[Arc] = Field(default_factory=lambda: ["front"])
    fire_control: DieCode = "0D"
    damage: DieCode = "4D"
    kind: Literal["energy", "ion", "missile", "tractor"] = "energy"
    # [minimum short range, end of short, medium, long], in space units/meters.
    space_ranges: tuple[float, float, float, float] = (1, 3, 12, 25)
    atmosphere_ranges: tuple[float, float, float, float] = (100, 300, 1200, 2500)
    operator_id: str | None = None  # None: pilot operated
    pilot_operated: bool = True
    ammo: int | None = Field(None, ge=0)
    status: Literal["operational", "disabled", "destroyed"] = "operational"
    repair_damage: Literal["intact", "lightly_damaged", "heavily_damaged", "severely_damaged", "destroyed"] = "intact"
    purchase_value: int = Field(0, ge=0, le=1000000000000)

    @model_validator(mode="after")
    def weapon_valid(self):
        if not self.arcs or len(set(self.arcs)) != len(self.arcs):
            raise ValueError("A weapon needs distinct fire arcs.")
        for ranges in (self.space_ranges, self.atmosphere_ranges):
            if ranges[0] < 0 or any(a > b for a, b in zip(ranges, ranges[1:])) or ranges[-1] <= 0:
                raise ValueError("Weapon ranges must increase from minimum to long range.")
        if int(self.damage.split("D")[0]) < 1:
            raise ValueError("A craft weapon needs at least 1D damage/tractor strength.")
        return self


class D6Vehicle(BaseModel):
    id: str = Field(default_factory=lambda: f"craft_{uuid.uuid4().hex[:12]}")
    name: str = Field(min_length=1, max_length=120)
    kind: Literal["vehicle", "starship"] = "starship"
    scale: Scale = "starfighter"
    is_player: bool = True
    occupied: bool = True
    piloting_skill: str = "space_transports"
    hull: DieCode = "4D"
    maneuverability: DieCode = "0D"
    shields: DieCode = "0D"
    space_move: float = Field(4, ge=0, le=10000)
    atmosphere_move: float = Field(280, ge=0, le=100000)
    airborne: bool = False
    altitude: float = Field(0, ge=0, le=1000000)
    crew: list[D6Crew] = Field(default_factory=list)
    weapons: list[D6VehicleWeapon] = Field(default_factory=list)
    source: str = "Custom craft; GM statistics"
    purchase_value: int = Field(0, ge=0, le=1000000000000)
    hyperdrive_multiplier: float | None = Field(None, gt=0, le=1000)
    backup_hyperdrive: float | None = Field(None, gt=0, le=1000)
    nav_computer: bool = False
    nav_computer_disabled: bool = False
    escape_pods_disabled: bool = False
    hull_breached: bool = False
    location: str = Field("", max_length=120)
    repair_projects: list[D6CraftRepairProject] = Field(default_factory=list)
    damage: CraftDamage = "intact"
    maneuverability_lost: int = Field(0, ge=0)
    shields_lost: int = Field(0, ge=0)
    speed_losses: int = Field(0, ge=0, le=6)
    ion_durations: list[int] = Field(default_factory=list)
    frozen_rounds: int = Field(0, ge=0)
    forced_moves: int = Field(0, ge=0, le=4)
    forced_half_speed: bool = False
    controls_dead: bool = False
    drives_disabled: bool = False
    weapons_disabled: bool = False
    hyperdrive_disabled: bool = False
    particle_shields: bool = True
    destruction_countdown: int | None = Field(None, ge=0, le=6)
    destruction_cause: Literal["generator", "structure"] | None = None
    generator_shutdown: bool = False
    shield_allocation: dict[Arc, DieCode] = Field(default_factory=dict)
    shields_rolled: bool = False
    dodge_roll: RollResult | None = None
    full_dodge: bool = False
    declared_moves: int = Field(0, ge=0, le=4)
    half_speed: bool = False
    moves_taken: int = Field(0, ge=0, le=4)
    distance_moved: float = Field(0, ge=0)
    spin_rounds: int = Field(0, ge=0)
    captured_by: str | None = None
    captured_weapon: str | None = None
    tractor_distance: float = Field(0, ge=0)
    damage_log: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def craft_valid(self):
        if int(self.hull.split("D")[0]) < 1:
            raise ValueError("A craft requires at least 1D hull/body strength.")
        crew_ids = [person.id for person in self.crew]
        weapon_ids = [weapon.id for weapon in self.weapons]
        if len(set(crew_ids)) != len(crew_ids) or len(set(weapon_ids)) != len(weapon_ids):
            raise ValueError("Crew and weapon IDs must be unique within a craft.")
        if self.crew and sum("pilot" in person.stations for person in self.crew) != 1:
            raise ValueError("Assign exactly one pilot station per craft.")
        for weapon in self.weapons:
            if weapon.operator_id is not None and weapon.operator_id not in crew_ids:
                raise ValueError("Weapon operator must be aboard this craft.")
        return self

    @property
    def max_moves(self):
        return 0 if self.drives_disabled or self.generator_shutdown else max(0, 4 - self.speed_losses)

    @property
    def half_speed_only(self):
        return not self.drives_disabled and not self.generator_shutdown and self.speed_losses == 4

    @property
    def out_of_fight(self):
        return self.damage == "destroyed" or self.controls_dead or self.generator_shutdown or not any(not person.d6.out_of_fight and not person.evacuated for person in self.crew)


class D6VehicleEncounter(BaseModel):
    id: str = Field(default_factory=lambda: f"flight_{uuid.uuid4().hex[:12]}")
    active: bool = True
    environment: Literal["space", "atmosphere"] = "space"
    round: int = 1
    craft: list[D6Vehicle] = Field(default_factory=list)
    actor_order: list[str] = Field(default_factory=list)
    current_turn_index: int = 0
    turn_acted: bool = False
    actions_started: bool = False
    initiative_winner: bool = True
    initiative: dict[str, int] = Field(default_factory=dict)
    combat_log: list[str] = Field(default_factory=list)
    boost: "D6VehicleBoostWindow | None" = None


class D6VehicleBoostWindow(BaseModel):
    actor_id: str
    turn_id: str
    kind: Literal["dodge", "shields"]
    points_spent: int = 0
    force_used: bool = False
    allocation: dict[Arc, DieCode] = Field(default_factory=dict)


D6VehicleEncounter.model_rebuild()


class D6FleetAddRequest(BaseModel):
    preset: str


class D6VehicleStartRequest(BaseModel):
    vehicle_id: str
    enemies: list[str] = Field(default_factory=lambda: ["tie_fighter"], min_length=1, max_length=8)
    environment: Literal["space", "atmosphere"] = "space"


class D6VehicleDeclareRequest(BaseModel):
    actor_id: str
    actions: int = Field(1, ge=1, le=10)
    force_point: bool = False
    moves: int = Field(0, ge=0, le=4)
    half_speed: bool = False


class D6VehicleRollRequest(BaseModel):
    actor_id: str
    character_points: int = Field(0, ge=0, le=5)
    mishap: Literal["penalty", "complication"] = "penalty"


class D6VehicleDodgeRequest(D6VehicleRollRequest):
    full: bool = False


class D6VehicleShieldRequest(D6VehicleRollRequest):
    allocation: dict[Arc, DieCode]
    difficulty: int | None = Field(None, ge=1, le=1000)


class D6VehicleAttackRequest(D6VehicleRollRequest):
    target_id: str
    weapon_id: str
    distance: float = Field(3, ge=0, le=1000000)
    fire_arc: Arc = "front"
    incoming_arc: Arc = "front"
    difficulty: int | None = Field(None, ge=1, le=1000)
    passenger_damage: bool = True


class D6VehicleMoveRequest(D6VehicleRollRequest):
    terrain_difficulty: int = Field(10, ge=1, le=1000)
    maneuver_modifier: int = Field(0, ge=0, le=1000)
    ram_target_id: str | None = None
    sideswipe: bool = False
    passenger_damage: bool = True
    collision_angle: Literal["obstacle", "head_on", "rear_ender", "t_bone"] = "obstacle"


class D6VehicleSystemRequest(BaseModel):
    actor_id: str
    action: Literal["shutdown_generator", "escape_tractor", "pull_tractor", "release_tractor", "evacuate"]
    target_id: str | None = None
