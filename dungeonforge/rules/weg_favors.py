"""Rare GM Favors are spent Dark Side FP, never an ordinary renewable balance."""
import time

from dungeonforge.rules import weg_dark_side as dark
from dungeonforge.rules.weg_d6 import WEGD6Rules
from dungeonforge.rules.weg_favor_models import DarkSideFavor
from dungeonforge.rules.weg_rewards import expenditure


SOURCE = "WEG40055 (1992), PDF p.54 / printed p.57, Favors."
NOTES = [
    "A very few individuals receive rare free offers: very powerful evil characters, or someone the Dark Side is actively and desperately recruiting. The GM must confirm the actual eligibility and exceptional moment. These are not routine point awards.",
    "Offering, declining or withdrawing an unused favor adds no DSP and grants no held FP. A unique offer can be used once; its moment key remains reserved after use, decline or withdrawal.",
    "Use treats the free point like the point granted by a Dark Side call: spend it immediately as the round's Dark Side boost. A new DSP is awarded no matter how it is used; only the existing plain corruption check decides a new fall. Already-consumed characters receive their normal +1 CP for a new DSP.",
    "The favor requires no call skill roll, call action, difficulty escalation or failed-call demand. The actual call counter and actions taken are unchanged. The shared Dark Side round marker enforces the same CP exclusion and one Dark Side point per round.",
    "Declare before actions and defenses. Personal pools double; equipment remains fixed. One separately spent normal FP may combine with the Dark Side point under the existing ×4 stacking convention. No point is added to the ordinary FP balance.",
    "Use requires the original actual actor, adventure and scene/encounter, with GM confirmation that the offered moment still applies. This preserves a situational offer rather than banking a transferable point. No numerical rarity cooldown is invented.",
    "A prior spent scene round must be advanced explicitly through the whole-scene Force time control. This action never silently resets a single actor, advances a fleet clock, or skips a pending navigation emergency or exclusive task.",
    "Only full native party, active personal opponents or eligible crew sheets can receive/use these boosts. Instructor summary records support moral rulings, not action pools.",
]


def scope(session):
    if session.vehicle_encounter and session.vehicle_encounter.active:
        return "vehicle", session.vehicle_encounter.id
    if session.encounter and session.encounter.active:
        return "personal", session.encounter.id
    return "scene", session.id


def same_scope(session, offer):
    return (offer.scope_kind, offer.scope_id) == scope(session) and offer.adventure == session.d6_advancement.adventure


def full_actor(session, actor_id, *, declaration=True):
    from dungeonforge.game import weg_dark_side as world, weg_force as force
    person = world.actor(session, actor_id)
    if person.kind == "instructor":
        raise ValueError("Use a full native party, encounter or crew sheet; an instructor summary has no favor action pool.")
    actual = force.actor(session, actor_id)
    if declaration and session.vehicle_encounter:
        from dungeonforge.game.weg_vehicle_combat import find_actor, eligible
        if not session.vehicle_encounter.active:
            raise ValueError("End the completed craft encounter before reviewing a new scene offer.")
        craft, crew = find_actor(session.vehicle_encounter, actual.id)
        if not eligible(craft, crew) or crew.evacuated:
            raise ValueError("Select an actual eligible, occupied crew station on an operational craft.")
    elif declaration and session.encounter and session.encounter.active:
        if not any(member.id == actual.id and member.d6 is not None for member in session.encounter.combatants):
            raise ValueError("The favored actor must actually be present in this encounter.")
    elif declaration and person.kind != "party":
        raise ValueError("An encounter-only actor needs a current active encounter.")
    return actual


def offer(session, req):
    from dungeonforge.game.weg_dark_side import actors
    person = full_actor(session, req.actor_id)
    state = person.state
    if state.wound == "dead" or state.corruption.dead:
        raise ValueError("A dead actor cannot receive a new Dark Side favor.")
    if not req.gm_rare_offer_confirmed or not req.reason.strip() or not req.moment_key.strip():
        raise ValueError("The GM must confirm an exceptional rare offer, actual eligibility, unique moment and reason.")
    if any(item.id == req.offer_id for actor in actors(session).values() for item in actor.state.corruption.favors):
        raise ValueError("This rare offer ID has already been recorded; it cannot grant another free point.")
    if any(item.moment_key.casefold() == req.moment_key.strip().casefold() for item in state.corruption.favors):
        raise ValueError("This actor's actual moment was already reviewed. Used, declined and withdrawn moments cannot be farmed or reopened.")
    if any(item.status == "offered" for item in state.corruption.favors):
        raise ValueError("Resolve the existing outstanding rare offer before the GM records another exceptional moment.")
    kind, id = scope(session)
    item = DarkSideFavor(id=req.offer_id, actor_id=person.id, actor_name=person.name,
        moment_key=req.moment_key.strip(), eligibility=req.eligibility, gm_rare_offer_confirmed=True,
        offer_reason=req.reason.strip(), adventure=session.d6_advancement.adventure, scope_kind=kind, scope_id=id)
    state.corruption.favors.append(item)
    return item


