"""Transactional native Force actions in scenes, personal combat, and ship stations."""

import time

from fastapi import APIRouter, HTTPException

from dungeonforge.api.weg_routes import native_session, record
from dungeonforge.game import weg_force as world
from dungeonforge.rules import weg_force as rules, weg_force_effects as effects
from dungeonforge.rules.base import RuleEvaluationResult
from dungeonforge.rules.weg_d6 import D6Roller, WEGD6Rules
from dungeonforge.rules.weg_force_catalog import POWERS, PROXIMITY, RELATIONSHIP, training_errors
from dungeonforge.rules.weg_force_models import (
    ForceBoostWindow, ForceContinueRequest, ForceEffect, ForceManageRequest,
    ForcePowerRequest, ForceReactionRequest, ForceTargetRequest,
)
from dungeonforge.rules.weg_models import D6BoostRequest


router = APIRouter(prefix="/api/weg-d6/force", tags=["Native WEG Force powers"])


def working():
    original = native_session()
    session = original.model_copy(deep=True)
    world.synchronize(session)
    return original, session


def commit(original, session, result=None, label="Force action", source=None, boost=True):
    if result:
        response = record(session, result, label, "check")
        if boost and source and source.state.force.attempt and source.state.force.attempt.rolls:
            attempt = source.state.force.attempt
            if attempt.id == result.state_changes.get("activation_id"):
                session.force_boost = ForceBoostWindow(actor_id=source.id, turn_id=response["turn"].id, attempt_id=attempt.id,
                    points_spent=attempt.rolls[-1].character_points, force_used=source.state.round_state.force_active or source.state.round_state.dark_side_called)
    else:
        session.force_boost = session.native_boost = None
        response = {"session": session}
    world.refresh_encounters(session)
    session.updated_at = time.time()
    for field in type(original).model_fields:
        setattr(original, field, getattr(session, field))
    response["session"] = original
    return response


def is_combat(session):
    return bool((session.encounter and session.encounter.active) or (session.vehicle_encounter and session.vehicle_encounter.active))


def extra_penalty(source):
    return source.crew.control_penalty if source.crew else 0


@router.get("/catalog")
def catalog():
    return {"powers": [spec.model_dump() for spec in POWERS.values()], "relationship": RELATIONSHIP, "proximity": PROXIMITY}


@router.get("/actors")
def actors():
    session = native_session()
    return {"actors": [{"id": person.id, "name": person.name, "race": person.race, "d6": person.state} for person in world.synchronize(session).values()]}


@router.post("/begin")
def begin(req: ForcePowerRequest):
    original, session = working()
    try:
        source, target, spec = world.normalize_request(session, req)
        world.validate_turn(session, source, req.power_id)
        if not is_combat(session):
            world.scene_declaration(source, req, spec)
        result = rules.begin(source.state, req, source.id, target.state if target else None, in_combat=is_combat(session), extra_penalty=extra_penalty(source))
        if req.power_id == "reduce_injury":
            result.state_changes["reaction"] = True
            if result.state_changes.get("complete"):
                if session.encounter:
                    from dungeonforge.game import weg_combat
                    weg_combat.refresh(session.encounter)
                    if any(not person.is_defeated for person in session.encounter.combatants if person.is_player) and any(not person.is_defeated for person in session.encounter.combatants if not person.is_player):
                        session.encounter.active = True
                if session.vehicle_encounter and any(not craft.out_of_fight for craft in session.vehicle_encounter.craft if craft.is_player) and any(not craft.out_of_fight for craft in session.vehicle_encounter.craft if not craft.is_player):
                    session.vehicle_encounter.active = True
        world.mark_action(session, source, result)
        return commit(original, session, result, f"{source.name}: {spec.name}", source)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/continue")
