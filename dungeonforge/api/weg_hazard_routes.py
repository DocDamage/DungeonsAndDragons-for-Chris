"""Actual falling injuries, fatigue and saved round-by-round drowning."""
from fastapi import APIRouter, HTTPException
from dungeonforge.api.weg_routes import native_session
from dungeonforge.api.weg_force_routes import commit
from dungeonforge.api.weg_advancement_routes import downtime, event as record_event, student
from dungeonforge.game.weg_force import advance_scene
from dungeonforge.game.weg_navigation import require_resolved
from dungeonforge.rules.weg_d6 import WEGD6Rules, D6Roller, parse_code, skill_key
from dungeonforge.rules.dice import DiceRoller
from dungeonforge.rules.base import RuleEvaluationResult
from dungeonforge.rules.weg_models import D6RoundState, normalize_code
from dungeonforge.rules.weg_hazard_models import HazardFall, HazardExertion, HazardRest, HazardSwim, HazardDrowningAction, HazardNext, HazardActor, D6Drowning
from dungeonforge.rules import weg_hazards as rules

router = APIRouter(prefix="/api/weg-d6/hazards", tags=["Native environmental hazards"])


def event(*args, **kwargs):
    return record_event(*args, category="Hazards", **kwargs)


def working(req, *, routine=True):
    original = native_session()
    session = original.model_copy(deep=True)
    person = student(session, req.actor_id)
    if not req.reason.strip():
        raise ValueError("Record the actual hazard, environment and GM scene facts.")
    if routine:
        downtime(session)
        from dungeonforge.game.weg_task_guards import require_available
        require_available(session, person.id)
    return original, session, person


def points(state, req, extra=0):
    if req.force_point and (req.character_points or extra) or req.character_points + extra > state.character_points or req.force_point and not state.force_points:
        raise ValueError("Choose available Character Points or a Force Point, never both.")


def save(original, session, person, result, label, req):
    person.d6.hazards.history.append({"operation": label, "reason": req.reason.strip(), "summary": result.summary,
        "success": result.success, "roll": result.roll_result.model_dump() if result.roll_result else None,
        "details": result.state_changes})
    result.summary = f"[WEG {label}] {person.name}: {result.summary} {req.reason.strip()}"
    return commit(original, session, result, label, boost=False)


@router.get("/catalog")
def catalog():
    return {"falling": [{"min": low, "max": high, "dice": dice} for low, high, dice in rules.FALLS],
        "bands": [{"name": name, "min": low, "max": high} for name, low, high in rules.BANDS],
        "source": "WEG40055 (1992), printed pp.79 (Willpower), 86 (Stamina/Swimming), 97 (falling)."}


@router.post("/fall")
def fall(req: HazardFall):
    try:
        original, session, person = working(req, routine=False)
        state = person.d6
        if state.wound == "dead":
            raise ValueError("This character is already dead.")
        if req.damage_code is not None:
            code = normalize_code(req.damage_code)
        elif req.standard_gravity:
            code = f"{rules.falling_dice(req.meters)}D"
        else:
            raise ValueError("Nonstandard gravity requires an explicit GM falling damage code.")
        WEGD6Rules.validate_action(state, "strength", req.resistance_character_points, defensive=True, free=True)
        damage = WEGD6Rules.damage_roll(*parse_code(code))
        resistance = D6Roller.values(*WEGD6Rules.resistance_pool(state, "physical"), req.resistance_character_points)
        state.character_points -= req.resistance_character_points
        state.round_state.character_points_spent |= bool(req.resistance_character_points)
        wound = WEGD6Rules.apply_damage(state, damage.total - resistance.total)
        result = event(f"Fell {req.meters:g} meters; {code} damage {damage.total} vs full Strength/physical armor {resistance.total}: {wound}.", changes={"meters": req.meters, "standard_gravity": req.standard_gravity, "damage": damage.model_dump(), "resistance": resistance.model_dump(), "wound": wound})
        result.damage_roll, result.resistance_roll, result.wound_result = damage, resistance, wound
        return save(original, session, person, result, "Falling", req)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/exert")
