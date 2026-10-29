"""Arc A's Durst children: actual consent, temporary abilities, remains and peace."""
from dungeonforge.campaign.strahd_death_house import SOURCE
from dungeonforge.rules.strahd_children_models import DurstChildrenEvent


ABILITIES = {"rose": ["Mending", "Light", "Shocking Grasp"], "thorn": ["Mage Hand"]}
SPIRIT_ACTIONS = {"consent_possession", "release_possession", "take_remains", "transfer_remains", "place_in_crypt", "retrieve_remains", "use_ability"}
INSIDE_ACTIONS = {"meet", "find_diary", "rose_bargain", "invite_children", "consent_possession", "take_remains", "place_in_crypt", "retrieve_remains"}
NOTES = [
    "Source: Reloaded Arc A, Children's Room; Family Crypts; Outside Death House. Older saves begin with these facts unreviewed, not with free NPC allies or reconstructed possessions.",
    "When Rose is actually convinced to reveal the basement entry, she points to the dollhouse and asks the party to take both children's bones and bury them outside. No DC is supplied; the GM reviews the actual conversation and promise.",
    "When the secret door is revealed Thorn asks if both children may accompany the party. A friendly player must permit possession. Each child has one recorded host; consent grants no permanent spell, class feature or extra character sheet.",
    "While actually possessed by Rose, a host can cast Mending, Light and Shocking Grasp. Thorn grants Mage Hand's effects as an action, without components, with an invisible spectral hand. Actual spell requirements, checks, attacks and effects still need their normal resolution.",
    "Rose's diary is an actual discovery, not a prerequisite invented for her possession ability and not an automatic permanent addition to known spells. Its contents concern her studies, friends, Thorn, Miss Klara and her parents' arguments; she does not know what those arguments were about.",
    "The quest ledger tracks each actual set of remains and its carrier separately. Putting either child's remains into the dungeon coffin does not bring peace. The children find those crypts distressing and prefer to leave.",
    "Actual house exit ends any recorded possessions. Children actually invited along can offer to watch the woods during rest; they refuse to proceed farther into Barovia and ask for burial. Only the GM-confirmed burial of both sets of carried remains outside releases them.",
    "This procedure awards no XP, heals nobody, creates no combatants and changes no permanent spells or class resources. It adds no generic companion sheet or invented spirit statistics.",
]


def people(session):
    return {person.id: person for person in [session.character, *session.character.companions]}


def facts(state):
    return state.model_dump(exclude={"events"})


def available_host(person):
    blocked = {"unconscious", "incapacitated", "paralyzed", "petrified", "stunned", "dead"}
    return person.current_hp > 0 and not blocked.intersection(condition.lower() for condition in getattr(person, "conditions", []))


def view(session):
    state = session.strahd_progress.children
    members = people(session)
    escaped = session.strahd_progress.death_house.status == "escaped"
    permissions = []
    for spirit in state.spirits:
        host = members.get(spirit.host_id)
        active = bool(host and not escaped and not state.at_peace and available_host(host))
        if spirit.host_id:
            permissions.append({"spirit": spirit.id, "host_id": spirit.host_id, "host_name": spirit.host_name,
                "active": active, "abilities": ABILITIES[spirit.id] if active else [],
                "note": "As an action, without components; the spectral hand is invisible." if spirit.id == "thorn" else "Temporary cantrip permission during this possession; normal spell resolution still applies.",
                "unavailable_reason": None if active else "The saved host is absent or incapacitated, the party exited, or the children are at peace."})
    return {**state.model_dump(), "permissions": permissions, "house_status": session.strahd_progress.death_house.status,
        "source_path": SOURCE, "rules": NOTES, "ability_catalog": ABILITIES}


