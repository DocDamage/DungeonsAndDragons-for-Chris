"""Native 1992 WEG Force powers. Fictional revelations remain with the GM.

Every Control/Sense/Alter component is its own action and must pass. Activation
and preparation survive round changes and save/load. Effect prose takes
precedence over the reversed Lightsaber Combat example on printed p.151.
"""

import math

from dungeonforge.rules.base import RuleEvaluationResult
from dungeonforge.rules.dice import RollResult
from dungeonforge.rules.weg_d6 import D6Roller, WEGD6Rules, parse_code
from dungeonforge.rules.weg_force_catalog import POWERS, PROXIMITY, RELATIONSHIP, training_errors
from dungeonforge.rules.weg_force_models import ForceAttempt, ForceEffect, ForcePowerRequest, ForceSkillRoll
from dungeonforge.rules import weg_force_effects as effects


def empty_roll(label):
    return RollResult(expression=label, dice_count=0, die_type=6, system="weg_d6", breakdown="No dice required")


def base_override(req, skill, base):
    return req.base_difficulties.get(skill, base)


def preparation_rounds(state, spec):
    return max(spec.preparation_rounds, 12 if state.origin.force_tradition == "tyia" else 1)


def force_component(state, skill, difficulty, points=0, mishap="penalty", *, internal=False, free=False, extra_penalty=0, strict=False, immediate=False):
    if not free:
        if state.wound == "dead" and not internal:
            raise ValueError("A dead character cannot activate this power.")
        if (not internal and not state.can_act) or (state.round_state.full_defense and not immediate):
            raise ValueError("This character cannot activate a Force skill in the current condition.")
        if state.round_state.actions_taken >= state.round_state.declared_actions and not immediate:
            raise ValueError("No declared actions remain; each Force skill is a separate action.")
    if points > 2 or points > state.character_points:
        raise ValueError("A Force skill roll allows at most two available Character Points.")
    if points and (state.round_state.force_active or state.round_state.dark_side_called):
        raise ValueError("Force and Character Points cannot combine on these rolls.")
    dice, pips = WEGD6Rules.pool(state, skill)
    dice -= extra_penalty
    if dice < 1:
        raise ValueError("Action, upkeep, injury, or control penalties leave no Force dice.")
    roll = D6Roller.values(dice, pips, points, mishap)
    state.character_points -= points
    state.round_state.character_points_spent |= points > 0
    if not free:
        effects.take_action(state)
    return ForceSkillRoll(skill=skill, difficulty=difficulty, success=roll.total > difficulty if strict else roll.total >= difficulty, roll=roll, character_points=points)


def resistance(target, req, *, control_only=False):
    if req.resistance_total is not None:
        return req.resistance_total, RollResult(expression="GM resistance", dice_count=0, die_type=6, total=req.resistance_total, system="weg_d6", breakdown=f"GM-recorded resistance {req.resistance_total}")
    if target is None:
        raise ValueError("Select a native target or enter its GM resistance total.")
    control = parse_code(target.force_skills["control"])
    perception = parse_code(target.attributes["perception"])
    if control_only and control[0] == 0:
        return 0, empty_roll("No trained Control to conceal identity")
    skill = "control" if control_only or req.resistance_skill == "control" or (req.resistance_skill == "auto" and control[0] > 0 and control >= perception) else "perception"
    dice, pips = WEGD6Rules.pool(target, skill)
    roll = D6Roller.values(dice, pips) if dice > 0 else empty_roll("Resistance pool depleted")
    return roll.total, roll


