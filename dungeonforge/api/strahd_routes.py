"""Explicit, stale-safe GM review of Reloaded progress and per-PC milestone XP."""
import time
import uuid
from functools import wraps
from threading import RLock

from fastapi import APIRouter, HTTPException

from dungeonforge.campaign import strahd_progress as rules
from dungeonforge.campaign.strahd import ACTS, ARCS
from dungeonforge.context.pipeline import ActionTurn
from dungeonforge.rules.base import RuleEvaluationResult
from dungeonforge.rules.dice import RollResult
from dungeonforge.rules.strahd_models import DeathHouseRequest, StrahdArcRequest, StrahdMilestoneRequest, StrahdRegisterRequest
from dungeonforge.rules.strahd_children_models import DurstChildrenRequest


router = APIRouter(prefix="/api/strahd/progress", tags=["Reloaded GM progress and milestone XP"])
_PROGRESS_LOCK = RLock()


def serialized(fn):
    """Two rapid reward requests must review sequential committed ledger versions."""
    @wraps(fn)
    def action(*args, **kwargs):
        with _PROGRESS_LOCK:
            return fn(*args, **kwargs)
    return action


def strahd_session():
    from dungeonforge.api import routes
    session = routes._ACTIVE_SESSION
    if session.edition != "5e" or not ("strahd" in session.source_folders or session.id == "session_strahd"):
        raise HTTPException(status_code=409, detail="Select a 5e Curse of Strahd Reloaded adventure before reviewing its milestones.")
    return session


def working(req):
    original = strahd_session()
    if (original.encounter and original.encounter.active) or original.vehicle_encounter:
        raise ValueError("Finish the active encounter before reviewing campaign rewards or progress.")
    if req.expected_updated_at != original.updated_at:
        raise ValueError("The adventure changed after this review; refresh the current PC roster, XP and source milestone.")
    return original, original.model_copy(deep=True)


def commit(original, session, summary, changes, label, *, procedure="GM milestone review", breakdown="Explicit source-backed GM review; no skill roll or automatic XP."):
    if original.updated_at != session.updated_at:
        raise ValueError("The adventure changed during this review; refresh before committing XP or progress.")
    result = RuleEvaluationResult(action_type="campaign_progress", success=True,
        roll_result=RollResult(expression=procedure, dice_count=0, die_type=6, total=0,
            system="5e", breakdown=breakdown),
        summary="[Reloaded Progress] " + summary, state_changes=changes)
    turn = ActionTurn(id=f"strahd_{uuid.uuid4().hex}", mode="story", player_input=label,
        dm_output=result.summary, rule_result=result, timestamp=time.time())
    session.history.append(turn)
    session.undone_history.clear()
    session.updated_at = max(time.time(), original.updated_at + 0.000001)
    for field in type(original).model_fields:
        setattr(original, field, getattr(session, field))
    return {"session": original, "turn": turn, "eval_result": result}


@router.get("/state")
@serialized
def state():
    session = strahd_session()
    accounts = {record.actor_id: record for record in session.strahd_progress.accounts}
    claimed = {record.milestone_id: record.id for record in session.strahd_progress.awards}
    actors = []
    for person in rules.people(session).values():
        account = accounts.get(person.id)
        total = account.baseline_xp + account.awarded_xp if account else None
        target = rules.xp_level(total) if total is not None else None
        actors.append({"id": person.id, "name": person.name, "sheet_level": person.level,
            "registered": account is not None, "baseline_xp": account.baseline_xp if account else None,
            "awarded_xp": account.awarded_xp if account else None, "total_xp": total,
            "xp_level": target, "level_up_pending": target is not None and target > person.level})
    latest = {record.arc: record for record in session.strahd_progress.arc_reviews}
    return {"updated_at": session.updated_at, "progress": session.strahd_progress, "actors": actors,
        "catalog": [{**item.model_dump(), "claimed": item.id in claimed, "award_id": claimed.get(item.id),
            "prerequisites_met": not (set(item.prerequisite_ids) - set(claimed))} for item in rules.CATALOG],
        "arcs": [{"id": letter, "title": title, "act": ACTS[act - 1],
            "status": latest[letter].status if letter in latest else "unreviewed",
            "reason": latest[letter].reason if letter in latest else None} for letter, title, act in ARCS],
        "rules": {"notes": rules.NOTES, "xp_source": rules.XP_SOURCE,
            "xp_thresholds": [{"level": index + 1, "xp": xp} for index, xp in enumerate(rules.XP_THRESHOLDS)]}}