def exert(req: HazardExertion):
    try:
        original, session, person = working(req)
        require_resolved(session)
        state, hazard = person.d6, person.d6.hazards
        if not state.can_act or state.force.attempt:
            raise ValueError("Choose a conscious character able to exert themselves, without a pending Force activation.")
        if req.gamorrean_retry and (state.species_id != "gamorrean" or hazard.willpower_driven):
            raise ValueError("Only a Gamorrean's actual Stamina check can use the one immediate retry.")
        if req.retry_character_points and not req.gamorrean_retry:
            raise ValueError("Retry Character Points require declaring the Gamorrean retry.")
        extra = (req.willpower_character_points if req.push_with_willpower and not hazard.willpower_driven else 0) + (req.retry_character_points if req.gamorrean_retry else 0)
        points(state, req, extra)
        if req.willpower_character_points and not req.push_with_willpower:
            raise ValueError("Willpower CP requires declaring the follow-up Willpower attempt.")
        follow_difficulty = rules.harder(req.difficulty, req.willpower_difficulty) if req.push_with_willpower or hazard.willpower_driven else None
        preview = state.model_copy(deep=True)
        preview.round_state = D6RoundState()
        WEGD6Rules.declare(preview, actions=2 if req.push_with_willpower and not hazard.willpower_driven else 1, force_point=req.force_point)
        WEGD6Rules.validate_action(preview, "willpower" if hazard.willpower_driven else "stamina", req.character_points)
        if req.push_with_willpower and not hazard.willpower_driven:
            preview.hazards.fatigued = True
            preview.round_state.actions_taken = 1
            WEGD6Rules.validate_action(preview, "willpower", req.willpower_character_points)
        advance_scene(session, req.rounds)
        if not state.can_act:
            return save(original, session, person, event("Time passed, but incapacitation interrupted exertion before the check; no points spent.", success=False), "Exertion", req)
        hazard.exertion_rounds += req.rounds
        hazard.rest_rounds = 0
        driven = hazard.willpower_driven
        WEGD6Rules.declare(state, actions=2 if req.push_with_willpower and not driven else 1, force_point=req.force_point)
        result = WEGD6Rules.roll_skill(state, "willpower" if driven else "stamina", follow_difficulty if driven else req.difficulty, req.character_points)
        rolls = [result.roll_result.model_dump()]
        if not result.success and req.gamorrean_retry:
            # This species retry repeats the check, not its declared action.
            trial = state.model_copy(deep=True)
            trial.round_state.actions_taken = 0
            retry = D6Roller.values(*WEGD6Rules.validate_action(trial, "stamina", req.retry_character_points), req.retry_character_points)
            state.character_points -= req.retry_character_points
            state.round_state.character_points_spent |= bool(req.retry_character_points)
            rolls.append(retry.model_dump())
            result.roll_result, result.success = retry, retry.total >= req.difficulty
            result.summary += f" One immediate Gamorrean retry: {retry.breakdown} vs {req.difficulty}."
            result.state_changes["gamorrean_retry"] = True
        if not result.success:
            hazard.fatigued = True
            if driven:
                hazard.willpower_driven, hazard.exhausted = False, True
            else:
                hazard.fatigue_failures += 1
                if req.push_with_willpower:
                    # Exertion and the possible follow-up were declared together.
                    follow = WEGD6Rules.roll_skill(state, "willpower", follow_difficulty, req.willpower_character_points)
                    rolls.append(follow.roll_result.model_dump())
                    hazard.willpower_driven, hazard.exhausted = follow.success, not follow.success
                    result.summary += " Follow-up: " + follow.summary
                    result.success = follow.success
                else:
                    hazard.exhausted = hazard.fatigue_failures >= 3
            if req.failure_damage_margin is not None:
                previous_stuns = (state.stun_count, list(state.stun_durations), list(state.stun_expiries), state.unconscious_rounds)
                injury = WEGD6Rules.apply_damage(state, req.failure_damage_margin)
                pushed = driven or req.push_with_willpower
                if pushed and injury not in {"unharmed", "stun resisted", "dead"}:
                    if injury in {"stunned", "unconscious"}:
                        state.stun_count, state.stun_durations, state.stun_expiries, state.unconscious_rounds = previous_stuns
                    next_wound = {"stunned": "wounded", "unconscious": "wounded", "wounded": "incapacitated", "incapacitated": "mortally_wounded", "mortally_wounded": "dead"}[injury]
                    state.wound = next_wound
                    state.round_state.blocked = True
                    state.recovery_days = 0
                    if next_wound == "mortally_wounded":
                        state.mortal_rounds = 0
                    from dungeonforge.rules import weg_force_effects as effects
                    effects.drop_on_injury(state)
                    effects.injury_reactions(state, severe_injury=True)
                    injury = next_wound
                result.state_changes.update(environmental_damage_margin=req.failure_damage_margin, willpower_worsened_injury=pushed, wound=injury)
                result.summary += f" GM-confirmed failed-check environmental injury: {injury}" + (" (one wound level worse for pushing)." if pushed else ".")
        result.summary += f" Fatigued {hazard.fatigued}; exhausted {hazard.exhausted}; Willpower-driven {hazard.willpower_driven}. Required rest {max(0, rules.rest_required(state) - hazard.rest_rounds)} rounds."
        result.state_changes.update(rolls=rolls, exertion_rounds=hazard.exertion_rounds, fatigue_failures=hazard.fatigue_failures,
            fatigued=hazard.fatigued, exhausted=hazard.exhausted, willpower_driven=hazard.willpower_driven)
        return save(original, session, person, result, "Exertion", req)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/stop-pushing")