def validate_request(state, req, target, in_combat=False):
    req.target_is_droid |= bool(target and target.droid)
    if state.droid:
        raise ValueError("Droids cannot learn or activate Force powers.")
    if (req.target_is_droid or (target and target.droid)) and req.power_id in {"accelerate_another_healing", "control_another_pain", "return_another_consciousness", "transfer_force", "injure_kill"}:
        raise ValueError("This power affects living organic physiology; use Droid repair for a mechanical body.")
    spec = POWERS.get(req.power_id)
    if spec is None:
        raise ValueError("Choose a power printed in the 1992 WEG catalog.")
    if req.power_id not in state.force.known_powers:
        raise ValueError("This power has not been learned. Record teacher/GM-approved training in the D6 sheet first.")
    if state.origin.force_tradition == "tyia" and req.power_id in {"reduce_injury", "remain_conscious"}:
        raise ValueError("The Tyia's one-minute minimum cannot meet this power's immediate or next-round injury-reaction window.")
    errors = training_errors(state)
    if errors:
        raise ValueError(" ".join(errors))
    if req.keep_up and not spec.can_keep_up:
        raise ValueError("This power cannot be kept up.")
    if any(skill not in spec.skills or not 1 <= value <= 1000 for skill, value in req.base_difficulties.items()):
        raise ValueError("Difficulty overrides must match this power's Force skills and be from 1 to 1000.")
    if spec.profiles and req.profile and req.profile not in spec.profiles:
        raise ValueError("Choose one of this power's listed uses.")
    if spec.target == "person" and target is None:
        raise ValueError("Select a native person as the target of this power.")
    if target and target.wound == "dead" and req.power_id != "reduce_injury":
        raise ValueError("This power cannot affect a dead target.")
    if req.target_is_droid and req.power_id in {"life_detection", "life_sense", "receptive_telepathy", "projective_telepathy", "affect_mind"}:
        raise ValueError("This power requires a living mind/sentient and cannot affect Droids.")
    if req.power_id == "lightsaber_combat" and state.force.saber_locked:
        raise ValueError("Lightsaber Combat failed earlier in this battle; it cannot be retried until the battle ends.")
    if req.power_id == "emptiness" and state.force.dark_side_consumed:
        raise ValueError("Characters consumed by the Dark Side cannot enter Emptiness.")
    if req.power_id == "absorb_dissipate_energy" and req.profile == "attack":
        raise ValueError("Prepare an energy-absorption reaction before the incoming attack; do not roll against invented damage.")
    if req.power_id == "reduce_injury":
        if not state.force.reduce_injury_available:
            raise ValueError("Reduce Injury is only available immediately after a newly suffered incapacitating, mortal, or killing injury.")
        if state.force_points < 1:
            raise ValueError("Reduce Injury requires one Force Point on success, separate from dice doubling.")
        if state.wound == "dead" and not req.permanent_injury.strip():
            raise ValueError("Record the permanent injury sacrificed to survive a killing blow.")
    if req.power_id == "remain_conscious":
        if not state.force.remain_pending or state.round_state.blocked or state.round_state.actions_taken:
            raise ValueError("Remain Conscious must be the first action of the round after the qualifying injury.")
    if req.power_id == "resist_stun" and (state.wound != "healthy" or state.stun_count or state.unconscious_rounds):
        raise ValueError("Resist Stun must be prepared before taking damage.")
    if req.power_id in {"accelerate_healing", "accelerate_another_healing"}:
        patient = target if req.power_id == "accelerate_another_healing" else state
        if patient.wound in {"healthy", "dead"}:
            raise ValueError("The patient needs a living wound to accelerate healing.")
        if patient.force.healing_day == patient.force.elapsed_rounds // 17280 and (patient.force.healing_rolls_remaining or patient.force.healing_rolls_used >= 2):
            raise ValueError("The patient's two accelerated healing rolls for this day are already granted/used.")
        if target is not None and req.power_id == "accelerate_another_healing" and req.proximity != "touching":
            raise ValueError("Accelerating another's healing requires physical contact.")
    if req.power_id == "transfer_force":
        if target.wound != "mortally_wounded" or not req.willing or req.proximity != "touching":
            raise ValueError("Transfer Force requires a willing, touched, mortally wounded patient.")
        if state.force_points < 1:
            raise ValueError("Transfer Force requires one Force Point in addition to any round-doubling point.")
    if req.power_id == "return_another_consciousness" and target.wound not in {"incapacitated", "mortally_wounded"} and target.unconscious_rounds == 0:
        raise ValueError("The target does not need to be returned to consciousness.")
    if req.power_id == "injure_kill":
        if req.proximity != "touching":
            raise ValueError("Injure/Kill requires physical contact.")
        if in_combat and req.target_id not in state.round_state.touched_targets:
            raise ValueError("First land a brawling attack on this target in the same round.")
    if req.power_id == "telekinesis" and (not req.in_sight or req.proximity == "hidden_nearby"):
        raise ValueError("The telekinetic target must be in sight.")
    if req.power_id == "life_detection" and req.distance_m > 10:
        raise ValueError("Life Detection is limited to ten meters.")
    if req.power_id == "receptive_telepathy" and req.keep_up and not req.willing:
        raise ValueError("Receptive Telepathy can only be kept up on a willing target without increasing proximity.")
    if req.power_id == "affect_mind" and not req.description.strip():
        raise ValueError("Describe the exact intended illusion, memory change, or conclusion before rolling.")
    if req.power_id not in {"telekinesis", "receptive_telepathy", "life_sense"} and any(effect.power_id == req.power_id and not effect.recipient for effect in state.force.effects):
        raise ValueError("This power is already active; drop its existing effect first.")
    return spec


