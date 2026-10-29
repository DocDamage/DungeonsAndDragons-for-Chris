"""Transactional native craft endpoints: reject invalid actions without spending resources."""

import time
import uuid

from fastapi import APIRouter, HTTPException

from dungeonforge.api.weg_routes import native_session, record
from dungeonforge.game import weg_vehicle_combat as combat
from dungeonforge.game.weg_vehicle_presets import vehicle_presets
from dungeonforge.rules.weg_d6 import WEGD6Rules
from dungeonforge.rules.weg_models import D6RoundState, D6BoostRequest
from dungeonforge.rules.weg_d6 import D6Roller
from dungeonforge.rules.weg_vehicle_models import (
    D6FleetAddRequest, D6Vehicle, D6VehicleAttackRequest, D6VehicleDeclareRequest,
    D6VehicleDodgeRequest, D6VehicleMoveRequest, D6VehicleShieldRequest,
    D6VehicleStartRequest, D6VehicleSystemRequest, D6VehicleBoostWindow,
)
from dungeonforge.rules.weg_vehicles import WEGVehicleRules


router = APIRouter(prefix="/api/weg-d6/vehicles", tags=["Native WEG vehicles and starships"])


def session_without_combat():
    session = native_session()
    from dungeonforge.rules.weg_hazards import drowning_people
    if drowning_people(session):
        raise HTTPException(status_code=409, detail="Resolve the saved drowning emergency before fleet actions.")
    from dungeonforge.rules.weg_navigation import active
    if active(session):
        raise HTTPException(status_code=409, detail="Finish or resolve the current hyperspace journey before changing the fleet or starting craft combat.")
    if (session.encounter and session.encounter.active) or session.vehicle_encounter:
        raise HTTPException(status_code=409, detail="End the current encounter before changing the fleet or starting another.")
    return session


def working_encounter():
    session = native_session()
    if not session.vehicle_encounter or not session.vehicle_encounter.active:
        raise HTTPException(status_code=409, detail="Start a vehicle/starship encounter first.")
    return session, session.vehicle_encounter.model_copy(deep=True)


def commit(session, encounter, result=None, text="Craft action", boost_kind=None, request=None, keep_boost=False):
    if not keep_boost:
        encounter.boost = None
        session.force_boost = None
    session.vehicle_encounter = encounter
    session.native_boost = None
    combat.bind_party(session, encounter)
    from dungeonforge.game.weg_force import synchronize
    synchronize(session)
    from dungeonforge.game.weg_rewards import synchronize as sync_rewards
    sync_rewards(session)
    session.updated_at = time.time()
    if result:
        response = record(session, result, text, "attack" if result.action_type == "vehicle_attack" else "check")
        if boost_kind:
            _, crew = combat.find_actor(encounter, request.actor_id)
            encounter.boost = D6VehicleBoostWindow(actor_id=crew.id, turn_id=response["turn"].id, kind=boost_kind,
                points_spent=request.character_points, force_used=crew.d6.round_state.force_active or crew.d6.round_state.dark_side_called,
                allocation=request.allocation if boost_kind == "shields" else {})
        return response
    return {"session": session}


@router.get("/catalog")
def catalog():
    return {"presets": [{**craft.model_dump(), "id": key} for key, craft in vehicle_presets().items()]}


@router.post("/add")
def add(req: D6FleetAddRequest):
    session = session_without_combat()
    try:
        if len(session.vehicles) >= 20:
            raise ValueError("The fleet supports up to twenty party craft.")
        presets = vehicle_presets()
        if req.preset not in presets:
            raise ValueError("Unknown craft preset.")
        craft = combat.configure_party(presets[req.preset], session)
        craft.id = f"craft_{uuid.uuid4().hex[:12]}"
        craft.occupied = False
        session.vehicles.append(craft)
        session.updated_at = time.time()
        return {"session": session}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/update")
def update(craft: D6Vehicle):
    session = session_without_combat()
    try:
        index = next((i for i, item in enumerate(session.vehicles) if item.id == craft.id), None)
        if index is None:
            raise ValueError("Party craft not found.")
        craft.is_player = True
        craft.repair_projects = session.vehicles[index].repair_projects
        combat.configure_party(craft, session)
        session.vehicles[index] = craft
        session.updated_at = time.time()
        return {"session": session}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/start")