@router.post("/register")
@serialized
def register(req: StrahdRegisterRequest):
    try:
        original, session = working(req)
        records = rules.register(session, req)
        summary = "; ".join(f"{record.name}: reviewed baseline {record.baseline_xp} XP" for record in records)
        return commit(original, session, summary + ". No old milestones or class levels were inferred.",
            {"strahd_accounts": [record.model_dump() for record in records]}, "Enroll actual player characters for milestone XP")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/quote")
@serialized
def quote(req: StrahdMilestoneRequest):
    try:
        _, session = working(req)
        return {"quote": rules.award(session, req)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/award")
@serialized
def award(req: StrahdMilestoneRequest):
    try:
        original, session = working(req)
        record = rules.award(session, req)
        allocations = "; ".join(f"{item.name}: +{item.xp} XP, total {item.total_xp}, XP level {item.xp_level}, sheet level {item.sheet_level}"
            + (" (level-up sheet review pending)" if item.level_up_pending else "") for item in record.allocations)
        return commit(original, session, f"{record.title}. {allocations}. Character sheets, resources and scene time are unchanged. GM review: {record.reason}",
            {"strahd_award": record.model_dump()}, "Review and award source milestone XP")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/arc")
@serialized
def arc(req: StrahdArcRequest):
    try:
        original, session = working(req)
        record = rules.review_arc(session, req)
        return commit(original, session, f"GM records Arc {record.arc}: {record.status}. {record.reason}. This progress review awards no XP.",
            {"strahd_arc_review": record.model_dump()}, "Review actual campaign arc progress")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/death-house/state")
@serialized
def death_house_state():
    from dungeonforge.campaign.strahd_death_house import view
    session = strahd_session()
    return {"updated_at": session.updated_at, "clock": view(session),
        "actors": [{"id": actor.id, "name": actor.name} for actor in rules.people(session).values()]}


@router.post("/death-house/quote")
@serialized
def death_house_quote(req: DeathHouseRequest):
    from dungeonforge.campaign.strahd_death_house import apply, view
    try:
        _, session = working(req)
        event = apply(session, req)
        return {"event": event, "clock": view(session)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/death-house/event")
@serialized
def death_house_event(req: DeathHouseRequest):
    from dungeonforge.campaign.strahd_death_house import apply, clock_label
    try:
        original, session = working(req)
        event = apply(session, req)
        summary = (f"Death House {event.action.replace('_', ' ')}: {event.status_before} → {event.status_after}; "
            f"pips {event.pips_before} → {event.pips_after}; clock {clock_label(event.pips_after)}. "
            + ("Chimes: " + ", ".join(event.chimes) + ". " if event.chimes else "")
            + " ".join(event.reminders) + f" GM evidence: {event.reason}")
        return commit(original, session, summary, {"strahd_death_house_event": event.model_dump()},
            "GM reviews actual Death House event", procedure="GM Death House clock review",
            breakdown="Source dice-clock procedure; no encounter, recovery, XP or escape outcome is inferred.")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/children/state")
@serialized
def children_state():
    from dungeonforge.campaign.strahd_children import view
    session = strahd_session()
    return {"updated_at": session.updated_at, "children": view(session),
        "actors": [{"id": actor.id, "name": actor.name} for actor in rules.people(session).values()]}


@router.post("/children/quote")
@serialized
def children_quote(req: DurstChildrenRequest):
    from dungeonforge.campaign.strahd_children import apply, view
    try:
        _, session = working(req)
        event = apply(session, req)
        return {"event": event, "children": view(session)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/children/event")
@serialized
def children_event(req: DurstChildrenRequest):
    from dungeonforge.campaign.strahd_children import apply
    try:
        original, session = working(req)
        event = apply(session, req)
        summary = f"Durst children: {event.action.replace('_', ' ')}. " + " ".join(event.effects) + f" GM evidence: {event.reason}"
        return commit(original, session, summary, {"strahd_children_event": event.model_dump()},
            "GM reviews actual Durst children event", procedure="GM Durst children review",
            breakdown="Actual source conversation, consent, ability or remains review; no permanent spell or automatic XP reward.")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
