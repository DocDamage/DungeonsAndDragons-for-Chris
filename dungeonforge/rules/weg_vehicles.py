"""WEG40055 (1992): PDF p.68 scale caps, pp.89–94 vehicles, pp.101–103 ships.

Equipment dice never receive Force Point doubling or character wound/MAP penalties.
GM-provided distance, fire arcs, terrain and passenger exposure describe the scene.
"""

import random

from dungeonforge.rules.base import RuleEvaluationResult
from dungeonforge.rules.dice import DiceRoller, RollResult
from dungeonforge.rules.weg_d6 import D6Roller, WEGD6Rules, parse_code
from dungeonforge.rules import weg_force_effects as effects


SCALES = ("character", "speeder", "walker", "starfighter", "capital", "death_star")
TO_HIT = (
    (6, 6, 6, 6, 6, 6), (4, 6, 6, 6, 6, 6), (3, 5, 6, 6, 6, 6),
    (2, 4, 5, 6, 6, 6), (None, 2, 2, 3, 6, 6), (None, None, None, None, 3, 6),
)
TO_DODGE = (
    (6, 5, 5, 3, None, None), (6, 6, 5, 4, 2, None), (None, 2, 6, 2, None, None),
    (6, 6, 6, 6, 6, 6), (None, None, None, 2, 6, 4), (None, None, None, None, 3, 6),
)
DAMAGE_CAP = (
    (6, 3, 2, 2, None, None), (6, 6, 3, 3, 1, None), (6, 6, 6, 3, 1, None),
    (6, 6, 6, 6, 3, None), (6, 6, 6, 6, 6, 1), (6, 6, 6, 6, 6, 6),
)
RESIST_CAP = (
    (6, 6, 6, 6, 6, 6), (3, 6, 6, 6, 6, 6), (2, 3, 6, 6, 6, 6),
    (2, 3, 3, 6, 6, 6), (None, 1, 1, 3, 6, 6), (None, None, None, None, 1, 6),
)
ARCS = ("front", "back", "left", "right")
RANK = {"intact": 0, "lightly_damaged": 1, "heavily_damaged": 2, "severely_damaged": 3, "destroyed": 4}


def cap_for(table, source, target):
    return table[SCALES.index(source)][SCALES.index(target)]


def capped(roll, cap):
    """Cap already rolled dice, including Wild/CP explosions; pips are unchanged."""
    result = roll.model_copy(deep=True)
    result.kept_rolls = [min(value, cap) for value in roll.kept_rolls] if cap else []
    result.total = sum(result.kept_rolls) + (roll.modifier if cap else 0)
    if cap != 6:
        result.breakdown += f"; scale cap {cap if cap else '— (cannot resist)'}: {result.kept_rolls}, pips {result.modifier if cap else 0:+d} = {result.total}"
    return result


def add_codes(*codes):
    pools = [parse_code(code) for code in codes]
    return sum(pool[0] for pool in pools), sum(pool[1] for pool in pools)


def pips(code):
    dice, extra = parse_code(code)
    return dice * 3 + extra


def code_from_pips(total):
    dice, extra = divmod(max(0, total), 3)
    return f"{dice}D" + (f"+{extra}" if extra else "")


def fixed_roll(dice, extra=0, cap=6):
    if cap is None:
        return RollResult(expression="Cannot resist", dice_count=0, die_type=6, system="weg_d6", breakdown="Scale chart: no resistance possible", total=0)
    roll = D6Roller.values(dice, extra) if dice > 0 else RollResult(
        expression=f"0D+{extra}" if extra else "0D", dice_count=0, die_type=6,
        modifier=extra, total=extra, system="weg_d6", breakdown=f"No equipment dice; pips {extra:+d} = {extra}",
    )
    return capped(roll, cap)


