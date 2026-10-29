"""Explicit GM rulings; narration and resting never replenish Force Points."""
from dungeonforge.rules.weg_reward_models import ForceExpenditure


def expenditure(state, source, *, guaranteed_heroic=False):
    item = ForceExpenditure(source=source, consumed=state.force.dark_side_consumed,
        guaranteed_heroic=guaranteed_heroic)
    state.rewards.expenditures.append(item)
    return item


def spend(state, source, *, guaranteed_heroic=False):
    if state.force_points < 1:
        raise ValueError("No Force Points remain.")
    state.force_points -= 1
    return expenditure(state, source, guaranteed_heroic=guaranteed_heroic)


def pending(state, adventure):
    return [item for item in state.rewards.expenditures if item.adventure == adventure and item.ruling is None and not item.forfeited]


def settle(state, req, adventure):
    """Mutates a transaction copy only; callers commit the whole party together."""
    items = pending(state, adventure)
    ids = [review.expenditure_id for review in req.reviews]
    if len(ids) != len(set(ids)) or set(ids) != {item.id for item in items}:
        raise ValueError("Review each pending Force Point expenditure exactly once, with no unknown or old entries.")
    if not req.reason.strip():
        raise ValueError("Record the GM's adventure reward reason.")
    if state.force.attempt or state.corruption.pending_demand:
        raise ValueError("Finish pending Force activations and Dark Side demands before closing the adventure.")
    consumed = state.force.dark_side_consumed
    if consumed and (req.character_points or req.zero_point_heroism):
        raise ValueError("Consumed characters cannot receive adventuring CP or the zero-point heroic award.")
    if req.zero_point_heroism and (not state.rewards.baseline_known or state.rewards.starting_force_points != 0):
        raise ValueError("Doing the Right Thing requires beginning this adventure with zero Force Points.")
    by_id = {review.expenditure_id: review for review in req.reviews}
    returned = 0
    for item in items:
        review = by_id[item.id]
        if not review.reason.strip():
            raise ValueError("Describe each Force Point's actual use and the GM ruling.")
        if item.guaranteed_heroic and review.ruling not in {"heroic", "heroic_climax"}:
            raise ValueError("Transfer Force is always heroic; review it as heroic or heroic at the decisive moment.")
        if review.ruling in {"evil", "evil_climax"}:
            previous = next((event for event in state.corruption.events if event.id == review.corruption_event_id and event.adventure == adventure and event.source in {"evil_force_point", "evil_act", "temptation", "injure_kill", "telekinetic_attack", "dark_side_favor"}), None)
            if previous is None:
                raise ValueError("Record the evil use's Dark Side Point first in Dark Side & atonement, then select its event here. Reward review never repeats corruption dice.")
        if item.consumed or consumed:
            amount = 2 if review.ruling == "evil_climax" else 0
        else:
            amount = {"heroic": 1, "heroic_climax": 2}.get(review.ruling, 0)
        item.ruling, item.reason, item.returned = review.ruling, review.reason.strip(), amount
        item.corruption_event_id = review.corruption_event_id
        returned += amount
    bonus = int(req.zero_point_heroism)
    total = state.force_points + returned + bonus
    excess = max(0, total - 5) if not state.force_sensitive else 0
    cp = req.character_points + 3 * excess
    if total - excess > 1_000_000 or state.character_points + cp > 1_000_000:
        raise ValueError("The reward would exceed the supported point storage limit.")
    state.force_points = total - excess
    state.character_points += cp
    state.force.heroic_force_returns = 0
    state.rewards.starting_force_points = state.force_points
    state.rewards.baseline_known = True
    return {"actor_id": req.actor_id, "reason": req.reason.strip(), "force_returned": returned,
        "zero_point_award": bonus, "force_converted": excess, "conversion_cp": 3 * excess,
        "character_points_awarded": req.character_points, "force_points": state.force_points,
        "character_points": state.character_points, "reviews": [item.model_dump() for item in items]}