def continue_power(req: ForceContinueRequest):
    original, session = working()
    try:
        source = world.actor(session, req.actor_id)
        attempt = source.state.force.attempt
        if not attempt:
            raise ValueError("No Force activation is in progress for this actor.")
        if attempt.preparation_remaining and req.force_point:
            raise ValueError("Finish preparation before declaring a Force Point for the actual skill rolls.")
        world.validate_turn(session, source, attempt.power_id)
        if not is_combat(session):
            world.scene_declaration(source, req, POWERS[attempt.power_id], continuation=True)
        elif req.force_point:
            raise ValueError("Declare Force Point use before round actions.")
        target = world.actor(session, attempt.target_id) if attempt.target_id and attempt.target_id != source.id else None
        result = rules.roll_next(source.state, target.state if target else None, req.character_points, req.mishap, extra_penalty=extra_penalty(source))
        world.mark_action(session, source, result)
        return commit(original, session, result, f"{source.name}: continue {POWERS[attempt.power_id].name}", source)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/boost")
def boost(req: D6BoostRequest):
    original, session = working()
    try:
        window = session.force_boost
        if not window or not session.history or session.history[-1].id != window.turn_id:
            raise ValueError("Only the latest unresolved Force component can receive CP before another roll/action.")
        source = world.actor(session, window.actor_id)
        attempt = source.state.force.attempt
        if not attempt or attempt.id != window.attempt_id:
            raise ValueError("This activation is no longer pending.")
        if window.force_used or source.state.round_state.force_active or source.state.round_state.dark_side_called:
            raise ValueError("Force and Character Points cannot be combined.")
        if window.points_spent + req.points > window.limit or req.points > source.state.character_points:
            raise ValueError("A Force component allows at most two available Character Points in total.")
        component = attempt.rolls[-1]
        bonus = D6Roller.bonus_dice(req.points)
        component.roll.raw_rolls.extend(bonus)
        component.roll.kept_rolls.extend(bonus)
        component.roll.bonus_rolls.extend(bonus)
        component.roll.total += sum(bonus)
        component.roll.breakdown += f"; +{req.points} CP {bonus} → {component.roll.total}"
        component.character_points += req.points
        component.success = component.roll.total > component.difficulty if attempt.power_id == "injure_kill" else component.roll.total >= component.difficulty
        attempt.failed = not component.success
        source.state.character_points -= req.points
        source.state.round_state.character_points_spent = True
        window.points_spent += req.points
        result = rules.activation_result(attempt, component, f"{component.skill.title()} updated: {component.roll.breakdown} vs {component.difficulty} → {'SUCCESS' if component.success else 'FAILED'}.")
        if not attempt.failed and len(attempt.rolls) == len(attempt.skills):
            target = world.actor(session, attempt.target_id) if attempt.target_id and attempt.target_id != source.id else None
            rules.finish(source.state, target.state if target else None, result)
            session.force_boost = None
            if attempt.power_id == "reduce_injury":
                if session.encounter:
                    from dungeonforge.game import weg_combat
                    weg_combat.refresh(session.encounter)
                    if all(any(not person.is_defeated for person in session.encounter.combatants if person.is_player == side) for side in (True, False)):
                        session.encounter.active = True
                if session.vehicle_encounter and all(any(not craft.out_of_fight for craft in session.vehicle_encounter.craft if craft.is_player == side) for side in (True, False)):
                    session.vehicle_encounter.active = True
        turn = session.history[-1]
        previous_events = turn.rule_result.state_changes.get("corruption_events", [])
        if previous_events:
            from dungeonforge.rules.weg_dark_models import CorruptionEvent
            from dungeonforge.rules.weg_dark_side import event_note
            result.state_changes["corruption_events"] = previous_events
            result.summary += " " + " ".join(event_note(CorruptionEvent.model_validate(item)) for item in previous_events)
        turn.rule_result, turn.dm_output = result, result.summary
        response = commit(original, session)
        if source.state.force.attempt:
            original.force_boost = window
        return {**response, "turn": turn, "eval_result": result}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/manage")
