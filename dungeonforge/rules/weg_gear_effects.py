"""1992 printed pp.153,157–158 conditional equipment, added after Force doubling."""
import re

from dungeonforge.rules.weg_gear_effect_models import D6GearContext, GearFacts, MacroPreparation

SOURCE = "WEG40055 (1992), printed pp.153, 157–158."
RANGED = {"blaster", "grenade", "missile_weapons", "bowcaster", "bows", "firearms", "thrown_weapons", "archaic_guns", "blaster_artillery"}
UNUSABLE = {"severely_damaged", "destroyed"}


def key(value):
    value = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return {"per": "perception", "str": "strength", "dex": "dexterity", "know": "knowledge", "mech": "mechanical", "tech": "technical"}.get(value, value)


def parent(state, skill):
    skill = key(skill)
    seen = set()
    while skill in state.specialization_parents and skill not in seen:
        seen.add(skill)
        skill = key(state.specialization_parents[skill])
    return skill


def roster(session):
    people = {person.id: (person.d6, session.character.inventory) for person in [session.character, *session.character.companions] if person.d6}
    if session.encounter and session.encounter.system == "weg_d6":
        for actor in session.encounter.combatants:
            if actor.d6 and actor.id not in people:
                people[actor.id] = (actor.d6, actor.inventory)
    return people


def refresh(session):
    """Bind real inventory on every working copy before any source pool is computed."""
    encounter = session.encounter if session.encounter and session.encounter.active else None
    for actor_id, (state, inventory) in roster(session).items():
        context = state.gear_context
        context._inventory = inventory
        context._actor_id, context._session_id = actor_id, session.id
        context._encounter_id = encounter.id if encounter else None
        context._round = encounter.round if encounter else None
        context._history_index = len(session.history)
        context._scope = None
        prep = context.preparation
        witness = session.history[prep.history_index].rule_result if prep and prep.history_index < len(session.history) else None
        context._preparation_verified = bool(witness and witness.state_changes.get("macro_preparation") == prep.model_dump())
        weapon = next((item for item in inventory if item.item_type == "weapon" and item.quantity > 0 and item.equipped
            and (item.equipped_by == actor_id or actor_id == session.character.id and item.equipped_by is None)), None)
        context._weapon_id = weapon.id if weapon else None


def clear_scopes(session):
    for state, _ in roster(session).values():
        state.gear_context._scope = None


def actual(context, id):
    return next((item for item in context._inventory if item.id == id and item.quantity == 1), None)


def worn(context, item):
    return bool(item and item.equipped and item.equipped_by == context._actor_id)


def armor_function(context, id, catalog, confirmed, reviewed, *, helmet=False):
    item = actual(context, id)
    return bool(confirmed and item and item.catalog_id == catalog and worn(context, item)
        and item.item_type == "armor" and item.armor_energy is not None and item.armor_physical is not None
        and item.armor_damage_state not in UNUSABLE and item.armor_damage_state == reviewed
        and ("head" in item.armor_locations if helmet else {"torso", "left_arm", "right_arm"}.issubset(item.armor_locations)))


def macro_function(context):
    item = actual(context, context.macro_item_id)
    return bool(context.macro_functional and item and item.catalog_id == "macrobinoculars" and worn(context, item)
        and item.weapon_damage_state not in UNUSABLE and item.weapon_damage_state == context.macro_reviewed_damage)


def current_facts(context):
    return context.observed_history_index == context._history_index and context.observed_encounter_id == context._encounter_id and context.observed_round == context._round


def range_band(weapon, distance, fallback=None):
    if distance is None or not weapon or not weapon.d6_ranges:
        return fallback
    low, short, medium, long = weapon.d6_ranges
    if distance > long:
        return None
    return "point_blank" if distance < low else "short" if distance <= short else "medium" if distance <= medium else "long"


def bind_check(state, skill):
    context = state.gear_context
    weapon = actual(context, context._weapon_id)
    context._scope = {"kind": "check", "skill": key(skill), "target_id": context.target_id,
        "weapon_id": context._weapon_id, "band": range_band(weapon, context.view_distance_m)}


