"""Bind Force powers to the canonical party, personal opponents, and ship stations."""

from dataclasses import dataclass

from dungeonforge.rules.base import Item
from dungeonforge.rules.weg_d6 import WEGD6Rules
from dungeonforge.rules.weg_force_models import ForcePowerRequest
from dungeonforge.rules import weg_force_effects as effects


@dataclass
class ForceActor:
    id: str
    name: str
    state: object
    race: str = "Human"
    weapon: Item | None = None
    crew: object | None = None


def actors(session):
    people = {person.id: person for person in [session.character, *session.character.companions] if person.d6}
    result = {}
    for person in people.values():
        weapon = next((item for item in session.character.inventory if item.equipped and item.item_type == "weapon" and item.equipped_by in {None, person.id}), None) if person.id == session.character.id else person.d6_weapon or Item(name=person.attack_name, damage=person.damage)
        result[person.id] = ForceActor(person.id, person.name, person.d6, person.race, weapon)
    if session.vehicle_encounter:
        from dungeonforge.game import weg_vehicle_combat
        weg_vehicle_combat.bind_party(session, session.vehicle_encounter)
        for craft in session.vehicle_encounter.craft:
            for crew in craft.crew:
                person = people.get(crew.character_id)
                result[crew.id] = ForceActor(crew.id, crew.name, crew.d6, person.race if person else "Human", crew=crew)
    elif session.encounter and session.encounter.system == "weg_d6":
        if session.encounter.active:
            from dungeonforge.game import weg_combat
            weg_combat.bind_party(session.encounter, session.character)
        for combatant in session.encounter.combatants:
            if combatant.d6:
                if combatant.id in people:
                    person = people[combatant.id]
                    combatant.d6 = person.d6
                    result[combatant.id] = ForceActor(combatant.id, person.name, person.d6, person.race, result[combatant.id].weapon)
                else:
                    result[combatant.id] = ForceActor(combatant.id, combatant.name, combatant.d6, combatant.race, combatant.weapon)
    return result


def actor(session, id=None):
    result = actors(session).get(id or session.character.id)
    if result is None:
        raise ValueError("Select a native Force user or target from the current party/encounter.")
    return result


def synchronize(session):
    roster = actors(session)
    from dungeonforge.rules.weg_gear_effects import refresh as refresh_gear
    refresh_gear(session)
    from dungeonforge.rules.weg_force_catalog import automatic_known_powers
    owned = set()
    for person in roster.values():
        person.state.force.known_powers = automatic_known_powers(person.state)
        if person.state.wound == "dead":
            reaction = person.state.force.attempt if person.state.force.attempt and person.state.force.attempt.power_id == "reduce_injury" else None
            effects.drop_on_injury(person.state)
            if reaction:
                person.state.force.attempt = reaction
            person.state.force.remain_pending = False
        owned.update((effect.source_id, effect.id) for effect in person.state.force.effects if not effect.recipient)
    for person in roster.values():
        person.state.force.effects = [effect for effect in person.state.force.effects if not (effect.recipient and effect.power_id == "control_another_pain" and (effect.source_id, effect.id) not in owned)]
        effects.settle_consciousness(person.state)
    return roster


def after_roll(session, result=None):
    from dungeonforge.game.weg_rewards import synchronize as sync_rewards
    sync_rewards(session)
    from dungeonforge.game.weg_dark_side import synchronize as sync_dark_side
    sync_dark_side(session, result)
    keep = set(result.state_changes.get("force_injury_targets", [])) if result else set()
    if result:
        changes = result.state_changes
        groups = [changes.get("passengers", []), changes.get("collision", {}).get("passengers", [])]
        groups += [collision.get("passengers", []) for collision in changes.get("ram_collisions", [])]
        for group in groups:
            keep.update(person["crew_id"] for person in group)
    for person in actors(session).values():
        if person.id not in keep:
            person.state.force.reduce_injury_available = False
        if result is None or result.action_type != "force_power":
            effects.finalize_failure(person.state)
    session.force_boost = None
    synchronize(session)


