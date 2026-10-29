"""Three actual power choices per initial Force skill, independent of later training."""
from dungeonforge.rules.weg_advancement_models import D6PowerGrant
from dungeonforge.rules.weg_force_catalog import POWERS


def slot_balance(powers, skills):
    def fit(index, remaining):
        if index == len(powers):
            return remaining
        for skill in POWERS[powers[index]].skills:
            if remaining.get(skill, 0):
                answer = fit(index + 1, {**remaining, skill: remaining[skill] - 1})
                if answer is not None:
                    return answer
        return None
    answer = fit(0, {skill: 3 for skill in skills})
    if answer is None:
        raise ValueError("Selected powers exceed the three earned choices for an initial Force skill.")
    return answer


def save_grants(character, powers, skills, origin_key, automatic=()):
    for skill, remaining in slot_balance(powers, skills).items():
        if remaining:
            character.d6.advancement.power_grants.append(D6PowerGrant(skill=skill, remaining=remaining,
                teacher_id=f"starting:{origin_key}", project_id=f"origin:{character.id}",
                allowed_powers=[power.id for power in POWERS.values() if skill in power.skills and power.id not in automatic]))
