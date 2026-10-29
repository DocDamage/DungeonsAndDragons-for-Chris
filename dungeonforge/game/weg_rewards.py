"""Stamp expenditures at session boundaries, including older Transfer Force saves."""
from dungeonforge.rules.weg_rewards import expenditure


def synchronize(session):
    from dungeonforge.game.weg_force import actors
    seen = set()
    for person in actors(session).values():
        state = person.state
        if id(state) in seen:
            continue
        seen.add(id(state))
        tracked = sum(item.guaranteed_heroic and item.ruling is None and not item.forfeited for item in state.rewards.expenditures)
        for index in range(max(0, state.force.heroic_force_returns - tracked)):
            item = expenditure(state, "legacy_transfer_force", guaranteed_heroic=True)
            item.id = f"legacy_transfer_{person.id}_{session.d6_advancement.adventure}_{tracked + index}"
        for item in state.rewards.expenditures:
            if item.adventure is None:
                item.adventure = session.d6_advancement.adventure