def apply(session, req):
    state = session.strahd_progress.children
    members = people(session)
    person = members.get(req.actor_id)
    if not person or person.d6 is not None:
        raise ValueError("Select an actual 5e party actor for this decision, host or remains carrier.")
    if not req.actual_event_confirmed or not req.reason.strip():
        raise ValueError("The GM must confirm the actual event and record its evidence.")
    if req.event_id.startswith("system_") or any(event.id == req.event_id for event in state.events):
        raise ValueError("Use a new event ID; recorded events cannot be charged or granted twice, and system IDs are reserved.")
    if state.at_peace:
        raise ValueError("Both children have found peace. Their possessions and source quest cannot be restarted or reclaimed.")
    if req.action in SPIRIT_ACTIONS and req.spirit is None:
        raise ValueError("Select the actual child spirit or set of remains.")
    if req.action not in SPIRIT_ACTIONS and req.spirit is not None:
        raise ValueError("This shared children event does not accept an individual spirit.")
    if req.action != "use_ability" and (req.spell is not None or req.spell_requirements_confirmed):
        raise ValueError("Only a temporary ability use accepts a spell and its normal requirements review.")
    if req.action != "rose_bargain" and req.burial_promise_confirmed:
        raise ValueError("A burial promise belongs to Rose's actual bargain.")
    if req.action not in {"invite_children", "consent_possession"} and req.friendly_host_confirmed:
        raise ValueError("Friendliness is reviewed for an invitation or consensual possession.")
    if req.action != "consent_possession" and req.host_consent_confirmed:
        raise ValueError("Host consent belongs to an actual possession review.")
    if req.action != "consent_possession" and req.player_host_confirmed:
        raise ValueError("Actual player-host confirmation belongs to a possession review.")
    if req.action in INSIDE_ACTIONS and session.strahd_progress.death_house.status == "escaped":
        raise ValueError("The house has already collapsed after the reviewed exit. Its inside discoveries and possessions cannot be newly claimed now.")
    if req.action != "meet" and not state.met:
        raise ValueError("Review the actual meeting in the Children's Room before claiming their bargain, aid or remains.")
    spirit = next((item for item in state.spirits if item.id == req.spirit), None)
    before, effects = facts(state), []
    if req.action == "meet":
        if state.met:
            raise ValueError("The actual first meeting is already recorded.")
        state.met = True
        effects.append("The actual meeting with Rose and Thorn in the Children's Room is recorded. No bargain, diary, remains or possession is inferred.")
    elif req.action == "find_diary":
        if state.diary_found:
            raise ValueError("Rose's diary has already been found and recorded; it is not a second spell reward.")
        state.diary_found, state.diary_holder_id, state.diary_holder_name = True, person.id, person.name
        effects.append("Rose's actual diary discovery and holder recorded. It contains Mending, Light and Shocking Grasp; no spell is permanently learned.")
    elif req.action == "rose_bargain":
        if state.secret_revealed or not req.burial_promise_confirmed:
            raise ValueError("Confirm the actual agreement to take and bury both children's bones; Rose's entry revelation is recorded once.")
        state.secret_revealed, state.burial_promised = True, True
        effects.append("Rose actually revealed the secret basement entry through the dollhouse after the reviewed conversation and burial promise. The stairs, amber lock and dungeon entry still need actual resolution.")
    elif req.action == "invite_children":
        if not state.secret_revealed or state.invited or not req.friendly_host_confirmed:
            raise ValueError("After Rose reveals the entry, review the actual friendly invitation for both children. It is recorded once and does not presume host consent.")
        state.invited = True
        effects.append("The party actually invited Rose and Thorn to accompany them. They are story allies, without invented generic companion statistics. No possession has been imposed.")
    elif req.action == "consent_possession":
        if not state.invited or spirit.host_id is not None or not req.friendly_host_confirmed or not req.player_host_confirmed or not req.host_consent_confirmed or not available_host(person):
            raise ValueError("A friendly, available actual host must explicitly permit this invited child's possession; release any existing host first.")
        spirit.host_id, spirit.host_name = person.id, person.name
        effects.append(f"{person.name} is the GM-confirmed actual friendly player-controlled host and explicitly permitted {spirit.name}'s possession. Temporary permission: {', '.join(ABILITIES[spirit.id])}. Permanent spells, slots, class features and player control are unchanged.")
        if spirit.id == "thorn":
            effects.append("Thorn's Mage Hand effect takes an action, uses no components and creates an invisible spectral hand; its actual effect needs normal GM resolution.")
    elif req.action == "release_possession":
        if spirit.host_id is None:
            raise ValueError("This child has no recorded possession to release.")
        effects.append(f"GM confirms {spirit.name}'s actual possession of {spirit.host_name} ended; temporary permission is removed.")
        spirit.host_id, spirit.host_name = None, None
    elif req.action in {"take_remains", "retrieve_remains", "transfer_remains", "place_in_crypt"}:
        expected = {"take_remains": "unreviewed", "retrieve_remains": "family_crypt", "transfer_remains": "carried", "place_in_crypt": "carried"}[req.action]
        if spirit.remains_location != expected:
            raise ValueError("Review the actual current set of remains and location; it cannot be copied, taken twice or retrieved from an unrecorded crypt.")
        if req.action == "transfer_remains" and (spirit.carrier_id == person.id or spirit.carrier_id not in members):
            raise ValueError("An actual handoff needs a different present party carrier and the existing carrier still present.")
        if req.action == "place_in_crypt":
            if spirit.carrier_id != person.id:
                raise ValueError("The actual recorded carrier must review placing these remains into their family crypt.")
            spirit.remains_location, spirit.carrier_id, spirit.carrier_name = "family_crypt", None, None
            effects.append(f"{spirit.name}'s remains placed in the family crypt. This does NOT bring peace, release possession or complete the promised outside burial.")
        else:
            spirit.remains_location, spirit.carrier_id, spirit.carrier_name = "carried", person.id, person.name
            effects.append(f"One actual set of {spirit.name}'s remains is now carried by {person.name}. The quest ledger retains its identity; it is not an extra inventory reward.")
    elif req.action == "use_ability":
        if spirit.host_id != person.id or not available_host(person) or req.spell not in ABILITIES[spirit.id] or not req.spell_requirements_confirmed:
            raise ValueError("Only this child's current available actual host can use a listed temporary ability after reviewing its normal spell requirements and effects.")
        if session.strahd_progress.death_house.status == "escaped":
            raise ValueError("House exit ends possessions; no temporary spirit casting remains available.")
        effects.append(f"GM reviewed {person.name}'s actual use of {req.spell} through {spirit.name}. Actual range, time, components when required, attacks and effects were separately resolved; this ledger applies no automatic spell effect or slot cost.")
    elif req.action == "bury_children":
        if session.strahd_progress.death_house.status != "escaped":
            raise ValueError("Outside burial requires an actual reviewed exit from Death House; dungeon coffins do not satisfy it.")
        if any(item.remains_location != "carried" or item.carrier_id not in members for item in state.spirits):
            raise ValueError("Both actual sets of remains must be carried by present party actors before the GM confirms their outside burial.")
        for item in state.spirits:
            item.remains_location, item.carrier_id, item.carrier_name = "buried_outside", None, None
            item.host_id, item.host_name = None, None
        state.at_peace, state.invited = True, False
        effects.append("The GM confirms both children's remains were actually buried outside after escape. Rose and Thorn thank the party and vanish; possessions and temporary permissions are ended. No XP or class reward is added.")
    elif req.action == "leave_children":
        if session.strahd_progress.death_house.status != "escaped" or not state.invited:
            raise ValueError("Review an actual departure without burial only for invited children after the actual house exit.")
        state.invited = False
        effects.append("The party actually departed without completing the outside burial. The children refuse to proceed farther into Barovia; they have not found peace, and the promised burial remains unresolved.")
    event = DurstChildrenEvent(id=req.event_id, action=req.action, actor_id=person.id, actor_name=person.name,
        spirit=req.spirit, spell=req.spell, reason=req.reason.strip(), source_path=SOURCE,
        effects=effects, before=before, after=facts(state), confirmations={field: getattr(req, field) for field in
            ("actual_event_confirmed", "burial_promise_confirmed", "friendly_host_confirmed", "player_host_confirmed", "host_consent_confirmed", "spell_requirements_confirmed")})
    state.events.append(event)
    return event


