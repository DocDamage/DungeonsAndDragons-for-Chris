import os
import time
import uuid
from fastapi import APIRouter, HTTPException
from typing import Dict, Any, Optional

from dungeonforge.game.models import GameSession
from dungeonforge.game.engine import GameEngine
from dungeonforge.rules.base import Character, Item, AbilityScores, Companion, SpellSlot
from dungeonforge.rules.dice import DiceRoller, RollResult
from dungeonforge.context.story_cards import StoryCard
from dungeonforge.campaign.obsidian_loader import ObsidianCampaignLoader
from dungeonforge.llm.mock import MockLLMClient
from dungeonforge.llm.api import APIClient
from dungeonforge.image.illustrator import SceneIllustrator
from dungeonforge.rules.weg_models import D6RoundState
from dungeonforge.api.schemas import (
    ActionRequest,
    AlterTurnRequest,
    RollDiceRequest,
    ConfigLLMRequest,
    LoadCampaignRequest,
    StartCombatRequest,
    CombatAttackRequest,
    IllustrateSceneRequest,
    CastSpellRequest,
    AddCompanionRequest,
    CompanionAttackRequest,
    LearnSpellRequest,
    UpdateCompanionHPRequest
)

router = APIRouter(prefix="/api")

# In-memory single active session for the desktop/web companion
_ACTIVE_SESSION = GameSession(
    id="session_strahd",
    title="Escape from Death House",
    edition="5e",
    character=Character(
        name="Varis Holimion",
        race="High Elf",
        class_name="Ranger",
        level=3,
        alignment="Chaotic Good",
        edition="5e",
        abilities=AbilityScores(str=12, dex=16, con=14, int=13, wis=15, cha=10),
        current_hp=28,
        max_hp=28,
        ac=15,
        gold=45,
        inventory=[
            Item(name="Longbow", quantity=1, item_type="weapon", damage="1d8", equipped=True),
            Item(name="Shortsword", quantity=2, item_type="weapon", damage="1d6", equipped=True),
            Item(name="Studded Leather Armor", quantity=1, item_type="armor", ac_bonus=2, equipped=True),
            Item(name="Potion of Healing", quantity=2, item_type="potion", description="Restores 2d4+2 HP")
        ],
        spell_slots={
            "1": SpellSlot(level=1, current=3, max_slots=3)
        },
        known_spells=["Hunter's Mark", "Cure Wounds", "Hail of Thorns"],
        companions=[
            Companion(
                id="comp_ireena",
                name="Ireena Kolyana",
                race="Human",
                class_name="Noble",
                level=3,
                current_hp=18,
                max_hp=18,
                ac=15,
                attack_name="Rapier",
                damage="1d8+2",
                avatar_url="/static/images/strahd/Ireena.png",
                notes="Adopted daughter of the late Burgomaster Kolyan Indirovich. Target of Strahd's obsession."
            ),
            Companion(
                id="comp_ismark",
                name="Ismark the Lesser",
                race="Human",
                class_name="Fighter",
                level=4,
                current_hp=32,
                max_hp=32,
                ac=16,
                attack_name="Greatsword",
                damage="2d6+3",
                avatar_url="/static/images/strahd/Ismark.png",
                notes="Brother to Ireena, determined to escort her safely to Vallaki or Krezk."
            )
        ],
        conditions=[]
    )
)

_ENGINE = GameEngine(llm_client=MockLLMClient())


@router.get("/session")
async def get_session() -> GameSession:
    return _ACTIVE_SESSION


@router.post("/session/edition")
async def set_edition(edition: str) -> GameSession:
    if edition not in {"2e", "3.5e", "5e", "weg_d6"}:
        raise HTTPException(status_code=422, detail="Unsupported rules system.")
    if edition == "weg_d6" and _ACTIVE_SESSION.character.d6 is None:
        raise HTTPException(status_code=409, detail="Select the native Star Wars D6 campaign to create a matching character.")
    if _ACTIVE_SESSION.edition == "weg_d6" and edition != "weg_d6":
        raise HTTPException(status_code=409, detail="Choose a D&D campaign with a matching character to change systems.")
    _ACTIVE_SESSION.edition = edition
    _ACTIVE_SESSION.character.edition = edition
    return _ACTIVE_SESSION


@router.post("/action")
async def execute_action(req: ActionRequest) -> Dict[str, Any]:
    try:
        turn = await _ENGINE.execute_turn(
            session=_ACTIVE_SESSION,
            mode=req.mode,
            input_text=req.text,
            target_ac=req.target_ac,
            target_dc=req.target_dc,
            weapon_name=req.weapon_name,
            ability_or_skill=req.ability_or_skill,
            advantage=req.advantage,
            disadvantage=req.disadvantage,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "turn": turn,
        "session": _ACTIVE_SESSION
    }


