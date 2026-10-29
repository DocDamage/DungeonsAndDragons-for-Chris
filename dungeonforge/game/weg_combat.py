"""WEG side initiative, declared action passes, defenses, and persistent wounds."""

import uuid

from dungeonforge.rules.base import Item
from dungeonforge.rules.weg_d6 import D6Roller, WEGD6Rules, parse_code
from dungeonforge.rules.weg_models import D6Character, D6RoundState
from dungeonforge.rules import weg_force_effects as effects


def archive(session):
    """Retain resolved native battlefield, gear and explosion evidence after combat."""
    encounter = session.encounter
    if not encounter or encounter.system != "weg_d6" or any(item.id == encounter.id for item in session.d6_combat_history):
        return
    from dungeonforge.rules.weg_explosives import pending
    if pending(encounter) or encounter.d6_round_closing:
        raise ValueError("Finish live fuses and round-end injury reactions before archiving this encounter.")
    saved = encounter.model_copy(deep=True)
    saved.active = False
    session.d6_combat_history.append(saved)


def refresh(encounter):
    for combatant in encounter.combatants:
        combatant.is_defeated = combatant.d6.out_of_fight
    enemies = [c for c in encounter.combatants if not c.is_player and not c.is_defeated]
    party = [c for c in encounter.combatants if c.is_player and not c.is_defeated]
    from dungeonforge.rules.weg_explosives import pending
    if pending(encounter) or encounter.d6_round_closing:
        encounter.active = True
        return
    if encounter.active and (not enemies or not party):
        encounter.active = False
        encounter.combat_log.append("VICTORY: enemy side is out of the fight." if not enemies else "DEFEAT: the party is out of the fight.")


def bind_party(encounter, character):
    for person in [character, *character.companions]:
        combatant = next((c for c in encounter.combatants if c.id == person.id), None)
        if combatant and combatant.d6:
            person.d6 = combatant.d6
    from dungeonforge.rules.weg_personal_equipment import canonical_party_gear
    canonical_party_gear(encounter, character)


def roll_initiative(encounter):
    sides = {}
    for player_side in (True, False):
        members = [c for c in encounter.combatants if c.is_player == player_side and not c.is_defeated]
        leader = max(members, key=lambda c: parse_code(c.d6.attributes["perception"]), default=None)
        sides[player_side] = leader
    scores = {}
    for _ in range(25):
        for side, leader in sides.items():
            if leader is None:
                scores[side] = 0
                continue
            dice, pips = WEGD6Rules.pool(leader.d6, "perception")
            roll = D6Roller.values(dice, pips, mishap="penalty") if dice > 0 else None
            scores[side] = roll.total if roll else 0
            encounter.combat_log.append(f"{'Party' if side else 'Enemy'} initiative ({leader.name}, Perception): {roll.breakdown if roll else 'pool depleted; no initiative dice'}")
        if scores[True] != scores[False] or not all(sides.values()):
            break
    encounter.d6_initiative_winner = scores[True] >= scores[False]
    for combatant in encounter.combatants:
        combatant.initiative = scores[combatant.is_player]
    order_sides(encounter, winner_first=True)


def order_sides(encounter, winner_first=True):
    if encounter.d6_actions_started:
        raise ValueError("Initiative order must be chosen before actions begin.")
    first_side = encounter.d6_initiative_winner if winner_first else not encounter.d6_initiative_winner
    encounter.combatants.sort(key=lambda c: (c.is_player != first_side, -parse_code(c.d6.attributes["perception"])[0], -parse_code(c.d6.attributes["perception"])[1]))
    encounter.current_turn_index = next((i for i, c in enumerate(encounter.combatants) if not c.is_defeated), 0)
    encounter.d6_turn_acted = False


