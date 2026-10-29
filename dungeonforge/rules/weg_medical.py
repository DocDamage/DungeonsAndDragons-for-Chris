"""Actual treatment clocks and source natural-healing workload modifiers."""
import math

from dungeonforge.rules.weg_d6 import D6Roller, WEGD6Rules, parse_code
from dungeonforge.rules.weg_models import D6RoundState
from dungeonforge.rules.base import RuleEvaluationResult

SOURCE = "WEG40055 (1992), printed p.67 (healing), p.90 (Medicine)."
DAY = 17_280
NATURAL_DAYS = {"wounded": 3, "incapacitated": 14, "mortally_wounded": 30}
BACTA = {"wounded": ("1d6", 720), "incapacitated": ("4d6", 720), "mortally_wounded": ("1d6", DAY)}
ACTIVE = {"active", "ready"}
WOUNDS = ("healthy", "wounded", "incapacitated", "mortally_wounded", "dead")


def members(session):
    return {person.id: person for person in [session.character, *session.character.companions] if person.d6}


def living_patient(session, id):
    person = members(session).get(id)
    if person is None:
        raise ValueError("Choose an actual native party member as patient.")
    if person.d6.droid or "droid" in person.race.lower():
        raise ValueError("Droids require actual Droid repair; organic healing cannot repair a chassis.")
    if person.d6.wound not in NATURAL_DAYS:
        raise ValueError("Choose a living wounded, incapacitated or mortally wounded patient.")
    return person


def active_project(session, patient_id):
    return next((project for project in session.d6_medical.projects if project.patient_id == patient_id and project.status in ACTIVE), None)


def record(session, project, operation, summary, **details):
    entry = {"project_id": project.id, "patient_id": project.patient_id, "operation": operation,
        "summary": summary, **details}
    project.history.append(entry)
    session.d6_medical.history.append(entry)
    return entry


def valid_patient(session, project):
    person = members(session).get(project.patient_id)
    return person if person and not person.d6.droid and "droid" not in person.race.lower() and person.d6.wound == project.initial_wound else None


def injury_snapshot(state):
    return {"stun_durations": list(state.stun_durations), "stun_expiries": list(state.stun_expiries),
        "unconscious_rounds": state.unconscious_rounds}


def new_injury(state, project, rounds=0):
    previous = project.observed_injury
    if not previous:
        return False
    for key in ("stun_durations", "stun_expiries"):
        expected = [value - rounds for value in previous.get(key, []) if value > rounds]
        actual = getattr(state, key)
        if len(actual) > len(expected) or max(actual, default=0) > max(expected, default=0):
            return True
    return state.unconscious_rounds > max(0, previous.get("unconscious_rounds", 0) - rounds)


def busy_actor_ids(session):
    return {project.patient_id for project in session.d6_medical.projects if project.status in ACTIVE
        and (project.kind == "bacta" or project.care_mode != "work")}


def protected_actor_ids(session):
    """Only actual successful, ongoing bacta suppresses untreated mortality."""
    return {project.patient_id for project in session.d6_medical.projects
        if project.kind == "bacta" and project.status == "active" and project.tank_confirmed
        and project.difficulty is not None and project.required_rounds > 0 and project.remaining_rounds > 0
        and project.treatment_roll and isinstance(project.treatment_roll.get("total"), (int, float))
        and math.isfinite(project.treatment_roll["total"]) and project.treatment_roll["total"] >= project.difficulty
        and valid_patient(session, project) and not new_injury(members(session)[project.patient_id].d6, project)}


def scene_interval(session, remaining):
    return min([remaining, *[project.remaining_rounds for project in session.d6_medical.projects
        if project.status == "active" and project.remaining_rounds > 0]])


def heal_fully(state):
    state.wound, state.recovery_days, state.mortal_rounds = "healthy", 0, 0
    state.stun_count, state.unconscious_rounds = 0, 0
    state.stun_durations.clear()
    state.stun_expiries.clear()
    state.round_state = D6RoundState()
    state.force.reduce_injury_available = False


def tick(session, rounds):
    """Called after each shared scene interval and its fleet injuries; never advances time."""
    entries = []
    for project in session.d6_medical.projects:
        if project.status not in ACTIVE:
            continue
        person = valid_patient(session, project)
        if person is None or project.kind == "bacta" and new_injury(person.d6, project, rounds):
            project.status = "interrupted"
            project.outcome = "Patient missing, dead, or injury changed; reassess actual treatment before further healing."
            entries.append(record(session, project, "interrupted", project.outcome))
            continue
        if project.status == "ready":
            if project.care_mode != "work":
                from dungeonforge.rules.weg_hazards import rest as actual_rest
                actual_rest(person.d6, rounds)
            continue
        if project.kind == "bacta":
            project.observed_injury = injury_snapshot(person.d6)
        passed = min(rounds, project.remaining_rounds)
        if project.kind == "bacta" or project.care_mode != "work":
            from dungeonforge.rules.weg_hazards import rest as actual_rest
            actual_rest(person.d6, passed)
        project.elapsed_rounds += passed
        project.remaining_rounds -= passed
        if project.remaining_rounds:
            continue
        if project.kind == "bacta":
            heal_fully(person.d6)
            project.status, project.outcome = "completed", "Actual bacta treatment completed; patient fully healed."
            entries.append(record(session, project, "completed", project.outcome, elapsed_rounds=project.elapsed_rounds))
        else:
            project.status, project.outcome = "ready", "The saved care period is complete; the actual Strength healing roll remains."
            entries.append(record(session, project, "ready", project.outcome, elapsed_rounds=project.elapsed_rounds))
    return entries


def natural_period(wound, mode, factor=1):
    return math.ceil(NATURAL_DAYS[wound] * DAY * (2 if mode == "easy" else 1) * factor)