@router.post("/turn/alter")
async def alter_turn(req: AlterTurnRequest) -> Dict[str, Any]:
    turn = _ENGINE.alter_turn(_ACTIVE_SESSION, req.turn_id, req.new_text)
    if not turn:
        raise HTTPException(status_code=404, detail="Turn not found")
    return {"turn": turn, "session": _ACTIVE_SESSION}


@router.post("/turn/undo")
async def undo_turn() -> Dict[str, Any]:
    turn = _ENGINE.undo_turn(_ACTIVE_SESSION)
    return {"undone": turn, "session": _ACTIVE_SESSION}


@router.post("/turn/redo")
async def redo_turn() -> Dict[str, Any]:
    turn = _ENGINE.redo_turn(_ACTIVE_SESSION)
    return {"redone": turn, "session": _ACTIVE_SESSION}


@router.post("/character")
async def update_character(char: Character) -> Character:
    if _ACTIVE_SESSION.vehicle_encounter:
        raise HTTPException(status_code=409, detail="End vehicle combat before editing crew sheets; active crew states are tracked at their stations.")
    if char.edition != _ACTIVE_SESSION.edition:
        raise HTTPException(status_code=422, detail="Character and session rules systems must match.")
    if _ACTIVE_SESSION.edition == "weg_d6":
        if char.d6 is None:
            raise HTTPException(status_code=422, detail="A native D6 sheet is required.")
        from dungeonforge.rules.weg_explosives import pending
        if pending(_ACTIVE_SESSION.encounter):
            previous = _ACTIVE_SESSION.character
            old_people = [previous, *previous.companions]
            new_people = [char, *char.companions]
            physical = lambda people: [(person.id, person.race, bool(person.d6 and person.d6.droid)) for person in people]
            if physical(old_people) != physical(new_people) or [item.model_dump() for item in previous.inventory] != [item.model_dump() for item in char.inventory]:
                raise HTTPException(status_code=409, detail="A live grenade uses its saved actual roster and physical equipment. Resolve the fuse before changing roster, species or inventory through a GM sheet edit.")
        from dungeonforge.rules.weg_force_catalog import training_errors
        previous_people = {person.id: person for person in [_ACTIVE_SESSION.character, *_ACTIVE_SESSION.character.companions] if person.d6}
        for person in [char, *char.companions]:
            previous = previous_people.get(person.id)
            if previous and person.d6:
                if previous.d6.dark_side_points != person.d6.dark_side_points or previous.d6.force.dark_side_consumed != person.d6.force.dark_side_consumed:
                    raise HTTPException(status_code=422, detail="Use Dark Side rulings or its explicit GM correction control to change corruption; ordinary sheet edits cannot bypass the checks.")
                person.d6.corruption = previous.d6.corruption
                if previous.d6.force_sensitive and not person.d6.force_sensitive:
                    raise HTTPException(status_code=422, detail="Force sensitivity is permanent once gained.")
                if previous.d6.advancement.project and any(getattr(previous.d6, field) != getattr(person.d6, field) for field in ("attributes", "skills", "force_skills", "specializations", "specialization_parents", "move", "force_sensitive")):
                    raise HTTPException(status_code=422, detail="Complete or abandon intensive study before making GM rank adjustments.")
                person.d6.advancement = previous.d6.advancement
                person.d6.rewards = previous.d6.rewards
                person.d6.origin = previous.d6.origin
                person.d6.hazards = previous.d6.hazards
            errors = training_errors(person.d6) if person.d6 else []
            if errors:
                raise HTTPException(status_code=422, detail=" ".join(errors))
        _ACTIVE_SESSION.force_boost = None
        _ACTIVE_SESSION.native_boost = None
        if _ACTIVE_SESSION.encounter and _ACTIVE_SESSION.encounter.active:
            from dungeonforge.game import weg_combat
            combatant = weg_combat.actor(_ACTIVE_SESSION.encounter, char.id)
            char.d6.round_state = combatant.d6.round_state
            combatant.d6 = char.d6
            combatant.weapon = next((item for item in char.inventory if item.quantity > 0 and item.equipped and item.item_type == "weapon" and item.equipped_by in {None, char.id}), None)
            weg_combat.refresh(_ACTIVE_SESSION.encounter)
    _ACTIVE_SESSION.character = char
    _ACTIVE_SESSION.updated_at = max(time.time(), _ACTIVE_SESSION.updated_at + 0.000001)
    return _ACTIVE_SESSION.character


@router.post("/character/roll-stats")
async def roll_character_stats() -> Dict[str, Any]:
    if _ACTIVE_SESSION.edition == "weg_d6":
        raise HTTPException(status_code=409, detail="Native D6 characters use attribute die codes, not 4d6 ability scores.")
    stats = {}
    breakdowns = {}
    for ability in ["str", "dex", "con", "int", "wis", "cha"]:
        res = DiceRoller.roll("4d6kh3")
        stats[ability] = res.total
        breakdowns[ability] = res.breakdown

    return {
        "stats": stats,
        "breakdowns": breakdowns
    }


