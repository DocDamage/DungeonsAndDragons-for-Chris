"""Scene tasks use the original 1992 Command chart, not the later edition's rule."""
import math

from dungeonforge.rules.weg_d6 import DIFFICULTIES, WEGD6Rules, parse_code, skill_key
from dungeonforge.rules.weg_tasks_models import D6TaskQuote, D6TaskStepQuote


COUNTS = (2, 4, 6, 10, 15, 25, 40, 60, 100, 150, 250, 400, 600, 1000, 1500)
BANDS = ("very_easy", "easy", "moderate", "difficult", "very_difficult", "heroic")
# Columns are the average whole skill dice, 1D through 8D+; rows are COUNTS.
COMMAND = (
    (2, 2, 1, 1, 1, 0, 0, 0), (3, 2, 2, 2, 1, 1, 0, 0),
    (3, 3, 2, 2, 2, 2, 1, 1), (3, 3, 3, 2, 2, 2, 1, 1),
    (4, 3, 3, 3, 2, 2, 2, 1), (4, 4, 3, 3, 3, 2, 2, 2),
    (4, 4, 4, 3, 3, 3, 2, 2), (5, 4, 4, 4, 3, 3, 3, 2),
    (5, 5, 4, 4, 4, 3, 3, 3), (5, 5, 5, 4, 4, 4, 3, 3),
    (5, 5, 5, 5, 4, 4, 4, 3), (5, 5, 5, 5, 5, 4, 4, 4),
    (5, 5, 5, 5, 5, 5, 4, 4), (5, 5, 5, 5, 5, 5, 5, 4),
    (5, 5, 5, 5, 5, 5, 5, 5),
)
PREPARATION_BANNED = {
    "brawling_parry", "dodge", "lightsaber", "melee_combat", "melee_parry", "running", "survival",
    "archaic_starship_piloting", "beast_riding", "capital_ship_piloting", "capital_ship_shields",
    "ground_vehicle_operation", "hover_vehicle_operation", "powersuit_operation", "repulsorlift_operation",
    "starfighter_piloting", "starship_shields", "swoop_operation", "space_transports", "walker_operation",
    "gambling", "hide", "sneak", "brawling", "stamina", "swimming",
}
COMBINING_BANNED = {
    "dodge", "brawling_parry", "melee_parry", "pick_pocket", "running", "languages", "law_enforcement",
    "streetwise", "value", "astrogation", "beast_riding", "forgery", "gambling", "hide", "sneak",
    "stealth", "stamina", "swimming",
}
NOTES = [
    "Scene tasks only. Combined combat, hit/damage application and split fire require encounter integration; a saved scene bonus cannot be exported to another action.",
    "All workers are actual party members in the declared priority order. On a partial Command result only the first successfully coordinated workers contribute.",
    "The group roll uses the actual coordinated workers' average whole skill dice plus the source bonus. Personal CP/FP can improve the commander's Command roll, but cannot be distributed to the aggregate group roll.",
    "Generic tasks record checks and fictional outcomes; they do not grant craft repairs, training, installed equipment or other paid mechanical benefits.",
    "The GM declares all required stages, difficulties and actual durations before work. Every required stage must succeed; changing that procedure requires a new project.",
    "The source does not specify fractional rushing rounding. Fractional dice, pips or rounds require a recorded GM up/down ruling.",
    "Maintaining another power breaks exclusive concentration. Scene time advanced outside this task invalidates its saved exclusive-work continuity.",
]


def roster(session):
    return {person.id: person for person in [session.character, *session.character.companions] if person.d6}


def actor(session, id):
    person = roster(session).get(id)
    if person is None:
        raise ValueError("Select an actual native party actor; supplied dice or fictional worker counts are not accepted.")
    return person


def involved(req):
    return set(req.participant_ids or [req.actor_id]) | ({req.commander_id} if req.commander_id else set())


def busy_actor_ids(session):
    return set().union(*(involved(project.request) for project in session.d6_tasks.projects if project.status == "pending"))


def available(person):
    state = person.d6
    if not state.can_act or state.force.attempt or state.corruption.pending_demand:
        raise ValueError(f"{person.name} must be conscious and free of another activation or unresolved Dark Side demand.")
    if any(effect.maintained and not effect.recipient for effect in state.force.effects):
        raise ValueError(f"{person.name} cannot maintain another power while declaring exclusive concentration on this task.")


def parent_skill(state, skill):
    key = skill_key(skill)
    return skill_key(state.specialization_parents.get(key, key))


def half(value, step):
    if value % 2:
        if not step.rush_rounding or not step.rounding_reason.strip():
            raise ValueError("Rushing produces a fractional duration or pool; record the GM's up/down rounding ruling and reason.")
        return math.ceil(value / 2) if step.rush_rounding == "up" else value // 2
    return value // 2