class WEGVehicleRules:
    @staticmethod
    def equipment(craft, code, losses=0):
        # Losses remove whole dice, leaving the original equipment pips intact.
        dice, extra = parse_code(code)
        return max(0, dice - losses - len(craft.ion_durations)), extra

    @staticmethod
    def validate_crew(crew, skill, points=0, defensive=False, equipment=(0, 0)):
        state = crew.d6
        if crew.evacuated:
            raise ValueError("An evacuated crew member cannot operate the craft.")
        if not state.can_act:
            raise ValueError("This crew member is wounded out, unconscious, or blocked for the round.")
        if state.round_state.full_defense or state.round_state.actions_taken >= state.round_state.declared_actions:
            raise ValueError("This crew member has no declared skill actions remaining.")
        limit = 5 if defensive or skill in state.specializations else 2
        if not 0 <= points <= limit or points > state.character_points:
            raise ValueError(f"This roll allows at most {limit} available Character Points.")
        if points and (state.round_state.force_active or state.round_state.dark_side_called):
            raise ValueError("Force and Character Points cannot be combined in one round.")
        dice, extra = WEGD6Rules.pool(state, skill)
        dice += equipment[0] - crew.control_penalty
        extra += equipment[1]
        if dice < 1:
            raise ValueError("Crew, action, wound, control, and equipment penalties leave no dice.")
        return dice, extra

    @staticmethod
    def crew_roll(crew, skill, points=0, mishap="penalty", defensive=False, equipment=(0, 0), cap=6):
        dice, extra = WEGVehicleRules.validate_crew(crew, skill, points, defensive, equipment)
        roll = capped(D6Roller.values(dice, extra, points, mishap), cap)
        crew.d6.character_points -= points
        crew.d6.round_state.character_points_spent |= points > 0
        effects.take_action(crew.d6)
        effects.settle_consciousness(crew.d6)
        return roll

    @staticmethod
    def operational(craft, movement=False):
        if craft.damage == "destroyed" or craft.generator_shutdown or craft.controls_dead:
            raise ValueError("This craft is destroyed or its controls/power are offline.")
        if craft.frozen_rounds and not movement:
            raise ValueError("Controls are frozen: only mandatory straight-line movement checks are possible.")

    @staticmethod
    def pilot(craft):
        return next(person for person in craft.crew if "pilot" in person.stations)

    @staticmethod
    def dodge(craft, crew, full=False, points=0, mishap="penalty"):
        WEGVehicleRules.operational(craft)
        if "pilot" not in crew.stations:
            raise ValueError("Only the pilot can make a vehicle dodge.")
        if craft.dodge_roll is not None:
            raise ValueError("A vehicle dodge has already been rolled this round.")
        if full and (crew.d6.round_state.declared_actions != 1 or crew.d6.round_state.actions_taken):
            raise ValueError("Full vehicle dodge must be the pilot's only skill action.")
        if full and craft.declared_moves and not craft.half_speed:
            raise ValueError("A full vehicle dodge permits only a free half-speed move.")
        equipment = WEGVehicleRules.equipment(craft, craft.maneuverability, craft.maneuverability_lost)
        roll = WEGVehicleRules.crew_roll(crew, craft.piloting_skill, points, mishap, True, equipment)
        craft.dodge_roll = roll
        craft.full_dodge = full
        crew.d6.round_state.full_defense = full
        return RuleEvaluationResult(action_type="vehicle_dodge", success=True, roll_result=roll,
            summary=f"[WEG D6 {'Full' if full else 'Normal'} Vehicle Dodge] {craft.name}: {roll.expression}; {roll.breakdown}. Scale caps are applied separately against each incoming weapon.")

    @staticmethod
    def shield_budget(craft):
        return max(0, pips(craft.shields) - 3 * (craft.shields_lost + len(craft.ion_durations)))

    @staticmethod
    def shields(craft, crew, allocation, difficulty=None, points=0, mishap="penalty"):
        WEGVehicleRules.operational(craft)
        if "shields" not in crew.stations:
            raise ValueError("Select a crew member at a shields station.")
        if craft.shields_rolled:
            raise ValueError("Shields have already been deployed or attempted this round.")
        allocation = {arc: code for arc, code in allocation.items() if pips(code) > 0}
        count = len(allocation)
        if count == 0 or sum(pips(code) for code in allocation.values()) > WEGVehicleRules.shield_budget(craft):
            raise ValueError("Allocate positive shield dice within the remaining shield pool.")
        target = difficulty or (10, 15, 20, 30)[count - 1]
        skill = "capital_ship_shields" if craft.scale in {"capital", "death_star"} else "starship_shields"
        roll = WEGVehicleRules.crew_roll(crew, skill, points, mishap, True)
        craft.shields_rolled = True
        craft.shield_allocation = allocation if roll.total >= target else {}
        return RuleEvaluationResult(action_type="vehicle_shields", success=roll.total >= target, roll_result=roll, target_value=target,
            summary=f"[WEG D6 Shields] {crew.name} on {craft.name}: {roll.breakdown} vs {target} ({count} arc(s)) → {'DEPLOYED' if roll.total >= target else 'FAILED'}. {craft.shield_allocation}")

    @staticmethod
    def lose_shields(craft, dice, incoming="front"):
        available = max(0, pips(craft.shields) - 3 * craft.shields_lost)
        loss = min(available, dice * 3)
        craft.shields_lost += dice
        # Remove the hit arc first, then other arcs in a stable order.
        for arc in [incoming, *(arc for arc in ARCS if arc != incoming)]:
            before = pips(craft.shield_allocation.get(arc, "0D"))
            removed = min(loss, before)
            if before > removed:
                craft.shield_allocation[arc] = code_from_pips(before - removed)
            else:
                craft.shield_allocation.pop(arc, None)
            loss -= removed

    @staticmethod
    def ionize(craft, count):
        craft.ion_durations.extend([2] * count)
        excess = max(0, sum(pips(code) for code in craft.shield_allocation.values()) - WEGVehicleRules.shield_budget(craft))
        for arc in ARCS:
            before = pips(craft.shield_allocation.get(arc, "0D"))
            removed = min(excess, before)
            if before > removed:
                craft.shield_allocation[arc] = code_from_pips(before - removed)
            else:
                craft.shield_allocation.pop(arc, None)
            excess -= removed
        if len(craft.ion_durations) >= max(1, parse_code(craft.maneuverability)[0]):
            if craft.frozen_rounds == 0:
                craft.forced_moves, craft.forced_half_speed = craft.declared_moves, craft.half_speed
            craft.frozen_rounds = max(craft.frozen_rounds, 3)
        return f"{count} controls ionized" + ("; controls frozen for the next two rounds" if craft.frozen_rounds else "")

    @staticmethod
    def passengers(craft, damage, exposed=True, only=None):
        dice = {"lightly_damaged": 1, "heavily_damaged": 3, "severely_damaged": 6, "destroyed": 11}.get(damage)
        if not exposed or not dice or not craft.occupied:
            return []
        damage_roll = fixed_roll(dice)
        results = []
        for crew in craft.crew:
            if only is not None and crew.id not in only:
                continue
            if crew.d6.wound == "dead" or crew.evacuated:
                continue
            resistance = fixed_roll(*WEGD6Rules.pool(crew.d6, "strength", free=True))
            outcome = WEGD6Rules.apply_damage(crew.d6, damage_roll.total - resistance.total)
            results.append({"crew_id": crew.id, "name": crew.name, "damage_roll": damage_roll.model_dump(), "resistance_roll": resistance.model_dump(), "outcome": outcome})
        return results

    @staticmethod
    def damage(craft, margin, *, ion=False, incoming="front", exposed=True):
        if margin < 0 or craft.damage == "destroyed":
            return "unharmed", []
        if ion:
            if margin >= 21:
                craft.controls_dead = True
                detail = "controls dead; repairs required"
            else:
                detail = WEGVehicleRules.ionize(craft, 1 + max(0, margin - 1) // 5)
            craft.damage_log.append(detail)
            return detail, []
        if margin <= 3:
            if pips(craft.shields) - 3 * craft.shields_lost >= 3:
                WEGVehicleRules.lose_shields(craft, 1, incoming)
                detail = "shields blown: −1D until repaired"
            else:
                detail = WEGVehicleRules.ionize(craft, 1)
            craft.damage_log.append(detail)
            return detail, []
        level = "lightly_damaged" if margin <= 8 else "heavily_damaged" if margin <= 12 else "severely_damaged" if margin <= 15 else "destroyed"
        if craft.damage == "severely_damaged":
            level = "destroyed"
        elif craft.damage == "heavily_damaged" and level in {"lightly_damaged", "heavily_damaged"}:
            level = "severely_damaged"
        craft.damage = level
        effect = "destroyed"
        damaged_gunner = None
        if level != "destroyed":
            die = random.randint(1, 6)
            ship = craft.kind == "starship"
            if level == "lightly_damaged":
                if die <= (2 if ship else 3):
                    craft.maneuverability_lost += 1
                    effect = "maneuverability −1D"
                elif die == (3 if ship else 4):
                    live = [w for w in craft.weapons if w.status != "destroyed"]
                    if live:
                        weapon = random.choice(live)
                        weapon.status = "destroyed"
                        weapon.repair_damage = "destroyed"
                        if weapon.operator_id and weapon.operator_id != WEGVehicleRules.pilot(craft).id:
                            damaged_gunner = weapon.operator_id
                        effect = f"{weapon.name} destroyed"
                    else:
                        effect = "unarmed emplacement hit"
                elif ship and die == 4:
                    live = [w for w in craft.weapons if w.status == "operational"]
                    if live:
                        weapon = random.choice(live)
                        weapon.status = "disabled"
                        weapon.repair_damage = "lightly_damaged"
                        effect = f"{weapon.name} disabled"
                    else:
                        effect = "weapons already offline"
                elif ship and die == 5:
                    WEGVehicleRules.lose_shields(craft, 1, incoming)
                    effect = "shields −1D"
                else:
                    craft.speed_losses = min(6, craft.speed_losses + 1)
                    effect = "one fewer move per round"
            elif level == "heavily_damaged":
                if die <= (2 if ship else 3):
                    craft.maneuverability_lost += 2
                    effect = "maneuverability −2D"
                elif ship and die <= 4:
                    live = [w for w in craft.weapons if w.status == "operational"]
                    system = random.choice(live).system if live else None
                    for weapon in craft.weapons:
                        if weapon.system == system and weapon.status != "destroyed":
                            weapon.status = "disabled"
                            weapon.repair_damage = "heavily_damaged"
                    effect = f"{system or 'weapon'} system disabled"
                elif ship and die == 5:
                    WEGVehicleRules.lose_shields(craft, 2, incoming)
                    effect = "shields −2D"
                else:
                    craft.speed_losses = min(6, craft.speed_losses + 2)
                    effect = "two fewer moves per round"
            elif level == "severely_damaged":
                if die == 1 or (not ship and die == 2):
                    craft.drives_disabled = True
                    effect = "dead in space" if ship else "powerplant destroyed"
                    moving = craft.declared_moves > 0 and not craft.half_speed
                    if (not ship and moving) or craft.airborne:
                        crash_dice = WEGVehicleRules.collision_dice(craft) + 3 if moving else WEGVehicleRules.falling_dice(craft.altitude)
                        crash = fixed_roll(crash_dice)
                        hull = WEGVehicleRules.hull_roll(craft)
                        WEGVehicleRules.damage(craft, crash.total - hull.total, exposed=False)
                        effect += f"; crash {crash.total} vs body {hull.total}: {craft.damage}"
                        craft.airborne, craft.altitude = False, 0
                elif die == (2 if ship else 3):
                    craft.destruction_countdown = 3
                    craft.destruction_cause = "generator"
                    effect = "generator overload; destruction in three rounds unless shut down"
                elif ship and die == 3:
                    craft.hyperdrive_disabled = True
                    effect = "hyperdrive disabled"
                elif die == 4:
                    craft.weapons_disabled = True
                    effect = "all weapons disabled"
                elif die == 5:
                    craft.destruction_countdown = random.randint(1, 6)
                    craft.destruction_cause = "structure"
                    effect = f"structural breakup; evacuate within {craft.destruction_countdown} round(s)"
                else:
                    craft.damage = "destroyed"
                    effect = "immediate destruction"
        detail = f"{craft.damage.replace('_', ' ')}: {effect}"
        craft.damage_log.append(detail)
        crew_damage = WEGVehicleRules.passengers(craft, craft.damage, exposed)
        if not exposed and damaged_gunner:
            crew_damage.extend(WEGVehicleRules.passengers(craft, craft.damage, True, only={damaged_gunner}))
        return detail, crew_damage

    @staticmethod
    def hull_roll(craft, arc=None, weapon_kind="energy", cap=6):
        dice, extra = parse_code(craft.hull)
        if craft.kind == "starship" and (not craft.particle_shields or craft.generator_shutdown):
            dice = max(0, dice - 2)
        if arc and weapon_kind == "energy":
            shield_dice, shield_pips = parse_code(craft.shield_allocation.get(arc, "0D"))
            dice, extra = dice + shield_dice, extra + shield_pips
        return fixed_roll(dice, extra, cap)

    @staticmethod
    def attack(craft, crew, target, weapon, req, environment):
        WEGVehicleRules.operational(craft)
        if crew.d6.origin.template_id == "protocol_droid" and target.occupied and any(member.d6.sentient and not member.evacuated and member.d6.wound != "dead" for member in target.crew):
            raise ValueError("This Protocol Droid cannot fire on a craft occupied by sentients because of its life-preservation programming.")
        if target.damage == "destroyed":
            raise ValueError("Target craft is destroyed.")
        if "gunner" not in crew.stations:
            raise ValueError("Select a crew member at a gunnery station.")
        operator = weapon.operator_id or WEGVehicleRules.pilot(craft).id
        if not weapon.pilot_operated and "pilot" in crew.stations:
            raise ValueError("This weapon requires a separate gunner; assign its gunner station or record a pilot-operated modification.")
        if operator != crew.id:
            raise ValueError("This weapon is assigned to another crew station.")
        if craft.weapons_disabled or weapon.status != "operational" or weapon.ammo == 0:
            raise ValueError("This weapon is offline, destroyed, or out of ammunition.")
        if req.fire_arc not in weapon.arcs:
            raise ValueError("Target is outside this weapon's firing arcs.")
        ranges = weapon.space_ranges if environment == "space" else weapon.atmosphere_ranges
        if req.distance > ranges[3]:
            raise ValueError("Target is beyond this weapon's long range.")
        base = req.difficulty or (25 if req.distance < ranges[0] else 10 if req.distance <= ranges[1] else 15 if req.distance <= ranges[2] else 20)
        if weapon.kind == "missile":
            speed = (target.space_move if environment == "space" else target.atmosphere_move) * (0.5 if target.half_speed else target.declared_moves)
            thresholds = (3, 4, 5, 6) if environment == "space" else (100, 151, 201, 251)
            base += sum(speed >= threshold for threshold in thresholds) * 5
        scale = weapon.scale or craft.scale
        hit_cap = cap_for(TO_HIT, scale, target.scale)
        if hit_cap is None:
            raise ValueError("This weapon scale cannot target that scale in the 1992 scale chart.")
        defense_cap = cap_for(TO_DODGE, target.scale, scale)
        defense = capped(target.dodge_roll, defense_cap).total if target.dodge_roll and defense_cap else None
        difficulty = base + defense if target.full_dodge and defense is not None else max(base, defense) if defense is not None else base
        equipment = WEGVehicleRules.equipment(craft, weapon.fire_control)
        roll = WEGVehicleRules.crew_roll(crew, weapon.skill, req.character_points, req.mishap, False, equipment, hit_cap)
        if weapon.ammo is not None:
            weapon.ammo -= 1
        if weapon.kind == "missile" and craft.kind == "starship":
            craft.particle_shields = False
        result = RuleEvaluationResult(action_type="vehicle_attack", success=roll.total >= difficulty, roll_result=roll, target_value=difficulty,
            summary=f"[WEG D6 Craft Attack] {crew.name}, {craft.name} → {target.name}, {weapon.name} ({scale} → {target.scale}, cap {hit_cap}): {roll.breakdown} vs {difficulty} → {'HIT' if roll.total >= difficulty else 'MISS'}.")
        if not result.success:
            return result
        if weapon.kind == "tractor":
            target.captured_by, target.captured_weapon = craft.id, weapon.id
            target.tractor_distance = req.distance
            result.summary += " Tractor lock established; hull escape or one pull per declared use."
            return result
        damage_cap = cap_for(DAMAGE_CAP, scale, target.scale)
        if damage_cap is None:
            result.summary += " This scale cannot damage the target's scale."
            return result
        damage_dice, damage_pips = WEGVehicleRules.equipment(craft, weapon.damage)
        result.damage_roll = fixed_roll(damage_dice, damage_pips, damage_cap)
        resist_cap = cap_for(RESIST_CAP, scale, target.scale)
        result.resistance_roll = WEGVehicleRules.hull_roll(target, req.incoming_arc, weapon.kind, resist_cap)
        margin = result.damage_roll.total - result.resistance_roll.total
        detail, passengers = WEGVehicleRules.damage(target, margin, ion=weapon.kind == "ion", incoming=req.incoming_arc, exposed=req.passenger_damage)
        result.state_changes = {"damage_margin": margin, "craft_damage": target.damage, "passengers": passengers}
        result.summary += f" Damage {result.damage_roll.breakdown}; hull/shields {result.resistance_roll.breakdown}; margin {margin}: {detail}."
        if passengers:
            result.summary += " Crew: " + "; ".join(f"{person['name']} {person['outcome']}" for person in passengers) + "."
        return result

    @staticmethod
    def collision_dice(craft):
        return 2 if craft.half_speed else {0: 3, 1: 3, 2: 4, 3: 6, 4: 10}[craft.declared_moves]

    @staticmethod
    def falling_dice(meters):
        return 0 if meters < 3 else 2 if meters <= 6 else 3 if meters <= 12 else 4 if meters <= 18 else 5 if meters <= 30 else 7 if meters <= 50 else 9

    @staticmethod
    def collision(craft, dice, exposed=True):
        damage = fixed_roll(max(0, dice))
        resistance = WEGVehicleRules.hull_roll(craft)
        detail, passengers = WEGVehicleRules.damage(craft, damage.total - resistance.total, exposed=exposed)
        return {"craft_id": craft.id, "damage_roll": damage.model_dump(), "resistance_roll": resistance.model_dump(), "effect": detail, "passengers": passengers}

    @staticmethod
    def move(craft, crew, req, environment, target=None):
        WEGVehicleRules.operational(craft, movement=True)
        if "pilot" not in crew.stations:
            raise ValueError("Only the pilot can move the craft.")
        if craft.captured_by:
            raise ValueError("Break the tractor lock before moving.")
        if craft.spin_rounds or craft.drives_disabled:
            raise ValueError("This craft must remain stationary while spinning or with drives disabled.")
        if craft.moves_taken >= craft.declared_moves:
            raise ValueError("All declared moves have been used; declare movement next round.")
        if craft.frozen_rounds and (req.maneuver_modifier or target):
            raise ValueError("Frozen controls must maintain speed and direction.")
        if target and craft.half_speed:
            raise ValueError("A ram requires a normal declared move.")
        terrain = req.terrain_difficulty
        free = craft.half_speed and terrain <= 15 and req.maneuver_modifier == 0 and not craft.half_speed_only and not craft.frozen_rounds
        if craft.half_speed and terrain > 15:
            terrain = 5 if terrain <= 20 else 10 if terrain <= 30 else 15
        movement_difficulty = terrain + req.maneuver_modifier
        difficulty = movement_difficulty
        if target:
            dodge_cap = cap_for(TO_DODGE, target.scale, craft.scale)
            dodge = capped(target.dodge_roll, dodge_cap).total if target.dodge_roll and dodge_cap else 5
            difficulty += dodge
        equipment = WEGVehicleRules.equipment(craft, craft.maneuverability, craft.maneuverability_lost)
        if free:
            if req.character_points:
                raise ValueError("A free half-speed move requires no roll or Character Points.")
            if not crew.d6.can_act or crew.evacuated:
                raise ValueError("An unconscious pilot cannot move a craft.")
            roll = RollResult(expression="Half-speed move", dice_count=0, die_type=6, system="weg_d6", total=difficulty, breakdown="Free half-speed movement; no roll required")
        else:
            roll = WEGVehicleRules.crew_roll(crew, craft.piloting_skill, req.character_points, req.mishap, False, equipment)
        craft.moves_taken += 1
        distance = (craft.space_move if environment == "space" else craft.atmosphere_move) * (0.5 if craft.half_speed else 1)
        craft.distance_moved += distance
        result = RuleEvaluationResult(action_type="vehicle_move", success=roll.total >= difficulty, roll_result=roll, target_value=difficulty,
            summary=f"[WEG D6 {'Ram' if target else 'Movement'}] {craft.name}, {distance:g} {'units' if environment == 'space' else 'meters'}: {roll.breakdown} vs {difficulty}.", state_changes={"free_move": free})
        fail_by = movement_difficulty - roll.total
        if fail_by > 0:
            result.success = False
            if craft.frozen_rounds:
                fail_by = max(16, fail_by)
            if fail_by <= 3:
                crew.control_penalty += 1
                effect = "slight slip; pilot −1D for the rest of the round"
            elif fail_by <= 6:
                crew.control_penalty += 3
                crew.next_control_penalty += 1
                effect = "control problems; pilot −3D this round, −1D next round"
            elif fail_by <= 10:
                craft.spin_rounds = 2
                direction = random.choice(("45° left", "straight ahead", "45° right"))
                effect = f"spin {direction}; stationary for the next round"
            else:
                modifier = -3 if fail_by <= 15 else 0 if fail_by <= 20 else 4
                modifier += {"head_on": 3, "rear_ender": -3, "t_bone": 0, "obstacle": 0}[req.collision_angle]
                collision = WEGVehicleRules.collision(craft, WEGVehicleRules.collision_dice(craft) + modifier, req.passenger_damage)
                result.state_changes["collision"] = collision
                effect = f"collision: {collision['effect']}"
            result.summary += f" Movement failed by {fail_by}: {effect}."
        elif target and result.success:
            target_dice = WEGVehicleRules.collision_dice(craft) - (3 if req.sideswipe else 0)
            own_dice = WEGVehicleRules.collision_dice(craft) - 3
            # Ramming damage has the attacker's scale, with both damage/resistance caps.
            collisions = []
            for victim, dice in ((craft, own_dice), (target, target_dice)):
                damage_cap = cap_for(DAMAGE_CAP, craft.scale, victim.scale)
                if damage_cap is None:
                    continue
                damage = fixed_roll(max(0, dice), cap=damage_cap)
                resistance = WEGVehicleRules.hull_roll(victim, cap=cap_for(RESIST_CAP, craft.scale, victim.scale))
                effect, passengers = WEGVehicleRules.damage(victim, damage.total - resistance.total, exposed=req.passenger_damage)
                collisions.append({"craft_id": victim.id, "effect": effect, "damage_roll": damage.model_dump(), "resistance_roll": resistance.model_dump(), "passengers": passengers})
            result.state_changes["ram_collisions"] = collisions
            result.summary += " Ram connects. " + "; ".join(f"{item['craft_id']}: {item['effect']}" for item in collisions)
        elif target:
            result.summary += " Ram misses; terrain crossed safely."
        else:
            result.summary += " Terrain crossed safely."
        return result

    @staticmethod
    def next_round(craft, advance_crew=True):
        if craft.frozen_rounds and craft.moves_taken < craft.declared_moves and craft.damage != "destroyed":
            collision = WEGVehicleRules.collision(craft, WEGVehicleRules.collision_dice(craft))
            craft.damage_log.append(f"Mandatory frozen-controls movement check skipped: automatic crash; {collision['effect']}")
        craft.ion_durations = [duration - 1 for duration in craft.ion_durations if duration > 1]
        craft.frozen_rounds = max(0, craft.frozen_rounds - 1)
        craft.spin_rounds = max(0, craft.spin_rounds - 1)
        craft.shield_allocation.clear()
        craft.shields_rolled = False
        craft.dodge_roll = None
        craft.full_dodge = False
        craft.moves_taken = craft.declared_moves = 0
        craft.distance_moved = 0
        craft.half_speed = False
        if craft.frozen_rounds:
            craft.declared_moves, craft.half_speed = craft.forced_moves, craft.forced_half_speed
        craft.particle_shields = not craft.generator_shutdown
        if craft.destruction_countdown is not None and craft.damage != "destroyed":
            craft.destruction_countdown = max(0, craft.destruction_countdown - 1)
            if craft.destruction_countdown == 0:
                craft.damage = "destroyed"
                craft.damage_log.append(f"{craft.destruction_cause} failure: craft destroyed")
                crew_damage = WEGVehicleRules.passengers(craft, "destroyed")
                if crew_damage:
                    craft.damage_log.append("Crew after timed destruction: " + "; ".join(f"{person['name']} {person['outcome']}" for person in crew_damage))
        if advance_crew:
            for crew in craft.crew:
                WEGD6Rules.next_round(crew.d6)
                crew.control_penalty = crew.next_control_penalty
                crew.next_control_penalty = 0