def stop_pushing(req: HazardActor):
    try:
        original, session, person = working(req)
        rules.stop_pushing(person.d6)
        return save(original, session, person, event(f"Stopped driving on with Willpower. Complete exhaustion requires {rules.rest_required(person.d6)} rounds of actual rest."), "Stop pushing", req)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/rest")
def rest(req: HazardRest):
    try:
        original, session, person = working(req)
        require_resolved(session)
        if person.d6.wound == "dead":
            raise ValueError("A dead character cannot rest.")
        if person.d6.hazards.willpower_driven:
            rules.stop_pushing(person.d6)
        advance_scene(session, req.rounds)
        rules.rest(person.d6, req.rounds)
        return save(original, session, person, event(f"Rested {req.rounds} rounds. Fatigued {person.d6.hazards.fatigued}; exhausted {person.d6.hazards.exhausted}; {max(0, rules.rest_required(person.d6) - person.d6.hazards.rest_rounds)} rest rounds remain."), "Exertion rest", req)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/swim")
def swim(req: HazardSwim):
    try:
        original, session, person = working(req)
        require_resolved(session, hazard_step=True)
        state = person.d6
        current_group = rules.drowning_people(session)
        if state.hazards.drowning or current_group and state.hazards.swim_round == session.d6_hazard_round:
            raise ValueError("This character's swimming opportunity in the current emergency round is already resolved.")
        if not state.can_act or state.force.attempt:
            raise ValueError("Choose a conscious swimmer without a pending Force activation.")
        points(state, req)
        rescue_difficulty = rules.harder(req.difficulty, req.rescue_difficulty) if req.breathing_risk and not state.droid else None
        if not current_group:
            advance_scene(session, 1)
            session.d6_hazard_round += 1
        state.hazards.swim_round = session.d6_hazard_round
        if not state.can_act:
            return save(original, session, person, event("The scene round passed, but injury interrupted swimming before the roll.", success=False), "Swimming", req)
        WEGD6Rules.declare(state, actions=req.actions, force_point=req.force_point)
        result = WEGD6Rules.roll_skill(state, "swimming", req.difficulty, req.character_points)
        if not result.success and req.breathing_risk and not state.droid:
            state.hazards.drowning = D6Drowning(initial_difficulty=req.difficulty, rescue_difficulty=rescue_difficulty, attempted_round=0, declared_round=0)
            result.summary += " Drowning begins; plain 2D death checks start at the beginning of the next saved round."
        result.state_changes.update(breathing_risk=req.breathing_risk, drowning=state.hazards.drowning.model_dump() if state.hazards.drowning else None)
        return save(original, session, person, result, "Swimming", req)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/drowning-action")
