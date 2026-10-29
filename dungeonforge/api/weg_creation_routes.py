"""New native characters and source-defined species conditions."""
import uuid
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from dungeonforge.api.weg_routes import native_session
from dungeonforge.api.weg_force_routes import commit
from dungeonforge.api.weg_advancement_routes import event
from dungeonforge.game.models import GameSession
from dungeonforge.game.saves import SaveManager
from dungeonforge.rules import weg_creation as creation
from dungeonforge.rules.weg_creation_models import D6CreationRequest
from dungeonforge.rules.weg_origin_models import D6SpeciesContext
from dungeonforge.rules.weg_d6 import WEGD6Rules, D6Roller

router = APIRouter(prefix="/api/weg-d6/creation", tags=["Native character creation and species"])


@router.get("/catalog")
def catalog():
    return creation.catalog()


@router.post("/preview")
def preview(req: D6CreationRequest):
    try:
        character, notes = creation.build(req)
        return {"character": character, "notes": notes, "source": creation.SOURCE}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/start")
def start(req: D6CreationRequest):
    from dungeonforge.api import routes
    from dungeonforge.campaign.campaign_manager import CampaignManager
    from dungeonforge.context.pipeline import ActionTurn
    original = routes._ACTIVE_SESSION
    try:
        if req.expected_updated_at != original.updated_at:
            raise ValueError("The current adventure changed; refresh and review the character before starting.")
        if original.vehicle_encounter or (original.encounter and original.encounter.active):
            raise ValueError("End the current encounter before starting another adventure.")
        if original.edition == "weg_d6":
            from dungeonforge.api.weg_template_routes import ready
            ready(original)
        character, notes = creation.build(req)
        preset = CampaignManager.load_campaign("star_wars_d6")
        if req.include_medic:
            character.companions = preset.starter_character.companions
        session = GameSession(id=f"session_star_wars_{uuid.uuid4().hex[:12]}", character=character,
            edition="weg_d6", campaign_name=preset.title, title=f"{character.name}: Galactic Rebellion",
            story_cards=preset.story_cards, active_quests=preset.active_quests, source_folders=[preset.source_folder],
            source_rule_system=preset.source_rule_system, rules_note=preset.rules_note)
        session.memory.front_memory = preset.initial_memory
        session.authors_note.text = preset.default_authors_note
        session.history.append(ActionTurn(id="prologue", mode="story", player_input="The adventure begins...", dm_output=preset.prologue_prompt))
        # Preserve the old adventure before changing the active session, including its full roster.
        slot = SaveManager().save_session(original.model_copy(deep=True), f"before_character_creation_{uuid.uuid4().hex[:12]}")
        routes._ACTIVE_SESSION = session
        return {"session": session, "backup_slot": slot, "notes": notes}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/recruit")
def recruit(req: D6CreationRequest):
    from dungeonforge.api.weg_advancement_routes import downtime
    from dungeonforge.rules.base import Companion, Item
    original = native_session()
    session = original.model_copy(deep=True)
    try:
        downtime(session)
        from dungeonforge.api.weg_template_routes import ready
        ready(session)
        if req.expected_updated_at != session.updated_at:
            raise ValueError("The party changed after this review; refresh and review the new companion again.")
        if len(session.character.companions) >= 19:
            raise ValueError("The native party supports twenty members including the player.")
        character, _ = creation.build(req)
        weapon = next((item for item in character.inventory if item.item_type == "weapon" and item.equipped), None) or Item(name="Brawling", damage="STR", d6_skill="brawling", damage_type="physical")
        companion = Companion(id=character.id, name=character.name, race=character.race, class_name=character.class_name,
            d6=character.d6, notes=character.notes, d6_weapon=weapon.model_copy(deep=True), attack_name=weapon.name, damage=weapon.damage or "STR")
        session.character.companions.append(companion)
        for item in character.inventory:
            session.character.inventory.append(item)
        return commit(original, session, event(f"GM recruits {companion.name}, {companion.race} {companion.class_name}, using the reviewed native creation budgets."), "Recruit native D6 companion", boost=False)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


class SpeciesContextRequest(BaseModel):
    actor_id: str | None = None
    context: D6SpeciesContext
    reason: str = Field(min_length=1, max_length=1000)
    deadly_danger: bool = False


def person(session, actor_id):
    from dungeonforge.game.weg_force import actor
    return actor(session, actor_id)