def step_quote(step, people):
    key = skill_key(step.skill)
    if not step.reason.strip():
        raise ValueError("Describe the actual procedure for every required task stage.")
    for person in people:
        WEGD6Rules.skill_code(person.d6, key)
        if step.mode == "prepared" and parent_skill(person.d6, key) in PREPARATION_BANNED:
            raise ValueError("This skill or its specialization cannot receive the preparation bonus (printed p.65).")
    preparation, work = 0, step.rounds
    if step.mode == "prepared":
        preparation = work
    elif step.mode == "rushed":
        if step.rounds < 2:
            raise ValueError("Only tasks taking two rounds or longer may be rushed.")
        work = half(step.rounds, step)
        for person in people:
            dice, pips = WEGD6Rules.pool(person.d6, key)
            if half(dice, step) < 1:
                raise ValueError("The rushed pool must retain at least one die.")
            half(pips, step)
    return D6TaskStepQuote(skill=key, mode=step.mode, difficulty=step.difficulty, base_rounds=step.rounds,
        preparation_rounds=preparation, work_rounds=work, total_rounds=preparation + work)


def command_level(count, average):
    row = max(index for index, value in enumerate(COUNTS) if value <= count)
    return row, COMMAND[row][min(8, max(1, average)) - 1]


def commanded(count, average, difficulty, total):
    row, target_level = command_level(count, average)
    if total >= difficulty:
        return COUNTS[row]
    level = next((index for index in reversed(range(len(BANDS))) if total >= DIFFICULTIES[BANDS[index]][0]), -1)
    column = min(8, max(1, average)) - 1
    if level == target_level:
        first = next(index for index in range(row + 1) if COMMAND[index][column] == level)
        chosen = min(first, row - 1)
        return COUNTS[chosen] if chosen >= 0 else 0
    return next((COUNTS[index] for index in reversed(range(row)) if COMMAND[index][column] <= level), 0)


def bonus(count):
    return max((index + 1 for index, value in enumerate(COUNTS) if value <= count), default=0)


def quote(session, req):
    if not req.label.strip() or not req.reason.strip() or not req.exclusive:
        raise ValueError("Name the actual task and confirm exclusive concentration throughout the declared work.")
    ids = req.participant_ids or [req.actor_id]
    if len(ids) != len(set(ids)) or req.actor_id not in ids:
        raise ValueError("Declare each actual worker once and select a representative from those workers.")
    participants = [actor(session, id) for id in ids]
    combined = bool(req.participant_ids)
    if involved(req) & busy_actor_ids(session):
        raise ValueError("An actor is already committed to a pending exclusive task; finish or cancel it first.")
    for id in involved(req):
        available(actor(session, id))
    if not combined and (req.commander_id or req.command_character_points or req.command_force_point or req.commander_participates):
        raise ValueError("Command declarations require an actual combined group.")
    if combined:
        if len(participants) < 2 or not req.commander_id:
            raise ValueError("Combined work needs at least two actual workers and a named commander.")
        if len(req.steps) != 1 or req.steps[0].mode != "normal":
            raise ValueError("Combined scene work currently supports one normal stage; preparation, rushing and multi-stage work use a solo task.")
        if (req.commander_id in ids) != req.commander_participates:
            raise ValueError("Include the commander in the workers exactly when declaring that the commander also participates.")
        if not (req.contact_confirmed and req.target_visible and req.same_range):
            raise ValueError("Every worker needs direct contact, a visible shared target and the same range category.")
        if req.participant_limit is None or len(ids) > req.participant_limit:
            raise ValueError("Record the GM's actual hands-on/terminal/equipment limit and keep the declared group within it.")
        key = skill_key(req.steps[0].skill)
        if any(parent_skill(person.d6, key) in COMBINING_BANNED for person in participants):
            raise ValueError("This skill or its specialization cannot be combined (printed p.70).")
        commander = actor(session, req.commander_id)
        if req.command_character_points and req.command_force_point:
            raise ValueError("Command cannot combine Character Points and a Force Point.")
        if req.command_character_points > commander.d6.character_points or req.command_force_point and commander.d6.force_points < 1:
            raise ValueError("The actual commander lacks the selected Character or Force Points.")
        limit = 5 if "command" in commander.d6.specializations else 2
        if req.command_character_points > limit:
            raise ValueError(f"This Command roll permits at most {limit} Character Points.")
        if req.commander_participates and req.steps[0].rounds > 1 and (req.command_character_points or req.command_force_point):
            raise ValueError("Long-task points require doing only one action; a participating commander is commanding and working.")
        average = sum(parse_code(WEGD6Rules.skill_code(person.d6, key)[0])[0] for person in participants) // len(participants)
        row, level = command_level(len(ids), average)
        band = BANDS[level]
        low, high = DIFFICULTIES[band]
        difficulty = req.command_difficulty if req.command_difficulty is not None else high or low
        if difficulty < low or high is not None and difficulty > high:
            raise ValueError(f"This source Command row requires {band.replace('_', ' ')} difficulty ({low}–{high or '1000'}).")
    else:
        average, band, difficulty, row = None, None, None, None
    steps = [step_quote(step, participants) for step in req.steps]
    details = [{"actor_id": person.id, "name": person.name,
        "skills": {step.skill: WEGD6Rules.skill_code(person.d6, step.skill)[0] for step in steps},
        "declared_actions": 2 if req.commander_participates and person.id == req.commander_id else 1}
        for person in participants]
    return D6TaskQuote(steps=steps, combined=combined, average_skill=average, command_band=band,
        command_difficulty=difficulty, declared_count=len(ids), table_count=COUNTS[row] if row is not None else 1,
        participants=details, notes=list(NOTES))
