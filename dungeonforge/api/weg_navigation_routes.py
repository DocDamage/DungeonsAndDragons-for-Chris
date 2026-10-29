"""Native course calculations, shared travel time, persistent mishaps and crew rescue."""
from fastapi import APIRouter, HTTPException
from dungeonforge.api.weg_routes import native_session
from dungeonforge.api.weg_force_routes import commit
from dungeonforge.api.weg_advancement_routes import downtime, event as record_event, people, student
from dungeonforge.api.weg_engineering_routes import craft_for
from dungeonforge.rules import weg_navigation as rules
from dungeonforge.game import weg_navigation as world
from dungeonforge.game.weg_force import advance_scene
from dungeonforge.rules.weg_d6 import WEGD6Rules
from dungeonforge.rules.weg_models import D6RoundState
from dungeonforge.rules.weg_navigation_models import D6Journey, D6NavigationRequest, D6NavigationAdvance, D6NavigationResolve, D6NavigationSuit, D6NavigationMemory

router = APIRouter(prefix="/api/weg-d6/navigation", tags=["Native hyperspace travel"])


def event(*args, **kwargs):
    return record_event(*args, category="Navigation", **kwargs)


def astromech(session, craft, req):
    if not req.astromech_id:
        return False
    unit = student(session, req.astromech_id)
    if not unit.d6.droid or unit.d6.droid.model != "r2" or not unit.d6.can_act or not any(crew.character_id == unit.id and (not crew.evacuated or req.boarding_confirmed) for crew in craft.crew):
        raise ValueError("Select a conscious R2 astromech actually assigned aboard this craft.")
    wanted = {req.origin.strip().lower(), req.destination.strip().lower()}
    return any({item['origin'].lower(), item['destination'].lower()} == wanted for item in unit.d6.droid.route_memory)


def course(session, req):
    if rules.active(session):
        raise ValueError("Finish or resolve the current journey before plotting another one.")
    craft = craft_for(session, req.craft_id)
    person = student(session, req.actor_id)
    if not any(crew.character_id == person.id and (not crew.evacuated or req.boarding_confirmed) for crew in craft.crew):
        raise ValueError("The astrogator must be assigned aboard this craft.")
    if not person.d6.can_act or person.d6.force.attempt:
        raise ValueError("The astrogator must be conscious and free of another activation.")
    if req.force_point and req.character_points or req.character_points > person.d6.character_points or req.force_point and person.d6.force_points < 1:
        raise ValueError("Choose available CP dice or a Force Point, never both.")
    return craft, person, rules.quote(craft, req, astromech(session, craft, req))


@router.get("/catalog")
def catalog():
    return {"systems": rules.SYSTEMS, "routes": rules.ROUTES, "route_types": rules.FACTORS, "source": "WEG40055 (1992), printed pp.110–112."}


@router.post("/quote")
def quote(req: D6NavigationRequest):
    try:
        _, _, q = course(native_session(), req)
        return {"quote": q}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/plot")
