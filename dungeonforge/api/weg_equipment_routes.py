"""In-game personal equipment purchases, canonical loadouts and paid gear work."""
from fastapi import APIRouter, HTTPException

from dungeonforge.api.weg_advancement_routes import downtime, event, student
from dungeonforge.api.weg_force_routes import commit
from dungeonforge.api.weg_routes import native_session
from dungeonforge.game.weg_force import advance_scene
from dungeonforge.game.weg_navigation import require_resolved
from dungeonforge.game.weg_task_guards import require_available
from dungeonforge.rules.base import Item
from dungeonforge.rules.weg_d6 import WEGD6Rules
from dungeonforge.rules import weg_equipment as rules
from dungeonforge.rules.weg_equipment_models import (
    EquipmentArmorBaseline, EquipmentLoadoutRequest, EquipmentPurchaseRecord,
    EquipmentPurchaseRequest, EquipmentReloadRequest, EquipmentWorkAttempt,
    EquipmentWorkCancel, EquipmentWorkProject, EquipmentWorkRequest,
)

router = APIRouter(prefix="/api/weg-d6/equipment", tags=["Native personal equipment"])


def working():
    original = native_session()
    session = original.model_copy(deep=True)
    downtime(session)
    require_resolved(session)
    return original, session


def revision(session, expected):
    if expected != session.updated_at:
        raise ValueError("The adventure changed after review; inspect the actual current equipment and credits again.")


def buyer(session, actor_id):
    person = student(session, actor_id)
    require_available(session, person.id)
    if not person.d6.can_act or person.d6.force.attempt:
        raise ValueError("Choose a conscious party member free of another activation or exclusive task.")
    return person


@router.get("/catalog")
def catalog():
    return rules.catalog()


@router.post("/quote")
def quote(req: EquipmentPurchaseRequest):
    try:
        _, session = working()
        person = buyer(session, req.actor_id)
        calculation = rules.quote_purchase(req, person)
        return {"quote": calculation, "affordable": calculation.total <= session.character.d6.credits}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/purchase")
def purchase(req: EquipmentPurchaseRequest):
    try:
        original, session = working()
        revision(session, req.expected_updated_at)
        person = buyer(session, req.actor_id)
        calculation = rules.quote_purchase(req, person)
        if calculation.total > session.character.d6.credits:
            raise ValueError("The actual party wallet cannot afford this purchase.")
        item = rules.make_item(req.catalog_id, calculation.unit_price)
        if len(session.character.inventory) + (req.quantity if item.item_type in {"weapon", "armor"} else 1) > 1000:
            raise ValueError("The party inventory supports up to 1,000 distinct item records.")
        acquired = [rules.make_item(req.catalog_id, calculation.unit_price) for _ in range(req.quantity)] if item.item_type in {"weapon", "armor"} else [item]
        if item.item_type not in {"weapon", "armor"}:
            acquired[0].quantity = req.quantity
        session.character.d6.credits -= calculation.total
        session.character.inventory.extend(acquired)
        record = EquipmentPurchaseRecord(actor_id=person.id, quote=calculation,
            inventory_ids=[item.id for item in acquired], legal_basis=req.legal_basis, reason=req.reason.strip())
        session.d6_equipment.purchases.append(record)
        result = event(f"Purchased {calculation.quantity} × {calculation.name}; {calculation.total} credits paid once. Stock/permission: {req.legal_basis}. {req.reason.strip()}", changes={"purchase": record.model_dump()})
        return commit(original, session, result, "Purchase personal equipment", boost=False)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/loadout")
