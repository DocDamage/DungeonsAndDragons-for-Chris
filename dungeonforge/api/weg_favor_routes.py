"""Stale-safe explicit GM offers; accepting never deposits a banked Force Point."""
import time
from functools import wraps
from threading import RLock

from fastapi import APIRouter, HTTPException

from dungeonforge.game import weg_dark_side as dark_world, weg_force as force_world
from dungeonforge.rules import weg_favors as rules
from dungeonforge.rules.base import RuleEvaluationResult
from dungeonforge.rules.weg_favor_models import FavorOfferRequest, FavorResolveRequest
from dungeonforge.rules.weg_force import empty_roll


router = APIRouter(prefix="/api/weg-d6/dark-side/favors", tags=["Rare native Dark Side Favors"])
_LOCK = RLock()


def serialized(fn):
    @wraps(fn)
    def action(*args, **kwargs):
        with _LOCK:
            return fn(*args, **kwargs)
    return action


def working(expected=None):
    from dungeonforge.api import routes
    original = routes._ACTIVE_SESSION
    if original.edition != "weg_d6" or original.character.d6 is None:
        raise HTTPException(status_code=409, detail="Select the native WEG D6 campaign before reviewing Favors.")
    if expected is not None and expected != original.updated_at:
        raise ValueError("The scene changed after this favor review. Refresh actual actors, rare offer and round declarations.")
    session = original.model_copy(deep=True)
    force_world.synchronize(session)
    dark_world.synchronize(session)
    return original, session


def commit(original, session, item, operation):
    from dungeonforge.api import routes
    from dungeonforge.api.weg_routes import record
    if routes._ACTIVE_SESSION is not original or original.updated_at != session.updated_at:
        raise ValueError("The actual scene changed during this favor review. Refresh before committing.")
    item_revision = session.updated_at
    used = operation == "use"
    note = ("Immediate Dark Side FP boost used; +1 DSP and its normal plain corruption check recorded. Zero call actions or attempts spent; no ordinary FP granted."
        if used else "Unused offer: no ordinary FP granted, no DSP penalty, no actions or scene time consumed.")
    result = RuleEvaluationResult(action_type="dark_side_favor", success=True, roll_result=empty_roll("Rare GM favor review"),
        summary=f"[WEG D6 Favors] {item.actor_name}: {operation} {item.id}, moment '{item.moment_key}'. {note}",
        state_changes={"dark_side_favor": item.model_dump()})
    if used:
        response = record(session, result, f"{item.actor_name}: rare Dark Side favor {operation}", "story")
        force_world.refresh_encounters(session)
    else:
        # An unused free offer is a GM ledger event, not a character action or
        # new roll. Preserve the latest CP/Force roll opportunity and attempt.
        response = {"eval_result": result, "session": session}
    if routes._ACTIVE_SESSION is not original or original.updated_at != item_revision:
        raise ValueError("The actual scene changed during this favor review. Refresh before committing.")
    session.updated_at = max(time.time(), item_revision + 0.000001)
    for field in type(original).model_fields:
        setattr(original, field, getattr(session, field))
    response["session"] = original
    return response


@router.get("/state")
@serialized
def state():
    original, session = working()
    actors = []
    for person in dark_world.actors(session).values():
        if person.kind == "instructor":
            continue
        try:
            actual = rules.full_actor(session, person.id, declaration=False)
        except ValueError:
            continue
        native = actual.state
        try:
            rules.full_actor(session, person.id)
            can_offer = native.wound != "dead" and not native.corruption.dead
        except ValueError:
            can_offer = False
        active_favor = next((offer.id for offer in reversed(native.corruption.favors)
            if offer.status == "used" and offer.used_clock == native.force.elapsed_rounds
            and native.round_state.dark_side_active and native.round_state.dark_side_called
            and rules.same_scope(session, offer)), None)
        actors.append({"id": actual.id, "name": actual.name, "kind": person.kind,
            "force_points": native.force_points, "character_points": native.character_points,
            "dark_side_points": native.dark_side_points, "wound": native.wound,
            "can_take_turn": native.can_take_turn, "pending_demand": native.corruption.pending_demand is not None,
            "pending_activation": native.force.attempt is not None,
            "declaration_available": can_offer,
            "active_favor_id": active_favor,
            "elapsed_rounds": native.force.elapsed_rounds, "round_state": native.round_state,
            "favors": [{**offer.model_dump(), "same_scope": rules.same_scope(session, offer)} for offer in native.corruption.favors]})
    return {"updated_at": original.updated_at, "adventure": session.d6_advancement.adventure,
        "actors": actors, "source": rules.SOURCE, "rules": rules.NOTES}


@router.post("/offer")
@serialized
def offer(req: FavorOfferRequest):
    try:
        original, session = working(req.expected_updated_at)
        item = rules.offer(session, req)
        return commit(original, session, item, "offer")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/resolve")
@serialized
def resolve(req: FavorResolveRequest):
    try:
        original, session = working(req.expected_updated_at)
        item = rules.resolve(session, req)
        return commit(original, session, item, req.action)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
