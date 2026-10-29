"""WEG40055 (1992), printed pp.15, 56–58, 140. No R&E temptation dice."""
import random

from dungeonforge.rules.dice import RollResult
from dungeonforge.rules.weg_d6 import D6Roller, WEGD6Rules, parse_code
from dungeonforge.rules.weg_dark_models import AtonementCycle, AtonementReview, CorruptionEvent, DarkDemand
from dungeonforge.rules import weg_force_effects as effects


def fallen(state):
    return state.force.dark_side_consumed if hasattr(state, "force") else state.dark_side_consumed


def set_fallen(state, value):
    if hasattr(state, "force"):
        state.force.dark_side_consumed = value
    else:
        state.dark_side_consumed = value


def plain_die(label):
    value = random.randint(1, 6)
    return RollResult(expression="1D6", dice_count=1, die_type=6, total=value, raw_rolls=[value], kept_rolls=[value], system="weg_d6", breakdown=f"{label}: plain 1D6 = {value} (no Wild Die, CP, or Force Point)")


def invalidate_atonement(state):
    cycle = state.corruption.atonement
    if cycle and cycle.status == "active":
        cycle.status = "failed"
        state.corruption.atonement_history.append(cycle)
        state.corruption.atonement = None
        return True
    return False


def gain_point(state, reason, source):
    before, was_fallen = state.dark_side_points, fallen(state)
    state.dark_side_points = min(1_000_000, before + 1)
    die = None if was_fallen else plain_die("Corruption check").total
    fell = not was_fallen and die < state.dark_side_points
    interrupted = invalidate_atonement(state)
    cp_awarded = 0
    if was_fallen:
        state.character_points = min(1_000_000, state.character_points + 1)
        cp_awarded = 1
    if fell:
        set_fallen(state, True)
        state.corruption.control_mode = "gm"
        state.corruption.fallen_adventure = None  # stamped with the actual session adventure
        state.corruption.redemption_deadline = None
        state.corruption.moment_keys.clear()
        if hasattr(state, "force"):
            state.force.effects = [effect for effect in state.force.effects if effect.power_id not in {"emptiness", "emptiness_bonus"}]
    event = CorruptionEvent(source=source, reason=reason + (" Atonement interrupted by a new Dark Side Point." if interrupted else ""), before=before, after=state.dark_side_points, fall_die=die, fell=fell, cp_awarded=cp_awarded)
    state.corruption.events.append(event)
    return event


def event_note(event):
    note = f"Dark Side Points {event.before} → {event.after}: {event.reason}"
    if event.fall_die is not None:
        note += f" Plain corruption die {event.fall_die} {'<' if event.fell else '≥'} {event.after}: {'FALLEN; GM control, existing CP/FP retained' if event.fell else 'not consumed'}."
    if event.cp_awarded:
        note += " Already consumed: +1 CP for receiving a Dark Side Point."
    return note


def call_level(state, harmful, adventure):
    previous = state.corruption.calls if state.corruption.calls_adventure == adventure else 0
    level = (1 if fallen(state) or state.force_sensitive else 2) + (0 if harmful else 2)
    if fallen(state):
        level += previous
    if level > 5:
        raise ValueError("This call exceeds Heroic, the corebook's final difficulty band; the GM must adjudicate it instead of inventing further numeric bands.")
    return level


def call(state, req, adventure, extra_penalty=0):
    if state.corruption.refuses_force:
        raise ValueError("A character who refuses to believe in the Force cannot call upon the Dark Side.")
    if state.corruption.pending_demand or state.corruption.dead:
        raise ValueError("Resolve the existing Dark Side demand before attempting another call.")
    if state.round_state.dark_side_called:
        raise ValueError("Only one Dark Side call is supported per round; advance the round before another call.")
    if state.round_state.character_points_spent or state.round_state.actions_taken or state.round_state.full_defense:
        raise ValueError("Declare a call before actions and defenses, in a round with no Character Point spending.")
    if not state.can_act or state.force.attempt:
        raise ValueError("The caller must be conscious, able to act, and free of another Force activation.")
    level = call_level(state, req.harmful, adventure)
    bands = ((1, 5), (6, 10), (11, 15), (16, 20), (21, 30), (31, 1000))
    low, high = bands[level]
    number = req.difficulty if req.difficulty is not None else (31 if level == 5 else high)
    if not low <= number <= high:
        raise ValueError(f"The GM difficulty must be within the call's band ({low}–{high}).")
    skill = req.skill
    if skill == "auto":
        skill = "control" if parse_code(state.force_skills["control"])[0] and parse_code(state.force_skills["control"]) >= parse_code(state.attributes["perception"]) else "perception"
    if state.round_state.force_active:
        if req.force_point:
            raise ValueError("A normal Force Point was already declared; do not spend it a second time.")
        state.round_state.declared_actions = req.actions
    else:
        WEGD6Rules.declare(state, req.actions, req.force_point)
    dice, pips = WEGD6Rules.validate_action(state, skill)
    if dice - extra_penalty < 1:
        raise ValueError("Crew/control penalties leave no dice for this call.")
    gain_point(state, f"Called on the Dark Side: {req.intention.strip()}", "dark_side_call")
    state.round_state.dark_side_called = True
    previous_calls = state.corruption.calls if state.corruption.calls_adventure == adventure else 0
    state.corruption.calls_adventure = adventure
    state.corruption.calls = previous_calls + 1
    roll = D6Roller.values(dice - extra_penalty, pips, mishap=req.mishap)
    effects.take_action(state)
    success = roll.total >= number
    if success:
        state.round_state.dark_side_active = True
        from dungeonforge.rules.weg_rewards import expenditure
        expenditure(state, "dark_side_call")
    elif fallen(state):
        penalty = plain_die("Failed Dark Side call demand")
        state.corruption.pending_demand = DarkDemand(cp_loss=penalty.total, roll=penalty)
    return roll, number, success, skill