def loadout(req: EquipmentLoadoutRequest):
    try:
        original, session = working()
        revision(session, req.expected_updated_at)
        actor = buyer(session, req.actor_id)
        if not req.reason.strip() or len(req.armor_ids) != len(set(req.armor_ids)):
            raise ValueError("Record actual equipment facts and choose each worn armor item only once.")
        weapon = rules.inventory_item(session, req.weapon_id) if req.weapon_id else None
        armor = [rules.inventory_item(session, id) for id in req.armor_ids]
        for item in [*armor, *([weapon] if weapon else [])]:
            owner = rules.equipped_owner(session, item)
            if owner and owner != actor.id:
                raise ValueError(f"{item.name} is assigned to another party member; release their actual loadout first.")
            if item.quantity != 1:
                raise ValueError("Assign a distinct weapon/armor item, not an ambiguous stack of several physical objects.")
        if weapon and weapon.item_type != "weapon":
            raise ValueError("Choose an actual weapon as the weapon loadout.")
        covered = set()
        for item in armor:
            if item.item_type != "armor" or item.armor_energy is None or item.armor_physical is None or not item.armor_locations or not item.armor_sides:
                raise ValueError("Choose armor with actual saved protection, body locations and sides; a descriptive legacy item is not a complete armor profile.")
            profile = {(location, side) for location in item.armor_locations for side in item.armor_sides}
            if covered & profile:
                raise ValueError("These armor pieces overlap. The book does not provide a general stacking rule; choose a compatible actual loadout.")
            covered |= profile
        if armor and req.use_legacy_armor:
            raise ValueError("Actual armor profiles replace aggregate GM armor ratings; those pools cannot be stacked.")
        baselines = session.d6_equipment.armor_baselines
        baselines.setdefault(actor.id, EquipmentArmorBaseline(armor_energy=actor.d6.armor_energy,
            armor_physical=actor.d6.armor_physical, dexterity_penalty=actor.d6.dexterity_penalty))
        for item in session.character.inventory:
            if rules.equipped_owner(session, item) == actor.id and item.item_type in {"weapon", "armor"}:
                item.equipped, item.equipped_by = False, None
        for item in [*armor, *([weapon] if weapon else [])]:
            item.equipped, item.equipped_by = True, actor.id
        if weapon and req.generator_connected is not None:
            if req.generator_connected and weapon.catalog_id not in {"e_web", "light_repeating_blaster"} and not weapon.requires_generator:
                raise ValueError("This weapon has no source generator feed; an arbitrary connection cannot grant unlimited ammunition.")
            weapon.generator_connected = req.generator_connected
        if actor.id != session.character.id:
            actor.d6_weapon = weapon if weapon else Item(name="Brawling", item_type="natural_weapon",
                damage="STR", d6_skill="brawling", damage_type="physical", equipped_by=actor.id)
            actor.attack_name, actor.damage = (weapon.name, weapon.damage or "STR") if weapon else ("Brawling", "STR")
        if armor:
            rules.mirror_armor(session, actor)
        elif req.use_legacy_armor is not False:
            baseline = baselines[actor.id]
            actor.d6.armor_energy, actor.d6.armor_physical, actor.d6.dexterity_penalty = baseline.armor_energy, baseline.armor_physical, baseline.dexterity_penalty
        else:
            actor.d6.armor_energy, actor.d6.armor_physical, actor.d6.dexterity_penalty = "0D", "0D", 0
        result = event(f"{actor.name}: actual weapon {weapon.name if weapon else 'unarmed'}; worn armor {', '.join(item.name for item in armor) or ('explicit prior GM armor ratings' if req.use_legacy_armor is not False else 'none')}. {req.reason.strip()}", changes={"actor_id": actor.id, "weapon_id": req.weapon_id, "armor_ids": req.armor_ids, "legacy_armor": not armor and req.use_legacy_armor is not False})
        return commit(original, session, result, "Assign personal loadout", boost=False)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/reload")
def reload(req: EquipmentReloadRequest):
    try:
        original, session = working()
        actor = buyer(session, req.actor_id)
        if not req.reason.strip():
            raise ValueError("Record the actual reload and compatible supplies.")
        rules.reload_requirements(session, actor.id, req.item_id, req.primary, req.power)
        advance_scene(session, 1)
        if not actor.d6.can_act:
            return commit(original, session, event("One scene round passed, but incapacitation interrupted the reload; no supplies were consumed.", success=False), "Interrupted personal reload", boost=False)
        WEGD6Rules.declare(actor.d6)
        item, changes = rules.reload_weapon(session, actor.id, req.item_id, req.primary, req.power)
        from dungeonforge.rules import weg_force_effects as effects
        effects.take_action(actor.d6)
        result = event(f"{actor.name}: {item.name} reload {'completed' if changes['success'] else 'failed its Moderate Strength check'}; one action / scene round passed. {req.reason.strip()}", success=changes["success"], changes={"item_id": item.id, **changes})
        return commit(original, session, result, "Reload personal weapon", boost=False)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def project_for(session, id):
    project = next((item for item in session.d6_equipment.work_projects if item.id == id), None)
    if project is None:
        raise ValueError("Choose an actual saved personal equipment project.")
    return project


