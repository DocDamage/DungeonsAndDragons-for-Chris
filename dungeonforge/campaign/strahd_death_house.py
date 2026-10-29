"""Reloaded Arc A's explicit GM dice clock, without invented adventure outcomes."""
from dungeonforge.campaign.strahd import ARCHIVE, SOURCES
from dungeonforge.rules.strahd_models import DeathHouseActor, DeathHouseEvent


SOURCE = f"{ARCHIVE}!/{SOURCES['opening']}"
FLOORS = {
    "first": ("First floor", ["Main Hall", "Cloakroom", "Den of Wolves", "Dining Room", "Kitchen and Pantry"]),
    "second": ("Second floor", ["Upper Hall", "Servants' Room", "Conservatory", "Library", "Secret Room"]),
    "third": ("Third floor", ["Balcony", "Master Suite", "Bathroom", "Storage Room", "Nursemaid's Suite"]),
    "attic": ("Attic", ["Attic Hall", "Spare Bedroom", "Children's Room", "Storage Room", "Guest Bedroom", "Secret Stairs"]),
    "basement": ("Basement", ["Family Crypts", "Cult Initiates' Quarters", "Well and Cultist Quarters", "Hidden Spiked Pit", "Dining Hall", "Larder", "Ghoulish Encounter", "Stairs Down", "Darklord's Shrine", "Hidden Trapdoor", "Cult Leader's Den", "Cult Leader's Quarters"]),
    "dungeon": ("Dungeon", ["Reliquary", "Prison", "Portcullis", "Ritual Chamber"]),
}
NOTES = [
    "GM reference: start only when the Main Hall grandfather clock actually strikes six. Older saves have an unstarted, unknown clock; the app does not reconstruct past play.",
    "Three dice start at 6, 6, 6. Each pip is twenty minutes. Decrease the lowest die first and remove a die at zero. A new floor or an entire-room Perception/Investigation check costs one pip; a short rest costs three.",
    "Revisiting a floor costs no new-floor pip. A repeated whole-room check is a new timed event. Each event has its own saved ID; resubmitting it cannot charge time twice.",
    "Midnight awakens the flesh mound. Allow at least one minute before it reaches the party, so Heavy Sleeper no longer limits its multiattack. Combat and pursuit need GM resolution; the clock never spawns enemies or rolls attacks.",
    "Long rests are impossible while trapped in Death House. Short rests in the main house bring one or more hauntings. This clock records time and evidence; it does not heal, spend Hit Dice, restore resources or complete a rest automatically.",
    "Damaging the tendrils or attacking the sleeping mound awakens it early. In that encounter Heavy Sleeper lasts one minute after waking; an attack on the sleeping mound can surprise it. Resolve those tactical facts with the GM.",
    "Sacrificing a living creature does not free the party: the mound's hunger cannot be sated. Its actual destruction opens the front door; the GM then resolves the collapsing-house escape.",
    "Actual escape, milestone XP, quest completion, NPC recruitment and sheet changes are separate explicit reviews. No floor, search, clock expiry or narration grants them automatically.",
]