def refresh_encounters(session):
    synchronize(session)
    if session.encounter and session.encounter.system == "weg_d6":
        from dungeonforge.game import weg_combat
        weg_combat.refresh(session.encounter)
    if session.vehicle_encounter:
        from dungeonforge.game import weg_vehicle_combat
        weg_vehicle_combat.refresh(session.vehicle_encounter)
        weg_vehicle_combat.bind_party(session, session.vehicle_encounter)


def scene_interval(session, remaining):
    """Stop at fleet casualties or arrival before advancing the rest of a long scene."""
    from dungeonforge.rules.weg_navigation import active
    interval = remaining
    for craft in session.vehicles:
        if craft.damage == "destroyed":
            continue
        if craft.destruction_countdown is not None:
            interval = min(interval, max(1, craft.destruction_countdown))
        if craft.frozen_rounds and (craft.declared_moves or craft.forced_moves):
            interval = min(interval, 1)
    journey = active(session)
    if journey and journey.status == "travelling":
        interval = min(interval, max(1, journey.remaining_rounds))
    from dungeonforge.rules.weg_medical import scene_interval as medical_interval
    interval = medical_interval(session, interval)
    return interval


def advance_scene(session, rounds, excluded_ids=(), *, emergency_step=False, hazard_step=False):
    from dungeonforge.game.weg_navigation import require_resolved
    if not emergency_step:
        require_resolved(session, hazard_step=hazard_step)
    if (session.encounter and session.encounter.active) or (session.vehicle_encounter and session.vehicle_encounter.active):
        raise ValueError("Use combat turns to advance Force time during an encounter.")
    if rounds < 0:
        raise ValueError("Scene time cannot run backwards.")
    from dungeonforge.rules.weg_models import D6RoundState
    from dungeonforge.game.weg_vehicle_combat import advance_fleet_time
    remaining = rounds
    excluded_clocks = {}
    while remaining:
        interval = scene_interval(session, remaining)
        from dungeonforge.rules import weg_medical as medical
        medically_protected = medical.protected_actor_ids(session)
        roster = synchronize(session)
        for person in roster.values():
            state = person.state
            if person.id in excluded_ids:
                # Recovery pre-accounted for the original timers and Force clock.
                # Fleet injury appends new stun timers or extends unconsciousness;
                # only those new clocks pass through the subsequent scene time.
                baseline = excluded_clocks.setdefault(person.id, {
                    "stun_durations": list(state.stun_durations), "stun_expiries": list(state.stun_expiries),
                    "stun_count": state.stun_count, "unconscious_rounds": state.unconscious_rounds,
                    "injured": False, "mortal": False})
                if baseline["mortal"] and person.id not in medically_protected:
                    WEGD6Rules.advance_mortality(state, interval)
                state.stun_durations = baseline["stun_durations"] + [value - interval
                    for value in state.stun_durations[len(baseline["stun_durations"]):] if value > interval]
                state.stun_expiries = baseline["stun_expiries"] + [value - interval
                    for value in state.stun_expiries[len(baseline["stun_expiries"]):] if value > interval]
                state.stun_count = baseline["stun_count"] + len(state.stun_expiries) - len(baseline["stun_expiries"])
                state.unconscious_rounds = max(baseline["unconscious_rounds"], state.unconscious_rounds - interval)
                if baseline["injured"]:
                    state.round_state = D6RoundState()
                continue
            if person.id not in medically_protected:
                WEGD6Rules.advance_mortality(state, interval)
            state.stun_durations = [value - interval for value in state.stun_durations if value > interval]
            state.stun_expiries = [value - interval for value in state.stun_expiries if value > interval]
            state.stun_count = len(state.stun_expiries)
            state.unconscious_rounds = max(0, state.unconscious_rounds - interval)
            if effects.find_effect(state, "hibernation_trance"):
                state.recovery_days += interval / 17280
            if effects.preparing(state):
                state.force.attempt.preparation_committed = True
            effects.tick(state, interval)
            state.round_state = D6RoundState()
        before = {person.id: (person.state.wound, list(person.state.stun_durations),
            list(person.state.stun_expiries), person.state.unconscious_rounds, person.state.round_state.model_dump())
            for person in roster.values() if person.id in excluded_ids}
        advance_fleet_time(session, interval)
        medical.tick(session, interval)
        for person in roster.values():
            if person.id not in before:
                continue
            state = person.state
            previous = before[person.id]
            current = (state.wound, state.stun_durations, state.stun_expiries,
                state.unconscious_rounds, state.round_state.model_dump())
            if previous != current:
                excluded_clocks[person.id]["injured"] = True
            if previous[0] != "mortally_wounded" and state.wound == "mortally_wounded":
                excluded_clocks[person.id]["mortal"] = True
        remaining -= interval
    session.native_boost = session.force_boost = None
    synchronize(session)