def difficulty(state, req, target, skill):
    id = req.power_id
    rel, prox = RELATIONSHIP[req.relationship], PROXIMITY[req.proximity]
    opposition = None
    patient = target if id in {"accelerate_another_healing", "control_another_pain", "return_another_consciousness", "transfer_force"} else state
    injury = patient.wound if patient else "healthy"
    fixed = 5
    modifier = 0
    if id == "absorb_dissipate_energy":
        fixed = {"": 5, "sunburn": 5, "intense_sun": 10, "solar_wind": 15, "radiation_storm": 20}[req.profile]
    elif id == "accelerate_healing":
        fixed = {"wounded": 10, "incapacitated": 15, "mortally_wounded": 20}.get(injury, 10)
    elif id == "control_pain":
        fixed = {"healthy": 5, "wounded": 5, "incapacitated": 10, "mortally_wounded": 20}.get(injury, 20)
    elif id in {"emptiness", "resist_stun"}:
        fixed = 10 if id == "emptiness" and state.origin.force_tradition == "tyia" else 15
    elif id == "hibernation_trance":
        fixed = 20
    elif id == "reduce_injury":
        fixed = {"incapacitated": 15, "mortally_wounded": 20, "dead": 30}.get(state.wound, 15)
    elif id == "remain_conscious":
        fixed = {"incapacitated": 15, "mortally_wounded": 20}.get(state.wound, 10)
    elif id == "life_detection":
        fixed = 5 if target.force_sensitive or any(parse_code(code)[0] for code in target.force_skills.values()) else 15
        modifier = rel
    elif id == "life_sense":
        modifier = rel + prox
        if not req.willing:
            resist, opposition = resistance(target, req, control_only=True)
            modifier += resist
    elif id in {"magnify_senses", "sense_force"}:
        fixed = 5 if id == "magnify_senses" else 20 if req.profile == "detail" else 15
        modifier = prox
    elif id == "receptive_telepathy":
        if not req.willing:
            fixed, opposition = resistance(target, req)
        modifier = prox + rel
    elif id == "injure_kill":
        fixed, opposition = resistance(target, req)
    elif id == "telekinesis":
        fixed = next(value for mass, value in ((1, 5), (10, 10), (100, 15), (1000, 20), (10000, 30), (100000, 31)) if req.mass_kg <= mass)
        modifier = prox + req.maneuver_modifier + 5 * max(0, math.ceil((req.speed_m_per_round - 10) / 10))
        if target and not req.willing:
            resist, opposition = resistance(target, req)
            modifier += resist
    elif id == "lightsaber_combat":
        fixed = 15 if skill == "control" else 10
    elif id == "projective_telepathy":
        if skill == "control":
            modifier = prox + (req.quiet_modifier if req.quiet else 0)
        else:
            modifier = rel
            if not req.willing:
                fixed, opposition = resistance(target, req)
    elif id == "accelerate_another_healing":
        modifier = rel if skill == "control" else 0
    elif id == "control_another_pain":
        if skill == "control":
            modifier = rel + prox
        else:
            fixed = {"healthy": 10, "wounded": 10, "incapacitated": 15, "mortally_wounded": 20}.get(injury, 20)
    elif id == "return_another_consciousness":
        fixed = 10 if skill == "control" or injury != "mortally_wounded" else 20
        modifier = prox + rel if skill == "control" else 0
    elif id == "transfer_force":
        fixed = 10 if skill == "control" else 15
        modifier = prox + rel if skill == "control" else 0
    elif id == "affect_mind":
        if skill == "control":
            fixed, modifier = {"": 5, "perception": 5, "memory": 10, "conclusion": 15}[req.profile], prox
        elif skill == "sense":
            fixed, opposition = resistance(target, req)
    # Opposed base totals are actual rolls, never replaced by a base difficulty override.
    total = (fixed if opposition is not None and id in {"injure_kill", "receptive_telepathy", "projective_telepathy", "affect_mind"} else base_override(req, skill, fixed)) + modifier
    if target:
        empty = effects.find_effect(target, "emptiness")
        if empty and (skill == "sense" or ("sense" not in POWERS[id].skills and skill == "control")):
            total += empty.parameters.get("entry_total", 0)
    if state.origin.force_tradition == "tyia" and skill == "alter":
        from dungeonforge.rules.weg_hazards import harder
        total = harder(total, req.tyia_alter_difficulty)
    return total, opposition


