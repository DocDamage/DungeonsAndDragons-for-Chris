"""Transactional actual grenades; round-end detonation is owned by combat's clock."""
from fastapi import APIRouter, HTTPException

from dungeonforge.api.weg_routes import native_session
from dungeonforge.api.weg_force_routes import commit
from dungeonforge.api.weg_advancement_routes import event
from dungeonforge.game.weg_navigation import require_resolved
from dungeonforge.rules import weg_explosives as rules
from dungeonforge.rules.weg_equipment import ITEMS
from dungeonforge.rules.weg_explosives_models import (
    D6BlastPositionsRequest, D6GrenadeIntentRequest, D6GrenadeRethrowRequest,
    D6GrenadeStepRequest, D6GrenadeThrowRequest,
)


router = APIRouter(prefix="/api/weg-d6/explosives", tags=["Native point-target grenades and saved explosions"])


def working(req):
    original = native_session()
    if req.expected_updated_at != original.updated_at:
        raise ValueError("The actual encounter changed; review its live grenade state and positions again.")
    require_resolved(original)
    if original.vehicle_encounter:
        raise ValueError("Use the character-scale grenade procedure on foot, outside a craft encounter.")
    session = original.model_copy(deep=True)
    encounter = session.encounter
    if not encounter or not encounter.active or encounter.system != "weg_d6":
        raise ValueError("Start the actual native personal encounter before declaring positions or throwing a grenade.")
    if getattr(encounter, "d6_round_closing", False):
        raise ValueError("Resolve the saved immediate injury reactions, then advance the native round; ordinary grenade actions cannot bypass that closing phase.")
    if not req.reason.strip():
        raise ValueError("Record the actual GM scene facts and source ruling.")
    actor_id = getattr(req, "actor_id", None)
    if actor_id:
        from dungeonforge.game.weg_task_guards import require_available
        require_available(session, actor_id)
    return original, session, encounter


@router.get("/state")
def state():
    session = native_session()
    encounter = session.encounter
    return {"encounter_id": encounter.id if encounter else None, "active": bool(encounter and encounter.active),
        "round": encounter.round if encounter else None, "current_actor_id": encounter.active_combatant.id if encounter and encounter.active_combatant else None,
        "actions_started": bool(encounter and encounter.d6_actions_started), "turn_acted": bool(encounter and encounter.d6_turn_acted),
        "round_closing": bool(encounter and getattr(encounter, "d6_round_closing", False)),
        "actors": [{"id": actor.id, "name": actor.name, "is_player": actor.is_player, "d6": actor.d6,
                    "weapon": actor.weapon, "armor": actor.armor} for actor in encounter.combatants] if encounter else [],
        "explosives": encounter.d6_explosives if encounter else None,
        "catalog": [{"id": id, "name": ITEMS[id]["name"], "ranges": ITEMS[id]["item"]["d6_ranges"],
                     "blast_radius": ITEMS[id]["blast_radius"], "blast_damage": ITEMS[id]["blast_damage"]} for id in rules.SUPPORTED],
        "source": rules.SOURCE, "notes": rules.NOTES}


def mutate(req, operation, label):
    try:
        original, session, encounter = working(req)
        result = operation(encounter, req)
        if not hasattr(result, "summary"):
            result = event(result if isinstance(result, str) else label + ": " + req.reason.strip())
        encounter.combat_log.append(result.summary)
        return commit(original, session, result, label, boost=False)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/positions")
def positions(req: D6BlastPositionsRequest):
    return mutate(req, rules.review_positions, "Review actual grenade positions")


@router.post("/declare-rethrow")
def declare_rethrow(req: D6GrenadeIntentRequest):
    return mutate(req, rules.declare_rethrow, "Declare three-action toss-away intent")


@router.post("/throw")
def throw(req: D6GrenadeThrowRequest):
    return mutate(req, rules.throw, "Throw actual point-target grenade")


@router.post("/move")
def approach(req: D6GrenadeStepRequest):
    return mutate(req, rules.approach, "Toss-away action 1/3: approach grenade")


@router.post("/grab")
def grab(req: D6GrenadeStepRequest):
    return mutate(req, rules.grab, "Toss-away action 2/3: grab grenade")


@router.post("/rethrow")
def rethrow(req: D6GrenadeRethrowRequest):
    return mutate(req, rules.rethrow, "Toss-away action 3/3: throw live grenade")