@router.post("/story-cards")
async def save_story_card(card: StoryCard) -> StoryCard:
    existing = next((c for c in _ACTIVE_SESSION.story_cards if c.id == card.id), None)
    if existing:
        _ACTIVE_SESSION.story_cards = [card if c.id == card.id else c for c in _ACTIVE_SESSION.story_cards]
    else:
        _ACTIVE_SESSION.story_cards.append(card)
    return card


@router.delete("/story-cards/{card_id}")
async def delete_story_card(card_id: str) -> Dict[str, str]:
    _ACTIVE_SESSION.story_cards = [c for c in _ACTIVE_SESSION.story_cards if c.id != card_id]
    return {"status": "deleted", "id": card_id}


@router.post("/dice/roll")
async def roll_dice(req: RollDiceRequest) -> RollResult:
    try:
        result = DiceRoller.roll(req.expression)
        if _ACTIVE_SESSION.edition == "weg_d6":
            from dungeonforge.game.weg_force import after_roll
            after_roll(_ACTIVE_SESSION)
        _ACTIVE_SESSION.native_boost = None
        if _ACTIVE_SESSION.vehicle_encounter:
            _ACTIVE_SESSION.vehicle_encounter.boost = None
        return result
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/campaign/load-obsidian")
async def load_obsidian_campaign(req: LoadCampaignRequest) -> Dict[str, Any]:
    from dungeonforge.library import get_library
    default_zip = str(get_library().resolve("curse of straud/Curse_of_Strahd_Reloaded_Part_1_of_3.zip"))
    zip_path = req.zip_path or default_zip

    if not os.path.exists(zip_path):
        raise HTTPException(status_code=404, detail=f"Campaign zip not found at {zip_path}")

    images_dir = os.path.join(os.path.dirname(__file__), "..", "..", "static", "images", "strahd")
    cards, quests = ObsidianCampaignLoader.load_from_archives([zip_path], max_cards=300, images_dir=images_dir)
    _ACTIVE_SESSION.story_cards = cards
    _ACTIVE_SESSION.active_quests = quests
    _ACTIVE_SESSION.edition = req.edition
    _ACTIVE_SESSION.character.edition = req.edition
    _ACTIVE_SESSION.campaign_name = "Curse of Strahd Reloaded"

    # Add initial memory
    _ACTIVE_SESSION.memory.front_memory = (
        "The party has been drawn through the mists into the valley of Barovia, "
        "a haunted demiplane ruled by the ancient vampire lord Count Strahd von Zarovich."
    )
    _ACTIVE_SESSION.authors_note.text = "Style: Gothic Horror, Dark Fantasy; Tone: Tense, atmospheric, suspenseful."

    return {
        "status": "loaded",
        "cards_loaded": len(cards),
        "acts_loaded": len(quests),
        "campaign_name": _ACTIVE_SESSION.campaign_name
    }


@router.post("/config/llm")
async def config_llm(req: ConfigLLMRequest) -> Dict[str, str]:
    global _ENGINE
    if req.provider == "mock":
        _ENGINE.llm = MockLLMClient()
    elif req.provider == "ollama":
        base_url = req.base_url or "http://localhost:11434/v1"
        _ENGINE.llm = APIClient(api_key=req.api_key, base_url=base_url, model=req.model or "llama3")
    elif req.provider in ["openai", "openrouter", "gemini"]:
        base_url = req.base_url or (
            "https://generativelanguage.googleapis.com/v1beta/openai" if req.provider == "gemini" else "https://api.openai.com/v1"
        )
        _ENGINE.llm = APIClient(api_key=req.api_key, base_url=base_url, model=req.model)

    return {"status": "configured", "provider": req.provider, "model": req.model}


# ==================== CAMPAIGN MANAGER ROUTES ====================

@router.get("/campaigns")
async def list_campaigns():
    from dungeonforge.campaign.campaign_manager import CampaignManager
    return {"campaigns": CampaignManager.campaign_catalog()}


