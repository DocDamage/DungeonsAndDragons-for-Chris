import time
import uuid

from fastapi import APIRouter, HTTPException

from dungeonforge.context.pipeline import ActionTurn
from dungeonforge.game import weg_combat
from dungeonforge.rules.base import RuleEvaluationResult
from dungeonforge.rules.dice import RollResult
from dungeonforge.rules.weg_d6 import D6Roller, WEGD6Rules
from dungeonforge.rules.weg_models import D6BoostRequest, D6BoostWindow, D6CheckRequest, D6DeclareRequest, D6DefenseRequest, D6PoolRequest, D6RecoveryRequest, D6RoundState


router = APIRouter(prefix="/api/weg-d6", tags=["Native Star Wars WEG D6"])


def native_session():
    from dungeonforge.api import routes
    session = routes._ACTIVE_SESSION
    if session.edition != "weg_d6" or session.character.d6 is None:
        raise HTTPException(status_code=409, detail="Select the native Star Wars D6 campaign first.")
    if session.encounter and session.encounter.active:
        weg_combat.bind_party(session.encounter, session.character)
    from dungeonforge.rules.weg_gear_effects import refresh as refresh_gear
    refresh_gear(session)
    return session


def record(session, result, text, mode="check"):
    from dungeonforge.game.weg_force import after_roll
    after_roll(session, result)
    session.native_boost = None
    turn = ActionTurn(id=f"d6_{uuid.uuid4().hex}", mode=mode, player_input=text, rule_result=result, dm_output=result.summary, timestamp=time.time())
    session.history.append(turn)
    session.undone_history.clear()
    session.updated_at = time.time()
    return {"turn": turn, "eval_result": result, "session": session}