@router.post("/work-quote")
def work_quote(req: EquipmentWorkRequest):
    try:
        _, session = working()
        return {"quote": rules.quote_work(rules.inventory_item(session, req.item_id), req)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/work-begin")
def work_begin(req: EquipmentWorkRequest):
    try:
        original, session = working()
        revision(session, req.expected_updated_at)
        item = rules.inventory_item(session, req.item_id)
        if item.quantity != 1:
            raise ValueError("Work on one distinct physical weapon or armor piece, not an entire inventory stack.")
        if any(project.status == "pending" and project.request.item_id == item.id for project in session.d6_equipment.work_projects):
            raise ValueError("This item already has a paid pending project. Attempt or cancel that work first.")
        calculation = rules.quote_work(item, req)
        if calculation.parts_cost > session.character.d6.credits:
            raise ValueError("The party cannot afford the actual replacement or improvement parts.")
        session.character.d6.credits -= calculation.parts_cost
        project = EquipmentWorkProject(request=req, quote=calculation, paid_credits=calculation.parts_cost)
        session.d6_equipment.work_projects.append(project)
        return commit(original, session, event(f"{item.name}: reserve {calculation.parts_cost} credits of parts once for {req.operation}; saved project {project.id}. {req.reason.strip()}", changes={"equipment_project": project.model_dump()}), "Begin personal equipment work", boost=False)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/work-attempt")
def work_attempt(req: EquipmentWorkAttempt):
    try:
        original, session = working()
        project = project_for(session, req.project_id)
        if project.status != "pending":
            raise ValueError("Only a pending paid project may be attempted; completed work cannot be rolled again.")
        item = rules.inventory_item(session, project.request.item_id)
        if rules.fingerprint(item) != project.quote.fingerprint:
            raise ValueError("The actual item damage, value or modification changed. Cancel and review the new work before using those parts.")
        actor = buyer(session, req.actor_id)
        if req.force_point and req.character_points or req.character_points > actor.d6.character_points or req.force_point and actor.d6.force_points < 1:
            raise ValueError("Choose available Character Points or a Force Point, never both.")
        standard = [15, 60, 120][min(len(project.attempts), 2)]
        minutes = req.minutes if req.minutes is not None else standard
        if minutes != standard and not req.timing_reason.strip():
            raise ValueError("Changing the printed standard attempt time requires the GM's actual timing reason.")
        advance_scene(session, minutes * 12)
        if not actor.d6.can_act:
            note = {"actor_id": actor.id, "minutes": minutes, "timing_reason": req.timing_reason.strip(), "success": False, "interrupted": True, "cp": 0, "fp": False}
            project.attempts.append(note)
            return commit(original, session, event("Time passed, but technician incapacitation interrupted personal equipment work; no roll or points spent.", success=False, changes={"equipment_attempt": note}), "Interrupted personal equipment work", boost=False)
        WEGD6Rules.declare(actor.d6, force_point=req.force_point)
        result = WEGD6Rules.roll_skill(actor.d6, project.quote.skill, project.quote.difficulty, req.character_points)
        project.attempts.append({"actor_id": actor.id, "minutes": minutes, "timing_reason": req.timing_reason.strip(), "success": result.success, "roll": result.roll_result.model_dump(), "cp": req.character_points, "fp": req.force_point})
        if result.success:
            rules.apply_work(item, project)
            project.status = "completed"
            for person in [session.character, *session.character.companions]:
                if person.d6:
                    rules.mirror_armor(session, person)
                    if person.id != session.character.id and person.d6_weapon and person.d6_weapon.id == item.id:
                        person.d6_weapon = item
                        person.damage = item.damage or "STR"
        result.summary = f"[WEG Equipment Work] {item.name}: {project.request.operation}, {minutes} minutes. " + result.summary + (" Actual item updated." if result.success else " Paid parts remain reserved for the next attempt.")
        result.state_changes["equipment_project"] = project.model_dump()
        return commit(original, session, result, "Attempt personal equipment work", boost=False)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/work-cancel")
def work_cancel(req: EquipmentWorkCancel):
    try:
        original, session = working()
        project = project_for(session, req.project_id)
        if project.status != "pending" or not req.reason.strip():
            raise ValueError("Choose pending work and record the actual cancellation reason.")
        project.status, project.cancellation_reason = "cancelled", req.reason.strip()
        return commit(original, session, event(f"Cancelled {project.quote.item_name} {project.request.operation}; no automatic parts refund. {req.reason.strip()}"), "Cancel personal equipment work", boost=False)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