def activation_result(attempt, component=None, summary=""):
    component = component or (attempt.rolls[-1] if attempt.rolls else None)
    return RuleEvaluationResult(action_type="force_power", success=not attempt.failed, roll_result=component.roll if component else empty_roll("Force preparation"),
        target_value=component.difficulty if component else None, force_rolls=attempt.rolls.copy(),
        summary=f"[WEG D6 Force: {POWERS[attempt.power_id].name}] {summary}",
        state_changes={"power_id": attempt.power_id, "activation_id": attempt.id, "complete": False})


def begin(state, req, source_id, target=None, *, in_combat=False, extra_penalty=0):
    if state.force.attempt:
        if state.force.attempt.failed:
            effects.finalize_failure(state)
        else:
            raise ValueError("Finish or cancel the current Force activation first.")
    spec = validate_request(state, req, target, in_combat)
    internal = req.power_id in {"reduce_injury", "remain_conscious"}
    if not state.can_act and not internal:
        raise ValueError("The caster must be conscious and able to act.")
    if in_combat and req.force_point:
        raise ValueError("Declare round Force Point use before the action phase.")
    required_rounds = preparation_rounds(state, spec)
    if required_rounds > 1 and req.force_point:
        raise ValueError("Complete preparation first, then declare the Force Point with the actual skill-roll actions.")
    attempt = ForceAttempt(power_id=req.power_id, source_id=source_id, target_id=req.target_id, skills=spec.skills, parameters=req.model_dump(), preparation_remaining=max(0, required_rounds - 1))
    attempt.parameters["_in_combat"] = in_combat
    state.force.attempt = attempt
    if attempt.preparation_remaining:
        if state.round_state.full_defense or state.round_state.actions_taken or state.round_state.declared_actions != 1:
            raise ValueError("Preparation occupies the whole round; declare one action and begin before other actions.")
        effects.take_action(state)
        attempt.preparation_committed = True
        return activation_result(attempt, summary=f"Preparation begun: {required_rounds} rounds required. Stay focused; {attempt.preparation_remaining} round boundaries remain before skill rolls.")
    return roll_next(state, target, req.character_points, req.mishap, extra_penalty=extra_penalty)