def bind_attack(session, actor_id, target_id, weapon, options=None):
    refresh(session)
    found = roster(session).get(actor_id)
    if not found:
        raise ValueError("Choose an actual combat actor before binding conditional gear.")
    state = found[0]
    context = state.gear_context
    context._scope = {"kind": "attack", "skill": key(weapon.d6_skill or "blaster") if weapon else "brawling",
        "target_id": target_id, "weapon_id": weapon.id if weapon else None,
        "band": range_band(weapon, options.distance_m if options else None,
            options.range_band if options else "short")}


def preparation_ready(state, context, weapon):
    prep = context.preparation
    return bool(prep and prep.actor_id == context._actor_id and context._preparation_verified and context.position_maintained and context.steady_rest and context.software_confirmed
        and context.software_facts.strip() and weapon and weapon.id == context.linked_weapon_id
        and weapon.id == prep.weapon_id and prep.macro_item_id == context.macro_item_id and prep.target_id == context.target_id
        and prep.encounter_id == context._encounter_id
        and (context._round is None and state.force.elapsed_rounds >= prep.completed_elapsed_round
            or context._round is not None and prep.round_number is not None and context._round > prep.round_number))


def gear_bonus(state, skill, attribute=None):
    """No client bonus number exists: derive each bonus from real current objects."""
    context = state.gear_context
    if not context._session_id or not context._actor_id or not context.reason.strip():
        return 0
    skill_key = key(skill)
    base = parent(state, skill_key)
    bonus = int(base == "lifting" and armor_function(context, context.powersuit_id, "bounty_hunter_armor",
        context.powersuit_functional, context.powersuit_reviewed_damage))
    scope = context._scope
    if not scope or scope.get("skill") != skill_key or not current_facts(context):
        return bonus
    visual = context.visual_task_confirmed and key(context.visual_skill) == skill_key
    mftas = armor_function(context, context.mftas_id, "stormtrooper_armor", context.mftas_functional,
        context.mftas_reviewed_damage, helmet=True)
    if mftas and skill_key == "perception" and visual and context.visibility_obscured:
        bonus += 2
    matching_target = bool(context.target_id and scope.get("target_id") == context.target_id)
    weapon = actual(context, scope.get("weapon_id"))
    if mftas and matching_target and base in RANGED and context.target_movement_m > 10 and weapon and worn(context, weapon) and weapon.weapon_damage_state not in UNUSABLE:
        bonus += 2
    if not macro_function(context) or not matching_target:
        return bonus
    if context.macro_mode in {"view", "linked"} and visual and attribute == "perception" and context.view_distance_m is not None and 100 < context.view_distance_m <= context.macro_model_range_m:
        bonus += 3
    if (context.macro_mode == "linked" and base == "blaster" and scope.get("band") in {"medium", "long"} and weapon and worn(context, weapon)
            and weapon.d6_skill == "blaster" and weapon.weapon_damage_state not in UNUSABLE and preparation_ready(state, context, weapon)):
        bonus += 3
    return bonus


def stamp_next_action(session, context):
    context.observed_history_index = len(session.history) + 1
    context.observed_encounter_id = session.encounter.id if session.encounter and session.encounter.active else None
    context.observed_round = session.encounter.round if session.encounter and session.encounter.active else None