def drowning_action(req: HazardDrowningAction):
    try:
        original, session, person = working(req, routine=req.action != "rescued")
        require_resolved(session, hazard_step=True)
        state, drowning = person.d6, person.d6.hazards.drowning
        if not drowning or state.wound == "dead":
            raise ValueError("Choose a living character in the saved drowning emergency.")
        if req.action in {"rescued", "pass"}:
            if req.character_points or req.force_point:
                raise ValueError("A GM rescue record or passed opportunity spends no points and makes no roll.")
            if req.action == "rescued":
                state.hazards.drowning = None
                result = event("GM records an actual completed rescue/escape from the water; drowning ends. This is a recorded scene fact, not a rolled rescue procedure.")
            else:
                if drowning.attempted_round == drowning.round or not state.can_act:
                    raise ValueError("This conscious swimmer's self-rescue opportunity is already resolved.")
                drowning.attempted_round = drowning.round
                result = event("Passed this round's self-rescue opportunity; drowning continues.")
        else:
            if not state.can_act or state.force.attempt:
                raise ValueError("This swimmer cannot take a conscious skill action.")
            if req.action == "swim" and drowning.attempted_round == drowning.round:
                raise ValueError("Only one self-rescue Swimming attempt is available each round.")
            if req.action == "other" and skill_key(req.skill) == "swimming":
                raise ValueError("Use the once-per-round self-rescue Swimming action.")
            points(state, req)
            if drowning.declared_round != drowning.round:
                WEGD6Rules.declare(state, actions=req.actions, force_point=req.force_point)
                drowning.declared_round = drowning.round
            elif req.force_point:
                raise ValueError("Declare a Force Point on the first action of the round, never a second time.")
            result = WEGD6Rules.roll_skill(state, "swimming" if req.action == "swim" else req.skill, drowning.rescue_difficulty if req.action == "swim" else req.difficulty, req.character_points)
            if req.action == "swim":
                drowning.attempted_round = drowning.round
                if result.success:
                    state.hazards.drowning = None
                    result.summary += " Self-rescue succeeds; drowning ends."
        return save(original, session, person, result, "Drowning action", req)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/drowning-next")
def drowning_next(req: HazardNext):
    try:
        original = native_session()
        session = original.model_copy(deep=True)
        downtime(session)
        require_resolved(session, hazard_step=True)
        people = rules.drowning_people(session)
        if not people or not req.reason.strip():
            raise ValueError("Select an active drowning emergency and record the next round's scene facts.")
        for person in people:
            drowning = person.d6.hazards.drowning
            if person.d6.can_act and drowning.attempted_round != drowning.round:
                raise ValueError("Resolve or pass every conscious swimmer's self-rescue opportunity before advancing.")
        advance_scene(session, 1, hazard_step=True)
        session.d6_hazard_round += 1
        notes = []
        for person in people:
            state, drowning = person.d6, person.d6.hazards.drowning
            if state.wound == "dead":
                continue
            drowning.round += 1
            roll = DiceRoller.roll("2d6")
            dead = roll.total < drowning.round
            if dead:
                state.wound = "dead"
                from dungeonforge.rules.weg_force_effects import drop_on_injury
                drop_on_injury(state)
            note = {"operation": "Drowning round", "round": drowning.round, "roll": roll.model_dump(), "dead": dead, "reason": req.reason.strip()}
            state.hazards.history.append(note)
            notes.append(f"{person.name}: plain 2D {roll.total}, drowning round {drowning.round}; {'drowned and died' if dead else 'alive'}.")
        return commit(original, session, event(" ".join(notes), changes={"drowning_rounds": notes}), "Next drowning round", boost=False)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