def roll_next(state, target, points=0, mishap="penalty", *, extra_penalty=0):
    attempt = state.force.attempt
    if attempt is None:
        raise ValueError("No Force activation is in progress.")
    if attempt.failed:
        raise ValueError("The last component failed. Add permitted CP before another roll, or cancel this activation.")
    if attempt.preparation_remaining:
        if state.round_state.actions_taken or state.round_state.declared_actions != 1 or attempt.preparation_committed:
            raise ValueError("Preparation requires one otherwise unused action/round; advance the round before continuing.")
        effects.take_action(state)
        attempt.preparation_committed = True
        return activation_result(attempt, summary=f"Preparation continues; {attempt.preparation_remaining} round boundaries remain.")
    req = ForcePowerRequest.model_validate(attempt.parameters)
    # Recheck prerequisites, patient condition, costs and physical restrictions at completion.
    validate_request(state, req, target, attempt.parameters.get("_in_combat", False))
    skill = attempt.skills[len(attempt.rolls)]
    target_number, opposition = difficulty(state, req, target, skill)
    internal = req.power_id in {"reduce_injury", "remain_conscious"}
    component = force_component(state, skill, target_number, points, mishap, internal=internal, extra_penalty=extra_penalty, strict=req.power_id == "injure_kill", immediate=req.power_id == "reduce_injury")
    component.opposition = opposition
    attempt.rolls.append(component)
    attempt.parameters["_last_component_round"] = state.force.elapsed_rounds
    if req.power_id == "injure_kill" and not attempt.dark_side_awarded:
        from dungeonforge.rules.weg_dark_side import gain_point
        gain_point(state, "Using Injure/Kill, including an unsuccessful attempt.", "injure_kill")
        attempt.dark_side_awarded = True
    attempt.failed = not component.success
    result = activation_result(attempt, component, f"{skill.title()} {component.roll.expression}: {component.roll.breakdown} vs {target_number} → {'SUCCESS' if component.success else 'FAILED'}. {len(attempt.rolls)}/{len(attempt.skills)} skill actions resolved.")
    if attempt.dark_side_awarded:
        result.summary += " One Dark Side Point awarded for using Injure/Kill; moral consequences remain with the GM."
    if attempt.failed:
        result.success = False
        result.summary += " No power effect yet; CP may improve this component before another roll."
        return result
    if len(attempt.rolls) == len(attempt.skills):
        finish(state, target, result)
    else:
        result.summary += " Resolve the remaining Force skill in another declared action/pass or the next consecutive round."
    return result


