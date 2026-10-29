"""Character-scale WEG Star Wars Second Edition (1992), not Revised & Expanded.

Source: WEG40055, printed pp. 28–30, 52–62, 67 (local PDF pp. 29–31,
49–59, 64). Default Wild-1 handling is the book's penalty option.
"""

import random
import re

from dungeonforge.rules.base import BaseRuleSystem, Character, Item, RuleEvaluationResult
from dungeonforge.rules.dice import DiceRoller, RollResult
from dungeonforge.rules.weg_models import ATTRIBUTES, SKILL_ATTRIBUTES, D6Character, D6Options, D6RoundState, normalize_code
from dungeonforge.rules import weg_force_effects as force_effects


DIFFICULTIES = {"very_easy": (1, 5), "easy": (6, 10), "moderate": (11, 15), "difficult": (16, 20), "very_difficult": (21, 30), "heroic": (31, None)}
RANGE_DIFFICULTIES = {"point_blank": 5, "short": 10, "medium": 15, "long": 20}


def skill_key(value):
    return re.sub(r"[\s/\-]+", "_", value.strip().lower())


def parse_code(value):
    code = normalize_code(value)
    dice, _, pips = code.partition("D")
    return int(dice), int(pips.lstrip("+") or 0)


class D6Roller:
    @staticmethod
    def bonus_dice(count):
        bonus = []
        for _ in range(count):
            chain = [random.randint(1, 6)]
            while chain[-1] == 6:
                if len(chain) > 100:
                    raise ValueError("Character Point die exceeded the roll limit.")
                chain.append(random.randint(1, 6))
            bonus.extend(chain)
        return bonus

    @staticmethod
    def values(dice, pips=0, character_points=0, mishap="penalty"):
        if not 1 <= dice <= 200:
            raise ValueError("The effective pool must contain 1 to 200 dice; reduce action penalties if no dice remain.")
        if not 0 <= character_points <= 5 or mishap not in {"penalty", "complication"}:
            raise ValueError("Invalid Character Point or Wild Die option.")
        normal = [random.randint(1, 6) for _ in range(dice - 1)]
        wild = [random.randint(1, 6)]
        kept = normal.copy()
        event = None
        if wild[0] == 1:
            event = mishap
            if mishap == "penalty" and kept:
                kept.remove(max(kept))
        else:
            while wild[-1] == 6:
                if len(wild) > 100:
                    raise ValueError("Wild Die exceeded the roll limit.")
                wild.append(random.randint(1, 6))
            kept.extend(wild)
        bonus = D6Roller.bonus_dice(character_points)
        kept.extend(bonus)
        total = sum(kept) + pips
        expression = f"{dice}D" + (f"{pips:+d}" if pips else "")
        detail = f"normal {normal}; Wild {wild}"
        if event:
            detail += f" ({event}: Wild 1 discarded" + (", highest normal die discarded)" if event == "penalty" else "; GM complication pending)")
        if bonus:
            detail += f"; CP dice {bonus}"
        if pips:
            detail += f"; pips {pips:+d}"
        return RollResult(
            expression=expression, dice_count=dice, die_type=6,
            raw_rolls=normal + wild + bonus, kept_rolls=kept, modifier=pips,
            total=total, system="weg_d6", wild_rolls=wild, mishap=event,
            bonus_rolls=bonus, breakdown=f"{detail} = {total}",
        )

    @staticmethod
    def roll(code, **options):
        dice, pips = parse_code(code)
        return D6Roller.values(dice, pips, **options)