def plot(req: D6NavigationRequest):
    original = native_session()
    session = original.model_copy(deep=True)
    try:
        downtime(session)
        if req.expected_updated_at != session.updated_at:
            raise ValueError("The adventure changed; review the current route before plotting.")
        craft, person, q = course(session, req)
        advance_scene(session, req.plotting_rounds)
        if craft.damage == "destroyed" or not person.d6.can_act:
            return commit(original, session, event("Time passed, but damage or incapacitation interrupted plotting; no jump or points spent.", success=False), "Interrupted astrogation", boost=False)
        # Recheck ship equipment after plotting time, which also advances fleet failures.
        q = rules.quote(craft, req, astromech(session, craft, req))
        WEGD6Rules.declare(person.d6, force_point=req.force_point)
        context = person.d6.species_context
        previous_familiar = context.familiar_destination
        context.familiar_destination = req.destination_visited or any(place.casefold() == req.destination.strip().casefold() for place in context.visited_locations)
        try:
            result = WEGD6Rules.roll_skill(person.d6, "astrogation", q.difficulty, req.character_points)
        finally:
            context.familiar_destination = previous_familiar
        journey = D6Journey(request=req, quote=q, remaining_rounds=q.rounds, roll=result.roll_result.model_dump(),
            miss=max(0, q.difficulty - result.roll_result.total), travellers=list(people(session)))
        craft.location, craft.occupied = req.origin.strip(), True
        for crew in craft.crew:
            if crew.character_id in journey.travellers:
                crew.evacuated = False
        if journey.miss > 10:
            journey.status = "aborted"
            journey.resolution.append("Missed by more than ten: the ship cannot enter hyperspace.")
        elif journey.miss == 10:
            journey.status = "ten_point_ruling"
            journey.resolution.append("The printed rule omits a miss of exactly ten. GM must choose no entry or a plain 2D mishap using this saved roll.")
        elif journey.miss:
            world.mishap(session, craft, journey)
        session.d6_navigation.journeys.append(journey)
        result.summary = f"[WEG Astrogation] {craft.name}: {req.origin} → {req.destination}. " + result.summary + f" Duration {journey.remaining_rounds / 720:g} hours; {journey.status}. " + " ".join(journey.resolution)
        result.state_changes["journey"] = journey.model_dump()
        return commit(original, session, result, "Plot hyperspace route", boost=False)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/advance")
def advance(req: D6NavigationAdvance):
    original = native_session()
    session = original.model_copy(deep=True)
    try:
        downtime(session)
        current = rules.active(session)
        if not current or current.status != "travelling":
            raise ValueError("Only an underway, resolved hyperspace journey can advance.")
        rounds = min(req.rounds, current.remaining_rounds)
        advance_scene(session, rounds)
        return commit(original, session, event(f"{rounds / 720:g} hours passed for the entire scene and fleet. Journey {current.status}; {current.remaining_rounds / 720:g} hours remain."), "Advance hyperspace time", boost=False)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def journey_for(session, id):
    journey = next((item for item in session.d6_navigation.journeys if item.id == id), None)
    if journey is None or rules.active(session) is not journey:
        raise ValueError("Select the current unresolved journey; old trips cannot be resolved twice.")
    return journey


@router.post("/resolve")
def resolve(req: D6NavigationResolve):
    original = native_session()
    session = original.model_copy(deep=True)
    try:
        downtime(session)
        current = journey_for(session, req.journey_id)
        craft = craft_for(session, current.request.craft_id)
        if not req.reason.strip():
            raise ValueError("Record the GM's actual navigation ruling or scene facts.")
        if req.action == "abort" and current.status == "ten_point_ruling":
            current.status = "aborted"
        elif req.action == "roll_mishap" and current.status == "ten_point_ruling":
            world.mishap(session, craft, current)
        elif req.action == "location" and current.status == "awaiting_location":
            if not req.location.strip():
                raise ValueError("Name the actual dropout system or realspace location.")
            craft.location = req.location.strip()
            current.status = "off_course" if current.mishap in {7, 8} else "interrupted"
        elif req.action == "close_call" and current.status == "close_call_pending":
            setattr(craft, {"drives": "drives_disabled", "nav_computer": "nav_computer_disabled", "weapons": "weapons_disabled", "escape_pods": "escape_pods_disabled"}[req.system], True)
            current.status = "travelling"
        elif req.action == "exposure" and current.status == "exposure_pending":
            members = people(session)
            if len(req.actor_ids) != len(set(req.actor_ids)) or set(req.actor_ids) - set(current.travellers) or set(req.actor_ids) - set(members):
                raise ValueError("Choose each actually exposed party member once.")
            current.crew_exposure = {}
            available = {item.name: item.quantity for item in session.character.inventory if item.sealed_survival_suit}
            # Worn suits remain worn across journeys; inventory quantities still limit assignments.
            worn = {}
            for id, member in members.items():
                suit = member.d6.survival_suit
                if suit and available.get(suit, 0) > 0:
                    worn[id] = suit
                    available[suit] -= 1
            for id in req.actor_ids:
                state = members[id].d6
                protected = bool(state.droid) or state.wound == "dead" or id in worn
                current.crew_exposure[id] = {"protected": protected, "phase": "protected" if protected else "suit" if state.can_act else "unconscious", "suit_round": -1, "breath_round": -1, "suit_name": worn.get(id)}
            current.status = "emergency" if any(not item["protected"] for item in current.crew_exposure.values()) else "abandoned"
        elif req.action == "next_round" and current.status == "emergency":
            members = people(session)
            for id, item in current.crew_exposure.items():
                if not item["protected"] and members[id].d6.can_act and (item["suit_round"] != 0 if current.emergency_round == 0 else item["breath_round"] != current.emergency_round):
                    raise ValueError("Resolve each conscious exposed character's initial suit attempt or current-round breathing check first.")
            advance_scene(session, 1, emergency_step=True)
            current.emergency_round += 1
        else:
            raise ValueError("That ruling does not match the saved navigation event.")
        current.resolution.append(req.reason.strip())
        return commit(original, session, event(f"Navigation ruling: {req.action}; {current.status}. {req.reason.strip()}"), "Resolve navigation event", boost=False)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/crew-emergency")
