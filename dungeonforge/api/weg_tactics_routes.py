"""Actual personal-combat gear actions; 1992 printed pp.65–66, 154–158."""
from types import SimpleNamespace
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from dungeonforge.api.weg_advancement_routes import event
from dungeonforge.api.weg_force_routes import commit
from dungeonforge.api.weg_routes import native_session
from dungeonforge.game import weg_combat
from dungeonforge.game.weg_navigation import require_resolved
from dungeonforge.game.weg_task_guards import require_available
from dungeonforge.rules import weg_equipment as equipment, weg_force_effects as effects
from dungeonforge.rules.weg_d6 import WEGD6Rules
from dungeonforge.rules.weg_models import D6CombatPreparation
from dungeonforge.rules.weg_tasks import PREPARATION_BANNED, parent_skill
from dungeonforge.rules.weg_cover_models import D6CoverFacts, D6CoverObject
from dungeonforge.rules.weg_d6 import parse_code

router = APIRouter(prefix="/api/weg-d6/tactics", tags=["Native personal combat tactics"])


@router.post("/cover")
def cover_facts(req: D6CoverFacts):
    original = native_session()
    session = original.model_copy(deep=True)
    try:
        encounter = session.encounter
        if not encounter or not encounter.active or session.vehicle_encounter:
            raise ValueError("Record battlefield facts in an actual active personal encounter.")
        from dungeonforge.rules.weg_explosives import pending
        if pending(encounter):
            raise ValueError("Resolve the live grenade using its saved actual geometry before changing battlefield cover facts.")
        if session.updated_at != req.expected_updated_at or not req.reason.strip():
            raise ValueError("Review the current encounter and record the actual GM battlefield facts.")
        target = weg_combat.actor(encounter, req.target_id)
        obj = next((item for item in encounter.cover_objects if item.id == req.object_id), None)
        if req.fraction != "none":
            if req.object_id and obj is None:
                raise ValueError("Choose an actual saved cover object.")
            if obj and (req.new_name or req.new_body):
                raise ValueError("Reusing a saved object preserves its actual body and damage; do not replace it through a cover assignment.")
            if not obj:
                if not req.new_name or not req.new_name.strip() or not req.new_body or parse_code(req.new_body)[0] < 1:
                    raise ValueError("New physical cover needs its actual name and at least 1D object Strength.")
                obj = D6CoverObject(name=req.new_name.strip(), body=req.new_body, reason=req.reason.strip())
                encounter.cover_objects.append(obj)
            if obj.damage_state == "destroyed":
                raise ValueError("Destroyed physical cover cannot protect someone again.")
        elif req.object_id or req.new_name or req.new_body:
            raise ValueError("No physical cover means no saved or newly invented object.")
        target.cover_id = obj.id if req.fraction != "none" else None
        target.cover_fraction = req.fraction
        target.concealment_dice = req.concealment_dice
        summary = f"GM records {target.name}: {req.fraction.replace('_', ' ')} physical cover" + (f" from {obj.name} ({obj.body}, {obj.damage_state.replace('_', ' ')})" if target.cover_id else "") + f"; visibility +{req.concealment_dice}D. {req.reason.strip()}"
        encounter.combat_log.append(summary)
        return commit(original, session, event(summary, changes={"battlefield_facts": req.model_dump(), "cover_id": target.cover_id}), "Record battlefield facts", boost=False)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


class D6GearAction(BaseModel):
    actor_id: str
    action: Literal["draw", "setting", "reload", "prepare"]
    item_id: str
    target_id: str | None = None
    stun: bool = False
    primary: bool = True
    power: bool = False
    expected_updated_at: float