@router.post("/species-context")
def species_context(req: SpeciesContextRequest):
    original = native_session()
    session = original.model_copy(deep=True)
    try:
        source = person(session, req.actor_id)
        state = source.state
        if not req.reason.strip():
            raise ValueError("Record the actual scene conditions for the species ability.")
        if not state.species_id:
            from dungeonforge.rules.weg_species import SPECIES
            identity = next((key for key, value in SPECIES.items() if value["name"].lower() == source.race.lower()), None)
            if not identity:
                raise ValueError("This sheet needs a recognized species identity before using its abilities.")
            state.species_id = identity
        if req.context.berserk and not state.species_context.berserk and (state.species_id != "wookiee" or not req.deadly_danger):
            raise ValueError("Wookiee rage requires immediate deadly danger to self or a life-debt companion.")
        if state.species_context.berserk and not req.context.berserk:
            raise ValueError("Use the Moderate calm-down check after all enemies are controlled.")
        state.species_context = req.context
        return commit(original, session, event(f"GM records {source.name}'s species conditions: {req.reason.strip()}"), "Species scene conditions", boost=False)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


class CalmRequest(BaseModel):
    actor_id: str | None = None
    enemies_controlled: bool = False
    difficulty: int = Field(15, ge=11, le=15)
    force_point: bool = False
    character_points: int = Field(0, ge=0, le=2)
    coordination_dice: int = Field(0, ge=0, le=30)
    coordination_reason: str = Field("", max_length=1000)


@router.post("/calm")
def calm(req: CalmRequest):
    original = native_session()
    session = original.model_copy(deep=True)
    try:
        source = person(session, req.actor_id)
        state = source.state
        if state.species_id != "wookiee" or not state.species_context.berserk:
            raise ValueError("Only an enraged Wookiee needs this check.")
        if not req.enemies_controlled or session.vehicle_encounter or (session.encounter and session.encounter.active):
            raise ValueError("All enemies must be controlled; finish the active encounter before the calm-down check.")
        WEGD6Rules.next_round(state)
        if req.coordination_dice and not req.coordination_reason.strip():
            raise ValueError("Record the actual coordination bonus earned by close friends.")
        if req.force_point and req.character_points or req.character_points > state.character_points:
            raise ValueError("Use available Character Points or a Force Point, never both.")
        WEGD6Rules.declare(state, force_point=req.force_point)
        dice, extra = WEGD6Rules.pool(state, "perception")
        dice += req.coordination_dice
        if dice < 1:
            raise ValueError("The rage penalty leaves no dice; use a Force Point or actual close-friend coordination to make a calm-down attempt possible.")
        roll = D6Roller.values(dice, extra, req.character_points)
        state.character_points -= req.character_points
        state.round_state.character_points_spent = bool(req.character_points)
        state.round_state.actions_taken += 1
        result = event(f"{source.name}: calm-down Perception {roll.breakdown} vs {req.difficulty}. " + req.coordination_reason.strip(), success=roll.total >= req.difficulty)
        result.roll_result, result.target_value = roll, req.difficulty
        if result.success:
            state.species_context.berserk = False
        result.summary += " Wookiee calms down." if result.success else " Wookiee remains enraged."
        return commit(original, session, result, "Wookiee calm-down check", boost=False)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


class StaminaRetryRequest(BaseModel):
    character_points: int = Field(0, ge=0, le=2)


@router.post("/stamina-retry")
def stamina_retry(req: StaminaRetryRequest):
    original = native_session()
    session = original.model_copy(deep=True)
    try:
        window = session.native_boost
        if not window or window.skill != "stamina" or not session.history or session.history[-1].id != window.turn_id:
            raise ValueError("A Gamorrean may retry only the immediately preceding failed stamina check.")
        source = person(session, window.actor_id)
        previous = session.history[-1].rule_result
        if source.state.species_id != "gamorrean" or previous.success or previous.state_changes.get("gamorrean_retry"):
            raise ValueError("This is not an unused failed Gamorrean stamina check.")
        trial = source.state.model_copy(deep=True)
        trial.round_state.actions_taken = 0
        dice, extra = WEGD6Rules.validate_action(trial, "stamina", req.character_points)
        roll = D6Roller.values(dice, extra, req.character_points)
        source.state.character_points -= req.character_points
        source.state.round_state.character_points_spent |= req.character_points > 0
        result = event(f"{source.name}'s one immediate Gamorrean stamina retry: {roll.total} vs {previous.target_value}; no extra declared action.", success=roll.total >= previous.target_value,
            changes={"gamorrean_retry": True, "first_roll": previous.roll_result.model_dump()})
        result.roll_result, result.target_value = roll, previous.target_value
        return commit(original, session, result, "Gamorrean stamina retry", boost=False)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
