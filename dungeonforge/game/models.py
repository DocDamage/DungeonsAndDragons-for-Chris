import time
from typing import List, Dict, Optional
from pydantic import BaseModel, Field

from dungeonforge.rules.base import Character
from dungeonforge.context.memory import Memory
from dungeonforge.context.story_cards import StoryCard
from dungeonforge.context.authors_note import AuthorsNote
from dungeonforge.context.pipeline import ActionTurn
from dungeonforge.game.combat import CombatEncounter
from dungeonforge.rules.weg_models import D6BoostWindow
from dungeonforge.rules.weg_vehicle_models import D6Vehicle, D6VehicleEncounter
from dungeonforge.rules.weg_force_models import ForceBoostWindow
from dungeonforge.rules.weg_advancement_models import D6AdvancementCampaign
from dungeonforge.rules.weg_navigation_models import D6NavigationState
from dungeonforge.rules.weg_tasks_models import D6TaskState
from dungeonforge.rules.strahd_models import StrahdProgressState
from dungeonforge.rules.weg_equipment_models import D6EquipmentState
from dungeonforge.rules.weg_medical_models import D6MedicalState


class GameSession(BaseModel):
    id: str = "session_default"
    title: str = "Escape into Barovia"
    edition: str = "5e"  # "2e", "3.5e", "5e"
    character: Character = Field(default_factory=Character)
    memory: Memory = Field(default_factory=Memory)
    authors_note: AuthorsNote = Field(default_factory=AuthorsNote)
    story_cards: List[StoryCard] = Field(default_factory=list)
    history: List[ActionTurn] = Field(default_factory=list)
    undone_history: List[ActionTurn] = Field(default_factory=list)
    active_quests: Dict[str, List[str]] = Field(default_factory=dict)
    campaign_name: str = "Curse of Strahd Reloaded"
    source_folders: List[str] = Field(default_factory=lambda: ["strahd"])
    source_rule_system: str = "D&D 5e"
    rules_note: Optional[str] = None
    encounter: Optional[CombatEncounter] = None
    d6_combat_history: List[CombatEncounter] = Field(default_factory=list)
    native_boost: Optional[D6BoostWindow] = None
    vehicles: List[D6Vehicle] = Field(default_factory=list)
    vehicle_encounter: Optional[D6VehicleEncounter] = None
    force_boost: Optional[ForceBoostWindow] = None
    d6_advancement: D6AdvancementCampaign = Field(default_factory=D6AdvancementCampaign)
    d6_navigation: D6NavigationState = Field(default_factory=D6NavigationState)
    d6_tasks: D6TaskState = Field(default_factory=D6TaskState)
    d6_hazard_round: int = 0
    strahd_progress: StrahdProgressState = Field(default_factory=StrahdProgressState)
    d6_equipment: D6EquipmentState = Field(default_factory=D6EquipmentState)
    d6_medical: D6MedicalState = Field(default_factory=D6MedicalState)
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)
