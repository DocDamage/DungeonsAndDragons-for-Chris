"""Separate craft encounters with individual crew declarations and action passes."""

import uuid

from dungeonforge.game.weg_vehicle_presets import vehicle_presets
from dungeonforge.rules.base import RuleEvaluationResult
from dungeonforge.rules.dice import RollResult
from dungeonforge.rules.weg_d6 import D6Roller, WEGD6Rules, parse_code
from dungeonforge.rules.weg_models import D6Character, D6RoundState
from dungeonforge.rules.weg_vehicle_models import D6Crew, D6VehicleEncounter
from dungeonforge.rules.weg_vehicles import WEGVehicleRules, DAMAGE_CAP, RESIST_CAP, cap_for, fixed_roll
from dungeonforge.rules import weg_force_effects as effects


def find_actor(encounter, actor_id):
    for craft in encounter.craft:
        for crew in craft.crew:
            if crew.id == actor_id:
                return craft, crew
    raise ValueError("Crew station not found in this encounter.")


def find_craft(encounter, craft_id):
    result = next((craft for craft in encounter.craft if craft.id == craft_id), None)
    if result is None:
        raise ValueError("Craft not found in this encounter.")
    return result


def party_people(session):
    return {person.id: person for person in [session.character, *session.character.companions] if person.d6}


def bind_party(session, encounter):
    people = party_people(session)
    for craft in encounter.craft:
        if craft.is_player:
            for crew in craft.crew:
                if crew.character_id in people:
                    people[crew.character_id].d6 = crew.d6
            index = next((i for i, saved in enumerate(session.vehicles) if saved.id == craft.id), None)
            if index is not None:
                session.vehicles[index] = craft


def configure_party(craft, session):
    people = party_people(session)
    if not craft.crew:
        craft.crew = [D6Crew(id=session.character.id, character_id=session.character.id, name=session.character.name,
            stations=["pilot", "gunner", "shields", "engineer"], d6=session.character.d6.model_copy(deep=True))]
        if session.character.companions and (craft.piloting_skill != "starfighter_piloting" or craft.name == "Y-wing"):
            person = next((person for person in session.character.companions if person.d6), None)
            if person:
                craft.crew.append(D6Crew(id=person.id, character_id=person.id, name=person.name,
                    stations=["gunner", "shields", "engineer"], d6=person.d6.model_copy(deep=True)))
                for weapon in craft.weapons:
                    if craft.name != "Y-wing" or weapon.kind == "ion":
                        weapon.operator_id = person.id
    for crew in craft.crew:
        if crew.character_id not in people or crew.id != crew.character_id:
            raise ValueError("Party stations must use the ID of a native character in your party.")
        crew.name = people[crew.character_id].name
        crew.d6 = people[crew.character_id].d6.model_copy(deep=True)
        crew.d6.round_state = D6RoundState()
        crew.d6.force.saber_locked = False
        for effect in crew.d6.force.effects:
            effect.activation_round = False
        crew.evacuated = False
        crew.control_penalty = crew.next_control_penalty = 0
    if not craft.crew or sum("pilot" in crew.stations for crew in craft.crew) != 1:
        raise ValueError("Assign exactly one pilot aboard the craft.")
    return craft


