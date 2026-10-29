"""Explicit GM moral rulings, automatic corruption checks and saved redemption."""
from fastapi import APIRouter, HTTPException

from dungeonforge.api.weg_routes import native_session
from dungeonforge.api.weg_force_routes import commit
from dungeonforge.game import weg_dark_side as world, weg_force as force_world
from dungeonforge.rules import weg_dark_side as rules
from dungeonforge.rules import weg_force_effects as effects
from dungeonforge.rules.base import RuleEvaluationResult
from dungeonforge.rules.weg_force import empty_roll
from dungeonforge.rules.weg_dark_models import (
    AtonementRequest, CorruptionEvent, DarkAwardRequest, DarkBeliefRequest,
    DarkCallRequest, DarkCorrectionRequest, DarkDemandRequest, DarkRedemptionRequest,
)

router = APIRouter(prefix="/api/weg-d6/dark-side", tags=["Native WEG Dark Side and atonement"])


def working():
    original = native_session()
    session = original.model_copy(deep=True)
    world.synchronize(session)
    return original, session


def downtime(session):
    if (session.encounter and session.encounter.active) or session.vehicle_encounter:
        raise ValueError("Record atonement, belief changes and GM corrections outside an encounter.")


def outcome(summary, roll=None, **options):
    return RuleEvaluationResult(action_type="dark_side", success=True, roll_result=roll or empty_roll("GM moral ruling"), summary=f"[WEG D6 Dark Side] {summary}", **options)


def require_alive(state):
    if state.corruption.dead or getattr(state, "wound", None) == "dead":
        raise ValueError("A dead character cannot undertake this action.")


@router.get("/state")
def state():
    session = native_session()
    world.synchronize(session)
    return {"adventure": session.d6_advancement.adventure, "actors": [{
        "id": person.id, "name": person.name, "kind": person.kind,
        "dark_side_points": person.state.dark_side_points, "consumed": rules.fallen(person.state),
        "force_sensitive": getattr(person.state, "force_sensitive", any(rules.parse_code(code)[0] for code in person.state.force_skills.values())),
        "character_points": person.state.character_points, "force_points": person.state.force_points,
        "attributes": person.state.attributes, "force_skills": person.state.force_skills,
        "corruption": person.state.corruption,
        "round_state": getattr(person.state, "round_state", None),
        "wound": getattr(person.state, "wound", "dead" if person.state.corruption.dead else "healthy"),
    } for person in world.actors(session).values()], "source": "WEG40055 (1992), printed pp.15, 56–58, 140",
        "notes": ["Corruption, demands and doubt use plain 1D6, without a Wild Die or point bonuses.", "Calls take one declared Control/Perception action before the action phase. Success spends the granted FP immediately; it is never stored.", "For the additional FP explicitly permitted by the book, each spent point doubles personal pools (normal + Dark Side = ×4); equipment stays fixed. Stacking arithmetic is an explicit engine convention.", "The next difficulty after Heroic is not numerically specified; calls beyond the listed bands require GM adjudication.", "A drain that leaves no whole die, including 0D+1/+2, is treated as the book's fatal 0D result. Only the chosen attribute/Force skill is drained.", "Atonement needs two consecutive completed adventures with explicit GM approval. A rejected adventure restarts the count; a new DSP interrupts the cycle.", "Fallen heroes default to GM control. A GM-approved redemption arc has a maximum three-adventure deadline; expiry makes the NPC status permanent.", "Moral judgments, actual confrontations and heroic sacrifices are GM rulings. No R&E per-DSP temptation bonus dice are added."]}


@router.post("/award")
def award(req: DarkAwardRequest):
    original, session = working()
    try:
        world.require_reason(req.reason)
        person = world.actor(session, req.actor_id)
        state = person.state
        require_alive(state)
        trained = any(rules.parse_code(value)[0] for value in state.force_skills.values())
        sensitive = getattr(state, "force_sensitive", trained)
        if req.cause == "temptation":
            if not state.corruption.atonement:
                raise ValueError("The temptation ruling applies to a character currently attempting atonement.")
        elif not req.player_warned:
            raise ValueError("The book requires a player warning and an opportunity to change the action before this ordinary GM award.")
        if req.cause == "inaction" and not trained:
            raise ValueError("The Jedi duty to intervene requires Force training; use the appropriate evil-action ruling for other characters.")
        if req.cause == "evil_act" and not (sensitive or trained or rules.fallen(state)):
            raise ValueError("Ordinary non-sensitive characters gain this DSP for evil while spending a Force Point, not every evil act.")
        rules.gain_point(state, req.reason.strip(), req.cause)
        result = outcome("GM records the moral consequence." + (" Evil while spending an FP: that spent point is not eligible for return; no extra FP is deducted here." if req.cause == "evil_force_point" else ""))
        return commit(original, session, result, f"{person.name}: Dark Side Point", boost=False)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/call")