def dice(pips):
    """First die is the lowest; six pips disappear before the next die changes."""
    return ([pips % 6] if pips % 6 else []) + [6] * (pips // 6)


def clock_label(pips):
    elapsed = (18 - pips) * 20
    hour, minute = divmod(18 * 60 + elapsed, 60)
    return "midnight" if hour == 24 else f"{hour - 12}:{minute:02d} p.m."


def view(session):
    state = session.strahd_progress.death_house
    return {**state.model_dump(), "dice": dice(state.remaining_pips),
        "clock_label": clock_label(state.remaining_pips) if state.status != "unstarted" else "not started / prior time unknown",
        "remaining_minutes": state.remaining_pips * 20 if state.status != "unstarted" else None,
        "clock_running": state.status == "exploring", "source_path": SOURCE,
        "floors": [{"id": id, "title": title, "rooms": rooms} for id, (title, rooms) in FLOORS.items()],
        "rules": NOTES}


def apply(session, req):
    """Validate all facts before changing even the disposable working copy."""
    state = session.strahd_progress.death_house
    if not req.actual_event_confirmed or not req.reason.strip():
        raise ValueError("The GM must confirm the actual source event and record its evidence.")
    if any(event.id == req.event_id for event in state.events):
        raise ValueError("This event ID was already recorded; it cannot charge time or resolve an outcome twice.")
    members = {person.id: person for person in [session.character, *session.character.companions]}
    if len(req.actor_ids) != len(set(req.actor_ids)) or not set(req.actor_ids) <= set(members):
        raise ValueError("Review actual party actors exactly once; supplied or absent actors are not witnesses.")
    if any(members[id].d6 is not None for id in req.actor_ids):
        raise ValueError("Death House uses actual 5e actors.")
    if req.action not in {"new_floor", "room_search", "short_rest"} and req.floor is not None:
        raise ValueError("This event does not accept a floor.")
    if req.action != "room_search" and (req.room is not None or req.skill is not None):
        raise ValueError("Only an entire-room check accepts a room and Perception/Investigation skill.")
    if req.action != "awakens_early" and req.early_trigger is not None:
        raise ValueError("Only an early awakening accepts a cause.")
    status, pips, requested, reminders = state.status, state.remaining_pips, 0, []
    floors = list(state.visited_floors)
    if req.action == "start":
        if status != "unstarted":
            raise ValueError("The Main Hall clock can start only once; it cannot reset an existing adventure.")
        status, pips, floors = "exploring", 18, ["first"]
        reminders.append("The Main Hall clock has struck six; the first floor is already entered. No entry pip is charged at initialization.")
    elif req.action in {"new_floor", "room_search", "short_rest"}:
        if status != "exploring":
            raise ValueError("Resolve the current pursuit, encounter or escape; source exploration pips run only before the mound awakens.")
        if req.floor not in FLOORS:
            raise ValueError("Select an actual Death House floor.")
        if req.action == "new_floor":
            if req.floor in floors:
                raise ValueError("That floor was already entered. Revisiting it does not cost another new-floor pip.")
            floors.append(req.floor)
            requested = 1
        else:
            if req.floor not in floors:
                raise ValueError("Record entry to this new floor before reviewing its room search or short rest.")
            if req.action == "room_search":
                if req.room not in FLOORS[req.floor][1] or req.skill not in {"perception", "investigation"}:
                    raise ValueError("Select a source room on this floor and a whole-room Perception or Investigation check.")
                requested = 1
            else:
                requested = 3
                reminders.append("Short-rest time reviewed. No HP, Hit Dice, spell slots or other recovery applied by this clock.")
                if req.floor in {"first", "second", "third", "attic"}:
                    reminders.append("Main-house short rest: the GM presents one or more source hauntings.")
                if pips < requested:
                    reminders.append("Midnight occurs before a full hour finishes. Resolve the approaching mound and whether this attempted rest completes; no recovery is presumed.")
        pips = max(0, pips - requested)
        if pips == 0:
            status = "hunting"
            reminders.append("MIDNIGHT: the flesh mound awakens and pursues the party. At least one minute passes before contact; Heavy Sleeper has expired on arrival. Resolve actual pursuit/combat with the GM.")
    elif req.action == "awakens_early":
        if status != "exploring" or req.early_trigger is None:
            raise ValueError("An early awakening requires the sleeping mound to be attacked or its tendrils damaged before midnight.")
        status = "awakened_early"
        reminders.append("Early awakening: GM resolves the first minute of Heavy Sleeper, surprise if attacked while sleeping, and the falling portcullis. No enemy or damage is created automatically.")
    elif req.action == "mound_destroyed":
        if status not in {"exploring", "hunting", "awakened_early"}:
            raise ValueError("Confirm the actual mound's destruction during the unresolved house adventure.")
        status = "escaping"
        reminders.append("The front door opens. On movement toward the exit Elisabeth begins the collapse. Resolve Gustav's obstruction and the cult figments; escape is not yet complete.")
    elif req.action == "escaped":
        if status != "escaping":
            raise ValueError("Record the mound's actual destruction and resolve the escape before confirming the party exited.")
        status = "escaped"
        reminders.append("Actual exit reviewed: the party emerges onto the Old Svalich Road in Barovia and the house collapses. The first long-rest 400 XP milestone still needs separate GM eligibility/reward review.")
    elapsed_before, elapsed_after = 18 - state.remaining_pips, 18 - pips
    chimes = ["midnight" if number == 6 else f"{6 + number}:00 p.m." for number in range(elapsed_before // 3 + 1, elapsed_after // 3 + 1)]
    event = DeathHouseEvent(id=req.event_id, action=req.action, reason=req.reason.strip(),
        actors=[DeathHouseActor(actor_id=id, name=members[id].name) for id in req.actor_ids],
        status_before=state.status, status_after=status, pips_before=state.remaining_pips, pips_after=pips,
        requested_pips=requested, floor=req.floor, room=req.room, skill=req.skill,
        early_trigger=req.early_trigger, chimes=chimes, reminders=reminders, source_path=SOURCE)
    state.status, state.remaining_pips, state.visited_floors = status, pips, floors
    state.events.append(event)
    if req.action == "escaped":
        from dungeonforge.campaign.strahd_children import on_house_exit
        on_house_exit(session, event)
    return event


def require_rest_allowed(session):
    if session.edition == "5e" and ("strahd" in session.source_folders or session.id == "session_strahd"):
        if session.strahd_progress.death_house.status not in {"unstarted", "escaped"}:
            raise ValueError("Death House is unresolved. Long rests are impossible while trapped. Use the GM Death House clock to review short-rest time (three pips) and hauntings; actual recovery needs a separate sheet review.")


def summary(session, *, guidance=True):
    state = session.strahd_progress.death_house
    if state.status == "unstarted":
        return "Death House clock is unstarted; prior house events and elapsed time are unknown. The GM has not confirmed the Main Hall's six-o'clock event."
    lines = [f"Death House reviewed state: {state.status}; dice {dice(state.remaining_pips)}; clock {clock_label(state.remaining_pips)}; {state.remaining_pips * 20} countdown minutes remain. Exploration clock running {state.status == 'exploring'}."]
    for event in state.events:
        lines.append(f"Death House event {event.id}: {event.action}; {event.status_before} → {event.status_after}; pips {event.pips_before} → {event.pips_after}; floor {event.floor or 'n/a'}; room {event.room or 'n/a'}; skill {event.skill or 'n/a'}; cause {event.early_trigger or 'n/a'}.")
        lines.append("Actual actors: " + "; ".join(f"{actor.name} [{actor.actor_id}]" for actor in event.actors) + ". GM evidence: " + (event.reason[:400] if guidance else event.reason))
        if event.chimes:
            lines.append("Clock chimes: " + ", ".join(event.chimes))
        lines.extend(event.reminders)
    lines.append(f"Death House source: {SOURCE} — Main Hall / Time in Death House; Ritual Chamber; Escape From Death House; Outside Death House.")
    if guidance:
        lines.append("Use the saved GM clock as authority. Do not infer newly entered floors, whole-room searches, rest completion, mound destruction, escape, XP or recruitment from prose. Use explicit Death House controls for those actual clock events. An active house prevents generic rest recovery; no long rest is available before actual escape.")
    return "\n".join(lines)
