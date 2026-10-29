"""Reviewed stock-template births and one-time earned starting-power selections."""
import uuid

from fastapi import APIRouter, HTTPException

from dungeonforge.api.weg_advancement_routes import downtime, event, student, fit_to_study
from dungeonforge.api.weg_force_routes import commit
from dungeonforge.api.weg_routes import native_session
from dungeonforge.context.pipeline import ActionTurn
from dungeonforge.game.models import GameSession
from dungeonforge.game.saves import SaveManager
from dungeonforge.rules import weg_templates as templates
from dungeonforge.rules.base import Companion, Item
from dungeonforge.rules.weg_force_catalog import POWERS
from dungeonforge.rules.weg_tasks import busy_actor_ids
from dungeonforge.rules.weg_navigation import active
from dungeonforge.game.weg_navigation import require_resolved
from dungeonforge.rules.weg_vehicle_models import D6Crew
from dungeonforge.rules.weg_templates import D6TemplateRequest, D6StartingPowerChoice


router = APIRouter(prefix="/api/weg-d6/templates", tags=["Printed WEG character templates"])


def ready(session):
    downtime(session)
    require_resolved(session)
    if active(session):
        raise ValueError("Finish or resolve the actual hyperspace journey before changing the roster or starting powers.")
    if busy_actor_ids(session):
        raise ValueError("Finish or cancel pending exclusive tasks before changing the roster or selecting starting powers.")


def prepared(req):
    character, notes = templates.build(req)
    character.companions = templates.equipment_companions(req.template_id, character)
    if req.include_medic:
        from dungeonforge.campaign.campaign_manager import CampaignManager
        character.companions.extend(person.model_copy(deep=True) for person in CampaignManager.load_campaign("star_wars_d6").starter_character.companions)
    craft = templates.starting_craft(req.template_id)
    for vessel in craft:
        vessel.crew = [D6Crew(id=character.id, character_id=character.id, name=character.name,
            stations=["pilot", "gunner", "shields", "engineer"], d6=character.d6.model_copy(deep=True))]
    return character, craft, notes


@router.get("/catalog")
def catalog():
    return templates.catalog()


@router.get("/state")
def state():
    session = native_session()
    people = [session.character, *session.character.companions]
    return {"actors": [{"id": person.id, "name": person.name, "template_id": person.d6.origin.template_id,
        "force_tradition": person.d6.origin.force_tradition, "force_skills": person.d6.force_skills,
        "known_powers": person.d6.force.known_powers,
        "grants": [{"id": grant.id, "skill": grant.skill, "remaining": grant.remaining,
                    "eligible_powers": templates.eligible_starting_powers(person, grant)}
                   for grant in person.d6.advancement.power_grants if grant.teacher_id.startswith("starting:")]}
        for person in people if person.d6], "source": templates.SOURCE}


@router.post("/preview")
def preview(req: D6TemplateRequest):
    try:
        character, craft, notes = prepared(req)
        return {"character": character, "craft": craft, "notes": notes, "source": templates.SOURCE}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/start")
def start(req: D6TemplateRequest):
    from dungeonforge.api import routes
    from dungeonforge.campaign.campaign_manager import CampaignManager
    original = routes._ACTIVE_SESSION
    try:
        ready(original)
        if req.expected_updated_at != original.updated_at:
            raise ValueError("The adventure changed after this template review; review the actual character again.")
        character, craft, notes = prepared(req)
        preset = CampaignManager.load_campaign("star_wars_d6")
        session = GameSession(id=f"session_star_wars_{uuid.uuid4().hex[:12]}", character=character, vehicles=craft,
            edition="weg_d6", campaign_name=preset.title, title=f"{character.name}: Galactic Rebellion",
            story_cards=preset.story_cards, active_quests=preset.active_quests, source_folders=[preset.source_folder],
            source_rule_system=preset.source_rule_system, rules_note=preset.rules_note)
        session.memory.front_memory = preset.initial_memory
        session.authors_note.text = preset.default_authors_note
        session.history.append(ActionTurn(id="prologue", mode="story", player_input="The adventure begins...", dm_output=preset.prologue_prompt))
        backup = SaveManager().save_session(original.model_copy(deep=True), f"before_template_creation_{uuid.uuid4().hex[:12]}")
        routes._ACTIVE_SESSION = session
        return {"session": session, "backup_slot": backup, "notes": notes}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/recruit")
def recruit(req: D6TemplateRequest):
    original = native_session()
    session = original.model_copy(deep=True)
    try:
        ready(session)
        if req.expected_updated_at != session.updated_at:
            raise ValueError("The party changed after this review; review the actual template companion again.")
        if req.include_medic:
            raise ValueError("The optional campaign medic is a new-adventure option; uncheck it to recruit this template.")
        character, craft, _ = prepared(req)
        if len(session.character.companions) + 1 + len(character.companions) > 19:
            raise ValueError("The reviewed template and equipment companions exceed the twenty-member party limit.")
        if len(session.vehicles) + len(craft) > 20:
            raise ValueError("The reviewed starting craft exceeds the twenty-craft party limit.")
        weapon = next((gear for gear in character.inventory if gear.item_type == "weapon" and gear.equipped), None) or Item(name="Brawling", damage="STR", d6_skill="brawling", damage_type="physical")
        companion = Companion(id=character.id, name=character.name, race=character.race, class_name=character.class_name,
            d6=character.d6, notes=character.notes, d6_weapon=weapon.model_copy(deep=True), attack_name=weapon.name, damage=weapon.damage or "STR")
        session.character.companions.extend([companion, *character.companions])
        for gear in character.inventory:
            session.character.inventory.append(gear)
        session.vehicles.extend(craft)
        result = event(f"GM recruits {companion.name} using the printed {companion.class_name} template, reviewed starting assets and earned power slots.")
        result.summary = f"[WEG Stock Template] {companion.name}: {companion.class_name}; native character and printed assets recruited."
        return commit(original, session, result, "Recruit printed template", boost=False)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/power-choice")
def power_choice(req: D6StartingPowerChoice):
    original = native_session()
    session = original.model_copy(deep=True)
    try:
        ready(session)
        if req.expected_updated_at != session.updated_at or not req.reason.strip():
            raise ValueError("Review the current earned starting slot and record the actual power selection.")
        person = student(session, req.actor_id)
        fit_to_study(person)
        templates.choose_starting_power(person, req.grant_id, req.power_id)
        result = event(f"{person.name} uses one earned starting power choice for {POWERS[req.power_id].name}. {req.reason.strip()}")
        result.summary = f"[WEG Starting Power] {person.name} selects {POWERS[req.power_id].name}; one actual starting slot consumed, no CP, study time or skill rank granted. {req.reason.strip()}"
        return commit(original, session, result, "Select earned starting power", boost=False)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