def call(req: DarkCallRequest):
    original, session = working()
    try:
        world.require_reason(req.intention)
        person = world.actor(session, req.actor_id)
        if person.kind == "instructor":
            raise ValueError("Use a full native encounter sheet for an instructor's action rolls; the instructor record supports moral rulings and atonement.")
        state = person.state
        require_alive(state)
        if state.corruption.pending_demand:
            raise ValueError("Settle the previous Dark Side demand before another call.")
        combat = session.vehicle_encounter or (session.encounter if session.encounter and session.encounter.active else None)
        if session.vehicle_encounter and not session.vehicle_encounter.active:
            raise ValueError("End the completed craft encounter before a new scene call.")
        if combat:
            started = combat.actions_started if session.vehicle_encounter else combat.d6_actions_started
            if started:
                raise ValueError("Call on the Dark Side during declarations, before attacks, actions or defenses.")
        elif state.round_state.actions_taken or state.round_state.dark_side_called or state.round_state.character_points_spent:
            force_world.advance_scene(session, 1)
        extra = 0
        if session.vehicle_encounter:
            from dungeonforge.game.weg_vehicle_combat import find_actor, eligible
            craft, crew = find_actor(session.vehicle_encounter, person.id)
            if not eligible(craft, crew):
                raise ValueError("This craft/crew station cannot act.")
            extra = crew.control_penalty
        roll, difficulty, success, skill = rules.call(state, req, session.d6_advancement.adventure, extra)
        result = outcome(f"{person.name} calls with {skill}: {roll.breakdown} vs {difficulty} → {'SUCCESS: granted FP spent immediately for this round' if success else 'FAILED: no FP granted'}. One declared action used; no CP dice may be used this round.", roll)
        result.success, result.target_value = success, difficulty
        if state.corruption.pending_demand:
            result.summary += f" Dark Side demands {state.corruption.pending_demand.cp_loss} CP or 1D from a chosen attribute/Force skill. Resolve the saved demand before further actions."
            result.state_changes["dark_demand"] = state.corruption.pending_demand.model_dump()
        if session.vehicle_encounter:
            session.vehicle_encounter.boost = None
            session.vehicle_encounter.combat_log.append(result.summary)
        elif session.encounter and session.encounter.active:
            session.encounter.combat_log.append(result.summary)
        return commit(original, session, result, f"{person.name}: call upon the Dark Side", boost=False)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/pay-demand")
def pay_demand(req: DarkDemandRequest):
    original, session = working()
    try:
        person = world.actor(session, req.actor_id)
        note = rules.settle_demand(person.state, req.method, req.key)
        return commit(original, session, outcome(f"{person.name}: {note}"), "Resolve Dark Side demand", boost=False)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/atonement")
def atonement(req: AtonementRequest):
    original, session = working()
    try:
        downtime(session)
        world.require_reason(req.reason)
        person = world.actor(session, req.actor_id)
        note = rules.atone(person.state, req, session.d6_advancement.adventure)
        return commit(original, session, outcome(f"{person.name}: {note} GM record: {req.reason.strip()}"), f"{person.name}: atonement {req.action}", boost=False)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/redemption")