def manage(req: ForceManageRequest):
    original, session = working()
    try:
        if req.action in {"leave_emptiness", "heal"}:
            from dungeonforge.game.weg_navigation import require_resolved
            require_resolved(session)
        source = world.actor(session, req.actor_id)
        state = source.state
        effect = next((effect for effect in state.force.effects if effect.id == req.effect_id), None)
        if req.action == "advance":
            world.advance_scene(session, req.rounds)
            result = RuleEvaluationResult(action_type="force_time", success=True, roll_result=rules.empty_roll("Time passes"), summary=f"[WEG D6 Force Time] {req.rounds} round(s) / {req.rounds * 5} seconds passed; preparation, stuns, mortality, and ongoing effects advanced.")
        elif req.action == "cancel":
            effects.cancel_attempt(state)
            result = RuleEvaluationResult(action_type="force_cancel", success=True, roll_result=rules.empty_roll("Cancel activation"), summary=f"[WEG D6 Force] {source.name} abandons the unfinished activation; spent actions and points are not refunded.")
        elif req.action == "drop":
            if not effect or effect.recipient or effect.power_id in {"emptiness", "hibernation_trance", "transfer_force"}:
                raise ValueError("Select a maintained power you own; trances require their waking/exit procedure.")
            state.force.effects = [item for item in state.force.effects if item.id != effect.id]
            result = RuleEvaluationResult(action_type="force_drop", success=True, roll_result=rules.empty_roll("Drop power"), summary=f"[WEG D6 Force] {source.name} drops {POWERS.get(effect.power_id).name if effect.power_id in POWERS else effect.power_id}; its upkeep ends.")
        elif req.action == "wake":
            if not effect or effect.power_id != "hibernation_trance" or not req.stimulus:
                raise ValueError("Confirm that the declared waking stimulus occurred; timed waking happens when its duration expires.")
            state.force.effects.remove(effect)
            result = RuleEvaluationResult(action_type="force_wake", success=True, roll_result=rules.empty_roll("Trance stimulus"), summary=f"[WEG D6 Force] {source.name} wakes from Hibernation Trance in response to the declared stimulus.")
        elif req.action == "leave_emptiness":
            if not effect or effect.power_id != "emptiness" or state.wound == "dead":
                raise ValueError("Select the living character's Emptiness effect.")
            elapsed = effect.parameters.get("meditated_rounds", 0)
            planned = effect.parameters["planned_rounds"]
            last = effect.parameters.get("last_exit_round")
            injury_exit = effect.parameters.get("injury_exit", False)
            if not injury_exit and (elapsed < planned or (last is not None and state.force.elapsed_rounds - last < 720)):
                raise ValueError("Exit at the declared time, once per later hour, or after injury worse than stun.")
            if not is_combat(session):
                state.round_state.actions_taken = 0
                state.round_state.declared_actions = 1
            component = rules.force_component(state, "control", 20, req.character_points, internal=True, extra_penalty=extra_penalty(source))
            effect.parameters["last_exit_round"] = state.force.elapsed_rounds
            effect.parameters["injury_exit"] = False
            if component.success:
                state.force.effects.remove(effect)
                state.force.effects.append(ForceEffect(power_id="emptiness_bonus", source_id=source.id, target_id=source.id, rounds_remaining=max(1, elapsed), parameters={"meditated_rounds": elapsed}))
            result = RuleEvaluationResult(action_type="force_exit", success=component.success, roll_result=component.roll, target_value=20, force_rolls=[component], summary=f"[WEG D6 Emptiness Exit] {component.roll.breakdown} vs 20 → {'AWAKE; Force bonus lasts ' + str(elapsed) + ' rounds' if component.success else 'FAILED; meditation continues'}.")
        else:
            if is_combat(session):
                raise ValueError("Resolve accelerated natural healing outside active combat.")
            grant = next((effect for effect in state.force.effects if effect.power_id == "accelerate_another_healing"), None)
            donor_present = not grant or grant.source_id in world.actors(session)
            result = rules.accelerated_heal(state, touching=req.stimulus if grant else True, donor_present=donor_present)
        return commit(original, session, result, f"{source.name}: {req.action.replace('_', ' ')}", boost=False)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/prepare-reaction")