def finish(state, target, result):
    attempt = state.force.attempt
    req = ForcePowerRequest.model_validate(attempt.parameters)
    spec = POWERS[attempt.power_id]
    patient = target if target is not None else state
    effect = ForceEffect(power_id=req.power_id, source_id=attempt.source_id, target_id=req.target_id or attempt.source_id, skills=spec.skills,
        maintained=req.keep_up, rounds_remaining=None if req.keep_up else 1, parameters={"description": req.description, "profile": req.profile})
    note = spec.description
    if req.power_id in {"control_pain", "control_another_pain"}:
        patient = target if req.power_id == "control_another_pain" else state
        effect.ready_in_rounds = 1
        effect.rounds_remaining = None if req.keep_up else 2
        state.force.effects.append(effect)
        if patient is not state:
            copy = effect.model_copy(deep=True)
            copy.recipient = True
            patient.force.effects.append(copy)
        effects.settle_consciousness(patient)
        note = "Pain suppression begins next round. Injuries, worsening wounds, and mortal death checks remain."
    elif req.power_id == "lightsaber_combat":
        state.force.effects.append(effect)
        note = "Lightsaber Combat active: Sense adds to attack/parry; Control modifies damage. Upkeep is two skill actions in later rounds."
    elif req.power_id == "resist_stun":
        state.force.effects.append(effect)
    elif req.power_id == "reduce_injury":
        if state.force_points < 1:
            raise ValueError("The required Force Point is no longer available.")
        from dungeonforge.rules.weg_rewards import spend
        spend(state, "reduce_injury")
        if state.wound == "dead":
            state.force.permanent_injuries.append(req.permanent_injury.strip())
        state.wound = "wounded"
        state.unconscious_rounds = 0
        state.force.reduce_injury_available = state.force.remain_pending = False
        note = "The new injury is reduced to wounded; one Force Point spent without doubling the roll. The current round's wound block still applies."
    elif req.power_id in {"remain_conscious", "return_another_consciousness"}:
        patient = target if req.power_id == "return_another_consciousness" else state
        patient.force.remain_pending = False
        patient.force.remain_actions = 1
        patient.round_state.blocked = False
        note = "Conscious for at most one further declared action; activate Control Pain to avoid collapsing afterward."
    elif req.power_id in {"accelerate_healing", "accelerate_another_healing"}:
        patient = target if req.power_id == "accelerate_another_healing" else state
        patient.force.healing_day = patient.force.elapsed_rounds // 17280
        patient.force.healing_rolls_remaining = 2 - patient.force.healing_rolls_used
        effect.rounds_remaining, effect.maintained = 17280, False
        effect.recipient = patient is not state
        patient.force.effects.append(effect)
        note = "Two +2 natural healing rolls are available for the current day. Another's healing rolls require continued physical contact."
    elif req.power_id == "transfer_force":
        if target.wound != "mortally_wounded" or state.force_points < 1:
            raise ValueError("The patient must still be mortally wounded and the transfer Force Point available.")
        from dungeonforge.rules.weg_rewards import spend
        spend(state, "transfer_force", guaranteed_heroic=True)
        if not state.force.dark_side_consumed:
            state.force.heroic_force_returns += 1
        effect.recipient, effect.maintained, effect.rounds_remaining = True, False, 725760
        target.force.effects.append(effect)
        note = "One Force Point transferred. Patient hibernates, still mortally wounded, for up to six weeks; further injury ends stabilization. " + ("Consumed character: no automatic heroic point return is owed; the Dark Side's adventure-end award rule requires a GM ruling." if state.force.dark_side_consumed else "Record the heroic point's return at adventure end.")
    elif req.power_id == "hibernation_trance":
        state.force.effects = [item for item in state.force.effects if not item.maintained]
        effect.parameters.update({"wake_after": req.duration_rounds, "wake_stimulus": req.description})
        effect.rounds_remaining = req.duration_rounds if req.keep_up else 1
        state.force.effects.append(effect)
    elif req.power_id == "emptiness":
        state.force.effects = [item for item in state.force.effects if not item.maintained]
        effect.rounds_remaining = None
        effect.parameters.update({"planned_rounds": req.duration_rounds, "meditated_rounds": 0, "entry_total": attempt.rolls[0].roll.total, "last_exit_round": None})
        state.force.effects.append(effect)
    elif req.power_id == "injure_kill":
        component = attempt.rolls[0]
        result.resistance_roll = component.opposition
        result.damage_roll = component.roll
        result.wound_result = WEGD6Rules.apply_damage(target, component.roll.total - component.difficulty)
        result.state_changes["force_injury_targets"] = [req.target_id]
        note = f"Alter {component.roll.total} vs resisting mind {component.difficulty}: {result.wound_result}. No separate Strength roll."
    elif req.power_id == "telekinesis":
        effect.parameters.update({"mass_kg": req.mass_kg, "speed": req.speed_m_per_round, "in_sight": req.in_sight, "proximity": req.proximity})
        state.force.effects.append(effect)
        note = f"One visible target ({req.mass_kg:g}kg) moves up to {req.speed_m_per_round:g}m/round. A separate Control action is required for a telekinetic attack; that use awards a Dark Side Point."
    elif req.power_id in {"life_detection", "life_sense", "receptive_telepathy"} and req.keep_up:
        state.force.effects.append(effect)
    if req.power_id == "life_sense":
        note += f" Recorded target injury: {target.wound.replace('_', ' ')}."
    if req.power_id == "receptive_telepathy" and attempt.rolls[-1].roll.total >= 2 * attempt.rolls[-1].difficulty:
        note += " Success doubled difficulty: a separate full round may probe memories up to 24 hours old; the GM supplies their content."
    if req.description:
        note += " Declared effect: " + req.description
    result.success = True
    result.state_changes["complete"] = True
    result.state_changes["effect_id"] = effect.id if effect in state.force.effects or (target and effect in target.force.effects) else None
    result.summary += " " + note
    state.force.attempt = None
    effects.settle_consciousness(state)