def normalize_request(session, req):
    from dungeonforge.rules.weg_force_catalog import POWERS
    source = actor(session, req.actor_id)
    spec = POWERS.get(req.power_id)
    if spec is None:
        raise ValueError("Unknown 1992 Force power.")
    req.actor_id = source.id
    if spec.target in {"self", "reaction"}:
        if req.target_id and req.target_id != source.id:
            raise ValueError("This power acts only on its user.")
        req.target_id = source.id
        target = None
    else:
        target = actor(session, req.target_id) if req.target_id else None
        if target:
            req.target_is_droid |= "droid" in target.race.lower()
            req.target_is_droid |= target.state.droid is not None
    return source, target, spec


def validate_turn(session, source, power_id=None):
    reactive = power_id == "reduce_injury" and source.state.force.reduce_injury_available
    if reactive:
        return
    from dungeonforge.game.weg_navigation import require_resolved
    require_resolved(session)
    from dungeonforge.game.weg_task_guards import require_available
    require_available(session, source.id)
    if session.vehicle_encounter:
        from dungeonforge.game import weg_vehicle_combat
        if not session.vehicle_encounter.active:
            raise ValueError("End the completed craft encounter before ordinary Force actions.")
        craft, crew = weg_vehicle_combat.validate_turn(session.vehicle_encounter, source.id)
        if crew.evacuated:
            raise ValueError("An evacuated station cannot take a crew Force action.")
    elif session.encounter and session.encounter.active:
        from dungeonforge.game import weg_combat
        weg_combat.validate_turn(session.encounter, weg_combat.actor(session.encounter, source.id))


def mark_action(session, source, result):
    if result.state_changes.get("reaction"):
        return
    if session.vehicle_encounter and session.vehicle_encounter.active:
        session.vehicle_encounter.actions_started = session.vehicle_encounter.turn_acted = True
        session.vehicle_encounter.combat_log.append(result.summary)
        session.vehicle_encounter.boost = None
    elif session.encounter and session.encounter.active:
        session.encounter.d6_actions_started = session.encounter.d6_turn_acted = True
        session.encounter.combat_log.append(result.summary)


def scene_declaration(source, req, spec, continuation=False):
    state = source.state
    if state.round_state.dark_side_called and state.round_state.actions_taken < state.round_state.declared_actions:
        if req.force_point:
            raise ValueError("A Dark Side call already declared this round; use the remaining declared actions.")
        return
    if not continuation:
        if req.power_id not in {"reduce_injury", "remain_conscious"} and (state.round_state.actions_taken or state.round_state.force_active or any(effect.activation_round for effect in state.force.effects)):
            WEGD6Rules.next_round(state)
        from dungeonforge.rules.weg_force import preparation_rounds
        actions = 1 if preparation_rounds(state, spec) > 1 else max(req.actions, len(spec.skills)) if req.same_round else req.actions
        # Internal post-injury powers are allowed to roll even though the normal
        # declaration guard correctly rejects unconscious/dead characters.
        if req.power_id in {"reduce_injury", "remain_conscious"}:
            if req.force_point:
                raise ValueError("Use the injury reaction without a new round-doubling declaration.")
            state.round_state.declared_actions = max(state.round_state.declared_actions, actions)
        else:
            WEGD6Rules.declare(state, actions, req.force_point)
    elif state.round_state.actions_taken == 0 and state.force.attempt:
        attempt = state.force.attempt
        planned = ForcePowerRequest.model_validate(attempt.parameters)
        actions = 1 if attempt.preparation_remaining else max(req.actions, len(attempt.skills) - len(attempt.rolls)) if planned.same_round else req.actions
        if state.force.remain_pending:
            state.round_state.declared_actions = actions
        else:
            WEGD6Rules.declare(state, actions, req.force_point)