def on_house_exit(session, clock_event):
    """The source explicitly ends existing possessions at the actual reviewed exit."""
    state = session.strahd_progress.children
    hosts = [item for item in state.spirits if item.host_id]
    if not hosts:
        return
    before = facts(state)
    effects = [f"Actual house exit ends {item.name}'s recorded possession of {item.host_name}; temporary abilities end." for item in hosts]
    for item in hosts:
        item.host_id, item.host_name = None, None
    state.events.append(DurstChildrenEvent(id=f"system_exit_{clock_event.id}", action="house_exit",
        reason=f"Automatic source consequence of the GM-confirmed actual exit {clock_event.id}: {clock_event.reason}",
        source_path=SOURCE, effects=effects, before=before, after=facts(state), confirmations={"actual_house_exit_source_consequence": True}))


def summary(session, *, guidance=True):
    state = session.strahd_progress.children
    if not state.events:
        return "Durst children: meeting, bargain, consent, temporary abilities, remains and burial are unreviewed; no spirit ally or possession is assumed."
    lines = [f"Durst children reviewed quest: met {state.met}; diary found {state.diary_found}; secret entry revealed {state.secret_revealed}; burial promised {state.burial_promised}; invited story allies {state.invited}; at peace {state.at_peace}."]
    for spirit in state.spirits:
        lines.append(f"{spirit.name}: host {spirit.host_name or 'none'} [{spirit.host_id or 'none'}]; remains {spirit.remains_location}; carrier {spirit.carrier_name or 'none'} [{spirit.carrier_id or 'none'}].")
    for permission in view(session)["permissions"]:
        lines.append(f"Temporary source permission for {permission['host_name']}: active {permission['active']}; {', '.join(permission['abilities']) or 'none currently available'}. {permission['note']}")
    for event in state.events:
        lines.append(f"Durst event {event.id}: {event.action}; actual actor {event.actor_name or 'source exit consequence'} [{event.actor_id or 'n/a'}]; spirit {event.spirit or 'both / shared'}; spell {event.spell or 'n/a'}. GM evidence: " + (event.reason[:400] if guidance else event.reason))
        lines.extend(event.effects)
    lines.append(f"Durst children source: {SOURCE} — Children's Room; Family Crypts; Outside Death House.")
    if guidance:
        lines.append("Only recorded actual consent supplies temporary spirit abilities. Do not invent hosts, permanent spells, remains, recruitment, peace or XP. Dungeon coffins cannot release the children. Invited children will not proceed farther into Barovia until their actual remains receive the requested outside burial; source house exit ends possessions. Normal spell resolution is separate from this GM event ledger.")
    return "\n".join(lines)