def absorb_incoming(state, damage_total):
    options = state.round_state.absorb_energy
    state.round_state.absorb_energy = None
    try:
        WEGD6Rules.validate_action(state, "control", options["character_points"], defensive=True)
        dice, pips = WEGD6Rules.pool(state, "control")
        roll = D6Roller.values(dice, pips, options["character_points"], options["mishap"])
        state.character_points -= options["character_points"]
        state.round_state.character_points_spent |= options["character_points"] > 0
        effects.take_action(state)
        component = ForceSkillRoll(skill="control", difficulty=15 + damage_total, success=roll.total >= 15 + damage_total, roll=roll, character_points=options["character_points"])
        effects.settle_consciousness(state)
        return component.success, component, f"Prepared Absorb/Dissipate Energy: {roll.breakdown} vs {component.difficulty} → {'ABSORBED' if component.success else 'FAILED; full incoming damage still applies'}."
    except ValueError as exc:
        return False, None, f"Prepared energy reaction unavailable: {exc} Incoming damage resolves normally."


def accelerated_heal(patient, *, touching=True, donor_present=True):
    if patient.force.healing_day != patient.force.elapsed_rounds // 17280 or patient.force.healing_rolls_remaining <= 0:
        raise ValueError("No accelerated natural healing rolls remain for the current day.")
    if patient.wound in {"healthy", "dead"}:
        raise ValueError("No living injury requires a healing roll.")
    grant = next((effect for effect in patient.force.effects if effect.power_id in {"accelerate_healing", "accelerate_another_healing"}), None)
    if grant and grant.power_id == "accelerate_another_healing" and (not touching or not donor_present):
        raise ValueError("The granting Jedi must be present and touching the patient for this healing roll.")
    roll = D6Roller.roll(patient.attributes["strength"])
    roll.modifier += 2
    roll.total += 2
    roll.breakdown += f"; accelerated healing +2 = {roll.total}"
    old = patient.wound
    if old == "wounded":
        patient.wound = "incapacitated" if roll.total <= 4 else "wounded" if roll.total <= 6 else "healthy"
    elif old == "incapacitated":
        patient.wound = "mortally_wounded" if roll.total <= 6 else "incapacitated" if roll.total <= 8 else "wounded"
    else:
        patient.wound = "dead" if roll.total <= 6 else "mortally_wounded" if roll.total <= 8 else "incapacitated"
    patient.force.healing_rolls_remaining -= 1
    patient.force.healing_rolls_used += 1
    if patient.wound != old:
        patient.recovery_days = 0
        patient.round_state.blocked = False
        if patient.wound == "mortally_wounded":
            patient.mortal_rounds = 0
    return RuleEvaluationResult(action_type="force_healing", success=patient.wound != "dead" and {"healthy": 0, "wounded": 1, "incapacitated": 2, "mortally_wounded": 3, "dead": 4}[patient.wound] < {"healthy": 0, "wounded": 1, "incapacitated": 2, "mortally_wounded": 3, "dead": 4}[old], roll_result=roll,
        summary=f"[WEG D6 Accelerated Healing] Strength {roll.breakdown}: {old.replace('_', ' ')} → {patient.wound.replace('_', ' ')}. {patient.force.healing_rolls_remaining} roll(s) remain today.")


def redirect_bolt(state, target, weapon, declaration, result):
    """A declared extra Control action redirects one successfully parried bolt."""
    state.round_state.redirect_blaster = None
    from dungeonforge.rules.weg_d6 import RANGE_DIFFICULTIES
    base = declaration.get("difficulty") or RANGE_DIFFICULTIES[declaration["range_band"]]
    defense = target.round_state
    number = base
    if defense.defense_skill == "dodge" and defense.defense_total is not None:
        number = base + defense.defense_total if defense.full_defense else defense.defense_total if defense.use_defense_roll else base
    try:
        if target.out_of_fight:
            raise ValueError("The declared reflected-bolt target is out of the fight.")
        component = force_component(state, "control", number, declaration["character_points"], declaration["mishap"])
    except ValueError as exc:
        result.summary += f" Redirect unavailable: {exc} The original bolt remains parried."
        return
    result.force_rolls.append(component)
    result.summary += f" Redirect Control {component.roll.total} vs {number}: {'HIT' if component.success else 'MISS'}."
    if component.success:
        damage = D6Roller.roll(weapon.damage or "4D")
        resist = D6Roller.values(*WEGD6Rules.resistance_pool(target, "energy"))
        outcome = WEGD6Rules.apply_damage(target, damage.total - resist.total)
        result.state_changes["redirected_injury"] = {"target_id": declaration["target_id"], "damage": damage.model_dump(), "resistance": resist.model_dump(), "wound": outcome}
        result.summary += f" Original bolt {damage.total} vs Strength/armor {resist.total}: {outcome}."
    effects.settle_consciousness(state)


