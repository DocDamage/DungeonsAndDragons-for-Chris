"""Source tables and actual persistent fatigue/drowning conditions."""

BANDS = [("Very Easy", 1, 5), ("Easy", 6, 10), ("Moderate", 11, 15), ("Difficult", 16, 20), ("Very Difficult", 21, 30), ("Heroic", 31, 1000)]
FALLS = [(3, 6, 2), (7, 12, 3), (13, 18, 4), (19, 30, 5), (31, 50, 7), (51, None, 9)]


def harder(difficulty, override=None):
    for index, (_, _, high) in enumerate(BANDS):
        if difficulty <= high:
            if index + 1 == len(BANDS):
                if override is None or override <= difficulty:
                    raise ValueError("Above Heroic has no higher printed band; record the GM's harder difficulty explicitly.")
                return override
            _, low, upper = BANDS[index + 1]
            if override is not None and not low <= override <= upper:
                raise ValueError(f"The next source difficulty band is {low}–{upper}.")
            return override if override is not None else low
    raise ValueError("Choose a source difficulty from 1 to 1000.")


def falling_dice(meters):
    # The printed distances are whole-meter bands. Fractional distances round up.
    import math
    if meters < 3:
        raise ValueError("The printed falling table starts at three meters; record a GM damage code below that distance.")
    distance = math.ceil(meters)
    for low, high, dice in FALLS:
        if low <= distance and (high is None or distance <= high):
            return dice
    raise ValueError("The printed falling table starts at three meters; record a GM damage code below that distance.")


def drowning_people(session):
    return [person for person in [session.character, *session.character.companions]
        if person.d6 and person.d6.hazards.drowning and person.d6.wound != "dead"]


def require_resolved(session):
    if drowning_people(session):
        raise ValueError("Resolve the saved drowning round with Environmental hazards before ordinary actions or scene time.")


def rest_required(state):
    hazard = state.hazards
    return hazard.exertion_rounds * (2 if hazard.exhausted or hazard.willpower_driven else 1)


def stop_pushing(state):
    if not state.hazards.willpower_driven:
        raise ValueError("This character is not driving on with Willpower.")
    state.hazards.willpower_driven = False
    state.hazards.fatigued = state.hazards.exhausted = True


def rest(state, rounds):
    hazard = state.hazards
    if hazard.willpower_driven:
        stop_pushing(state)
    if not hazard.fatigued and not hazard.exhausted:
        return
    hazard.rest_rounds += rounds
    if hazard.rest_rounds >= rest_required(state):
        hazard.fatigue_failures = 0
        hazard.fatigued = hazard.exhausted = False
        hazard.exertion_rounds = hazard.rest_rounds = 0