def prepare_reaction(req: ForceReactionRequest):
    original, session = working()
    try:
        source = world.actor(session, req.actor_id)
        state = source.state
        if not session.encounter or not session.encounter.active or session.vehicle_encounter:
            raise ValueError("Prepare personal blaster reactions in a native character encounter; they do not shield a ship's hull.")
        power_id = "absorb_dissipate_energy" if req.action == "absorb_energy" else "lightsaber_combat"
        if power_id not in state.force.known_powers or training_errors(state):
            raise ValueError("Learn this power and all required Force training first.")
        WEGD6Rules.validate_action(state, "control", req.character_points, defensive=req.action == "absorb_energy")
        if req.action == "absorb_energy":
            if state.origin.force_tradition == "tyia":
                raise ValueError("The Tyia's one-minute minimum cannot prepare an immediate incoming-energy reaction.")
            state.round_state.absorb_energy = {"character_points": req.character_points, "mishap": req.mishap}
            note = "Absorb/Dissipate Energy is prepared for one incoming personal energy hit. Its actual damage determines the Control difficulty."
        else:
            if req.character_points > 2 or not effects.find_effect(state, "lightsaber_combat") or state.round_state.defense_skill != "lightsaber":
                raise ValueError("Activate Lightsaber Combat, roll a lightsaber parry, and reserve an extra Control action (max 2 CP).")
            if not req.attacker_id or not req.target_id or req.target_id == source.id:
                raise ValueError("Declare the specific shooter's shot and a different reflected-bolt target.")
            world.actor(session, req.attacker_id)
            world.actor(session, req.target_id)
            state.round_state.redirect_blaster = req.model_dump()
            note = "One specified shooter's blaster bolt will be redirected if the declared lightsaber parry stops it; Control and original bolt damage resolve normally."
        result = RuleEvaluationResult(action_type="force_reaction", success=True, roll_result=rules.empty_roll("Prepare reaction"), summary=f"[WEG D6 Force Reaction] {source.name}: {note} No reaction die/action is spent until it triggers.")
        return commit(original, session, result, f"{source.name}: prepare {req.action.replace('_', ' ')}", boost=False)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/telekinetic-attack")
def telekinetic_attack(req: ForceTargetRequest):
    original, session = working()
    try:
        source, target = world.actor(session, req.actor_id), world.actor(session, req.target_id)
        if source.id == target.id:
            raise ValueError("Choose a different living target.")
        world.validate_turn(session, source)
        result = rules.telekinetic_attack(source.state, target.state, req.effect_id, req.character_points, req.mishap, extra_penalty(source))
        if result.wound_result:
            result.state_changes["force_injury_targets"] = [target.id]
        world.mark_action(session, source, result)
        return commit(original, session, result, f"{source.name}: telekinetic attack", boost=False)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/detect-life")
def detect_life(req: ForceTargetRequest):
    original, session = working()
    try:
        from dungeonforge.game.weg_navigation import require_resolved
        require_resolved(session)
        source, target = world.actor(session, req.actor_id), world.actor(session, req.target_id)
        if "droid" in target.race.lower() or source.id == target.id:
            raise ValueError("Choose another living creature within ten meters.")
        result = rules.life_detection_scan(source.state, target.state, req.character_points, req.mishap, extra_penalty(source))
        return commit(original, session, result, f"{source.name}: detect approaching life (GM confirms ≤10m)", boost=False)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/touch")
def brawling_touch(req: ForceTargetRequest):
    original, session = working()
    try:
        if not session.encounter or not session.encounter.active or session.vehicle_encounter:
            raise ValueError("Resolve a brawling touch in personal combat; the GM confirms physical contact in a scene.")
        source, target = world.actor(session, req.actor_id), world.actor(session, req.target_id)
        if source.id == target.id or target.state.wound == "dead":
            raise ValueError("Choose another living target within brawling reach.")
        world.validate_turn(session, source)
        defense = target.state.round_state
        number = 10
        if defense.defense_skill in {"brawling_parry", "melee_parry", "lightsaber"} and defense.defense_total is not None:
            parry = defense.defense_total + (5 if defense.defense_skill == "melee_parry" else 0)
            number = number + parry if defense.full_defense else parry if defense.use_defense_roll else number
        result = WEGD6Rules.roll_skill(source.state, "brawling", max(1, number), req.character_points, req.mishap)
        result.action_type = "force_touch"
        result.target_value, result.success = number, result.roll_result.total >= number
        result.summary = f"[WEG D6 Brawling Touch] {result.roll_result.breakdown} vs {number}: {'SUCCESS' if result.success else 'FAILED'}."
        if result.success:
            source.state.round_state.touched_targets.append(target.id)
        result.summary += " Brawling touch only; no damage. GM confirms physical reach. A successful touch permits Injure/Kill in another declared action this round."
        world.mark_action(session, source, result)
        return commit(original, session, result, f"{source.name}: brawling touch on {target.name}", boost=False)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