def make_enemy(preset):
    catalog = vehicle_presets()
    if preset not in catalog:
        raise ValueError(f"Unknown enemy craft preset '{preset}'.")
    craft = catalog[preset].model_copy(deep=True)
    craft.id = f"enemy_craft_{uuid.uuid4().hex[:10]}"
    craft.is_player = False
    skills = {craft.piloting_skill: "4D+1", "starship_gunnery": "4D", "capital_ship_gunnery": "4D+2", "starship_shields": "3D", "capital_ship_shields": "4D", "vehicle_blasters": "4D"}
    if preset in {"star_destroyer", "corvette"}:
        skills[craft.piloting_skill] = "5D+1" if preset == "star_destroyer" else "3D+2"
    state = D6Character(attributes={"dexterity": "3D", "knowledge": "2D", "mechanical": "3D", "perception": "3D", "strength": "2D", "technical": "2D"}, skills=skills, character_points=0, force_points=0)
    state.corruption.refuses_force = preset in {"tie_fighter", "star_destroyer"}
    craft.crew = [D6Crew(id=f"{craft.id}_pilot", name=f"{craft.name} pilot", stations=["pilot", "gunner", "shields", "engineer"], d6=state)]
    if preset == "ywing":
        gunner = D6Crew(id=f"{craft.id}_gunner", name="Y-wing gunner", stations=["gunner", "shields", "engineer"], d6=state.model_copy(deep=True))
        craft.crew.append(gunner)
        for weapon in craft.weapons:
            if not weapon.pilot_operated:
                weapon.operator_id = gunner.id
    if preset in {"star_destroyer", "corvette"}:
        for role in ("gunner", "shields"):
            craft.crew.append(D6Crew(id=f"{craft.id}_{role}", name=f"{craft.name} {role} station", stations=[role, "engineer"], d6=state.model_copy(deep=True)))
        for weapon in craft.weapons:
            weapon.operator_id = craft.crew[1].id
    return craft


def start(session, vehicle_id, enemies, environment):
    craft = next((craft for craft in session.vehicles if craft.id == vehicle_id), None)
    if craft is None:
        raise ValueError("Add a party craft before starting an encounter.")
    party = configure_party(craft.model_copy(deep=True), session)
    party.occupied = True
    if party.damage == "destroyed" or party.controls_dead or party.generator_shutdown:
        raise ValueError("Repair or replace this craft before starting another encounter.")
    encounter = D6VehicleEncounter(environment=environment, craft=[party, *(make_enemy(preset) for preset in enemies)])
    if environment == "space" and any(c.kind != "starship" for c in encounter.craft):
        raise ValueError("Surface vehicles cannot take part in a space encounter; choose atmosphere/ground.")
    if environment == "atmosphere" and any(c.atmosphere_move <= 0 for c in encounter.craft):
        raise ValueError("This craft has no atmospheric movement rating.")
    if party.out_of_fight:
        raise ValueError("The party needs a conscious crew.")
    for vehicle in encounter.craft:
        if environment == "space":
            vehicle.airborne, vehicle.altitude = False, 0
        clear_round(vehicle)
    initiative(encounter)
    encounter.combat_log.append("Declare crew actions and moves, then deploy dodges/shields before the action phase. Equipment dice are never Force-doubled.")
    return encounter


def clear_round(craft):
    craft.shield_allocation = {}
    craft.shields_rolled = False
    craft.dodge_roll = None
    craft.full_dodge = False
    craft.moves_taken = craft.declared_moves = 0
    craft.distance_moved = 0
    craft.half_speed = False
    if craft.frozen_rounds:
        craft.declared_moves, craft.half_speed = craft.forced_moves, craft.forced_half_speed


def eligible(craft, crew):
    return not craft.out_of_fight and crew.d6.can_take_turn and not crew.evacuated


def initiative(encounter):
    leaders = {}
    for side in (True, False):
        members = [crew for craft in encounter.craft if craft.is_player == side for crew in craft.crew if eligible(craft, crew)]
        if not members:
            refresh(encounter)
            return
        leaders[side] = max(members, key=lambda crew: parse_code(crew.d6.attributes["perception"]))
    scores = {}
    for _ in range(25):
        for side, crew in leaders.items():
            # Perception initiative uses wounds but never MAP, Force, or Character Points.
            dice, extra = parse_code(crew.d6.attributes["perception"])
            dice -= (crew.d6.wound == "wounded") + len(crew.d6.stun_durations)
            roll = D6Roller.values(dice, extra) if dice > 0 else None
            scores[side] = roll.total if roll else 0
            encounter.combat_log.append(f"{'Party' if side else 'Enemy'} Perception initiative ({crew.name}): {roll.breakdown if roll else 'no dice; 0'}")
        if scores[True] != scores[False]:
            break
    encounter.initiative = {"party": scores[True], "enemy": scores[False]}
    encounter.initiative_winner = scores[True] >= scores[False]
    order_sides(encounter, True)