class WEGD6Rules(BaseRuleSystem):
    @staticmethod
    def require(character):
        if character.d6 is None:
            raise ValueError("This character needs a native WEG D6 sheet.")
        return character.d6

    @staticmethod
    def skill_code(state, skill):
        skill = skill_key(skill)
        aliases = {"dex": "dexterity", "str": "strength", "per": "perception", "know": "knowledge", "mech": "mechanical", "tech": "technical"}
        skill = aliases.get(skill, skill)
        if skill in ATTRIBUTES:
            return state.attributes[skill], skill
        if skill in {"control", "sense", "alter"}:
            code = state.force_skills.get(skill, "0D")
            if parse_code(code)[0] == 0:
                raise ValueError(f"{skill.title()} must be trained; Force sensitivity alone does not grant Force skills.")
            return code, None
        trained = {skill_key(key): value for key, value in state.skills.items()}
        custom = {skill_key(key): value for key, value in state.skill_attributes.items()}
        attribute = custom.get(skill, SKILL_ATTRIBUTES.get(skill))
        if attribute is None and skill in state.specialization_parents:
            parent = state.specialization_parents[skill]
            attribute = custom.get(parent, SKILL_ATTRIBUTES.get(parent))
        if attribute is None:
            raise ValueError(f"Unknown skill '{skill}'. Assign it to one of the six WEG attributes in the character sheet.")
        if skill in {skill_key(key) for key in state.advanced_skills} and skill not in trained:
            raise ValueError(f"{skill.replace('_', ' ').title()} is an advanced skill and cannot be used untrained.")
        return trained.get(skill, state.attributes[attribute]), attribute

    @staticmethod
    def declare(state, actions=1, force_point=False):
        if not state.can_take_turn:
            raise ValueError("This character cannot declare actions while incapacitated, unconscious, or blocked by a new wound.")
        if state.round_state.actions_taken or state.round_state.force_active or state.round_state.character_points_spent or state.round_state.dark_side_called:
            raise ValueError("Actions and Force Point use must be declared before rolling this round.")
        if not 1 <= actions <= 10:
            raise ValueError("Declare 1 to 10 actions.")
        if force_point and state.force_points < 1:
            raise ValueError("No Force Points remain.")
        state.round_state.declared_actions = actions
        state.round_state.force_active = force_point
        if force_point:
            from dungeonforge.rules.weg_rewards import spend
            spend(state, "round_boost")

    @staticmethod
    def force_factor(state):
        return (2 if state.round_state.force_active else 1) * (2 if state.round_state.dark_side_active else 1)

    @staticmethod
    def pool(state, skill, *, free=False):
        code, attribute = WEGD6Rules.skill_code(state, skill)
        if state.droid and state.species_context.heavy_grasper and skill_key(skill) == "lifting":
            if state.droid.model in {"r2", "9g"}:
                code = "2D" if state.droid.model == "r2" else "4D"
        dice, pips = parse_code(code)
        factor = WEGD6Rules.force_factor(state)
        from dungeonforge.rules.weg_species import check_bonus, check_penalty
        dice += check_bonus(state, skill_key(skill), attribute)
        if state.droid and state.droid.model == "9g" and skill_key(skill) == "search":
            if state.species_context.long_range_sensor and 25 <= state.species_context.target_distance_m <= 50:
                dice += 2
            if state.species_context.moving_target_sensor:
                dice += 2
        dice, pips = dice * factor, pips * factor
        from dungeonforge.rules.weg_gear_effects import gear_bonus
        dice += gear_bonus(state, skill_key(skill), attribute)
        dice -= check_penalty(state, attribute)
        if skill_key(skill) == "first_aid" and "medicine" in state.skills:
            medicine_dice, medicine_pips = parse_code(state.skills["medicine"])
            dice, pips = dice + medicine_dice * factor, pips + medicine_pips * factor
        if skill_key(skill) == "lightsaber" and force_effects.find_effect(state, "lightsaber_combat"):
            sense_dice, sense_pips = parse_code(state.force_skills["sense"])
            dice, pips = dice + sense_dice * factor, pips + sense_pips * factor
        if skill_key(skill) in {"control", "sense", "alter"}:
            pips += force_effects.force_bonus(state)
        if not free:
            dice -= int(state.hazards.fatigued)
            if state.hazards.drowning and skill_key(skill) != "swimming":
                dice -= 3
            dice -= state.round_state.declared_actions - 1
            dice -= force_effects.upkeep(state)
            if not force_effects.pain(state):
                dice -= (1 if state.wound == "wounded" else 0) + len(state.stun_durations)
            if attribute == "dexterity":
                dice -= state.dexterity_penalty
        return dice, pips

    @staticmethod
    def validate_action(state, skill, character_points=0, *, defensive=False, free=False):
        if not free and not state.can_act:
            raise ValueError("This character cannot act in the current wound or stun state.")
        if not free and state.round_state.full_defense:
            raise ValueError("A full defense allows no other skill actions this round.")
        if not free and state.round_state.actions_taken >= state.round_state.declared_actions:
            raise ValueError("All declared actions have been used; advance the round.")
        limit = 5 if defensive or skill_key(skill) in {skill_key(s) for s in state.specializations} else 2
        if not 0 <= character_points <= limit:
            raise ValueError(f"This roll permits at most {limit} Character Points.")
        if character_points > state.character_points:
            raise ValueError("Not enough Character Points.")
        if character_points and (state.round_state.force_active or state.round_state.dark_side_called):
            raise ValueError("Character Points and a Force Point cannot be used in the same round.")
        dice, pips = WEGD6Rules.pool(state, skill, free=free)
        if dice < 1:
            raise ValueError("Action, wound, stun, or armor penalties leave no dice to roll.")
        return dice, pips

    @staticmethod
    def roll_skill(state, skill, difficulty, character_points=0, mishap="penalty", *, action=True, defensive=False, free=False):
        if not 1 <= difficulty <= 1000:
            raise ValueError("Difficulty must be between 1 and 1000.")
        from dungeonforge.rules.weg_gear_effects import bind_check
        bind_check(state, skill)
        dice, pips = WEGD6Rules.validate_action(state, skill, character_points, defensive=defensive, free=free)
        roll = D6Roller.values(dice, pips, character_points, mishap)
        state.character_points -= character_points
        state.round_state.character_points_spent |= character_points > 0
        if action and not free:
            force_effects.take_action(state)
            force_effects.settle_consciousness(state)
        success = roll.total >= difficulty
        return RuleEvaluationResult(
            action_type="skill_check", success=success, roll_result=roll, target_value=difficulty,
            summary=f"[WEG D6 Check: {skill.replace('_', ' ').title()}] {roll.expression} vs difficulty {difficulty}: {roll.breakdown} → {'SUCCESS' if success else 'FAILED'}.",
        )

    @staticmethod
    def defense(state, skill="dodge", full=False, use_roll=True, character_points=0):
        if state.round_state.defense_skill is not None:
            raise ValueError("A defense has already been resolved for this round.")
        if full and (state.round_state.declared_actions != 1 or state.round_state.actions_taken):
            raise ValueError("Full defense must be the only declared skill action this round.")
        result = WEGD6Rules.roll_skill(state, skill, 1, character_points, defensive=True)
        state.round_state.defense_skill = skill
        state.round_state.defense_total = result.roll_result.total
        state.round_state.full_defense = full
        state.round_state.use_defense_roll = use_roll
        result.action_type = "defense"
        result.summary = f"[WEG D6 {'Full' if full else 'Normal'} {skill.replace('_', ' ').title()}] {result.roll_result.breakdown}. " + ("Add this roll to the attack's base difficulty." if full else "Use this roll for attacks this round." if use_roll else "Keep each attack's base difficulty this round.")
        return result

    @staticmethod
    def weapon_skill(weapon):
        if weapon and weapon.d6_skill:
            return skill_key(weapon.d6_skill)
        name = weapon.name.lower() if weapon else ""
        return "lightsaber" if "lightsaber" in name else "melee_combat" if any(word in name for word in ("vibro", "knife", "blade", "staff")) else "blaster" if weapon else "brawling"

    @staticmethod
    def damage_pool(state, weapon, control_dice=None):
        damage = (weapon.damage or "4D") if weapon else "STR"
        damage = damage.strip().upper().replace(" ", "")
        if damage.startswith("STR"):
            dice, pips = parse_code(state.attributes["strength"])
            from dungeonforge.rules.weg_species import check_bonus
            dice += check_bonus(state, "strength", "strength")
            if state.species_id == "wookiee" and state.species_context.berserk and WEGD6Rules.weapon_skill(weapon) == "brawling":
                dice += 2
            factor = WEGD6Rules.force_factor(state)
            dice, pips = dice * factor, pips * factor
            if damage != "STR":
                if not damage.startswith("STR+"):
                    raise ValueError("Use STR or STR+1D for Strength-based damage.")
                bonus_dice, bonus_pips = parse_code(damage[4:])
                dice, pips = dice + bonus_dice, pips + bonus_pips
        else:
            dice, pips = parse_code(damage)
        if weapon and weapon.d6_damage_max:
            maximum = parse_code(weapon.d6_damage_max)
            total = min(dice * 3 + pips, maximum[0] * 3 + maximum[1])
            dice, pips = divmod(total, 3)
        if weapon and weapon.weapon_damage_state in {"severely_damaged", "destroyed"}:
            raise ValueError("A severely damaged or destroyed weapon cannot attack.")
        if weapon:
            dice = max(0, dice - {"lightly_damaged": 1, "heavily_damaged": 2}.get(weapon.weapon_damage_state, 0))
        elif dice < 1:
            raise ValueError("Unarmed damage must have at least one die.")
        if WEGD6Rules.weapon_skill(weapon) == "lightsaber" and force_effects.find_effect(state, "lightsaber_combat"):
            control, control_pips = parse_code(state.force_skills["control"])
            factor = WEGD6Rules.force_factor(state)
            control, control_pips = control * factor, control_pips * factor
            if control_dice is not None:
                if abs(control_dice) > control:
                    raise ValueError("Choose at most the current full Control dice for lightsaber damage.")
                control, control_pips = control_dice, 0
            dice, pips = max(0, dice + control), pips + control_pips
        elif control_dice is not None:
            raise ValueError("Activate Lightsaber Combat before choosing Control damage dice.")
        return dice, pips

    @staticmethod
    def damage_roll(dice, pips=0, mishap="penalty"):
        return D6Roller.values(dice, pips, mishap=mishap) if dice else RollResult(expression="0D", dice_count=0, die_type=6, total=pips, modifier=pips, system="weg_d6", breakdown=f"No damage dice; pips {pips:+d} = {pips}")

    @staticmethod
    def resistance_pool(state, damage_type="energy", armor_items=None, location=None, side="front"):
        # Resisting damage is a free action, using full Strength (printed p.30).
        dice, pips = WEGD6Rules.pool(state, "strength", free=True)
        if armor_items is None:
            armor_dice, armor_pips = parse_code(state.armor_energy if damage_type == "energy" else state.armor_physical)
        else:
            from dungeonforge.rules.weg_personal_equipment import armor_for_hit, armor_pips
            item = armor_for_hit(armor_items, damage_type, location, side)
            armor_dice, armor_pips = divmod(armor_pips(item, damage_type) if item else 0, 3)
        return dice + armor_dice, pips + armor_pips

    @staticmethod
    def apply_damage(state, margin, stun=False):
        state.force.reduce_injury_available = False
        old_wound = state.wound
        if margin < 0 or state.wound == "dead":
            return "unharmed" if state.wound != "dead" else "dead"
        if state.droid:
            state.droid.repair_attempts = 0
        resisted_stun = force_effects.find_effect(state, "resist_stun")
        if resisted_stun and margin <= 3:
            return "stun resisted"
        converted_stun = bool(resisted_stun and stun and margin > 3)
        if margin <= 3 or converted_stun:
            state.stun_count += 1
            state.stun_durations.append(2)
            state.stun_expiries.append(360)
            force_effects.drop_on_injury(state)
            if not converted_stun and state.stun_count >= parse_code(state.attributes["strength"])[0]:
                state.unconscious_rounds = max(state.unconscious_rounds, DiceRoller.roll("2d6").total * 12)
                force_effects.injury_reactions(state)
                return "unconscious"
            force_effects.injury_reactions(state)
            return "stunned"
        if stun:
            state.unconscious_rounds = max(state.unconscious_rounds, DiceRoller.roll(f"{margin}d6").total)
            force_effects.drop_on_injury(state)
            state.round_state.blocked = True
            force_effects.injury_reactions(state)
            return "unconscious"
        result = "wounded" if margin <= 8 else "incapacitated" if margin <= 12 else "mortally_wounded" if margin <= 15 else "dead"
        if state.wound == "wounded" and result == "wounded":
            result = "incapacitated"
        elif state.wound == "incapacitated" and result in {"wounded", "incapacitated"}:
            result = "mortally_wounded"
        elif state.wound == "mortally_wounded":
            result = "dead" if result in {"incapacitated", "mortally_wounded", "dead"} else "mortally_wounded"
        state.wound = result
        state.round_state.blocked = True
        state.recovery_days = 0
        if result == "mortally_wounded" and old_wound != "mortally_wounded":
            state.mortal_rounds = 0
        force_effects.drop_on_injury(state)
        force_effects.injury_reactions(state, severe_injury=True)
        return result

    @staticmethod
    def bowcaster_check(attacker, weapon, options, fire_control=None):
        if not weapon or weapon.catalog_id != "bowcaster" or not (fire_control["shots"] if fire_control is not None else attacker.round_state.weapon_shots.get(weapon.id, 0)):
            return None
        check = WEGD6Rules.roll_skill(attacker, "strength", 10, options.bowcaster_strength_character_points, action=False, free=True)
        if not check.success:
            attacker.round_state.bowcaster_blocked.append(weapon.id)
        return check

    @staticmethod
    def resolve_attack(attacker, target, weapon=None, options=None, *, armor_items=None, prepared=False, cover=None, cover_fraction="none", concealment_dice=0, fire_control=None, target_weapon=None):
        options = options or D6Options()
        from dungeonforge.rules.weg_personal_equipment import validate_weapon, record_shot, armor_for_hit, apply_armor_damage, refresh_armor
        band = validate_weapon(attacker, weapon, options, fire_control)
        if weapon and weapon.d6_skill == "grenade":
            raise ValueError("Use the explosive procedure with an actual landing point, scatter, trigger and every exposed actor; grenades cannot resolve as a single-target ordinary attack.")
        physical_cover = cover is not None and cover.damage_state != "destroyed" and cover_fraction != "none"
        if options.attack_cover and not physical_cover:
            raise ValueError("Choose actual saved physical cover before targeting its protection.")
        if physical_cover and cover_fraction == "full" and not options.attack_cover:
            raise ValueError("Full physical cover prevents a direct character hit; explicitly attack its protection.")
        if attacker.origin.template_id == "protocol_droid" and target.sentient:
            raise ValueError("This Protocol Droid's life-preservation programming prevents injuring a sentient, even in self-defense.")
        if target.out_of_fight:
            raise ValueError("Target is already out of the fight.")
        skill = WEGD6Rules.weapon_skill(weapon)
        WEGD6Rules.validate_action(attacker, skill, options.character_points)
        if options.target_weapon and (not target_weapon or target_weapon.quantity < 1 or target_weapon.weapon_damage_state == "destroyed"):
            raise ValueError("Choose an actual drawn, undestroyed target weapon.")
        if options.target_weapon and (options.called_shot or options.hit_location is not None or options.location_damage):
            raise ValueError("Choose the held weapon or a character body location for this called shot.")
        if options.called_shot and options.hit_location in {None, "random"}:
            raise ValueError("A called shot needs an actual specified body location.")
        attack_dice, attack_pips = WEGD6Rules.pool(attacker, skill)
        attack_dice += int(prepared) - int(options.called_shot or options.target_weapon)
        if attack_dice < 1:
            raise ValueError("The called-shot penalty leaves no attack dice.")
        WEGD6Rules.validate_action(target, "strength", options.resistance_character_points, defensive=True, free=True)
        damage_dice, damage_pips = WEGD6Rules.damage_pool(attacker, weapon, options.lightsaber_control_dice)
        damage_type = weapon.damage_type if weapon else "physical"
        if damage_type not in {"energy", "physical"}:
            raise ValueError("Native weapon damage_type must be energy or physical.")
        resistance_dice, resistance_pips = WEGD6Rules.resistance_pool(target, damage_type, armor_items)
        ranged = skill in {"blaster", "grenade", "missile_weapons", "bowcaster", "bows", "firearms", "thrown_weapons", "archaic_guns", "blaster_artillery"}
        base = options.difficulty or (RANGE_DIFFICULTIES[band] if ranged else (weapon.d6_difficulty if weapon and weapon.d6_difficulty else 20 if skill == "lightsaber" else 10))
        if weapon and weapon.catalog_id == "blaster_carbine" and band == "long":
            base += 5
        visibility = DiceRoller.roll(f"{concealment_dice}d6") if concealment_dice else None
        if visibility:
            base += visibility.total
        defense = target.round_state
        matching = (defense.defense_skill == "dodge" or (skill == "blaster" and defense.defense_skill == "lightsaber" and force_effects.find_effect(target, "lightsaber_combat"))) if ranged else defense.defense_skill in {"melee_parry", "brawling_parry", "lightsaber"}
        difficulty = base
        if matching and defense.defense_total is not None:
            defense_total = defense.defense_total + (5 if skill == "brawling" and defense.defense_skill == "melee_parry" else 0)
            if defense.full_defense:
                difficulty += defense_total
            elif defense.use_defense_roll:
                difficulty = defense_total
        if weapon and weapon.weapon_damage_state == "heavily_damaged":
            difficulty += 10
        object_difficulty = difficulty
        cover_bonus = None
        if physical_cover and not options.attack_cover:
            cover_dice = {"quarter": 1, "half": 2, "three_quarters": 3}.get(cover_fraction, 0)
            cover_bonus = DiceRoller.roll(f"{cover_dice}d6") if cover_dice else None
            if cover_bonus:
                difficulty += cover_bonus.total
        strength_check = WEGD6Rules.bowcaster_check(attacker, weapon, options, fire_control)
        if strength_check and not strength_check.success:
            return RuleEvaluationResult(action_type="attack", success=False, roll_result=strength_check.roll_result, target_value=10,
                summary="[WEG Bowcaster] Additional-shot Easy Strength check failed; no shot, ammunition or attack action consumed. No more bowcaster shots this round.",
                state_changes={"no_attack_action": True, "bowcaster_strength": strength_check.model_dump()})
        # A zero defense total is legal even though a user-selected base difficulty is not.
        roll = D6Roller.values(attack_dice, attack_pips, options.character_points, options.mishap)
        if matching and not ranged and skill != "brawling" and defense.defense_skill == "brawling_parry":
            roll.total += 10
            roll.modifier += 10
            roll.breakdown += f"; armed attack vs unarmed parry +10 = {roll.total}"
        attacker.character_points -= options.character_points
        attacker.round_state.character_points_spent |= options.character_points > 0
        force_effects.take_action(attacker)
        record_shot(attacker, weapon, fire_control)
        hit = roll.total >= difficulty
        hit_cover = bool(physical_cover and (options.attack_cover and hit or not hit and roll.total >= object_difficulty))
        result = RuleEvaluationResult(
            action_type="attack", success=hit, roll_result=roll, target_value=difficulty,
            summary=f"[WEG D6 Attack: {skill}] {roll.expression} vs difficulty {difficulty}: {roll.breakdown} → {'HIT' if hit else 'MISS'}.",
        )
        if strength_check:
            result.state_changes["bowcaster_strength"] = strength_check.model_dump()
        if prepared:
            result.state_changes["preparation_bonus"] = "1D"
            result.summary += " One complete preparation round and one exclusive attack round: +1D."
        if weapon:
            result.state_changes["weapon"] = {"id": weapon.id, "ammo": weapon.ammo, "power_ammo": weapon.power_ammo, "quantity": weapon.quantity, "shots_this_round": attacker.round_state.weapon_shots[weapon.id]}
        if visibility:
            result.state_changes["concealment"] = visibility.model_dump()
        if cover_bonus:
            result.state_changes["cover_bonus"] = cover_bonus.model_dump()
        if hit_cover:
            from dungeonforge.rules.weg_personal_equipment import LEVELS
            impact = WEGD6Rules.damage_roll(damage_dice, damage_pips, options.mishap)
            body = D6Roller.roll(cover.body, mishap="penalty")
            margin = impact.total - body.total
            severity = "intact" if margin <= 3 else "lightly_damaged" if margin <= 8 else "heavily_damaged" if margin <= 12 else "severely_damaged" if margin <= 15 else "destroyed"
            cover.damage_state = LEVELS[max(LEVELS.index(cover.damage_state), LEVELS.index(severity))]
            loss = {"lightly_damaged": 4, "heavily_damaged": 2, "severely_damaged": 1, "destroyed": 0}.get(severity)
            result.state_changes["cover_impact"] = {"id": cover.id, "name": cover.name, "damage": impact.model_dump(), "body": body.model_dump(), "margin": margin, "outcome": severity, "saved_damage": cover.damage_state, "transmitted_penalty_dice": loss}
            result.summary += f" Hit {cover.name}: damage {impact.total} vs body {body.total}: {severity.replace('_', ' ')}."
            if loss is None:
                result.success = bool(options.attack_cover)
                result.summary += " The object absorbs all damage."
                force_effects.settle_consciousness(attacker)
                return result
            damage_dice = max(0, damage_dice - loss)
            hit = True
            result.success = True
            result.summary += f" Reroll weapon damage at −{loss}D against the protected character."
        if hit:
            if options.target_weapon:
                from dungeonforge.rules.weg_personal_equipment import LEVELS
                result.damage_roll = WEGD6Rules.damage_roll(damage_dice, damage_pips, options.mishap)
                result.resistance_roll = D6Roller.roll(target_weapon.weapon_body, mishap="penalty")
                margin = result.damage_roll.total - result.resistance_roll.total
                severity = "intact" if margin <= 3 else "lightly_damaged" if margin <= 8 else "heavily_damaged" if margin <= 12 else "severely_damaged" if margin <= 15 else "destroyed"
                previous = target_weapon.weapon_damage_state
                target_weapon.weapon_damage_state = LEVELS[max(LEVELS.index(previous), LEVELS.index(severity))]
                result.state_changes["target_weapon_damage"] = {"id": target_weapon.id, "name": target_weapon.name, "before": previous, "after": target_weapon.weapon_damage_state, "margin": margin, "outcome": severity}
                result.summary += f" Called shot at held weapon (−1D attack): damage {result.damage_roll.total} vs weapon body {result.resistance_roll.total}: {target_weapon.weapon_damage_state.replace('_', ' ')}."
                force_effects.settle_consciousness(attacker)
                return result
            location = options.hit_location
            partial_armor = armor_items and any(set(item.armor_locations) != {"head", "torso", "left_arm", "right_arm", "left_leg", "right_leg"} for item in armor_items)
            if location == "random" or location is None and (options.location_damage or partial_armor):
                from dungeonforge.rules.weg_personal_equipment import hit_location
                location = hit_location()
            if location:
                result.state_changes["hit_location"] = location
                result.state_changes["called_shot"] = options.called_shot
                if options.location_damage:
                    damage_dice = max(0, damage_dice + (1 if location == "head" else -1 if location == "torso" else 0))
            resistance_dice, resistance_pips = WEGD6Rules.resistance_pool(target, damage_type, armor_items, location, options.attack_side)
            result.damage_roll = WEGD6Rules.damage_roll(damage_dice, damage_pips, options.mishap)
            if damage_type == "energy" and target.round_state.absorb_energy:
                from dungeonforge.rules.weg_force import absorb_incoming
                absorbed, component, note = absorb_incoming(target, result.damage_roll.total)
                result.summary += " " + note
                if component:
                    result.force_rolls.append(component)
                if absorbed:
                    result.state_changes["absorbed"] = True
                    force_effects.settle_consciousness(attacker)
                    return result
            result.resistance_roll = D6Roller.values(resistance_dice, resistance_pips, options.resistance_character_points, mishap="penalty")
            target.character_points -= options.resistance_character_points
            target.round_state.character_points_spent |= options.resistance_character_points > 0
            margin = result.damage_roll.total - result.resistance_roll.total
            result.wound_result = WEGD6Rules.apply_damage(target, margin, options.stun)
            result.state_changes.update({"damage_margin": margin, "wound": target.wound, "stun_count": target.stun_count})
            if armor_items is not None:
                worn = armor_for_hit(armor_items, damage_type, location, options.attack_side)
                changed = apply_armor_damage(worn, result.wound_result)
                if changed:
                    result.state_changes["armor_damage"] = changed
                    refresh_armor(target, armor_items)
            result.summary += f" Damage {result.damage_roll.total} vs Strength + armor {result.resistance_roll.total} (margin {margin}): {result.wound_result.replace('_', ' ').upper()}."
        elif skill == "blaster" and matching and defense.defense_skill == "lightsaber":
            result.state_changes["parried_blaster"] = True
        if not hit and skill == "lightsaber" and base - roll.total > 10:
            self_damage = D6Roller.roll(weapon.damage if weapon and weapon.damage else "5D")
            self_resist = D6Roller.values(*WEGD6Rules.resistance_pool(attacker, "energy"))
            outcome = WEGD6Rules.apply_damage(attacker, self_damage.total - self_resist.total)
            result.state_changes["self_injury"] = {"damage": self_damage.model_dump(), "resistance": self_resist.model_dump(), "outcome": outcome}
            result.summary += f" Lightsaber mishandled (missed base by >10): self damage {self_damage.total} vs Strength/armor {self_resist.total}: {outcome}."
        force_effects.settle_consciousness(attacker)
        return result

    @staticmethod
    def next_round(state):
        state.round_state = D6RoundState()
        state.stun_durations = [duration - 1 for duration in state.stun_durations if duration > 1]
        state.stun_expiries = [duration - 1 for duration in state.stun_expiries if duration > 1]
        state.stun_count = len(state.stun_expiries)
        state.unconscious_rounds = max(0, state.unconscious_rounds - 1)
        WEGD6Rules.advance_mortality(state, 1)
        force_effects.tick(state)

    @staticmethod
    def advance_mortality(state, rounds):
        if state.droid:
            return None
        last_roll = None
        stabilized = force_effects.find_effect(state, "transfer_force")
        if stabilized and stabilized.recipient:
            rounds = max(0, rounds - (stabilized.rounds_remaining or 0))
        for _ in range(min(rounds, 13)):
            if state.wound != "mortally_wounded":
                break
            state.mortal_rounds += 1
            last_roll = DiceRoller.roll("2d6")
            if last_roll.total < state.mortal_rounds:
                state.wound = "dead"
                force_effects.drop_on_injury(state)
                state.force.remain_pending = False
        return last_roll

    @staticmethod
    def recover(state, method, minutes=1, days=0, healer=None):
        if state.droid and method != "rest":
            raise ValueError("Droids require Droid repair and replacement parts; medpacs and natural healing cannot repair a chassis.")
        if state.wound == "dead":
            raise ValueError("A dead character cannot recover through rest or first aid.")
        if method == "rest":
            from dungeonforge.rules.weg_hazards import rest as rest_hazards
            rest_hazards(state, minutes * 12)
            death_roll = WEGD6Rules.advance_mortality(state, minutes * 12)
            if state.wound == "dead":
                force_effects.tick(state, minutes * 12)
                return death_roll, "The untreated mortal wound proved fatal while time passed. Medical treatment was needed before resting."
            state.care_elapsed_minutes += minutes
            if state.care_elapsed_minutes >= 1440:
                state.medpacs_used = 0
                state.medpac_blocked = False
                state.care_elapsed_minutes %= 1440
            state.stun_count = 0
            state.stun_durations.clear()
            state.stun_expiries.clear()
            state.unconscious_rounds = max(0, state.unconscious_rounds - minutes * 12)
            state.round_state = D6RoundState()
            state.recovery_days += minutes / 1440
            force_effects.tick(state, minutes * 12)
            return None, f"Rested {minutes} minute(s). Stun penalties cleared; wound remains {state.wound.replace('_', ' ')}."
        if method == "natural":
            required = {"wounded": 3, "incapacitated": 14, "mortally_wounded": 30}.get(state.wound)
            if not required:
                raise ValueError("No wound requires natural healing.")
            if state.recovery_days + days < required:
                raise ValueError(f"Natural healing at this wound level requires {required} days of complete rest.")
            from dungeonforge.rules.weg_hazards import rest as rest_hazards
            rest_hazards(state, int(days * 17280))
            death_roll = WEGD6Rules.advance_mortality(state, int(days * 24 * 60 * 12))
            if state.wound == "dead":
                force_effects.tick(state, int(days * 17280))
                return death_roll, "The untreated mortal wound proved fatal before the scheduled healing roll. Medical treatment was needed first."
            roll = D6Roller.roll(state.attributes["strength"])
            old = state.wound
            if old == "wounded":
                state.wound = "incapacitated" if roll.total <= 4 else "wounded" if roll.total <= 6 else "healthy"
            elif old == "incapacitated":
                state.wound = "mortally_wounded" if roll.total <= 6 else "incapacitated" if roll.total <= 8 else "wounded"
            else:
                state.wound = "dead" if roll.total <= 6 else "mortally_wounded" if roll.total <= 8 else "incapacitated"
            state.recovery_days = 0
            state.medpacs_used = 0
            state.medpac_blocked = False
            state.round_state = D6RoundState()
            state.stun_count = 0
            state.stun_durations.clear()
            state.stun_expiries.clear()
            state.unconscious_rounds = 0
            force_effects.tick(state, int(days * 17280))
            return roll, f"After {days} days of complete rest, Strength {roll.breakdown}: {old.replace('_', ' ')} → {state.wound.replace('_', ' ')}."
        if method != "medpac":
            raise ValueError("Unknown WEG recovery method.")
        healer = healer or state
        if not healer.can_act:
            raise ValueError("The healer must be conscious and able to act; choose a companion for an incapacitated patient.")
        if state.medpac_blocked:
            raise ValueError("Further medpacs are unsafe until 24 hours have passed.")
        if state.wound == "healthy" and state.unconscious_rounds == 0 and state.stun_count == 0:
            raise ValueError("No injury needs a medpac.")
        base = {"healthy": 0, "wounded": 1, "incapacitated": 2, "mortally_wounded": 3}[state.wound]
        level = min(5, base + state.medpacs_used)
        difficulty = (5, 10, 15, 20, 30, 31)[level]
        dice, pips = WEGD6Rules.pool(healer, "first_aid")
        dice -= 1 if healer is state else 0
        roll = D6Roller.values(dice, pips)
        state.medpacs_used += 1
        if roll.total >= difficulty:
            state.wound = {"healthy": "healthy", "wounded": "healthy", "incapacitated": "wounded", "mortally_wounded": "incapacitated"}[state.wound]
            state.unconscious_rounds = 0
            state.round_state.blocked = False
            state.stun_count = 0
            state.stun_durations.clear()
            state.stun_expiries.clear()
        elif difficulty - roll.total > 10:
            state.medpac_blocked = True
        return roll, f"Medpac first aid vs {difficulty}: {roll.breakdown} → {'improved one injury level' if roll.total >= difficulty else 'no improvement'}. Wound: {state.wound.replace('_', ' ')}."

    def evaluate_attack(self, character: Character, target_ac: int, weapon: Item | None = None, advantage=False, disadvantage=False, bonus_mod=0):
        if advantage or disadvantage:
            raise ValueError("WEG D6 uses difficulty and dice-pool modifiers, not d20 advantage.")
        state = self.require(character)
        if state.origin.template_id == "protocol_droid":
            raise ValueError("Use an actual confirmed nonsentient target; this Protocol Droid cannot make an unspecified harmful narrative attack.")
        # Unopposed narrative attack: no target resistance/wound can be resolved without a target.
        skill = self.weapon_skill(weapon)
        self.damage_pool(state, weapon)
        if skill == "grenade":
            raise ValueError("Use actual grenade positions, triggers, scatter and blast resolution in the explosive controls.")
        from dungeonforge.rules.weg_personal_equipment import validate_weapon, record_shot
        options = D6Options(stun=bool(weapon and weapon.stun_mode))
        validate_weapon(state, weapon, options)
        self.validate_action(state, skill)
        strength = self.bowcaster_check(state, weapon, options)
        if strength and not strength.success:
            return RuleEvaluationResult(action_type="attack", success=False, roll_result=strength.roll_result, target_value=10,
                summary="[WEG Bowcaster] Additional-shot Easy Strength failed; no shot, ammunition or attack action consumed.", state_changes={"no_attack_action": True})
        result = self.roll_skill(state, skill, target_ac)
        record_shot(state, weapon)
        if weapon:
            result.state_changes["weapon"] = {"id": weapon.id, "ammo": weapon.ammo, "power_ammo": weapon.power_ammo, "quantity": weapon.quantity}
        result.action_type = "attack"
        result.summary = result.summary.replace("Check:", "Attack:").replace("SUCCESS", "HIT").replace("FAILED", "MISS") + " Resolve target Strength resistance in an encounter."
        return result

    def evaluate_ability_check(self, character, ability, dc_or_target, skill_name=None):
        return self.roll_skill(self.require(character), skill_name or ability, dc_or_target)

    def evaluate_saving_throw(self, character, save_name, dc, advantage=False, disadvantage=False):
        if advantage or disadvantage:
            raise ValueError("WEG D6 uses native resistance rolls.")
        return self.roll_skill(self.require(character), save_name, dc, free=True)

    def apply_short_rest(self, character, hit_dice_spent=1):
        self.recover(self.require(character), "rest")
        return character

    def apply_long_rest(self, character):
        # Eight hours do not satisfy the native 3/14/30-day natural healing schedule.
        state = self.require(character)
        self.recover(state, "rest", minutes=480)
        return character