def require_on_foot(session):
    if session.vehicle_encounter:
        raise HTTPException(status_code=409, detail="Use the vehicle encounter's crew controls until the encounter ends.")
    from dungeonforge.game.weg_navigation import require_resolved
    try:
        require_resolved(session)
        from dungeonforge.game.weg_task_guards import require_available
        require_available(session, session.character.id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/pool")
def roll_pool(req: D6PoolRequest):
    try:
        roll = D6Roller.roll(req.code, mishap=req.mishap)
        from dungeonforge.api import routes
        routes._ACTIVE_SESSION.native_boost = None
        from dungeonforge.game.weg_force import after_roll
        after_roll(routes._ACTIVE_SESSION)
        if routes._ACTIVE_SESSION.vehicle_encounter:
            routes._ACTIVE_SESSION.vehicle_encounter.boost = None
        return roll
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/check")
def check(req: D6CheckRequest):
    session = native_session()
    require_on_foot(session)
    try:
        if session.encounter and session.encounter.active:
            if req.force_point:
                raise ValueError("Declare a Force Point before actions begin using round declarations.")
            combatant = weg_combat.actor(session.encounter, session.character.id)
            weg_combat.validate_turn(session.encounter, combatant)
            result = WEGD6Rules.roll_skill(combatant.d6, req.skill, req.difficulty, req.character_points, req.mishap)
            session.encounter.d6_actions_started = session.encounter.d6_turn_acted = True
            session.encounter.combat_log.append(result.summary)
        else:
            state = session.character.d6.model_copy(deep=True)
            if state.force.attempt:
                raise ValueError("Finish or cancel the Force activation before a separate scene check.")
            dark_actions = state.round_state.dark_side_called and state.round_state.actions_taken < state.round_state.declared_actions
            if dark_actions:
                if req.force_point:
                    raise ValueError("The call's round is already declared; use its remaining actions before a new Force Point declaration.")
            else:
                if state.round_state.actions_taken or state.round_state.force_active or state.round_state.dark_side_called:
                    WEGD6Rules.next_round(state)
                WEGD6Rules.declare(state, req.actions, req.force_point)
            result = WEGD6Rules.roll_skill(state, req.skill, req.difficulty, req.character_points, req.mishap)
            session.character.d6 = state
        response = record(session, result, f"{req.skill.replace('_', ' ').title()} vs {req.difficulty}")
        state = session.character.d6
        session.native_boost = D6BoostWindow(
            turn_id=response["turn"].id, actor_id=session.character.id, skill=req.skill,
            points_spent=req.character_points,
            limit=5 if req.skill in state.specializations else 2,
            force_used=req.force_point or state.round_state.force_active or state.round_state.dark_side_called,
            encounter_id=session.encounter.id if session.encounter and session.encounter.active else None,
            round_number=session.encounter.round if session.encounter and session.encounter.active else None,
            total=result.roll_result.total,
        )
        return response
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/declare")
def declare(req: D6DeclareRequest):
    session = native_session()
    require_on_foot(session)
    if not session.encounter or not session.encounter.active:
        raise HTTPException(status_code=409, detail="Round declarations require an active encounter; use the check form for scene rolls.")
    try:
        if session.encounter.d6_actions_started:
            raise ValueError("The action phase has begun; make new declarations next round.")
        combatant = weg_combat.actor(session.encounter, req.actor_id or session.character.id)
        WEGD6Rules.declare(combatant.d6, req.actions, req.force_point)
        from dungeonforge.game.weg_rewards import synchronize
        synchronize(session)
        session.encounter.combat_log.append(f"{combatant.name} declares {req.actions} action(s)" + (" and spends one Force Point." if req.force_point else "."))
        weg_combat.bind_party(session.encounter, session.character)
        session.updated_at = time.time()
        return {"session": session}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/defend")
def defend(req: D6DefenseRequest):
    session = native_session()
    require_on_foot(session)
    if not session.encounter or not session.encounter.active:
        raise HTTPException(status_code=409, detail="Declare defenses in an active encounter.")
    try:
        if session.encounter.d6_actions_started:
            raise ValueError("Defenses must be rolled before the action phase begins.")
        combatant = weg_combat.actor(session.encounter, req.actor_id or session.character.id)
        if req.skill == "lightsaber" and WEGD6Rules.weapon_skill(combatant.weapon) != "lightsaber":
            raise ValueError("Equip a lightsaber before parrying with it.")
        result = WEGD6Rules.defense(combatant.d6, req.skill, req.full, req.use_roll, req.character_points)
        session.encounter.combat_log.append(f"{combatant.name}: {result.summary}")
        weg_combat.bind_party(session.encounter, session.character)
        response = record(session, result, f"{combatant.name}: {'Full' if req.full else 'Normal'} {req.skill}")
        session.native_boost = D6BoostWindow(
            turn_id=response["turn"].id, actor_id=combatant.id, skill=req.skill, points_spent=req.character_points,
            limit=5, force_used=combatant.d6.round_state.force_active or combatant.d6.round_state.dark_side_called, defensive=True,
            encounter_id=session.encounter.id, round_number=session.encounter.round,
            total=result.roll_result.total,
        )
        return response
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/boost")
def boost(req: D6BoostRequest):
    session = native_session()
    require_on_foot(session)
    try:
        window = session.native_boost
        if window is None or not session.history or session.history[-1].id != window.turn_id:
            raise ValueError("Only the latest native check or defense can receive Character Points before another roll.")
        if window.force_used:
            raise ValueError("A Force Point was used on this roll; Character Points cannot be added.")
        if window.points_spent + req.points > window.limit:
            raise ValueError(f"This roll permits {window.limit} Character Points in total.")
        if window.encounter_id:
            if not session.encounter or not session.encounter.active or session.encounter.id != window.encounter_id or session.encounter.round != window.round_number:
                raise ValueError("The roll's combat round has ended.")
            state = weg_combat.actor(session.encounter, window.actor_id).d6
        else:
            state = session.character.d6
        if state.character_points < req.points:
            raise ValueError("Not enough Character Points.")
        if state.round_state.force_active or state.round_state.dark_side_called:
            raise ValueError("Force and Character Points cannot be combined this round.")
        turn = session.history[-1]
        result = turn.rule_result
        bonus = D6Roller.bonus_dice(req.points)
        roll = result.roll_result
        roll.raw_rolls.extend(bonus)
        roll.kept_rolls.extend(bonus)
        roll.bonus_rolls.extend(bonus)
        roll.total += sum(bonus)
        roll.breakdown += f"; +{req.points} CP {bonus} → {roll.total}"
        state.character_points -= req.points
        state.round_state.character_points_spent = True
        window.points_spent += req.points
        window.total = roll.total
        if window.defensive:
            state.round_state.defense_total = roll.total
            result.success = True
            result.summary = f"[WEG D6 {'Full' if state.round_state.full_defense else 'Normal'} Defense: {window.skill}] {roll.breakdown}."
        else:
            result.success = roll.total >= result.target_value
            result.summary = f"[WEG D6 Check: {window.skill}] vs difficulty {result.target_value}: {roll.breakdown} → {'SUCCESS' if result.success else 'FAILED'}."
        turn.dm_output = result.summary
        session.updated_at = time.time()
        if session.encounter and session.encounter.active:
            session.encounter.combat_log.append(result.summary)
            weg_combat.bind_party(session.encounter, session.character)
        return {"turn": turn, "eval_result": result, "session": session}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/initiative")
def initiative(winner_first: bool = True):
    session = native_session()
    if not session.encounter or not session.encounter.active:
        raise HTTPException(status_code=409, detail="No active encounter.")
    try:
        weg_combat.order_sides(session.encounter, winner_first)
        session.updated_at = time.time()
        return {"session": session}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/recover")
def recover(req: D6RecoveryRequest):
    session = native_session()
    require_on_foot(session)
    if session.encounter and session.encounter.active:
        raise HTTPException(status_code=409, detail="End combat before recovery; use defenses and action rolls during an encounter.")
    try:
        from dungeonforge.rules.weg_medical import active_project
        if active_project(session, session.character.id):
            raise ValueError("This patient has a saved medical procedure. Complete or cancel and reassess it before a separate recovery action.")
        if req.method in {"rest", "natural"}:
            from dungeonforge.game.weg_navigation import require_resolved
            require_resolved(session)
        state = session.character.d6.model_copy(deep=True)
        healer = state
        item = None
        if req.method == "medpac":
            item = next((item for item in session.character.inventory if "medpac" in item.name.lower() and item.quantity > 0), None)
            if item is None:
                raise ValueError("No medpac remains in inventory.")
            if req.healer_id and req.healer_id != session.character.id:
                from dungeonforge.game.weg_task_guards import require_available
                require_available(session, req.healer_id)
                companion = next((comp for comp in session.character.companions if comp.id == req.healer_id), None)
                if companion is None or companion.d6 is None:
                    raise ValueError("Choose a native D6 companion as healer.")
                healer = companion.d6
        old_wound = state.wound
        old_stuns, old_unconscious = state.stun_count, state.unconscious_rounds
        roll, summary = WEGD6Rules.recover(state, req.method, req.minutes, req.days, healer)
        session.character.d6 = state
        if req.method in {"rest", "natural"}:
            from dungeonforge.game.weg_force import advance_scene
            advance_scene(session, req.minutes * 12 if req.method == "rest" else int(req.days * 17280), excluded_ids={session.character.id})
        if item is not None:
            item.quantity -= 1
            if item.quantity == 0:
                session.character.inventory.remove(item)
        wound_rank = {"healthy": 0, "wounded": 1, "incapacitated": 2, "mortally_wounded": 3, "dead": 4}
        result = RuleEvaluationResult(
            action_type="recovery", success=state.wound != "dead" and (req.method == "rest" or wound_rank[state.wound] < wound_rank[old_wound] or state.stun_count < old_stuns or state.unconscious_rounds < old_unconscious),
            roll_result=roll or RollResult(expression="Rest", dice_count=0, die_type=6, system="weg_d6", breakdown="No dice required"),
            summary=f"[WEG D6 Recovery] {summary}", state_changes={"wound": state.wound},
        )
        return record(session, result, f"{req.method.title()} recovery", "rest")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
