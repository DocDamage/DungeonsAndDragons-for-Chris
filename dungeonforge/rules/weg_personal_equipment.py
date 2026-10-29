"""Actual personal gear in attacks: 1992 printed pp.65–68, 154–158."""
import math


LEVELS = ("intact", "lightly_damaged", "heavily_damaged", "severely_damaged", "destroyed")


def hit_location():
    from dungeonforge.rules.dice import DiceRoller
    roll = DiceRoller.roll("1d6").total
    if roll == 4:
        return "left_arm" if DiceRoller.roll("1d6").total <= 3 else "right_arm"
    return {1: "head", 2: "torso", 3: "torso", 5: "left_leg", 6: "right_leg"}[roll]


def armor_pips(item, profile):
    from dungeonforge.rules.weg_d6 import parse_code
    value = getattr(item, "armor_energy" if profile == "energy" else "armor_physical")
    if value is None or item.armor_damage_state in {"severely_damaged", "destroyed"}:
        return 0
    dice, extra = parse_code(value)
    return max(0, dice * 3 + extra - {"intact": 0, "lightly_damaged": 1, "heavily_damaged": 3}[item.armor_damage_state])


def armor_for_hit(items, profile, location=None, side="front"):
    candidates = [item for item in items if item.quantity > 0 and side in item.armor_sides and (location is None or location in item.armor_locations)]
    return max(candidates, key=lambda item: armor_pips(item, profile), default=None)


def apply_armor_damage(item, injury):
    severity = {"wounded": "lightly_damaged", "incapacitated": "heavily_damaged", "mortally_wounded": "severely_damaged", "dead": "destroyed"}.get(injury)
    if item is None or severity is None:
        return None
    before = item.armor_damage_state
    item.armor_damage_state = LEVELS[max(LEVELS.index(before), LEVELS.index(severity))]
    return {"id": item.id, "name": item.name, "before": before, "after": item.armor_damage_state}


def validate_weapon(state, weapon, options, fire_control=None):
    if weapon is None:
        if options.bowcaster_strength_character_points:
            raise ValueError("An unarmed attack has no bowcaster Strength check.")
        return options.range_band
    if weapon.quantity <= 0 or weapon.weapon_damage_state in {"severely_damaged", "destroyed"}:
        raise ValueError("The actual weapon is expended, severely damaged or destroyed and cannot be used.")
    if weapon.requires_generator and not weapon.generator_connected:
        raise ValueError("This weapon requires its actual connected power generator.")
    generator = weapon.generator_connected and (weapon.requires_generator or weapon.catalog_id == "light_repeating_blaster")
    if (not generator and weapon.ammo == 0) or weapon.power_ammo == 0:
        raise ValueError("The actual weapon is out of ammunition or power; reload its real compatible supply first.")
    if weapon.catalog_id and options.stun and not weapon.d6_can_stun:
        raise ValueError("This source weapon has no stun setting.")
    if weapon.catalog_id and weapon.d6_can_stun and options.stun != weapon.stun_mode:
        raise ValueError("Use the weapon-setting action before firing on a different setting.")
    shots = fire_control["shots"] if fire_control is not None else state.round_state.weapon_shots.get(weapon.id, 0)
    if weapon.id in state.round_state.bowcaster_blocked:
        raise ValueError("This bowcaster's additional-shot Strength attempt already failed this round.")
    if weapon.d6_fire_rate is not None and weapon.catalog_id != "bowcaster":
        if weapon.d6_fire_rate >= 1 and shots >= math.floor(weapon.d6_fire_rate):
            raise ValueError("This weapon has reached its printed fire rate for this round.")
        if weapon.d6_fire_rate < 1:
            last = fire_control["last"] if fire_control is not None else state.weapon_last_fired.get(weapon.id)
            now = fire_control["now"] if fire_control is not None else state.force.elapsed_rounds
            if last is not None and now - last < math.ceil(1 / weapon.d6_fire_rate):
                raise ValueError("This weapon has not waited its printed number of rounds between shots.")
    if options.bowcaster_strength_character_points and (weapon.catalog_id != "bowcaster" or not shots):
        raise ValueError("Additional-shot Strength CP applies only after this actual bowcaster's first shot of the round.")
    if options.character_points + options.bowcaster_strength_character_points > state.character_points:
        raise ValueError("The actor cannot afford both declared attack and bowcaster Strength dice.")
    if options.bowcaster_strength_character_points and (state.round_state.force_active or state.round_state.dark_side_called):
        raise ValueError("Force and Character Points cannot combine on the bowcaster Strength check.")
    if options.distance_m is not None and weapon.d6_ranges:
        low, short, medium, long = weapon.d6_ranges
        if options.distance_m > long:
            raise ValueError("The actual target is beyond this weapon's printed long range.")
        return "point_blank" if options.distance_m < low else "short" if options.distance_m <= short else "medium" if options.distance_m <= medium else "long"
    return options.range_band


