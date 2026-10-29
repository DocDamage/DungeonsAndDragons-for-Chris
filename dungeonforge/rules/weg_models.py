"""Persistent character-scale state for Star Wars WEG Second Edition (1992)."""

import re
from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, Field, field_validator, model_validator
from dungeonforge.rules.weg_force_models import ForceState
from dungeonforge.rules.weg_advancement_models import D6AdvancementState
from dungeonforge.rules.weg_dark_models import CorruptionState
from dungeonforge.rules.weg_reward_models import D6Rewards
from dungeonforge.rules.weg_origin_models import D6DroidState, D6Origin, D6SpeciesContext
from dungeonforge.rules.weg_hazard_models import D6HazardState
from dungeonforge.rules.weg_gear_effect_models import D6GearContext


ATTRIBUTES = ("dexterity", "knowledge", "mechanical", "perception", "strength", "technical")
SKILL_ATTRIBUTES = {
    **dict.fromkeys(("archaic_guns", "blaster_artillery", "bowcaster", "bows", "firearms", "thrown_weapons"), "dexterity"),
    **dict.fromkeys(("business", "law_enforcement"), "knowledge"),
    **dict.fromkeys(("archaic_starship_piloting", "hover_vehicle_operation", "powersuit_operation", "glider"), "mechanical"),
    **dict.fromkeys(("forgery", "investigation"), "perception"),
    **dict.fromkeys(("capital_starship_repair", "capital_starship_weapon_repair", "demolition", "ground_vehicle_repair", "hover_vehicle_repair", "security", "starship_weapon_repair", "walker_repair", "primitive_construction"), "technical"),
    **dict.fromkeys(("agriculture", "ecology"), "knowledge"),
    **dict.fromkeys(("blaster", "dodge", "melee_combat", "melee_parry", "brawling_parry", "grenade", "missile_weapons", "pick_pocket", "lightsaber", "running", "vehicle_blasters"), "dexterity"),
    **dict.fromkeys(("alien_species", "bureaucracy", "cultures", "intimidation", "languages", "planetary_systems", "streetwise", "survival", "tactics", "value", "willpower"), "knowledge"),
    **dict.fromkeys(("astrogation", "beast_riding", "communications", "repulsorlift_operation", "space_transports", "starfighter_piloting", "starship_gunnery", "starship_shields", "sensors", "walker_operation", "capital_ship_piloting", "capital_ship_gunnery", "capital_ship_shields", "swoop_operation", "ground_vehicle_operation"), "mechanical"),
    **dict.fromkeys(("bargain", "command", "con", "gambling", "hide", "search", "sneak", "persuasion"), "perception"),
    **dict.fromkeys(("brawling", "climbing_jumping", "lifting", "stamina", "swimming"), "strength"),
    **dict.fromkeys(("armor_repair", "blaster_repair", "computer_programming_repair", "demolitions", "droid_programming", "droid_repair", "first_aid", "medicine", "repulsorlift_repair", "space_transports_repair", "starfighter_repair"), "technical"),
}
AttributeName = Literal["dexterity", "knowledge", "mechanical", "perception", "strength", "technical"]
WoundLevel = Literal["healthy", "wounded", "incapacitated", "mortally_wounded", "dead"]


def normalize_code(value):
    if not isinstance(value, str):
        raise ValueError("Use a WEG die code such as 3D or 3D+2.")
    code = re.sub(r"\s+", "", value.upper())
    match = re.fullmatch(r"(\d{1,2})D(?:\+([12]))?", code)
    if not match or int(match[1]) > 50:
        raise ValueError("Use 0D to 50D with zero, one, or two pips, such as 3D+2.")
    return f"{int(match[1])}D" + (f"+{match[2]}" if match[2] else "")


DieCode = Annotated[str, BeforeValidator(normalize_code)]


