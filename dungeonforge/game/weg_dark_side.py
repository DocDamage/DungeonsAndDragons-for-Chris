"""Canonical corruption events for party members, combatants, crew and instructors."""
from dataclasses import dataclass
from dungeonforge.rules import weg_dark_side as rules


@dataclass
class DarkActor:
    id: str
    name: str
    state: object
    kind: str = "character"


def actors(session):
    from dungeonforge.game import weg_force
    party = {person.id for person in [session.character, *session.character.companions]}
    result = {id: DarkActor(id, person.name, person.state, "party" if id in party else "encounter") for id, person in weg_force.actors(session).items()}
    for teacher in session.d6_advancement.instructors:
        result[teacher.id] = DarkActor(teacher.id, teacher.name, teacher, "instructor")
    return result


def actor(session, id=None):
    person = actors(session).get(id or session.character.id)
    if not person:
        raise ValueError("Select an available native character, crew member, opponent or instructor.")
    return person


def synchronize(session, result=None):
    adventure = session.d6_advancement.adventure
    notes, recorded = [], []
    for person in actors(session).values():
        state, dark = person.state, person.state.corruption
        if dark.calls_adventure != adventure:
            dark.calls_adventure, dark.calls = adventure, 0
        if rules.fallen(state) and dark.fallen_adventure is None:
            dark.fallen_adventure = adventure
            dark.control_mode = "gm"
        if rules.fallen(state) and hasattr(state, "force"):
            state.force.effects = [effect for effect in state.force.effects if effect.power_id not in {"emptiness", "emptiness_bonus"}]
        if person.kind != "party":
            dark.control_mode = "gm"
        if dark.control_mode == "redemption" and dark.redemption_deadline is not None and adventure >= dark.redemption_deadline:
            dark.control_mode, dark.npc_permanent = "gm", True
            notes.append(f"{person.name}'s redemption deadline has expired: permanently GM-controlled, including if later redeemed.")
        for event in dark.events:
            if event.adventure is None:
                event.adventure = adventure
            if result is not None and not event.reported:
                event.reported = True
                notes.append(f"{person.name}: {rules.event_note(event)}")
                recorded.append({"actor_id": person.id, **event.model_dump()})
    if result is not None:
        if notes:
            result.summary += " " + " ".join(notes)
        if recorded:
            result.state_changes["corruption_events"] = recorded


def require_reason(reason):
    if not reason.strip():
        raise ValueError("Record the GM ruling or declared intention.")