@router.post("/campaign/switch/{campaign_id}")
def switch_campaign(campaign_id: str):
    global _ACTIVE_SESSION
    from dungeonforge.campaign.campaign_manager import CampaignManager
    from dungeonforge.library import FOLDERS, get_library
    try:
        preset = CampaignManager.load_campaign(campaign_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    new_session = GameSession(
        id=f"session_{preset.id}", campaign_name=preset.title, title=preset.title,
        edition=preset.edition, character=preset.starter_character,
        story_cards=preset.story_cards, active_quests=preset.active_quests,
        source_folders=[preset.source_folder], source_rule_system=preset.source_rule_system,
        rules_note=preset.rules_note,
    )
    new_session.memory.front_memory = preset.initial_memory
    new_session.authors_note.text = preset.default_authors_note

    # Split vaults include image-only archives; import every part before matching cards.
    if preset.id == "strahd":
        directory = get_library().resolve(FOLDERS["strahd"]["directory"])
        archives = sorted(directory.glob("*.zip"))
        if archives:
            images_dir = os.path.join(os.path.dirname(__file__), "..", "..", "static", "images", "strahd")
            extra_cards, _ = ObsidianCampaignLoader.load_from_archives(archives, max_cards=300, images_dir=images_dir)
            new_session.story_cards.extend(extra_cards)
            # The Reloaded adventure summary defines five acts. Archive folders
            # and summary documents do not replace its canonical quest catalog.

    # Add initial prologue turn
    from dungeonforge.context.pipeline import ActionTurn
    new_session.history.append(ActionTurn(
        id="prologue",
        mode="story",
        player_input="The adventure begins...",
        dm_output=preset.prologue_prompt
    ))

    _ACTIVE_SESSION = new_session
    return {"status": "switched", "campaign": preset.title, "session": _ACTIVE_SESSION}

@router.get("/compendium/search")
async def search_compendium(q: str = "", category: str = "all", edition: str = "all", limit: int = 40):
    from dungeonforge.compendium import get_compendium_db
    db = get_compendium_db()
    results = db.search(query=q, category=category, edition=edition, limit=limit)
    return {"results": results, "count": len(results)}


@router.get("/compendium/entry/{entry_id}")
async def get_compendium_entry(entry_id: str):
    from dungeonforge.compendium import get_compendium_db
    db = get_compendium_db()
    entry = db.get_entry(entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Compendium entry not found")
    return entry


# ==================== TACTICAL COMBAT ROUTES ====================

@router.post("/combat/start")
async def start_combat(req: StartCombatRequest) -> Dict[str, Any]:
    if _ACTIVE_SESSION.vehicle_encounter:
        raise HTTPException(status_code=409, detail="End the vehicle/starship encounter before starting character combat.")
    from dungeonforge.game.combat import CombatEncounter
    encounter = CombatEncounter()
    enemies = req.enemies
    if _ACTIVE_SESSION.edition == "weg_d6":
        from dungeonforge.game.weg_navigation import require_resolved
        try:
            require_resolved(_ACTIVE_SESSION)
            from dungeonforge.game.weg_task_guards import require_available
            require_available(_ACTIVE_SESSION, _ACTIVE_SESSION.character.id, *(person.id for person in _ACTIVE_SESSION.character.companions))
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        if _ACTIVE_SESSION.encounter and _ACTIVE_SESSION.encounter.active:
            raise HTTPException(status_code=409, detail="End the current encounter before starting another.")
        if not enemies:
            from dungeonforge.campaign.campaign_manager import CampaignManager
            enemies = CampaignManager.d6_stormtroopers()
    if not enemies:
        # Default Barovian ambush: 2x Dire Wolves
        enemies = [
            {"name": "Dire Wolf Alpha", "hp": 37, "ac": 14, "dex_mod": 2, "image_url": "/static/images/strahd/Bridge Revenant.png"},
            {"name": "Dire Wolf Packmate", "hp": 28, "ac": 14, "dex_mod": 2}
        ]
    try:
        starting_character = _ACTIVE_SESSION.character.model_copy(deep=True) if _ACTIVE_SESSION.edition == "weg_d6" else _ACTIVE_SESSION.character
        encounter.start(player=starting_character, enemies=enemies, edition=_ACTIVE_SESSION.edition)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if _ACTIVE_SESSION.edition == "weg_d6":
        from dungeonforge.game import weg_combat
        weg_combat.archive(_ACTIVE_SESSION)
    _ACTIVE_SESSION.encounter = encounter
    _ACTIVE_SESSION.character = starting_character
    _ACTIVE_SESSION.native_boost = None
    _ACTIVE_SESSION.updated_at = time.time()
    return {"encounter": encounter, "session": _ACTIVE_SESSION}


@router.post("/combat/attack")
async def combat_attack(req: CombatAttackRequest) -> Dict[str, Any]:
    if not _ACTIVE_SESSION.encounter or not _ACTIVE_SESSION.encounter.active:
        raise HTTPException(status_code=400, detail="No active combat encounter")

    if _ACTIVE_SESSION.edition == "weg_d6":
        from dungeonforge.api.weg_force_routes import commit
        from dungeonforge.game import weg_combat
        from dungeonforge.game.weg_navigation import require_resolved
        from dungeonforge.game.weg_task_guards import require_available
        session = _ACTIVE_SESSION.model_copy(deep=True)
        try:
            require_resolved(session)
            require_available(session, req.attacker_id or session.character.id)
            weg_combat.bind_party(session.encounter, session.character)
            attacker = weg_combat.actor(session.encounter, req.attacker_id or session.character.id)
            weapon = attacker.weapon
            if req.weapon_id and (not weapon or weapon.id != req.weapon_id):
                raise ValueError("Draw the chosen actual weapon with its combat action before attacking.")
            if req.weapon_name and (not weapon or weapon.name.lower() != req.weapon_name.lower()):
                raise ValueError("The named weapon is not this actor's actual drawn weapon.")
            from dungeonforge.rules.weg_gear_effects import bind_attack
            bind_attack(session, attacker.id, req.target_id, weapon, req.d6_options)
            eval_result = weg_combat.attack(session.encounter, session.character, req.target_id, weapon, req.d6_options, attacker.id)
            response = commit(_ACTIVE_SESSION, session, eval_result, f"{attacker.name} attacks", boost=False)
            return {**response, "encounter": _ACTIVE_SESSION.encounter}
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    weapon = None
    if req.weapon_name:
        weapon = next((i for i in _ACTIVE_SESSION.character.inventory if i.name.lower() == req.weapon_name.lower()), None)
    if not weapon and _ACTIVE_SESSION.character.inventory:
        weapon = next((i for i in _ACTIVE_SESSION.character.inventory if i.item_type == "weapon" and i.equipped), None)

    try:
        eval_result = _ACTIVE_SESSION.encounter.attack_target(
            attacker=_ACTIVE_SESSION.character,
            target_id=req.target_id,
            weapon=weapon,
            advantage=req.advantage,
            disadvantage=req.disadvantage,
            edition=_ACTIVE_SESSION.edition,
            d6_options=req.d6_options, attacker_id=req.attacker_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    _ACTIVE_SESSION.native_boost = None
    if _ACTIVE_SESSION.edition == "weg_d6":
        from dungeonforge.api.weg_routes import record
        attacker = next(person for person in _ACTIVE_SESSION.encounter.combatants if person.id == (req.attacker_id or _ACTIVE_SESSION.character.id))
        response = record(_ACTIVE_SESSION, eval_result, f"{attacker.name} attacks", mode="attack")
        return {**response, "encounter": _ACTIVE_SESSION.encounter}
    return {
        "eval_result": eval_result,
        "encounter": _ACTIVE_SESSION.encounter,
        "session": _ACTIVE_SESSION
    }


@router.post("/combat/next")
async def combat_next_turn() -> Dict[str, Any]:
    if _ACTIVE_SESSION.vehicle_encounter:
        raise HTTPException(status_code=409, detail="Use Next crew action in the craft encounter.")
    if not _ACTIVE_SESSION.encounter:
        raise HTTPException(status_code=400, detail="No active combat encounter")

    before_round = _ACTIVE_SESSION.encounter.round
    curr = _ACTIVE_SESSION.encounter.next_turn()
    _ACTIVE_SESSION.native_boost = None
    if _ACTIVE_SESSION.edition == "weg_d6":
        if _ACTIVE_SESSION.encounter.round != before_round:
            from dungeonforge.game.weg_vehicle_combat import advance_fleet_time
            advance_fleet_time(_ACTIVE_SESSION, 1)
        from dungeonforge.game import weg_combat
        weg_combat.bind_party(_ACTIVE_SESSION.encounter, _ACTIVE_SESSION.character)
        from dungeonforge.game.weg_force import after_roll, refresh_encounters
        if _ACTIVE_SESSION.encounter.d6_round_results:
            from dungeonforge.api.weg_routes import record
            from dungeonforge.rules.base import RuleEvaluationResult
            blasts = _ACTIVE_SESSION.encounter.d6_round_results
            injured = list(dict.fromkeys(id for blast in blasts for id in blast.state_changes.get("force_injury_targets", [])))
            result = RuleEvaluationResult(action_type="explosion", success=True, roll_result=blasts[0].roll_result, summary=" ".join(blast.summary for blast in blasts),
                state_changes={"round_end_blasts": [blast.model_dump() for blast in blasts], "force_injury_targets": injured})
            record(_ACTIVE_SESSION, result, "Saved round-end explosions", mode="attack")
        else:
            after_roll(_ACTIVE_SESSION)
        refresh_encounters(_ACTIVE_SESSION)
    _ACTIVE_SESSION.updated_at = time.time()
    return {"active_combatant": curr, "encounter": _ACTIVE_SESSION.encounter, "session": _ACTIVE_SESSION}


@router.post("/combat/end")
async def end_combat() -> Dict[str, Any]:
    if _ACTIVE_SESSION.vehicle_encounter:
        raise HTTPException(status_code=409, detail="Use End craft encounter to preserve crew and craft state.")
    if _ACTIVE_SESSION.edition == "weg_d6" and _ACTIVE_SESSION.encounter:
        from dungeonforge.rules.weg_explosives import pending
        if pending(_ACTIVE_SESSION.encounter):
            raise HTTPException(status_code=409, detail="Resolve the actual live grenade timers through combat rounds before ending this encounter; ending cannot freeze a fuse.")
        if _ACTIVE_SESSION.encounter.d6_round_closing:
            raise HTTPException(status_code=409, detail="Resolve immediate blast injury reactions, then use Finish round before ending the encounter.")
    _ACTIVE_SESSION.native_boost = None
    _ACTIVE_SESSION.force_boost = None
    if _ACTIVE_SESSION.encounter:
        if _ACTIVE_SESSION.edition == "weg_d6":
            from dungeonforge.game import weg_combat
            weg_combat.bind_party(_ACTIVE_SESSION.encounter, _ACTIVE_SESSION.character)
            weg_combat.archive(_ACTIVE_SESSION)
            for person in [_ACTIVE_SESSION.character, *_ACTIVE_SESSION.character.companions]:
                if person.d6:
                    person.d6.round_state = D6RoundState()
                    person.d6.force.saber_locked = False
                    for effect in person.d6.force.effects:
                        effect.activation_round = False
        _ACTIVE_SESSION.encounter.active = False
        _ACTIVE_SESSION.encounter = None
    _ACTIVE_SESSION.updated_at = time.time()
    return {"status": "combat_ended", "session": _ACTIVE_SESSION}


# ==================== SAVE / LOAD & EXPORT ROUTES ====================

@router.get("/session/saves")
async def list_saves():
    from dungeonforge.game.saves import SaveManager
    mgr = SaveManager()
    return {"saves": mgr.list_saves()}


@router.post("/session/save")
async def save_session_slot(slot_name: Optional[str] = None):
    from dungeonforge.game.saves import SaveManager
    mgr = SaveManager()
    slot_id = mgr.save_session(_ACTIVE_SESSION, slot_name=slot_name)
    return {"status": "saved", "slot_id": slot_id, "session": _ACTIVE_SESSION}


@router.post("/session/load/{slot_id}")
async def load_session_slot(slot_id: str):
    global _ACTIVE_SESSION
    from dungeonforge.game.saves import SaveManager
    mgr = SaveManager()
    loaded = mgr.load_session(slot_id)
    if not loaded:
        raise HTTPException(status_code=404, detail="Save slot not found")
    _ACTIVE_SESSION = loaded
    return {"status": "loaded", "session": _ACTIVE_SESSION}


@router.delete("/session/save/{slot_id}")
async def delete_save_slot(slot_id: str):
    from dungeonforge.game.saves import SaveManager
    mgr = SaveManager()
    success = mgr.delete_save(slot_id)
    return {"status": "deleted" if success else "not_found", "slot_id": slot_id}


@router.get("/session/export/markdown")
async def export_markdown():
    from dungeonforge.game.saves import SaveManager
    from fastapi.responses import PlainTextResponse
    mgr = SaveManager()
    text = mgr.export_markdown_chronicle(_ACTIVE_SESSION)
    return PlainTextResponse(text, media_type="text/markdown")


# ==================== INVENTORY ITEM USE ====================

@router.post("/character/use-item")
async def use_inventory_item(item_name: str):
    if _ACTIVE_SESSION.edition == "weg_d6":
        if "medpac" not in item_name.lower():
            raise HTTPException(status_code=400, detail="Use the native D6 recovery controls for consumables.")
        from dungeonforge.api.weg_routes import recover
        from dungeonforge.rules.weg_models import D6RecoveryRequest
        data = recover(D6RecoveryRequest(method="medpac"))
        return {**data, "status": "used", "effect": data["turn"].dm_output, "character": _ACTIVE_SESSION.character}
    item = next((i for i in _ACTIVE_SESSION.character.inventory if i.name.lower() == item_name.lower()), None)
    if not item:
        raise HTTPException(status_code=404, detail="Item not in inventory")

    healed_amount = 0
    effect_summary = ""

    if item.item_type in ["potion", "consumable"] or "healing" in item.name.lower():
        # Roll healing: 2d4+2
        roll = DiceRoller.roll("2d4+2")
        healed_amount = min(roll.total, _ACTIVE_SESSION.character.max_hp - _ACTIVE_SESSION.character.current_hp)
        _ACTIVE_SESSION.character.current_hp += healed_amount
        effect_summary = f"Drank {item.name}: Restored {healed_amount} HP! (Current HP: {_ACTIVE_SESSION.character.current_hp}/{_ACTIVE_SESSION.character.max_hp})"
    else:
        effect_summary = f"Used {item.name}."

    # Decrement item
    item.quantity -= 1
    if item.quantity <= 0:
        _ACTIVE_SESSION.character.inventory = [i for i in _ACTIVE_SESSION.character.inventory if i.name != item.name]

    # Create narrative turn
    from dungeonforge.context.pipeline import ActionTurn
    turn = ActionTurn(
        id=f"use_{uuid.uuid4().hex}",
        mode="do",
        player_input=f"use {item.name}",
        dm_output=f"You consume the {item.name}. {effect_summary}",
        timestamp=time.time()
    )
    _ACTIVE_SESSION.history.append(turn)

    return {
        "status": "used",
        "effect": effect_summary,
        "character": _ACTIVE_SESSION.character,
        "session": _ACTIVE_SESSION
    }


# ==================== SCENE ILLUSTRATOR ROUTES ====================

@router.post("/scene/illustrate")
async def illustrate_scene(req: IllustrateSceneRequest) -> Dict[str, Any]:
    turn_found = None
    context_text = None
    if req.turn_id:
        turn_found = next((t for t in _ACTIVE_SESSION.history if t.id == req.turn_id), None)
        if turn_found:
            context_text = turn_found.dm_output

    img_url = SceneIllustrator.generate_image_url(
        prompt=req.prompt,
        context_text=context_text,
        style=req.style_preset,
        width=req.width,
        height=req.height
    )

    if turn_found:
        turn_found.image_url = img_url
        _ACTIVE_SESSION.updated_at = time.time()

    return {
        "status": "illustrated",
        "image_url": img_url,
        "turn_id": req.turn_id,
        "session": _ACTIVE_SESSION
    }


# ==================== SPELLBOOK & MAGIC ROUTES ====================

@router.post("/character/cast-spell")
async def cast_spell(req: CastSpellRequest) -> Dict[str, Any]:
    if _ACTIVE_SESSION.edition == "weg_d6":
        raise HTTPException(status_code=409, detail="WEG D6 uses trained Control, Sense, and Alter checks, not D&D spell slots.")
    character = _ACTIVE_SESSION.character
    slot_key = str(req.slot_level)

    # Validate spell slot if not a cantrip
    if req.slot_level > 0:
        if slot_key not in character.spell_slots:
            raise HTTPException(status_code=400, detail=f"No level {req.slot_level} spell slots configured.")
        if character.spell_slots[slot_key].current <= 0:
            raise HTTPException(status_code=400, detail=f"No remaining level {req.slot_level} spell slots.")
        character.spell_slots[slot_key].current -= 1

    # Determine damage or healing
    dmg_dice = req.damage_or_healing
    healing_dice = None
    lower_spell = req.spell_name.lower()

    if not dmg_dice:
        if "cure" in lower_spell or "heal" in lower_spell:
            wis_mod = character.abilities.modifier("wis")
            healing_dice = f"1d8+{max(1, wis_mod)}"
        elif "magic missile" in lower_spell:
            dmg_dice = "3d4+3"
        elif "fireball" in lower_spell:
            dmg_dice = "8d6"
        elif "hail of thorns" in lower_spell:
            dmg_dice = "1d10"
        elif "thunderwave" in lower_spell:
            dmg_dice = "2d8"
        elif "scorching ray" in lower_spell:
            dmg_dice = "6d6"
        elif "zap" in lower_spell:
            dmg_dice = "2d6+2"

    combat_result = None
    summary_text = ""

    # If in combat and target specified, execute in encounter
    if _ACTIVE_SESSION.encounter and _ACTIVE_SESSION.encounter.active and req.target_id:
        combat_result = _ACTIVE_SESSION.encounter.cast_spell_at_target(
            caster=character,
            spell_name=req.spell_name,
            slot_level=req.slot_level,
            target_id=req.target_id,
            damage_dice=dmg_dice,
            healing_dice=healing_dice
        )
        summary_text = combat_result["summary"]
    elif healing_dice:
        heal_roll = DiceRoller.roll(healing_dice)
        restored = min(heal_roll.total, character.max_hp - character.current_hp)
        character.current_hp += restored
        summary_text = f"Cast {req.spell_name}: Restored {restored} HP! (Current HP: {character.current_hp}/{character.max_hp})"
    elif dmg_dice:
        dmg_roll = DiceRoller.roll(dmg_dice)
        summary_text = f"Cast {req.spell_name}: Arcane power unleashed dealing {dmg_roll.total} damage ({dmg_roll.breakdown})!"
    else:
        summary_text = f"Cast {req.spell_name}: Magical incantation takes effect."

    # Add narrative turn to history
    from dungeonforge.context.pipeline import ActionTurn
    turn = ActionTurn(
        id=f"cast_{uuid.uuid4().hex}",
        mode="cast",
        player_input=f"cast {req.spell_name} (Level {req.slot_level})",
        dm_output=f"Weaving intricate somatic gestures and uttering words of power, you cast {req.spell_name}. {summary_text}",
        timestamp=time.time()
    )
    _ACTIVE_SESSION.history.append(turn)
    _ACTIVE_SESSION.updated_at = time.time()

    return {
        "status": "cast",
        "turn": turn,
        "spell_name": req.spell_name,
        "slot_level": req.slot_level,
        "slots_remaining": character.spell_slots.get(slot_key).current if slot_key in character.spell_slots else 0,
        "character": character,
        "encounter": _ACTIVE_SESSION.encounter,
        "session": _ACTIVE_SESSION
    }


@router.post("/character/spell-slots/restore")
async def restore_spell_slots(level: Optional[int] = None) -> Dict[str, Any]:
    character = _ACTIVE_SESSION.character
    if level is not None:
        key = str(level)
        if key in character.spell_slots:
            character.spell_slots[key].current = character.spell_slots[key].max_slots
    else:
        for slot in character.spell_slots.values():
            slot.current = slot.max_slots

    return {
        "status": "restored",
        "spell_slots": character.spell_slots,
        "session": _ACTIVE_SESSION
    }


@router.post("/character/spells/learn")
async def learn_spell(req: LearnSpellRequest) -> Dict[str, Any]:
    character = _ACTIVE_SESSION.character
    if req.spell_name not in character.known_spells:
        character.known_spells.append(req.spell_name)
    return {"status": "learned", "known_spells": character.known_spells, "session": _ACTIVE_SESSION}


@router.delete("/character/spells/{spell_name}")
async def unlearn_spell(spell_name: str) -> Dict[str, Any]:
    character = _ACTIVE_SESSION.character
    character.known_spells = [s for s in character.known_spells if s.lower() != spell_name.lower()]
    return {"status": "unlearned", "known_spells": character.known_spells, "session": _ACTIVE_SESSION}


# ==================== PARTY COMPANIONS ROUTES ====================

@router.post("/character/companions")
async def add_companion(req: AddCompanionRequest) -> Dict[str, Any]:
    if _ACTIVE_SESSION.edition == "weg_d6":
        raise HTTPException(status_code=409, detail="Use reviewed native character/template recruitment so the companion has an actual D6 sheet and equipment.")
    new_comp = Companion(
        id=f"comp_{int(time.time())}_{str(uuid.uuid4())[:4]}",
        name=req.name,
        race=req.race,
        class_name=req.class_name,
        level=req.level,
        current_hp=req.current_hp,
        max_hp=req.max_hp,
        ac=req.ac,
        attack_name=req.attack_name,
        damage=req.damage,
        avatar_url=req.avatar_url,
        notes=req.notes or ""
    )
    _ACTIVE_SESSION.character.companions.append(new_comp)
    _ACTIVE_SESSION.updated_at = time.time()
    return {"status": "companion_added", "companion": new_comp, "session": _ACTIVE_SESSION}


@router.delete("/character/companions/{companion_id}")
async def delete_companion(companion_id: str) -> Dict[str, Any]:
    if _ACTIVE_SESSION.edition == "weg_d6" and ((_ACTIVE_SESSION.encounter and _ACTIVE_SESSION.encounter.active) or _ACTIVE_SESSION.vehicle_encounter):
        raise HTTPException(status_code=409, detail="Finish the native encounter before changing its actual party roster.")
    _ACTIVE_SESSION.character.companions = [c for c in _ACTIVE_SESSION.character.companions if c.id != companion_id]
    _ACTIVE_SESSION.updated_at = time.time()
    return {"status": "companion_removed", "companion_id": companion_id, "session": _ACTIVE_SESSION}


@router.post("/character/companions/{companion_id}/hp")
async def update_companion_hp(companion_id: str, req: UpdateCompanionHPRequest) -> Dict[str, Any]:
    comp = next((c for c in _ACTIVE_SESSION.character.companions if c.id == companion_id), None)
    if not comp:
        raise HTTPException(status_code=404, detail="Companion not found")

    comp.current_hp = max(0, min(comp.max_hp, comp.current_hp + req.hp_change))
    _ACTIVE_SESSION.updated_at = time.time()
    return {"status": "updated", "companion": comp, "session": _ACTIVE_SESSION}


@router.post("/combat/companion-attack")
async def companion_attack(req: CompanionAttackRequest) -> Dict[str, Any]:
    if not _ACTIVE_SESSION.encounter or not _ACTIVE_SESSION.encounter.active:
        raise HTTPException(status_code=400, detail="No active combat encounter")

    companion = next((c for c in _ACTIVE_SESSION.character.companions if c.id == req.companion_id), None)
    if not companion:
        raise HTTPException(status_code=404, detail="Companion not found in party")
    if _ACTIVE_SESSION.edition == "weg_d6":
        native = next((person for person in _ACTIVE_SESSION.encounter.combatants if person.id == companion.id), None)
        from dungeonforge.rules.weg_models import D6Options
        return await combat_attack(CombatAttackRequest(target_id=req.target_id, attacker_id=companion.id,
            d6_options=D6Options(stun=bool(native and native.weapon and native.weapon.stun_mode))))

    try:
        eval_result = _ACTIVE_SESSION.encounter.attack_with_companion(
            companion=companion,
            target_id=req.target_id,
            advantage=req.advantage,
            disadvantage=req.disadvantage,
            edition=_ACTIVE_SESSION.edition
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    _ACTIVE_SESSION.native_boost = None
    if _ACTIVE_SESSION.edition == "weg_d6":
        weg_combat.bind_party(_ACTIVE_SESSION.encounter, _ACTIVE_SESSION.character)
        from dungeonforge.api.weg_routes import record
        response = record(_ACTIVE_SESSION, eval_result, f"{companion.name} attacks", mode="attack")
        return {**response, "encounter": _ACTIVE_SESSION.encounter}
    return {"eval_result": eval_result, "encounter": _ACTIVE_SESSION.encounter, "session": _ACTIVE_SESSION}