class D6RoundState(BaseModel):
    weapon_shots: dict[str, int] = Field(default_factory=dict)
    bowcaster_blocked: list[str] = Field(default_factory=list)
    declared_actions: int = Field(1, ge=1, le=10)
    actions_taken: int = Field(0, ge=0, le=10)
    force_active: bool = False
    dark_side_called: bool = False
    dark_side_active: bool = False
    character_points_spent: bool = False
    defense_skill: str | None = None
    defense_total: int | None = None
    full_defense: bool = False
    use_defense_roll: bool = True
    blocked: bool = False
    absorb_energy: dict | None = None
    redirect_blaster: dict | None = None
    touched_targets: list[str] = Field(default_factory=list)


class D6CombatPreparation(BaseModel):
    encounter_id: str
    round_number: int
    weapon_id: str
    target_id: str


class D6Character(BaseModel):
    gear_context: D6GearContext = Field(default_factory=D6GearContext)
    combat_preparation: D6CombatPreparation | None = None
    weapon_last_fired: dict[str, int] = Field(default_factory=dict)
    sentient: bool = True
    hazards: D6HazardState = Field(default_factory=D6HazardState)
    vacuum_unconscious: bool = False
    survival_suit: str | None = None
    species_id: str = ""
    species_context: D6SpeciesContext = Field(default_factory=D6SpeciesContext)
    droid: D6DroidState | None = None
    origin: D6Origin = Field(default_factory=D6Origin)
    attributes: dict[AttributeName, DieCode] = Field(default_factory=lambda: dict.fromkeys(ATTRIBUTES, "3D"))
    skills: dict[str, DieCode] = Field(default_factory=dict)
    skill_attributes: dict[str, AttributeName] = Field(default_factory=dict)
    advanced_skills: list[str] = Field(default_factory=lambda: ["medicine"])
    specializations: list[str] = Field(default_factory=list)
    specialization_parents: dict[str, str] = Field(default_factory=dict)
    species_attribute_maximums: dict[AttributeName, DieCode] = Field(default_factory=dict)
    move: int = Field(10, ge=1, le=1000)
    move_maximum: int | None = Field(None, ge=1, le=1000)
    force_skills: dict[Literal["control", "sense", "alter"], DieCode] = Field(default_factory=lambda: {"control": "0D", "sense": "0D", "alter": "0D"})
    force_sensitive: bool = False
    character_points: int = Field(5, ge=0, le=1_000_000)
    force_points: int = Field(1, ge=0, le=1_000_000)
    dark_side_points: int = Field(0, ge=0, le=1_000_000)
    credits: int = Field(250, ge=0)
    armor_energy: DieCode = "0D"
    armor_physical: DieCode = "0D"
    dexterity_penalty: int = Field(0, ge=0, le=50)
    wound: WoundLevel = "healthy"
    stun_count: int = Field(0, ge=0)
    stun_durations: list[Annotated[int, Field(ge=0, le=2)]] = Field(default_factory=list)
    stun_expiries: list[Annotated[int, Field(ge=0, le=360)]] = Field(default_factory=list)
    unconscious_rounds: int = Field(0, ge=0)
    mortal_rounds: int = Field(0, ge=0)
    medpacs_used: int = Field(0, ge=0)
    medpac_blocked: bool = False
    care_elapsed_minutes: int = Field(0, ge=0)
    recovery_days: float = Field(0, ge=0)
    round_state: D6RoundState = Field(default_factory=D6RoundState)
    force: ForceState = Field(default_factory=ForceState)
    advancement: D6AdvancementState = Field(default_factory=D6AdvancementState)
    corruption: CorruptionState = Field(default_factory=CorruptionState)
    rewards: D6Rewards = Field(default_factory=D6Rewards)

    @field_validator("attributes")
    @classmethod
    def all_attributes(cls, value):
        if set(value) != set(ATTRIBUTES):
            raise ValueError("All six WEG attributes are required.")
        return value

    @model_validator(mode="after")
    def skill_metadata(self):
        if self.droid and (self.force_sensitive or any(int(code.split("D")[0]) for code in self.force_skills.values()) or self.force.known_powers):
            raise ValueError("Droids cannot be Force-sensitive or have Force skills or powers.")
        if self.droid and any(int(code.split("D")[0]) * 3 + (int(code[-1]) if '+' in code else 0) > 39 for code in self.skills.values()):
            raise ValueError("Droid skills cannot exceed 13D.")
        if self.rewards.baseline_known and self.rewards.starting_force_points is None:
            self.rewards.starting_force_points = self.force_points
        if any(int(code.split("D")[0]) < 1 for code in self.attributes.values()) and not (self.wound == "dead" and self.corruption.dead):
            raise ValueError("All six WEG attributes require at least 1D, except a saved death caused by a Dark Side drain.")
        for skill in self.skills:
            if skill in SKILL_ATTRIBUTES:
                self.skill_attributes.setdefault(skill, SKILL_ATTRIBUTES[skill])
        for skill in ("control", "sense", "alter"):
            self.force_skills.setdefault(skill, "0D")
        if not self.force_sensitive and any(int(code.split("D")[0]) for code in self.force_skills.values()):
            raise ValueError("Trained Force skills require a Force-sensitive character.")
        return self

    @property
    def can_act(self):
        if self.hazards.exhausted:
            return False
        if self.vacuum_unconscious:
            return False
        if self.droid and self.droid.destroyed:
            return False
        from dungeonforge.rules.weg_force_effects import can_act
        return can_act(self)

    @property
    def can_take_turn(self):
        if self.hazards.exhausted:
            return False
        if self.vacuum_unconscious:
            return False
        if self.droid and self.droid.destroyed:
            return False
        from dungeonforge.rules.weg_force_effects import can_take_turn
        return can_take_turn(self)

    @property
    def out_of_fight(self):
        if self.vacuum_unconscious:
            return True
        if self.droid and self.droid.destroyed:
            return True
        from dungeonforge.rules.weg_force_effects import out_of_fight
        return out_of_fight(self)