def telekinetic_attack(state, target, effect_id, points=0, mishap="penalty", extra_penalty=0):
    from dungeonforge.rules.weg_vehicles import TO_HIT, DAMAGE_CAP, RESIST_CAP, cap_for, capped, fixed_roll
    held = next((effect for effect in state.force.effects if effect.id == effect_id and effect.power_id == "telekinesis" and not effect.recipient), None)
    if not held or not held.parameters.get("in_sight"):
        raise ValueError("Select an active, visible telekinetic object first.")
    if target.out_of_fight:
        raise ValueError("The target is already out of the fight.")
    mass = held.parameters["mass_kg"]
    dice, scale = (1, "character") if mass < 1 else (2, "character") if mass <= 10 else (4, "character") if mass <= 100 else (3, "speeder") if mass <= 1000 else (3, "starfighter") if mass <= 10000 else (5, "starfighter")
    defense = target.round_state
    number = (10 + (defense.defense_total or 0) if defense.full_defense else defense.defense_total) if defense.defense_skill == "dodge" and defense.use_defense_roll else 10
    component = force_component(state, "control", number, points, mishap, extra_penalty=extra_penalty)
    component.roll = capped(component.roll, cap_for(TO_HIT, scale, "character"))
    component.success = component.roll.total >= number
    from dungeonforge.rules.weg_dark_side import gain_point
    gain_point(state, "Attacking with Telekinesis, including an unsuccessful attack.", "telekinetic_attack")
    result = RuleEvaluationResult(action_type="force_attack", success=component.success, roll_result=component.roll, target_value=number, force_rolls=[component],
        summary=f"[WEG D6 Telekinetic Attack] Control {component.roll.total} vs {number}: {'HIT' if component.success else 'MISS'}. One Dark Side Point awarded for attacking with the Force.")
    if component.success:
        result.damage_roll = fixed_roll(dice, 0, cap_for(DAMAGE_CAP, scale, "character"))
        result.resistance_roll = fixed_roll(*WEGD6Rules.resistance_pool(target, "physical"), cap_for(RESIST_CAP, scale, "character"))
        result.wound_result = WEGD6Rules.apply_damage(target, result.damage_roll.total - result.resistance_roll.total)
        result.summary += f" Object {dice}D {scale} damage {result.damage_roll.total} vs scaled Strength/physical armor {result.resistance_roll.total}: {result.wound_result}."
    effects.settle_consciousness(state)
    return result


def life_detection_scan(state, target, points=0, mishap="penalty", extra_penalty=0):
    if not effects.find_effect(state, "life_detection") or not state.can_act:
        raise ValueError("Activate and keep up Life Detection before scanning an approaching creature within ten meters.")
    req = ForcePowerRequest(power_id="life_detection", willing=False)
    number, opposition = resistance(target, req)
    component = force_component(state, "sense", number, points, mishap, free=True, extra_penalty=extra_penalty)
    component.opposition = opposition
    detail = "Presence detected." if component.success else "Presence concealed."
    if component.roll.total - number >= 10:
        detail += f" Force sensitive: {target.force_sensitive}; trained in the Force: {any(parse_code(code)[0] for code in target.force_skills.values())}. GM identifies previously met creatures."
    return RuleEvaluationResult(action_type="force_detection", success=component.success, roll_result=component.roll, target_value=number, force_rolls=[component], summary=f"[WEG D6 Life Detection] Free Sense {component.roll.total} vs {number}. {detail}")