def start(encounter, player, enemies):
    from dungeonforge.game.combat import Combatant
    if player.d6 is None:
        raise ValueError("Start a native Star Wars D6 character before combat.")
    combatants = []
    for person in [player, *player.companions]:
        if person.d6 is None:
            raise ValueError(f"{person.name} needs a native D6 sheet.")
        person.d6.round_state = D6RoundState()
        person.d6.force.saber_locked = False
        for effect in person.d6.force.effects:
            effect.activation_round = False
        weapon = next((item for item in player.inventory if item.equipped and item.item_type == "weapon" and item.equipped_by in {None, player.id}), None) if person is player else person.d6_weapon or Item(name=person.attack_name, damage=person.damage, d6_skill="blaster")
        if weapon and weapon.weapon_damage_state not in {"severely_damaged", "destroyed"}:
            WEGD6Rules.damage_pool(person.d6, weapon)
        combatants.append(Combatant(id=person.id, name=person.name, race=person.race, is_player=True, d6=person.d6, weapon=weapon, is_defeated=person.d6.out_of_fight))
    for enemy in enemies:
        if not enemy.get("d6"):
            raise ValueError("Native D6 enemies require six attribute pools in a d6 sheet; HP and AC stat blocks cannot be used.")
        state = D6Character.model_validate(enemy["d6"])
        state.round_state = D6RoundState()
        enemy_id = f"enemy_{uuid.uuid4().hex[:8]}"
        weapon = Item.model_validate(enemy.get("weapon") or {"name": "Blaster", "damage": "4D", "d6_skill": "blaster"})
        weapon.equipped, weapon.equipped_by = True, enemy_id
        inventory = [Item.model_validate(item) for item in enemy.get("inventory", [])]
        inventory = [item for item in inventory if item.id != weapon.id] + [weapon]
        armor = [Item.model_validate(item) for item in enemy.get("armor", [])]
        for item in armor:
            item.equipped, item.equipped_by = True, enemy_id
            if not any(existing.id == item.id for existing in inventory):
                inventory.append(item)
        if weapon.weapon_damage_state not in {"severely_damaged", "destroyed"}:
            WEGD6Rules.damage_pool(state, weapon)
        if armor:
            from dungeonforge.rules.weg_personal_equipment import refresh_armor
            refresh_armor(state, armor)
        combatants.append(Combatant(id=enemy_id, name=enemy.get("name", "Imperial Trooper"), race=enemy.get("race", "Human"), d6=state, weapon=weapon, inventory=inventory, armor=armor, is_defeated=state.out_of_fight))
    if not any(c.is_player and not c.is_defeated for c in combatants) or not any(not c.is_player and not c.is_defeated for c in combatants):
        raise ValueError("Each side needs at least one conscious combatant.")
    encounter.combatants = combatants
    encounter.system = "weg_d6"
    encounter.combat_log.clear()
    encounter.round = 1
    encounter.active = True
    encounter.d6_actions_started = False
    encounter.d6_turn_acted = False
    encounter.d6_round_closing = False
    encounter.d6_round_results.clear()
    encounter.cover_objects.clear()
    encounter.weapon_fire.clear()
    from dungeonforge.rules.weg_explosives_models import D6ExplosivesState
    encounter.d6_explosives = D6ExplosivesState()
    bind_party(encounter, player)
    roll_initiative(encounter)
    encounter.combat_log.append("WEG D6 combat: declare actions and defenses, then resolve one action per combatant in side order.")


def actor(encounter, actor_id):
    result = next((c for c in encounter.combatants if c.id == actor_id), None)
    if not result or result.d6 is None:
        raise ValueError("Native D6 combatant not found.")
    return result


def validate_turn(encounter, combatant):
    if not encounter.active:
        raise ValueError("No active combat encounter.")
    if encounter.active_combatant is None or encounter.active_combatant.id != combatant.id:
        raise ValueError("Advance to this combatant's action before rolling.")
    if encounter.d6_turn_acted:
        raise ValueError("This action pass is complete; advance to the next combatant.")