def redemption(req: DarkRedemptionRequest):
    original, session = working()
    try:
        world.require_reason(req.reason)
        person = world.actor(session, req.actor_id)
        state, dark = person.state, person.state.corruption
        if not rules.fallen(state) or dark.pending_demand or dark.dead:
            raise ValueError("Redemption requires a consumed character with no unsettled failed-call demand.")
        before = state.dark_side_points
        if req.action == "allow_arc":
            downtime(session)
            require_alive(state)
            if person.kind != "party" or dark.npc_permanent or dark.redemption_deadline is not None:
                raise ValueError("Only a fallen party hero without an expired/active arc can begin this player redemption arc.")
            deadline = (dark.fallen_adventure or session.d6_advancement.adventure) + req.adventures
            if session.d6_advancement.adventure >= deadline:
                raise ValueError("The requested redemption deadline has already passed.")
            dark.control_mode, dark.redemption_deadline = "redemption", deadline
            note = f"GM permits a player redemption arc until adventure boundary {deadline}. Expiry makes GM control permanent."
            result = outcome(note)
        else:
            jedi = world.actor(session, req.light_jedi_id) if req.light_jedi_id else None
            if jedi is None or jedi.id == person.id or rules.fallen(jedi.state) or rules.parse_code(jedi.state.force_skills.get("control", "0D"))[0] == 0:
                raise ValueError("Select another present Jedi of the Light with trained Control.")
            require_alive(jedi.state)
            if hasattr(jedi.state, "wound"):
                awake = ((jedi.state.wound in {"healthy", "wounded"} and jedi.state.unconscious_rounds == 0)
                    or effects.pain(jedi.state) or jedi.state.force.remain_pending or (jedi.state.force.remain_actions or 0) > 0)
                if effects.sleeping(jedi.state) or not awake:
                    raise ValueError("The confronting Jedi must be conscious and present.")
            if req.action == "moment_of_doubt":
                require_alive(state)
                key = req.confrontation_key.strip()
                if not key or key in dark.moment_keys:
                    raise ValueError("Record a new actual confrontation; each confrontation key may cause only one Moment of Doubt for this character.")
                die = rules.plain_die("Moment of Doubt")
                reduction = rules.parse_code(jedi.state.force_skills["control"])[0] + die.total
                state.dark_side_points = max(0, before - reduction)
                dark.moment_keys.append(key)
                note = f"{jedi.name} affirms the Light Side's power in confrontation '{key}': whole Control dice + plain 1D6 = {reduction}; DSP {before} → {state.dark_side_points}."
                if state.dark_side_points == 0:
                    note += " " + rules.redeem(state)
                result = outcome(note, die, state_changes={"doubt_reduction": reduction, "redeemed": not rules.fallen(state)})
            else:
                note = rules.redeem(state)
                if req.died:
                    if hasattr(state, "wound"):
                        state.wound = "dead"
                        effects.drop_on_injury(state)
                        state.force.remain_pending = False
                    else:
                        dark.dead = True
                    note += " The GM records death from the heroic sacrifice."
                result = outcome(f"Heroic sacrifice in {jedi.name}'s presence, risking certain death in defense of the innocent: {note}")
            dark.events.append(CorruptionEvent(source="redemption", reason=req.reason.strip(), before=before, after=state.dark_side_points))
        result.summary += " GM record: " + req.reason.strip()
        return commit(original, session, result, f"{person.name}: {req.action.replace('_', ' ')}", boost=False)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/belief")
def belief(req: DarkBeliefRequest):
    original, session = working()
    try:
        downtime(session)
        person = world.actor(session, req.actor_id)
        person.state.corruption.refuses_force = req.refuses_force
        return commit(original, session, outcome(f"{person.name}: GM records {'refusal to believe in the Force; Dark Side calls unavailable' if req.refuses_force else 'no refusal to believe in the Force'}."), "Force belief", boost=False)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/correction")
def correction(req: DarkCorrectionRequest):
    original, session = working()
    try:
        downtime(session)
        world.require_reason(req.reason)
        person = world.actor(session, req.actor_id)
        state = person.state
        if state.corruption.pending_demand or (req.consumed and req.points == 0) or (not req.consumed and req.points > 6):
            raise ValueError("Settle any demand first. Consumed characters need a positive DSP total; more than six DSP cannot remain unconsumed under the plain-die rule.")
        before, was_fallen = state.dark_side_points, rules.fallen(state)
        rules.invalidate_atonement(state)
        state.dark_side_points = req.points
        rules.set_fallen(state, req.consumed)
        if req.consumed and not was_fallen:
            state.corruption.control_mode = "gm"
            state.corruption.fallen_adventure = session.d6_advancement.adventure
        elif not req.consumed and was_fallen:
            state.corruption.control_mode = "gm" if state.corruption.npc_permanent or person.kind != "party" else "player"
            state.corruption.redemption_deadline = None
        state.corruption.events.append(CorruptionEvent(source="gm_correction", reason=f"Explicit legacy/GM correction, no retrospective dice or redemption toll: {req.reason.strip()}", before=before, after=req.points))
        return commit(original, session, outcome(f"{person.name}: GM corrects DSP/consumption state; held resources unchanged. Use the redemption procedure for actual redemption."), "GM corruption correction", boost=False)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