def settle_demand(state, method, key):
    demand = state.corruption.pending_demand
    if not demand:
        raise ValueError("There is no unpaid Dark Side demand.")
    if method == "character_points":
        if state.character_points < demand.cp_loss:
            raise ValueError("Not enough CP to pay the demand; choose an attribute or trained Force skill to lose 1D.")
        state.character_points -= demand.cp_loss
        note = f"Lost {demand.cp_loss} CP to the Dark Side demand (a penalty, not CP dice spending)."
    else:
        pools = state.attributes if method == "attribute" else state.force_skills
        if key not in pools or parse_code(pools[key])[0] < 1:
            raise ValueError("Choose an existing attribute or trained Force skill with at least 1D.")
        dice, extra = parse_code(pools[key])
        old = pools[key]
        pools[key] = f"{dice - 1}D" + (f"+{extra}" if extra else "")
        note = f"Dark Side takes 1D from {key}: {old} → {pools[key]}. Other absolute learned skills are unchanged."
        if dice == 1:
            state.corruption.dead = True
            set_fallen(state, True)
            state.corruption.control_mode = "gm"
            if hasattr(state, "wound"):
                state.wound = "dead"
                effects.drop_on_injury(state)
                state.force.remain_pending = False
                state.force.reduce_injury_available = False
            invalidate_atonement(state)
            note += " No whole die remains: consumed by the Dark Side and dead."
    state.corruption.pending_demand = None
    return note


def atone(state, req, adventure):
    if fallen(state):
        raise ValueError("A consumed character needs redemption to the Light; ordinary atonement does not undo a fall.")
    if state.corruption.dead or getattr(state, "wound", None) == "dead" or state.corruption.pending_demand:
        raise ValueError("The character must be alive and free of a Dark Side demand.")
    cycle = state.corruption.atonement
    if req.action == "begin":
        if state.dark_side_points < 1 or cycle:
            raise ValueError("Begin atonement with at least one Dark Side Point and no active cycle.")
        state.corruption.atonement = AtonementCycle(started_adventure=adventure, next_review=adventure, intention=req.reason.strip())
        return "Atonement begins. Two completed adventures require explicit GM reviews of Jedi-code conduct and active opposition to evil. Downtime grants no progress."
    if cycle is None:
        raise ValueError("No active atonement cycle to review or abandon.")
    if req.action == "abandon":
        cycle.status = "abandoned"
        state.corruption.atonement_history.append(cycle)
        state.corruption.atonement = None
        return "Atonement abandoned; no Dark Side Point removed."
    reviewed = req.adventure if req.adventure is not None else cycle.next_review
    if reviewed != cycle.next_review or reviewed >= adventure:
        raise ValueError("Review the next unreviewed completed adventure in order; an adventure boundary alone does not approve conduct.")
    approved = req.action == "approve"
    cycle.reviews.append(AtonementReview(adventure=reviewed, approved=approved, reason=req.reason.strip()))
    cycle.next_review += 1
    cycle.consecutive = cycle.consecutive + 1 if approved else 0
    if cycle.consecutive < 2:
        return f"Adventure {reviewed}: {'GM approves conduct' if approved else 'GM rejects conduct; the two-adventure count restarts'}. {cycle.consecutive}/2 consecutive approved adventures; DSP unchanged."
    before = state.dark_side_points
    state.dark_side_points = max(0, before - 1)
    cycle.status = "completed"
    state.corruption.atonement_history.append(cycle)
    state.corruption.atonement = None
    state.corruption.events.append(CorruptionEvent(source="atonement", reason=f"Two GM-approved adventures: {req.reason.strip()}", before=before, after=state.dark_side_points))
    return "Two adventures approved: remove one Dark Side Point. No CP/FP awarded. Another point requires a new cycle and two further adventures."


def redeem(state):
    if state.corruption.pending_demand:
        raise ValueError("Settle the outstanding failed-call demand before recording redemption.")
    state.dark_side_points = 0
    set_fallen(state, False)
    state.character_points = state.force_points = 0
    if hasattr(state, "force"):
        state.force.heroic_force_returns = 0
        for item in state.rewards.expenditures:
            if item.ruling is None:
                item.forfeited = True
    if hasattr(state, "round_state"):
        state.round_state.dark_side_active = False
    if hasattr(state, "advancement"):
        for course in state.advancement.history:
            if course.status == "suspended":
                course.status = "forfeited"
    if state.corruption.control_mode == "redemption" and not state.corruption.npc_permanent:
        state.corruption.control_mode = "player"
    else:
        state.corruption.control_mode = "gm"
    state.corruption.redemption_deadline = None
    return "Redeemed to the Light. Final toll: all held Force Points and Character Points lost; suspended CP and unclaimed prior heroic FP returns are forfeited. Learned skills/powers remain."