def configure(session, req):
    refresh(session)
    found = roster(session).get(req.actor_id)
    if found is None:
        raise ValueError("Choose an actual native actor.")
    state, inventory = found
    old = state.gear_context
    if not req.reason.strip():
        raise ValueError("Record the actual equipment, visual task, target and GM scene facts.")
    facts = D6GearContext(**req.model_dump(include=set(GearFacts.model_fields)))
    facts._inventory, facts._actor_id, facts._session_id = inventory, req.actor_id, session.id
    for id, catalog, enabled, helmet, reviewed_key in ((facts.powersuit_id, "bounty_hunter_armor", facts.powersuit_functional, False, "powersuit_reviewed_damage"),
            (facts.mftas_id, "stormtrooper_armor", facts.mftas_functional, True, "mftas_reviewed_damage")):
        if id:
            item = actual(facts, id)
            if not item:
                raise ValueError("Choose one actual distinct armor record, not a missing item or ambiguous stack.")
            setattr(facts, reviewed_key, item.armor_damage_state)
            if item.catalog_id != catalog or not worn(facts, item) or enabled and not armor_function(facts, id, catalog, enabled, item.armor_damage_state, helmet=helmet):
                raise ValueError("The selected source armor must actually be worn by this actor, cover the required areas, and have confirmed functioning equipment; severe/destroyed gear is unusable.")
        elif enabled:
            raise ValueError("A functioning armor bonus needs its actual worn source item ID.")
    if facts.visual_task_confirmed:
        from dungeonforge.rules.weg_d6 import WEGD6Rules
        _, attribute = WEGD6Rules.skill_code(state, facts.visual_skill)
        if attribute != "perception":
            raise ValueError("Macrobinocular observation needs an actual Perception/search-oriented visual skill, not a bonus to unrelated skills.")
    encounter = session.encounter if session.encounter and session.encounter.active else None
    if facts.target_movement_m > 10 or facts.macro_mode != "off":
        if not facts.target_id.strip():
            raise ValueError("Record the actual observation/attack target.")
        if encounter and not any(actor.id == facts.target_id and actor.id != req.actor_id for actor in encounter.combatants):
            raise ValueError("Select the actual other combatant as the target for these conditions.")
    if facts.macro_mode != "off":
        item = actual(facts, facts.macro_item_id)
        if not item or item.catalog_id != "macrobinoculars" or item.weapon_damage_state in UNUSABLE or not facts.macro_functional:
            raise ValueError("Choose the actual distinct functional source macrobinoculars.")
        if item.equipped_by and item.equipped_by != req.actor_id:
            raise ValueError("These actual macrobinoculars are already assigned to someone else; release them first.")
        item.equipped, item.equipped_by = True, req.actor_id
        facts.macro_reviewed_damage = item.weapon_damage_state
        if facts.view_distance_m is None:
            raise ValueError("Record the actual target/observation distance; the macro bonus does not extend weapon range.")
        if facts.macro_mode == "linked":
            weapon = actual(facts, facts.linked_weapon_id)
            if not weapon or not worn(facts, weapon) or weapon.item_type != "weapon" or weapon.d6_skill != "blaster" or weapon.weapon_damage_state in UNUSABLE:
                raise ValueError("Link only this actor's actual drawn usable blaster; its saved ranges and other statistics remain authoritative.")
            if not facts.software_confirmed or not facts.software_facts.strip() or not facts.steady_rest:
                raise ValueError("A linked macro needs actual installed programming software, a steady resting spot and a full preparation round.")
    previous_macro = next((item for item in inventory if item.id == old.macro_item_id and item.catalog_id == "macrobinoculars"), None)
    if previous_macro and (facts.macro_mode == "off" or previous_macro.id != facts.macro_item_id) and previous_macro.equipped_by == req.actor_id:
        previous_macro.equipped, previous_macro.equipped_by = False, None
    if facts.position_maintained and old.preparation and facts.macro_item_id == old.preparation.macro_item_id and facts.linked_weapon_id == old.preparation.weapon_id and facts.target_id == old.preparation.target_id:
        facts.preparation = old.preparation
    facts.history = [*old.history, {"kind": "facts", "reason": facts.reason, "target_id": facts.target_id}]
    stamp_next_action(session, facts)
    state.gear_context = facts
    refresh(session)
    return state


def mark_prepared(session, actor_id, weapon_id, target_id, *, downtime=False):
    refresh(session)
    found = roster(session).get(actor_id)
    if not found:
        raise ValueError("Choose an actual actor for preparation.")
    state = found[0]
    context = state.gear_context
    if context.macro_mode != "linked":
        return False
    weapon = actual(context, weapon_id)
    if not macro_function(context) or not weapon or weapon_id != context.linked_weapon_id or target_id != context.target_id or not worn(context, weapon) or not context.software_confirmed or not context.software_facts.strip() or not context.steady_rest:
        context.preparation = None
        return False
    context.preparation = MacroPreparation(actor_id=actor_id, history_index=len(session.history), macro_item_id=context.macro_item_id, weapon_id=weapon_id,
        target_id=target_id, encounter_id=context._encounter_id, round_number=None if downtime else context._round,
        completed_elapsed_round=state.force.elapsed_rounds)
    context.position_maintained = True
    context.history.append({"kind": "preparation", "target_id": target_id, "weapon_id": weapon_id,
        "round_number": context._round, "elapsed_round": state.force.elapsed_rounds})
    stamp_next_action(session, context)
    return True
