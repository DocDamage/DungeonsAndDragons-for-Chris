from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any, Literal
import uuid
from pydantic import BaseModel, Field
from dungeonforge.rules.dice import RollResult
from dungeonforge.rules.weg_models import D6Character, DieCode
from dungeonforge.rules.weg_force_models import ForceSkillRoll


class AbilityScores(BaseModel):
    strength: int = Field(default=10, alias="str")
    dexterity: int = Field(default=10, alias="dex")
    constitution: int = Field(default=10, alias="con")
    intelligence: int = Field(default=10, alias="int")
    wisdom: int = Field(default=10, alias="wis")
    charisma: int = Field(default=10, alias="cha")

    model_config = {"populate_by_name": True}

    @property
    def str(self) -> int:
        return self.strength

    @property
    def dex(self) -> int:
        return self.dexterity

    @property
    def con(self) -> int:
        return self.constitution

    @property
    def int(self) -> int:
        return self.intelligence

    @property
    def wis(self) -> int:
        return self.wisdom

    @property
    def cha(self) -> int:
        return self.charisma

    def modifier(self, ability: str) -> int:
        """Standard 3.5e / 5e modifier: (score - 10) // 2"""
        norm = ability.lower()[:3]
        score = getattr(self, norm, 10)
        return (score - 10) // 2


class Item(BaseModel):
    id: str = Field(default_factory=lambda: f"item_{uuid.uuid4().hex[:12]}")
    name: str
    quantity: int = 1
    item_type: str = "misc"  # weapon, armor, potion, scroll, wondrous, quest
    damage: Optional[str] = None  # e.g. "1d8+2"
    ac_bonus: Optional[int] = None
    equipped: bool = False
    description: str = ""
    d6_skill: Optional[str] = None
    d6_difficulty: Optional[int] = Field(None, ge=1, le=1000)
    damage_type: str = "energy"
    sealed_survival_suit: bool = False
    catalog_id: str | None = None
    unit_cost: int | None = Field(None, ge=0)
    availability: str = ""
    source: str = ""
    equipped_by: str | None = None
    ammo: int | None = Field(None, ge=0)
    ammo_capacity: int | None = Field(None, ge=0)
    ammo_type: str | None = None
    reload_catalog_id: str | None = None
    power_ammo: int | None = Field(None, ge=0)
    power_ammo_capacity: int | None = Field(None, ge=0)
    power_reload_catalog_id: str | None = None
    requires_generator: bool = False
    generator_connected: bool = False
    d6_ranges: tuple[float, float, float, float] | None = None
    d6_damage_max: DieCode | None = None
    d6_fire_rate: float | None = Field(None, gt=0)
    d6_can_stun: bool = False
    stun_mode: bool = False
    d6_scale: Literal["character", "speeder", "walker", "starfighter", "capital", "death_star"] = "character"
    weapon_body: DieCode = "2D"
    weapon_damage_state: Literal["intact", "lightly_damaged", "heavily_damaged", "severely_damaged", "destroyed"] = "intact"
    armor_energy: DieCode | None = None
    armor_physical: DieCode | None = None
    armor_dexterity_penalty: int = Field(0, ge=0, le=50)
    armor_locations: list[Literal["head", "torso", "left_arm", "right_arm", "left_leg", "right_leg"]] = Field(default_factory=list)
    armor_sides: list[Literal["front", "back"]] = Field(default_factory=lambda: ["front", "back"])
    armor_damage_state: Literal["intact", "lightly_damaged", "heavily_damaged", "severely_damaged", "destroyed"] = "intact"
    original_damage: str | None = None
    original_armor_energy: DieCode | None = None
    original_armor_physical: DieCode | None = None
    damage_modification_pips: int = Field(0, ge=0, le=5)
    armor_modification_pips: int = Field(0, ge=0, le=5)


class SpellSlot(BaseModel):
    level: int
    current: int
    max_slots: int


class Companion(BaseModel):
    id: str
    name: str
    race: str = "Human"
    class_name: str = "Fighter"
    level: int = 2
    current_hp: int = 18
    max_hp: int = 18
    ac: int = 14
    attack_name: str = "Shortsword"
    damage: str = "1d6+2"
    avatar_url: Optional[str] = None
    notes: str = ""
    d6: Optional[D6Character] = None
    d6_weapon: Optional[Item] = None


class Character(BaseModel):
    id: str = "player_1"
    name: str = "Adventurer"
    race: str = "Human"
    class_name: str = "Fighter"
    level: int = 1
    alignment: str = "Neutral Good"
    edition: str = "5e"  # "2e", "3.5e", "5e"

    abilities: AbilityScores = Field(default_factory=AbilityScores)

    current_hp: int = 10
    max_hp: int = 10
    temp_hp: int = 0

    ac: int = 10
    speed: int = 30

    # Currency
    gold: int = 50
    silver: int = 0
    copper: int = 0

    # Gear & Magic
    inventory: List[Item] = Field(default_factory=list)
    spell_slots: Dict[str, SpellSlot] = Field(default_factory=dict)
    known_spells: List[str] = Field(default_factory=list)
    companions: List[Companion] = Field(default_factory=list)

    # Status
    conditions: List[str] = Field(default_factory=list)  # Poisoned, Blinded, Blessed, etc.
    death_saves_success: int = 0
    death_saves_failure: int = 0

    # Edition-specific caches
    thac0: Optional[int] = None  # 2e
    bab: Optional[int] = None    # 3.5e
    proficiency_bonus: Optional[int] = None  # 5e

    saving_throws: Dict[str, int] = Field(default_factory=dict)
    skills: Dict[str, int] = Field(default_factory=dict)
    notes: str = ""
    d6: Optional[D6Character] = None


class RuleEvaluationResult(BaseModel):
    action_type: str  # attack, saving_throw, ability_check, skill_check, rest
    success: bool
    is_crit: bool = False
    is_fumble: bool = False
    roll_result: RollResult
    target_value: Optional[int] = None
    damage_dealt: Optional[int] = None
    summary: str
    state_changes: Dict[str, Any] = Field(default_factory=dict)
    damage_roll: Optional[RollResult] = None
    resistance_roll: Optional[RollResult] = None
    wound_result: Optional[str] = None
    force_rolls: List[ForceSkillRoll] = Field(default_factory=list)


class BaseRuleSystem(ABC):
    """Shared interface for deterministic tabletop rules engines."""

    @abstractmethod
    def evaluate_attack(
        self,
        character: Character,
        target_ac: int,
        weapon: Optional[Item] = None,
        advantage: bool = False,
        disadvantage: bool = False,
        bonus_mod: int = 0
    ) -> RuleEvaluationResult:
        pass

    @abstractmethod
    def evaluate_saving_throw(
        self,
        character: Character,
        save_name: str,
        dc: int,
        advantage: bool = False,
        disadvantage: bool = False
    ) -> RuleEvaluationResult:
        pass

    @abstractmethod
    def evaluate_ability_check(
        self,
        character: Character,
        ability: str,
        dc_or_target: int,
        skill_name: Optional[str] = None
    ) -> RuleEvaluationResult:
        pass

    @abstractmethod
    def apply_short_rest(self, character: Character, hit_dice_spent: int = 1) -> Character:
        pass

    @abstractmethod
    def apply_long_rest(self, character: Character) -> Character:
        pass