def order_sides(encounter, winner_first):
    if encounter.actions_started:
        raise ValueError("Choose initiative order before actions begin.")
    first = encounter.initiative_winner if winner_first else not encounter.initiative_winner
    pairs = [(craft, crew) for craft in encounter.craft for crew in craft.crew if eligible(craft, crew)]
    pairs.sort(key=lambda pair: (pair[0].is_player != first, -parse_code(pair[1].d6.attributes["perception"])[0], -parse_code(pair[1].d6.attributes["perception"])[1]))
    encounter.actor_order = [crew.id for _, crew in pairs]
    encounter.current_turn_index = 0
    encounter.turn_acted = False


def refresh(encounter):
    for craft in encounter.craft:
        if craft.captured_by:
            captor = next((c for c in encounter.craft if c.id == craft.captured_by), None)
            weapon = next((w for w in captor.weapons if w.id == craft.captured_weapon), None) if captor else None
            if not captor or captor.out_of_fight or captor.frozen_rounds or captor.weapons_disabled or not weapon or weapon.status != "operational":
                craft.captured_by = craft.captured_weapon = None
    sides = {side: any(craft.is_player == side and not craft.out_of_fight for craft in encounter.craft) for side in (True, False)}
    if encounter.active and not all(sides.values()):
        encounter.active = False
        encounter.combat_log.append("VICTORY: enemy craft disabled, abandoned, or destroyed." if sides[True] else "DEFEAT: party craft disabled, abandoned, or destroyed.")


def validate_turn(encounter, actor_id):
    if not encounter.active:
        raise ValueError("No active craft encounter.")
    if not encounter.actor_order or encounter.actor_order[encounter.current_turn_index] != actor_id or encounter.turn_acted:
        raise ValueError("Advance to this crew member's action before rolling.")
    craft, crew = find_actor(encounter, actor_id)
    if not eligible(craft, crew):
        raise ValueError("This crew member or craft cannot act.")
    return craft, crew


def finish(encounter, result):
    encounter.actions_started = True
    # Half-speed movement is free and leaves the current skill action available.
    encounter.turn_acted = not result.state_changes.get("free_move", False)
    encounter.combat_log.append(result.summary)
    refresh(encounter)


def next_turn(encounter):
    if not encounter.active:
        return
    if not encounter.actor_order:
        raise ValueError("This encounter has no active crew.")
    _, current = find_actor(encounter, encounter.actor_order[encounter.current_turn_index])
    if not encounter.turn_acted:
        effects.skip_turn(current.d6)
        current.d6.round_state.actions_taken = min(current.d6.round_state.declared_actions, current.d6.round_state.actions_taken + 1)
    encounter.actions_started = True
    for offset in range(1, len(encounter.actor_order) + 1):
        index = (encounter.current_turn_index + offset) % len(encounter.actor_order)
        craft, crew = find_actor(encounter, encounter.actor_order[index])
        if eligible(craft, crew) and (crew.d6.round_state.actions_taken < crew.d6.round_state.declared_actions or (craft.half_speed and craft.moves_taken == 0 and "pilot" in crew.stations)):
            encounter.current_turn_index = index
            encounter.turn_acted = False
            return
    encounter.round += 1
    encounter.actions_started = encounter.turn_acted = False
    for craft in encounter.craft:
        previous_log = len(craft.damage_log)
        WEGVehicleRules.next_round(craft)
        encounter.combat_log.extend(f"{craft.name}: {line}" for line in craft.damage_log[previous_log:])
    refresh(encounter)
    if encounter.active:
        initiative(encounter)
        encounter.combat_log.append(f"Round {encounter.round}: declare new crew actions, movement, dodges, and shields.")


