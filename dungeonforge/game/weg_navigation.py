"""Hyperspace clocks and plain-dice mishaps; mechanical state survives narration."""
from dungeonforge.rules.dice import DiceRoller
from dungeonforge.rules.weg_navigation import active


def require_resolved(session, *, hazard_step=False):
    current = active(session)
    if current and current.status != "travelling":
        raise ValueError("Resolve the saved navigation ruling or exposed-crew emergency before advancing scene time.")
    if not hazard_step:
        from dungeonforge.rules.weg_hazards import require_resolved as require_hazards
        require_hazards(session)


def tick(session, rounds):
    current = active(session)
    if not current:
        return
    if current.status == "emergency":
        people = {person.id: person for person in [session.character, *session.character.companions] if person.d6}
        for id, entry in current.crew_exposure.items():
            if id in people and people[id].d6.wound == "dead":
                entry["protected"], entry["phase"] = True, "dead"
        if all(entry["protected"] for entry in current.crew_exposure.values()):
            current.status = "abandoned"
        return
    if current.status != "travelling":
        return
    craft = next((item for item in session.vehicles if item.id == current.request.craft_id), None)
    if not craft or craft.damage == "destroyed" or craft.generator_shutdown or craft.hull_breached:
        current.status = "interrupted"
        current.resolution.append("Journey interrupted by loss of the spaceworthy craft.")
        return
    passed = min(rounds, current.remaining_rounds)
    current.remaining_rounds -= passed
    current.elapsed_rounds += passed
    if current.remaining_rounds == 0:
        current.status = "arrived"
        craft.location = current.request.destination.strip()
        for person in [session.character, *session.character.companions]:
            if person.id in current.travellers:
                places = person.d6.species_context.visited_locations
                if craft.location not in places:
                    places.append(craft.location)
        current.resolution.append(f"Arrived at {craft.location} after {current.elapsed_rounds / 720:g} hours.")


def plain(journey, expression):
    roll = DiceRoller.roll(expression)
    journey.auxiliary_rolls.append(roll.model_dump())
    return roll.total


def mishap(session, craft, journey):
    value = plain(journey, "2d6")
    journey.mishap = value
    if value == 2:
        craft.hyperdrive_disabled = True
        journey.status = "awaiting_location"
        journey.resolution.append("Hyperdrive cut-out and damaged: main hyperdrive needs Moderate repair; GM must record actual dropout location.")
    elif value <= 4:
        change = plain(journey, f"{journey.miss}d6")
        sign = -1 if plain(journey, "1d6") <= 3 else 1
        journey.remaining_rounds = max(1, journey.remaining_rounds + sign * change * 720)
        journey.status = "travelling"
        journey.resolution.append(f"Radiation fluctuations: duration changed by {sign * change} hours using the book's suggested ±1D hours per missed point.")
    elif value <= 6:
        journey.status = "awaiting_location"
        journey.resolution.append("Hyperdrive safety cut-out: GM must record dropout location; plot a new route.")
    elif value <= 8:
        journey.status = "awaiting_location"
        journey.resolution.append("Off course: GM must record the actual wrong system before plotting again.")
    elif value == 9:
        days = plain(journey, "1d6")
        journey.remaining_rounds += days * 17280
        journey.status = "travelling"
        journey.resolution.append(f"Mynocks: journey extended by {days} days.")
    elif value == 10:
        journey.status = "close_call_pending"
        journey.resolution.append("Close call: GM must select the actual damaged system; the journey can then continue to its destination.")
    else:
        journey.status = "exposure_pending"
        craft.damage, craft.hull_breached = "heavily_damaged", True
        journey.resolution.append("Collision: heavy damage and ruptured hull. Ship is no longer spaceworthy; GM must identify crew exposed to vacuum. Abandon the ship.")