def crew_emergency(req: D6NavigationSuit):
    original = native_session()
    session = original.model_copy(deep=True)
    try:
        downtime(session)
        current = journey_for(session, req.journey_id)
        entry = current.crew_exposure.get(req.actor_id)
        if current.status != "emergency" or not entry or entry["protected"] or not req.reason.strip():
            raise ValueError("Choose an actually exposed, unprotected character and record the attempted action.")
        target = student(session, req.actor_id)
        if req.method == "wait":
            if current.emergency_round or entry["suit_round"] == 0 or not target.d6.can_act:
                raise ValueError("Only a conscious character's unresolved initial suit opportunity can be passed.")
            if req.character_points or req.force_point or req.gamorrean_retry or req.retry_character_points:
                raise ValueError("Passing the initial suit opportunity spends no points and makes no roll.")
            entry["suit_round"], entry["phase"] = 0, "breathing"
            current.resolution.append(f"Initial suit opportunity passed by {target.name}: {req.reason.strip()}")
            return commit(original, session, event(f"{target.name} remains exposed; breathing checks begin next round. {req.reason.strip()}"), "Pass initial suit opportunity", boost=False)
        source = target
        if req.method == "rescue":
            source = student(session, req.rescuer_id)
            helper = current.crew_exposure.get(source.id)
            if source.id == target.id or helper and not helper["protected"] or not source.d6.can_act:
                raise ValueError("A different conscious, protected rescuer must perform this action.")
            key = f"rescuer:{source.id}"
            if key in current.crew_exposure and current.crew_exposure[key].get("acted_round") == current.emergency_round:
                raise ValueError("This rescuer already used the emergency action this round.")
        elif not source.d6.can_act:
            raise ValueError("An unconscious character needs an actual protected rescuer.")
        if req.method == "breathe":
            if current.emergency_round == 0 or entry["breath_round"] == current.emergency_round:
                raise ValueError("Make one breathing check in each emergency round after the first suit round.")
            difficulty = (10, 15, 20, 30, 31)[min(current.emergency_round - 1, 4)]
            skill = "stamina"
        else:
            if req.method == "suit" and entry["suit_round"] == current.emergency_round:
                raise ValueError("Only one suit attempt is available to this character in each emergency round.")
            if req.method == "suit" and current.emergency_round and entry["breath_round"] != current.emergency_round:
                raise ValueError("Resolve this round's breathing check before trying to put on the suit again.")
            item = next((item for item in session.character.inventory if item.name == req.suit_name and item.sealed_survival_suit and item.quantity > 0), None)
            if item is None:
                raise ValueError("Select an actual sealed survival suit from inventory; a filtering breath mask is not a vacuum suit.")
            assigned = sum(person.d6.survival_suit == item.name for person in [session.character, *session.character.companions] if person.d6)
            if target.d6.survival_suit != item.name and assigned >= item.quantity:
                raise ValueError("Every suit of this type is already assigned to another party member.")
            difficulty, skill = 15, "survival"
        if req.gamorrean_retry and (req.method != "breathe" or source.d6.species_id != "gamorrean") or req.retry_character_points and not req.gamorrean_retry:
            raise ValueError("Only a Gamorrean's breathing Stamina check can declare its one immediate retry.")
        if req.force_point and (req.character_points or req.retry_character_points) or req.character_points + req.retry_character_points > source.d6.character_points:
            raise ValueError("Choose available CP dice or a Force Point, not both.")
        tracker = current.crew_exposure.setdefault(f"actor_round:{source.id}", {"protected": True, "phase": "action_tracker", "last_action_round": -1})
        if tracker["last_action_round"] != current.emergency_round:
            source.d6.round_state = D6RoundState()
            WEGD6Rules.declare(source.d6, actions=req.actions, force_point=req.force_point)
            tracker["last_action_round"] = current.emergency_round
        elif req.force_point:
            raise ValueError("An FP must be declared on this character's first emergency action, and cannot be spent a second time in the same round.")
        result = WEGD6Rules.roll_skill(source.d6, skill, difficulty, req.character_points)
        if not result.success and req.gamorrean_retry:
            from dungeonforge.rules.weg_d6 import D6Roller
            trial = source.d6.model_copy(deep=True)
            trial.round_state.actions_taken = 0
            retry = D6Roller.values(*WEGD6Rules.validate_action(trial, "stamina", req.retry_character_points), req.retry_character_points)
            first = result.roll_result.model_dump()
            source.d6.character_points -= req.retry_character_points
            source.d6.round_state.character_points_spent |= bool(req.retry_character_points)
            result.roll_result, result.success = retry, retry.total >= difficulty
            result.state_changes.update(gamorrean_retry=True, first_roll=first)
            result.summary += f" One immediate Gamorrean retry: {retry.breakdown} vs {difficulty}."
        if req.method == "breathe":
            entry["breath_round"] = current.emergency_round
            if not result.success:
                entry["phase"] = "unconscious"
                target.d6.vacuum_unconscious = True
                target.d6.unconscious_rounds = max(12, target.d6.unconscious_rounds)
        else:
            if req.method == "suit":
                entry["suit_round"] = current.emergency_round
            else:
                current.crew_exposure[f"rescuer:{source.id}"] = {"protected": True, "phase": "helper", "acted_round": current.emergency_round}
            if result.success:
                entry["protected"], entry["phase"], entry["suit_name"] = True, "protected", req.suit_name
                target.d6.survival_suit = req.suit_name
                target.d6.vacuum_unconscious = False
            else:
                entry["phase"] = "breathing" if not target.d6.vacuum_unconscious else "unconscious"
        if all(item["protected"] for item in current.crew_exposure.values()):
            current.status = "abandoned"
        current.resolution.append(f"Emergency round {current.emergency_round}, {source.name}: {req.method} {'succeeded' if result.success else 'failed'}. {req.reason.strip()}")
        result.summary = "[WEG Hull Breach] " + result.summary + f" {target.name}: {entry['phase']}; journey {current.status}."
        return commit(original, session, result, "Hull breach crew action", boost=False)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/route-memory")
def route_memory(req: D6NavigationMemory):
    original = native_session()
    session = original.model_copy(deep=True)
    try:
        unit = student(session, req.actor_id)
        if not unit.d6.droid or unit.d6.droid.model != "r2" or not req.reason.strip():
            raise ValueError("Choose an R2 astromech and record the GM-confirmed downloaded/preprogrammed route data.")
        origin, destination = req.origin.strip(), req.destination.strip()
        if not origin or not destination or origin.lower() == destination.lower():
            raise ValueError("Record two distinct actual systems.")
        memory = unit.d6.droid.route_memory
        if any({item['origin'].lower(), item['destination'].lower()} == {origin.lower(), destination.lower()} for item in memory):
            raise ValueError("This preprogrammed route is already in memory.")
        if len(memory) >= 10:
            raise ValueError("An R2 can store at most ten preprogrammed hyperspace jumps.")
        memory.append({"origin": origin, "destination": destination, "reason": req.reason.strip()})
        return commit(original, session, event(f"GM records actual preprogrammed route data in {unit.name}: {origin} ↔ {destination}. {len(memory)}/10 jump slots. {req.reason.strip()}"), "Record astromech route data", boost=False)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