def validate_use(session, person, item, req):
    from dungeonforge.game.weg_navigation import require_resolved
    from dungeonforge.game.weg_task_guards import require_available
    require_resolved(session)
    require_available(session, person.id)
    state, round_state = person.state, person.state.round_state
    if not same_scope(session, item) or not req.current_moment_confirmed or not req.consequence_accepted:
        raise ValueError("Confirm that this original actor's offered moment still applies in its original adventure and scene/encounter, and accept the automatic DSP consequence.")
    if state.wound == "dead" or state.corruption.dead or not state.can_take_turn:
        raise ValueError("The favored actor must be alive, conscious and able to declare an action.")
    if state.corruption.pending_demand or state.force.attempt:
        raise ValueError("Settle the existing Dark Side demand or pending Force activation before favor use.")
    if round_state.dark_side_called or round_state.dark_side_active:
        raise ValueError("A Dark Side call or favor was already used in this round. One Dark Side boost per round; advance the shared round before another.")
    if round_state.actions_taken or round_state.character_points_spent or round_state.full_defense or round_state.defense_skill:
        raise ValueError("Declare the favor before actions, defenses and CP spending. Advance the shared scene/combat round explicitly when the prior round is spent.")
    if session.vehicle_encounter and session.vehicle_encounter.actions_started:
        raise ValueError("Declare favor use before craft actions or defenses begin.")
    if session.encounter and session.encounter.active and session.encounter.d6_actions_started:
        raise ValueError("Declare favor use before personal encounter actions or defenses begin.")
    if req.force_point and round_state.force_active:
        raise ValueError("A normal Force Point was already declared; do not spend it twice.")
    if req.force_point and state.force_points < 1:
        raise ValueError("No ordinary Force Points remain for the separately requested normal FP.")


def resolve(session, req):
    person = full_actor(session, req.actor_id, declaration=False)
    state = person.state
    item = next((item for item in state.corruption.favors if item.id == req.offer_id and item.actor_id == person.id), None)
    if not item or item.status != "offered":
        raise ValueError("Select this actual actor's still-unused rare offer. A resolved or another actor's favor cannot be used again.")
    if not req.reason.strip():
        raise ValueError("Record the actual decision and intention for this offer.")
    if req.action != "use":
        if req.force_point or req.current_moment_confirmed or req.consequence_accepted:
            raise ValueError("Decline or withdrawal does not declare any point spending or DSP consequence.")
        item.status = "declined" if req.action == "decline" else "withdrawn"
    else:
        person = full_actor(session, req.actor_id)
        validate_use(session, person, item, req)
        if state.round_state.force_active:
            state.round_state.declared_actions = req.actions
        else:
            WEGD6Rules.declare(state, req.actions, req.force_point)
        event = dark.gain_point(state, f"Used rare Dark Side favor {item.id} at '{item.moment_key}': {req.reason.strip()}", "dark_side_favor")
        # Existing point guards, scene declarations and Force components all use
        # this shared Dark Side marker. No call attempt/action is performed.
        state.round_state.dark_side_called = True
        state.round_state.dark_side_active = True
        spent = expenditure(state, "dark_side_favor")
        spent.adventure, spent.corruption_event_id = session.d6_advancement.adventure, event.id
        item.status = "used"
        item.current_moment_confirmed, item.consequence_accepted = True, True
        item.used_clock = state.force.elapsed_rounds
        combat = session.vehicle_encounter or (session.encounter if session.encounter and session.encounter.active else None)
        item.used_round = combat.round if combat else None
        item.actions_declared, item.normal_force_point_spent = req.actions, req.force_point
        item.corruption_event_id, item.expenditure_id = event.id, spent.id
    item.resolution_reason, item.resolved_at = req.reason.strip(), time.time()
    return item


def summary(state, name, *, guidance=True):
    if not state.corruption.favors:
        return ""
    lines = [f"### RARE DARK SIDE FAVORS — {name}"]
    for item in state.corruption.favors:
        lines.append(f"Favor {item.id}: {item.status}; actual actor {item.actor_name} [{item.actor_id}]; adventure {item.adventure}; {item.scope_kind} [{item.scope_id}]; actual rare moment {item.moment_key}; eligibility {item.eligibility}; GM rare offer confirmed {item.gm_rare_offer_confirmed}.")
        lines.append("GM offer reason: " + (item.offer_reason[:400] if guidance else item.offer_reason))
        if item.resolution_reason:
            lines.append("Actual decision: " + (item.resolution_reason[:400] if guidance else item.resolution_reason))
        if item.status == "used":
            lines.append(f"Immediate Dark Side FP boost used; +1 DSP already recorded by event {item.corruption_event_id}; expenditure {item.expenditure_id} source dark_side_favor; actual round {item.used_round}, personal clock {item.used_clock}; {item.actions_declared} declared actions, zero call actions consumed; separate normal FP spent {item.normal_force_point_spent}. No ordinary FP was granted by the favor.")
        else:
            lines.append("Unused offer: no FP balance granted and no DSP penalty.")
        lines.append(item.source)
    if guidance:
        lines.append("A favor is a rare explicit GM offer, never an automatic point award or renewable reserve. Do not fabricate, duplicate, reopen, transfer or bank one. Only explicit use awards its DSP and immediate round boost; only the plain corruption check determines a new fall. Respect the recorded actual moment/scope and spent/declined/withdrawn outcomes.")
    return "\n".join(lines)