def medicine(session, req):
    changed = req.medicine_bonus_dice or req.medicine_time_factor != 1
    if not req.medicine_item_id:
        if changed or req.medicine_confirmed or req.strong_medicine_confirmed:
            raise ValueError("Medicine modifiers require an actual inventory dose, not a free healing bonus.")
        return {}
    item = next((item for item in session.character.inventory if item.id == req.medicine_item_id), None)
    if item is None or item.quantity < req.medicine_quantity:
        raise ValueError("The actual medicine dose is not available in party inventory.")
    if not changed or not req.medicine_confirmed or not req.medicine_facts.strip():
        raise ValueError("Record the actual medicine, dose and confirmed healing effect before consuming it.")
    if (req.medicine_bonus_dice > 1 or req.medicine_time_factor < 0.5) and not req.strong_medicine_confirmed:
        raise ValueError("Stronger effects require explicit GM confirmation of an actual exceptional medicine/regimen; the ordinary source effects are +1D and/or at most half time.")
    result = {"item_id": item.id, "name": item.name, "quantity": req.medicine_quantity,
        "bonus_dice": req.medicine_bonus_dice, "time_factor": req.medicine_time_factor,
        "facts": req.medicine_facts.strip(), "exceptional": req.strong_medicine_confirmed,
        "unit_cost": item.unit_cost, "source": item.source}
    item.quantity -= req.medicine_quantity
    if not item.quantity:
        session.character.inventory.remove(item)
    return result


def doctor_medicine(session, req, trained):
    if not req.medicine_item_id:
        if req.medicine_bonus_dice or req.medicine_confirmed or req.medicine_facts.strip():
            raise ValueError("A doctor Medicine bonus needs an actual inventory dose and GM effect facts.")
        return {}
    if not trained:
        raise ValueError("This medicine effect increases actual trained Medicine; it cannot grant Medicine or enhance untrained First Aid/Technical.")
    item = next((item for item in session.character.inventory if item.id == req.medicine_item_id), None)
    if item is None or item.quantity < req.medicine_quantity:
        raise ValueError("The actual doctor medicine dose is not available in party inventory.")
    if not req.medicine_confirmed or req.medicine_bonus_dice < 1 or not req.medicine_facts.strip():
        raise ValueError("Confirm the actual dose and GM-specified Medicine bonus; no fixed doctor bonus is printed.")
    dose = {"application": "operator_medicine", "item_id": item.id, "name": item.name,
        "quantity": req.medicine_quantity, "bonus_dice": req.medicine_bonus_dice,
        "facts": req.medicine_facts.strip(), "unit_cost": item.unit_cost, "source": item.source,
        "convention": "External dose dice are added after Force Point doubling; the source does not specify their interaction."}
    item.quantity -= req.medicine_quantity
    if not item.quantity:
        session.character.inventory.remove(item)
    return dose


def roll_operator(state, skill, difficulty, character_points, dose):
    if not dose:
        return WEGD6Rules.roll_skill(state, skill, difficulty, character_points)
    if not state.can_act or state.round_state.full_defense or state.round_state.actions_taken >= state.round_state.declared_actions:
        raise ValueError("The actual operator needs a usable declared action.")
    if character_points > state.character_points or character_points and (state.round_state.force_active or state.round_state.dark_side_called):
        raise ValueError("Use available Character Points without mixing them with a Force Point.")
    dice, pips = WEGD6Rules.pool(state, skill)
    dose.update(pool_dice=dice, pool_pips=pips)
    dice += dose["bonus_dice"]
    if dice < 1:
        raise ValueError("The actual Medicine pool and confirmed dose leave no dice to roll.")
    roll = D6Roller.values(dice, pips, character_points, "penalty")
    state.character_points -= character_points
    state.round_state.character_points_spent |= bool(character_points)
    from dungeonforge.rules import weg_force_effects as effects
    effects.take_action(state)
    effects.settle_consciousness(state)
    return RuleEvaluationResult(action_type="skill_check", success=roll.total >= difficulty,
        roll_result=roll, target_value=difficulty,
        summary=f"Medicine {dice}D{pips:+d}, including actual external dose +{dose['bonus_dice']}D: {roll.breakdown} vs {difficulty}.")


def resolve_natural(state, project):
    dice, pips = parse_code(state.attributes["strength"])
    modifier = (-1 if project.care_mode == "work" else 1 if project.care_mode == "easy" else 0)
    bonus = project.medicine.get("bonus_dice", 0)
    dice = max(0, dice + modifier + bonus)
    roll = WEGD6Rules.damage_roll(dice, pips, mishap="penalty")
    old = state.wound
    if old == "wounded":
        new = "incapacitated" if roll.total <= 4 else "wounded" if roll.total <= 6 else "healthy"
    elif old == "incapacitated":
        new = "mortally_wounded" if roll.total <= 6 else "incapacitated" if roll.total <= 8 else "wounded"
    else:
        new = "dead" if roll.total <= 6 else "mortally_wounded" if roll.total <= 8 else "incapacitated"
    state.wound, state.recovery_days = new, 0
    state.round_state = D6RoundState(blocked=new in {"incapacitated", "mortally_wounded", "dead"})
    # The care clock already expired old timers. A new stun after that period
    # remains its own injury; resolving this wound must not erase it instantly.
    if new == "mortally_wounded" and old != new:
        state.mortal_rounds = 0
    if new != old:
        state.force.reduce_injury_available = False
    if WOUNDS.index(new) > WOUNDS.index(old):
        from dungeonforge.rules import weg_force_effects as effects
        effects.drop_on_injury(state)
    return roll, old, new, modifier, bonus