def attack(encounter, character, target_id, weapon=None, options=None, actor_id=None):
    bind_party(encounter, character)
    attacker = actor(encounter, actor_id or character.id)
    target = actor(encounter, target_id)
    if attacker.id == target.id:
        raise ValueError("Choose a different combatant as target.")
    validate_turn(encounter, attacker)
    used_weapon = weapon if attacker.id == character.id else attacker.weapon
    preparation = attacker.d6.combat_preparation
    prepared = bool(preparation and preparation.encounter_id == encounter.id and preparation.round_number == encounter.round - 1
        and used_weapon and preparation.weapon_id == used_weapon.id and preparation.target_id == target.id
        and attacker.d6.round_state.declared_actions == 1 and not attacker.d6.round_state.actions_taken
        and not attacker.d6.round_state.defense_skill and not effects.upkeep(attacker.d6))
    cover = next((item for item in encounter.cover_objects if item.id == target.cover_id), None)
    fired = encounter.weapon_fire.get(used_weapon.id, {}) if used_weapon else {}
    fire_control = {"shots": fired.get("shots", 0) if fired.get("round") == encounter.round else 0, "last": fired.get("round"), "now": encounter.round}
    result = WEGD6Rules.resolve_attack(attacker.d6, target.d6, used_weapon, options, armor_items=target.armor or None, prepared=prepared,
        cover=cover, cover_fraction=target.cover_fraction, concealment_dice=target.concealment_dice, fire_control=fire_control, target_weapon=target.weapon)
    if used_weapon and not result.state_changes.get("no_attack_action"):
        encounter.weapon_fire[used_weapon.id] = {"round": encounter.round, "shots": fire_control["shots"] + 1}
    result.state_changes["force_injury_targets"] = ([target.id] if result.wound_result else []) + ([attacker.id] if result.state_changes.get("self_injury") else [])
    if result.success and WEGD6Rules.weapon_skill(used_weapon) == "brawling":
        attacker.d6.round_state.touched_targets.append(target.id)
    if result.state_changes.get("parried_blaster") and target.d6.round_state.redirect_blaster:
        declaration = target.d6.round_state.redirect_blaster
        if declaration["attacker_id"] == attacker.id:
            from dungeonforge.rules.weg_force import redirect_bolt
            receiver = actor(encounter, declaration["target_id"])
            redirect_bolt(target.d6, receiver.d6, used_weapon, declaration, result)
            if result.state_changes.get("redirected_injury"):
                result.state_changes["force_injury_targets"].append(receiver.id)
    encounter.d6_actions_started = True
    encounter.d6_turn_acted = not result.state_changes.get("no_attack_action", False)
    encounter.combat_log.append(f"{attacker.name} → {target.name}: {result.summary}")
    refresh(encounter)
    bind_party(encounter, character)
    return result


def next_turn(encounter):
    encounter.d6_round_results.clear()
    if not encounter.active:
        return None
    current = encounter.active_combatant
    if current and not encounter.d6_turn_acted and not encounter.d6_round_closing:
        effects.skip_turn(current.d6)
        current.d6.round_state.actions_taken = min(current.d6.round_state.declared_actions, current.d6.round_state.actions_taken + 1)
    encounter.d6_actions_started = True
    for offset in range(1, len(encounter.combatants) + 1) if not encounter.d6_round_closing else ():
        index = (encounter.current_turn_index + offset) % len(encounter.combatants)
        candidate = encounter.combatants[index]
        state = candidate.d6
        if state.can_take_turn and state.round_state.actions_taken < state.round_state.declared_actions:
            encounter.current_turn_index = index
            encounter.d6_turn_acted = False
            return candidate
    from dungeonforge.rules.weg_explosives import end_round
    encounter.d6_round_results.extend(end_round(encounter, encounter.round, limit=1))
    if encounter.d6_round_results:
        encounter.d6_round_closing = True
        encounter.d6_turn_acted = True
        encounter.combat_log.append("Round-end explosion resolved. Resolve immediate injury reactions, then continue any remaining due blasts before advancing the round.")
        refresh(encounter)
        return encounter.active_combatant
    encounter.d6_round_closing = False
    encounter.round += 1
    encounter.d6_actions_started = False
    encounter.d6_turn_acted = False
    for combatant in encounter.combatants:
        WEGD6Rules.next_round(combatant.d6)
    refresh(encounter)
    if not encounter.active:
        return None
    encounter.combat_log.append(f"--- Round {encounter.round}: new Perception side initiative ---")
    roll_initiative(encounter)
    return encounter.active_combatant