def record_shot(state, weapon, fire_control=None):
    if weapon is None:
        return
    generator = weapon.generator_connected and (weapon.requires_generator or weapon.catalog_id == "light_repeating_blaster")
    if weapon.ammo is not None and not generator:
        weapon.ammo -= 1
    if weapon.power_ammo is not None:
        weapon.power_ammo -= 1
    if weapon.d6_skill == "grenade":
        weapon.quantity -= 1
    state.round_state.weapon_shots[weapon.id] = (fire_control["shots"] if fire_control is not None else state.round_state.weapon_shots.get(weapon.id, 0)) + 1
    state.weapon_last_fired[weapon.id] = state.force.elapsed_rounds


def canonical_party_gear(encounter, character):
    """Saved encounter copies bind back to the actual inventory IDs, never fresh ammo."""
    inventory = {item.id: item for item in character.inventory}
    people = {person.id: person for person in [character, *character.companions]}
    for combatant in encounter.combatants:
        if combatant.id not in people:
            own = {item.id: item for item in combatant.inventory}
            if combatant.weapon and combatant.weapon.id in own:
                combatant.weapon = own[combatant.weapon.id]
            combatant.armor = [own.get(item.id, item) for item in combatant.armor]
            continue
        current = combatant.weapon
        if current and current.id in inventory:
            combatant.weapon = inventory[current.id]
            if combatant.id == character.id and combatant.weapon.equipped and combatant.weapon.equipped_by is None:
                combatant.weapon.equipped_by = character.id
            if combatant.weapon.quantity <= 0 or not combatant.weapon.equipped or combatant.weapon.equipped_by != combatant.id:
                combatant.weapon = None
        elif current and current.item_type != "natural_weapon" and (combatant.id == character.id or current.catalog_id or current.equipped_by):
            combatant.weapon = None
        assigned = [item for item in character.inventory if item.quantity > 0 and item.equipped and item.equipped_by == combatant.id]
        chosen = next((item for item in assigned if item.item_type == "weapon"), None)
        if chosen:
            combatant.weapon = chosen
        combatant.armor = [item for item in assigned if item.item_type == "armor" and item.armor_energy is not None and item.armor_physical is not None]
        person = people[combatant.id]
        if person is not character and combatant.weapon:
            person.d6_weapon = combatant.weapon
        elif person is not character and person.d6_weapon and person.d6_weapon.item_type != "natural_weapon" and (person.d6_weapon.catalog_id or person.d6_weapon.equipped_by):
            from dungeonforge.rules.base import Item
            combatant.weapon = person.d6_weapon = Item(name="Brawling", item_type="natural_weapon", damage="STR", d6_skill="brawling", damage_type="physical", equipped_by=person.id)


def refresh_armor(state, items):
    """Keep the sheet's summary in step with actual worn armor damage."""
    for profile in ("energy", "physical"):
        value = max((armor_pips(item, profile) for item in items), default=0)
        setattr(state, "armor_" + profile, f"{value // 3}D" + (f"+{value % 3}" if value % 3 else ""))
    state.dexterity_penalty = sum(item.armor_dexterity_penalty for item in items if item.quantity > 0 and item.armor_damage_state != "destroyed")