def start(req: D6VehicleStartRequest):
    session = session_without_combat()
    try:
        encounter = combat.start(session, req.vehicle_id, req.enemies, req.environment)
        for craft in session.vehicles:
            craft.occupied = False
        return commit(session, encounter)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/declare")
def declare(req: D6VehicleDeclareRequest):
    session, encounter = working_encounter()
    try:
        if encounter.actions_started:
            raise ValueError("Make declarations before actions begin.")
        craft, crew = combat.find_actor(encounter, req.actor_id)
        if not combat.eligible(craft, crew):
            raise ValueError("This craft/crew cannot declare actions.")
        if "pilot" not in crew.stations and (req.moves or req.half_speed):
            raise ValueError("Only the pilot declares movement.")
        if "pilot" in crew.stations:
            if craft.frozen_rounds and (req.moves != craft.forced_moves or req.half_speed != craft.forced_half_speed):
                raise ValueError("Frozen controls must maintain the previous declared speed and direction.")
            if req.half_speed and req.moves != 1:
                raise ValueError("Half-speed movement must be exactly one move, with no other moves.")
            if not req.half_speed and req.moves > craft.max_moves:
                raise ValueError("Damage has reduced this craft's maximum moves.")
            if req.half_speed and craft.max_moves == 0 and not craft.half_speed_only:
                raise ValueError("This craft can no longer move.")
            if req.moves > req.actions and not req.half_speed:
                raise ValueError("Each normal move must be included in the pilot's declared actions.")
            craft.declared_moves, craft.half_speed = req.moves, req.half_speed
        WEGD6Rules.declare(crew.d6, req.actions, req.force_point)
        encounter.combat_log.append(f"{crew.name}: {req.actions} action(s), {req.moves} move(s){' at half speed' if req.half_speed else ''}{', Force Point spent' if req.force_point else ''}.")
        return commit(session, encounter)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/initiative")
def initiative(winner_first: bool = True):
    session, encounter = working_encounter()
    try:
        combat.order_sides(encounter, winner_first)
        return commit(session, encounter)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/dodge")
def dodge(req: D6VehicleDodgeRequest):
    session, encounter = working_encounter()
    try:
        if encounter.actions_started:
            raise ValueError("Roll vehicle dodges before actions begin.")
        craft, crew = combat.find_actor(encounter, req.actor_id)
        result = WEGVehicleRules.dodge(craft, crew, req.full, req.character_points, req.mishap)
        encounter.combat_log.append(result.summary)
        return commit(session, encounter, result, f"{craft.name}: vehicle dodge", "dodge", req)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/shields")
def shields(req: D6VehicleShieldRequest):
    session, encounter = working_encounter()
    try:
        if encounter.actions_started:
            raise ValueError("Deploy shields during the defensive phase, before actions begin.")
        craft, crew = combat.find_actor(encounter, req.actor_id)
        result = WEGVehicleRules.shields(craft, crew, req.allocation, req.difficulty, req.character_points, req.mishap)
        encounter.combat_log.append(result.summary)
        return commit(session, encounter, result, f"{craft.name}: deploy shields", "shields", req)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/attack")
def attack(req: D6VehicleAttackRequest):
    session, encounter = working_encounter()
    try:
        craft, crew = combat.validate_turn(encounter, req.actor_id)
        target = combat.find_craft(encounter, req.target_id)
        if target.id == craft.id:
            raise ValueError("Select another craft as target.")
        weapon = next((weapon for weapon in craft.weapons if weapon.id == req.weapon_id), None)
        if weapon is None:
            raise ValueError("Weapon not found aboard this craft.")
        result = WEGVehicleRules.attack(craft, crew, target, weapon, req, encounter.environment)
        combat.finish(encounter, result)
        return commit(session, encounter, result, f"{craft.name}: {weapon.name} at {target.name}")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/boost")