def system_action(encounter, req):
    craft, crew = validate_turn(encounter, req.actor_id)
    if not crew.d6.can_act or crew.d6.round_state.full_defense or crew.d6.round_state.actions_taken >= crew.d6.round_state.declared_actions:
        raise ValueError("No declared skill actions remain for this crew member.")
    roll = RollResult(expression="System action", dice_count=0, die_type=6, system="weg_d6", breakdown="No skill roll required")
    success = True
    if req.action == "evacuate":
        crew.evacuated = True
        summary = f"{crew.name} evacuates {craft.name}; GM confirms a safe exit/escape pod."
    elif req.action == "shutdown_generator":
        if "engineer" not in crew.stations or craft.destruction_cause != "generator" or craft.destruction_countdown is None:
            raise ValueError("An engineer can shut down an overloaded generator before its countdown ends.")
        craft.generator_shutdown = True
        craft.destruction_countdown = None
        craft.drives_disabled = craft.weapons_disabled = True
        craft.shield_allocation.clear()
        craft.particle_shields = False
        summary = f"{craft.name}: generator shut down; explosion prevented, power and drives offline until repaired."
    elif req.action == "escape_tractor":
        if "pilot" not in crew.stations or not craft.captured_by:
            raise ValueError("Only a captured craft's pilot can attempt a hull escape.")
        captor = find_craft(encounter, craft.captured_by)
        weapon = next(w for w in captor.weapons if w.id == craft.captured_weapon)
        scale = weapon.scale or captor.scale
        roll = WEGVehicleRules.hull_roll(craft, cap=cap_for(RESIST_CAP, scale, craft.scale))
        beam = fixed_roll(*WEGVehicleRules.equipment(captor, weapon.damage), cap_for(DAMAGE_CAP, scale, craft.scale))
        success = roll.total > beam.total
        if success:
            craft.captured_by = craft.captured_weapon = None
        summary = f"{craft.name}: hull escape {roll.breakdown} vs tractor {beam.breakdown} → {'FREE' if success else 'HELD'}. Equipment dice are not Force-doubled."
    else:
        WEGVehicleRules.operational(craft)
        target = find_craft(encounter, req.target_id)
        if target.captured_by != craft.id:
            raise ValueError("This craft does not hold the target in a tractor beam.")
        weapon = next(w for w in craft.weapons if w.id == target.captured_weapon)
        if (weapon.operator_id or WEGVehicleRules.pilot(craft).id) != crew.id:
            raise ValueError("Use the crew station operating the tractor beam.")
        if req.action == "release_tractor":
            target.captured_by = target.captured_weapon = None
            summary = f"{craft.name} releases {target.name}."
        else:
            target.tractor_distance = max(0, target.tractor_distance - 1)
            summary = f"{craft.name} pulls {target.name} one unit closer; separation {target.tractor_distance:g}."
    effects.take_action(crew.d6)
    effects.settle_consciousness(crew.d6)
    return RuleEvaluationResult(action_type="vehicle_system", success=success, roll_result=roll, summary=f"[WEG D6 Systems] {summary}")


def advance_fleet_time(session, rounds, advance_characters=False):
    """Rest passes real time: pending craft explosions cannot be evaded by ending combat."""
    from dungeonforge.game.weg_navigation import tick
    # Scene advances stop at the next fleet event. Travel through that interval
    # happens before an explosion at its boundary, then the new damage is checked.
    tick(session, rounds)
    people = party_people(session)
    if advance_characters:
        for _ in range(rounds):
            for person in people.values():
                WEGD6Rules.next_round(person.d6)
    notes = []
    for craft in session.vehicles:
        for crew in craft.crew:
            if craft.occupied and crew.character_id in people:
                crew.d6 = people[crew.character_id].d6
        old_damage = craft.damage
        ticks = min(rounds, max(3, craft.destruction_countdown or 0))
        for _ in range(ticks):
            WEGVehicleRules.next_round(craft, advance_crew=False)
        if old_damage != craft.damage:
            notes.append(f"{craft.name}: {craft.damage.replace('_', ' ')} after timed system failure")
            if craft.occupied:
                notes.append("Crew injuries: " + ", ".join(f"{crew.name} {crew.d6.wound.replace('_', ' ')}" for crew in craft.crew if not crew.evacuated))
    tick(session, 0)
    return notes
