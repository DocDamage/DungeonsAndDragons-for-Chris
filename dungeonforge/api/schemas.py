from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field
from dungeonforge.rules.base import Character, Item
from dungeonforge.context.story_cards import StoryCard
from dungeonforge.rules.weg_models import D6Options


class ActionRequest(BaseModel):
    mode: str = "do"  # "do", "say", "story", "attack", "check", "rest"
    text: str
    target_ac: Optional[int] = None
    target_dc: Optional[int] = None
    weapon_name: Optional[str] = None
    ability_or_skill: Optional[str] = None
    advantage: bool = False
    disadvantage: bool = False


class AlterTurnRequest(BaseModel):
    turn_id: str
    new_text: str


class RollDiceRequest(BaseModel):
    expression: str = "1d20"


class ConfigLLMRequest(BaseModel):
    provider: str = "mock"  # "mock", "ollama", "openai", "openrouter", "gemini"
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    model: str = "llama3"


class LoadCampaignRequest(BaseModel):
    zip_path: Optional[str] = None
    edition: str = "5e"


class StartCombatRequest(BaseModel):
    enemies: List[Dict[str, Any]] = Field(default_factory=list)


class CombatAttackRequest(BaseModel):
    target_id: str
    weapon_id: Optional[str] = None
    weapon_name: Optional[str] = None
    advantage: bool = False
    disadvantage: bool = False
    d6_options: Optional[D6Options] = None
    attacker_id: Optional[str] = None


class IllustrateSceneRequest(BaseModel):
    prompt: Optional[str] = None
    turn_id: Optional[str] = None
    style_preset: Optional[str] = None
    width: int = 800
    height: int = 512


class CastSpellRequest(BaseModel):
    spell_name: str
    slot_level: int = 1
    target_id: Optional[str] = None
    target_ac_or_dc: Optional[int] = None
    damage_or_healing: Optional[str] = None


class AddCompanionRequest(BaseModel):
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
    notes: Optional[str] = ""


class CompanionAttackRequest(BaseModel):
    companion_id: str
    target_id: str
    advantage: bool = False
    disadvantage: bool = False


class LearnSpellRequest(BaseModel):
    spell_name: str


class UpdateCompanionHPRequest(BaseModel):
    hp_change: int