def boost(req: D6BoostRequest):
    session, encounter = working_encounter()
    try:
        window = encounter.boost
        if not window or not session.history or session.history[-1].id != window.turn_id:
            raise ValueError("Only the latest craft dodge or shields roll can receive points before another roll/action.")
        craft, crew = combat.find_actor(encounter, window.actor_id)
        if window.force_used or crew.d6.round_state.force_active or crew.d6.round_state.dark_side_called:
            raise ValueError("Force and Character Points cannot be combined.")
        if window.points_spent + req.points > 5 or req.points > crew.d6.character_points:
            raise ValueError("A defense allows at most five available Character Points in total.")
        turn = session.history[-1].model_copy(deep=True)
        result = turn.rule_result
        roll = result.roll_result
        bonus = D6Roller.bonus_dice(req.points)
        roll.raw_rolls.extend(bonus)
        roll.kept_rolls.extend(bonus)
        roll.bonus_rolls.extend(bonus)
        roll.total += sum(bonus)
        roll.breakdown += f"; +{req.points} CP {bonus} → {roll.total}"
        window.points_spent += req.points
        crew.d6.character_points -= req.points
        crew.d6.round_state.character_points_spent = True
        if window.kind == "dodge":
            craft.dodge_roll = roll
            result.summary = f"[WEG D6 Vehicle Dodge] {craft.name}: {roll.breakdown}; scale caps apply per incoming weapon."
        else:
            result.success = roll.total >= result.target_value
            if result.success:
                from dungeonforge.rules.weg_vehicles import pips
                craft.shield_allocation = {arc: code for arc, code in window.allocation.items() if pips(code)}
            result.summary = f"[WEG D6 Shields] {craft.name}: {roll.breakdown} vs {result.target_value} → {'DEPLOYED' if result.success else 'FAILED'}."
        turn.dm_output = result.summary
        session.history[-1] = turn
        encounter.combat_log.append(result.summary)
        commit(session, encounter, keep_boost=True)
        return {"session": session, "turn": turn, "eval_result": result}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/move")
def move(req: D6VehicleMoveRequest):
    session, encounter = working_encounter()
    try:
        craft, crew = combat.validate_turn(encounter, req.actor_id)
        target = combat.find_craft(encounter, req.ram_target_id) if req.ram_target_id else None
        if target and (target.id == craft.id or target.damage == "destroyed"):
            raise ValueError("Choose another intact craft for a ram.")
        result = WEGVehicleRules.move(craft, crew, req, encounter.environment, target)
        combat.finish(encounter, result)
        return commit(session, encounter, result, f"{craft.name}: {'ram' if target else 'move'}")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/system")
def system(req: D6VehicleSystemRequest):
    session, encounter = working_encounter()
    try:
        result = combat.system_action(encounter, req)
        combat.finish(encounter, result)
        return commit(session, encounter, result, req.action.replace("_", " "))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/next")
def next_turn():
    session, encounter = working_encounter()
    combat.next_turn(encounter)
    response = commit(session, encounter)
    from dungeonforge.game.weg_force import after_roll
    after_roll(session)
    return response


@router.post("/end")
def end():
    session = native_session()
    if session.vehicle_encounter:
        encounter = session.vehicle_encounter
        for craft in encounter.craft:
            for crew in craft.crew:
                crew.d6.round_state = D6RoundState()
                crew.d6.force.saber_locked = False
                for effect in crew.d6.force.effects:
                    effect.activation_round = False
            if all(crew.evacuated for crew in craft.crew):
                craft.occupied = False
        combat.bind_party(session, encounter)
    session.vehicle_encounter = None
    session.native_boost = None
    session.force_boost = None
    return {"session": session}


@router.post("/advance")
def advance():
    session = session_without_combat()
    notes = combat.advance_fleet_time(session, 1, advance_characters=True)
    session.updated_at = time.time()
    return {"session": session, "effects": notes}


@router.post("/disembark/{vehicle_id}")
def disembark(vehicle_id: str):
    session = session_without_combat()
    craft = next((craft for craft in session.vehicles if craft.id == vehicle_id), None)
    if not craft:
        raise HTTPException(status_code=404, detail="Party craft not found.")
    craft.occupied = False
    for crew in craft.crew:
        crew.evacuated = True
    return {"session": session}
