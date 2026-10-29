"""Actual source equipment and per-action GM conditions, without client bonuses."""
from fastapi import APIRouter, HTTPException

from dungeonforge.api.weg_routes import native_session
from dungeonforge.api.weg_force_routes import commit
from dungeonforge.api.weg_advancement_routes import event
from dungeonforge.game.weg_force import advance_scene
from dungeonforge.game.weg_navigation import require_resolved
from dungeonforge.game.weg_task_guards import require_available
from dungeonforge.rules import weg_gear_effects as gear, weg_force_effects as effects
from dungeonforge.rules.weg_gear_effect_models import GearFactsRequest, GearPrepareRequest

router = APIRouter(prefix="/api/weg-d6/gear-effects", tags=["Native conditional equipment"])


def working(req):
    original = native_session()
    session = original.model_copy(deep=True)
    gear.refresh(session)
    if req.expected_updated_at != session.updated_at or not req.reason.strip():
        raise ValueError("Review the current actual equipment and record the GM task/target/scene facts.")
    return original, session


@router.get("/catalog")
def catalog():
    return {"source": gear.SOURCE, "notes": [
        "Corellian PowerSuit adds1D to lifting only, not to all Strength, melee damage or damage resistance.",
        "MFTAS adds2D to literal Perception attribute checks in darkness, smoke or other visibility obstruction; it does not grant a blanket bonus to all Perception-based skills.",
        "MFTAS adds2D to ranged weapon skill uses against a target moving more than10 meters in the round. Exactly10m does not qualify.",
        "Macrobinoculars add3D to an actual appropriate Perception/search-oriented visual task beyond100m. An average set reaches1km; actual variant model ranges require GM facts.",
        "Linked macrobinoculars add3D to medium/long blaster shots only, with actual installed programming software, a steady sniper rest and at least one real preparation round. They do not extend the blaster's range or change its saved statistics.",
        "Select actual source inventory IDs. Functional confirmations record current damage; new damage invalidates that confirmation. Severely damaged or destroyed gear is unusable.",
        "Visual/target facts apply to the next recorded action and the current encounter round. Reconfirm them for another action. Confirming an unchanged position can preserve a real matching preparation; it cannot create one.",
        "These physical equipment dice are added after Force Point doubling. Independent printed effects can apply together; duplicate instruments cannot multiply an effect."]}


@router.get("/state")
def state():
    session = native_session().model_copy(deep=True)
    gear.refresh(session)
    return {"actors": [{"id": actor_id, "facts": state.gear_context} for actor_id, (state, _) in gear.roster(session).items()], "source": gear.SOURCE}


@router.post("/configure")
def configure(req: GearFactsRequest):
    try:
        original, session = working(req)
        state = gear.configure(session, req)
        result = event(f"GM confirms actual conditional equipment for {req.actor_id}; target {req.target_id or 'no target condition'}, visual skill {req.visual_skill}. {req.reason.strip()}",
            category="Equipment", changes={"actor_id": req.actor_id, "gear_facts": state.gear_context.model_dump()})
        return commit(original, session, result, "Confirm conditional equipment", boost=False)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/prepare")
def prepare(req: GearPrepareRequest):
    try:
        original, session = working(req)
        if session.encounter and session.encounter.active or session.vehicle_encounter:
            raise ValueError("During personal combat use the actual weapon's Prepare action for a full exclusive round; end vehicle combat before on-foot sniper preparation.")
        require_resolved(session)
        require_available(session, req.actor_id)
        found = gear.roster(session).get(req.actor_id)
        if not found:
            raise ValueError("Choose an actual native actor.")
        state = found[0]
        context = state.gear_context
        weapon = gear.actual(context, context.linked_weapon_id)
        if not state.can_act or state.force.attempt or effects.upkeep(state):
            raise ValueError("One full preparation round requires an available conscious actor without another exclusive activation or maintained action.")
        if (context.macro_mode != "linked" or not gear.macro_function(context) or not weapon or not gear.worn(context, weapon)
                or weapon.weapon_damage_state in gear.UNUSABLE or context.target_id != req.target_id
                or not context.software_confirmed or not context.software_facts.strip() or not context.steady_rest):
            raise ValueError("Confirm the actual linked source macro, drawn blaster, software, target and steady position before preparation.")
        advance_scene(session, 1)
        gear.refresh(session)
        success = bool(state.can_act)
        if success:
            effects.take_action(state)
            success = gear.mark_prepared(session, req.actor_id, weapon.id, req.target_id, downtime=True)
        summary = "A full shared scene round passed; actual linked sniper preparation recorded." if success else "A full shared scene round passed, but injury or changed equipment interrupted preparation."
        return commit(original, session, event(summary + " " + req.reason.strip(), category="Equipment", success=success,
            changes={"actor_id": req.actor_id, "target_id": req.target_id, "prepared": success, "rounds": 1,
                "macro_preparation": state.gear_context.preparation.model_dump() if success else None}), "Prepare linked macrobinoculars", boost=False)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