@router.post("/gear")
def gear(req: D6GearAction):
    original = native_session()
    session = original.model_copy(deep=True)
    try:
        if session.updated_at != req.expected_updated_at:
            raise ValueError("The encounter changed; review the actual actor and equipment again.")
        require_resolved(session)
        require_available(session, req.actor_id)
        encounter = session.encounter
        if session.vehicle_encounter or not encounter or not encounter.active:
            raise ValueError("These gear actions require the active personal combat encounter.")
        weg_combat.bind_party(encounter, session.character)
        actor = weg_combat.actor(encounter, req.actor_id)
        weg_combat.validate_turn(encounter, actor)
        state = actor.d6
        if not state.can_take_turn or state.round_state.full_defense or state.round_state.actions_taken >= state.round_state.declared_actions or state.force.attempt:
            raise ValueError("The actor needs a usable declared action and no other exclusive activation.")
        inventory = session.character.inventory if actor.is_player else actor.inventory
        item = next((item for item in inventory if item.id == req.item_id and item.quantity >= 1 and item.item_type == "weapon"), None)
        if item is None:
            raise ValueError("Choose this side's actual distinct physical weapon by saved ID.")
        owner = item.equipped_by or (session.character.id if actor.is_player and item.equipped else None)
        changes = {"actor_id": actor.id, "item_id": item.id, "action": req.action}
        success = True
        if req.action == "draw":
            if owner and owner != actor.id:
                raise ValueError("Release another actor's actual loadout before drawing their weapon.")
            if actor.weapon and actor.weapon.id == item.id and item.equipped:
                raise ValueError("This actual weapon is already drawn.")
            if item.weapon_damage_state in {"severely_damaged", "destroyed"}:
                raise ValueError("Choose a usable weapon.")
            if item.quantity > 1:
                if equipment.ITEMS.get(item.catalog_id, {}).get("category") != "explosive":
                    raise ValueError("Assign a distinct physical weapon before drawing an ambiguous weapon stack.")
                from dungeonforge.rules.base import Item
                drawn = Item(**{**item.model_dump(exclude={"id"}), "quantity": 1, "equipped": False})
                item.quantity -= 1
                item = drawn
                inventory.append(item)
                changes.update(item_id=item.id, split_from_id=req.item_id)
            for previous in inventory:
                if previous.item_type == "weapon" and (previous.equipped_by == actor.id or actor.id == session.character.id and previous.equipped and previous.equipped_by is None):
                    previous.equipped, previous.equipped_by = False, None
            item.equipped, item.equipped_by = True, actor.id
            actor.weapon = item
            note = "drew the actual weapon"
        else:
            if item.quantity != 1:
                raise ValueError("Use one actual drawn physical weapon, not a stack.")
            if not actor.weapon or actor.weapon.id != item.id or owner != actor.id:
                raise ValueError("Draw this actor's actual weapon before using it.")
            if req.action == "setting":
                if not item.d6_can_stun or item.stun_mode == req.stun:
                    raise ValueError("Choose a different setting on an actual stun-capable weapon.")
                item.stun_mode = req.stun
                changes["stun_mode"] = item.stun_mode
                note = "changed to stun" if req.stun else "changed to normal damage"
            elif req.action == "reload":
                person = SimpleNamespace(id=actor.id, d6=state, inventory=inventory, companions=[])
                proxy = session if actor.is_player else SimpleNamespace(character=person)
                _, reloaded = equipment.reload_weapon(proxy, actor.id, item.id, req.primary, req.power)
                if not actor.is_player:
                    actor.inventory = proxy.character.inventory
                changes.update(reloaded)
                success = reloaded["success"]
                note = "reloaded from actual compatible supplies" if success else "failed the bowcaster's Moderate Strength reload check; supplies retained"
            else:
                target = weg_combat.actor(encounter, req.target_id)
                if target.id == actor.id or target.d6.out_of_fight:
                    raise ValueError("Prepare against an actual other conscious target.")
                if parent_skill(state, WEGD6Rules.weapon_skill(item)) in PREPARATION_BANNED:
                    raise ValueError("This weapon skill cannot receive the preparation bonus.")
                if state.round_state.declared_actions != 1 or state.round_state.actions_taken or state.round_state.defense_skill or effects.upkeep(state):
                    raise ValueError("Preparation requires one complete round doing only that task, without defense or maintained actions.")
                note = "prepared one exclusive round; +1D only for the same weapon and target next round with one exclusive attack action"
        effects.take_action(state)
        if req.action == "prepare":
            state.combat_preparation = D6CombatPreparation(encounter_id=encounter.id, round_number=encounter.round, weapon_id=item.id, target_id=req.target_id)
            from dungeonforge.rules.weg_gear_effects import mark_prepared
            if mark_prepared(session, actor.id, item.id, req.target_id):
                changes["macro_preparation"] = state.gear_context.preparation.model_dump()
        effects.settle_consciousness(state)
        encounter.d6_actions_started = encounter.d6_turn_acted = True
        summary = f"{actor.name}: {item.name}; {note}. One declared action used."
        encounter.combat_log.append(summary)
        weg_combat.bind_party(encounter, session.character)
        return commit(original, session, event(summary, success=success, changes=changes), "Personal combat gear action", boost=False)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