class D6Options(BaseModel):
    target_weapon: bool = False
    attack_cover: bool = False
    hit_location: Literal["random", "head", "torso", "left_arm", "right_arm", "left_leg", "right_leg"] | None = None
    called_shot: bool = False
    location_damage: bool = False
    attack_side: Literal["front", "back"] = "front"
    distance_m: float | None = Field(None, ge=0, le=1000000)
    bowcaster_strength_character_points: int = Field(0, ge=0, le=2)
    character_points: int = Field(0, ge=0, le=5)
    resistance_character_points: int = Field(0, ge=0, le=5)
    range_band: Literal["point_blank", "short", "medium", "long"] = "short"
    difficulty: int | None = Field(None, ge=1, le=1000)
    stun: bool = False
    mishap: Literal["penalty", "complication"] = "penalty"
    lightsaber_control_dice: int | None = Field(None, ge=-100, le=100)


class D6DeclareRequest(BaseModel):
    actor_id: str | None = None
    actions: int = Field(1, ge=1, le=10)
    force_point: bool = False


class D6CheckRequest(BaseModel):
    skill: str
    difficulty: int = Field(10, ge=1, le=1000)
    actions: int = Field(1, ge=1, le=10)
    force_point: bool = False
    character_points: int = Field(0, ge=0, le=5)
    mishap: Literal["penalty", "complication"] = "penalty"


class D6DefenseRequest(BaseModel):
    actor_id: str | None = None
    skill: Literal["dodge", "melee_parry", "brawling_parry", "lightsaber"] = "dodge"
    full: bool = False
    use_roll: bool = True
    character_points: int = Field(0, ge=0, le=5)


class D6RecoveryRequest(BaseModel):
    method: Literal["rest", "natural", "medpac"]
    minutes: int = Field(1, ge=1, le=1440)
    days: float = Field(0, ge=0, le=365)
    healer_id: str | None = None


class D6PoolRequest(BaseModel):
    code: DieCode = "3D+2"
    mishap: Literal["penalty", "complication"] = "penalty"


class D6BoostWindow(BaseModel):
    turn_id: str
    actor_id: str
    skill: str
    points_spent: int = 0
    limit: int = 2
    force_used: bool = False
    defensive: bool = False
    encounter_id: str | None = None
    round_number: int | None = None
    total: int = 0


class D6BoostRequest(BaseModel):
    points: int = Field(1, ge=1, le=5)
