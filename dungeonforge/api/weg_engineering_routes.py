"""Transactional quotes, parts purchases and saved repair attempts."""
from fastapi import APIRouter, HTTPException
from dungeonforge.api.weg_routes import native_session
from dungeonforge.api.weg_force_routes import commit
from dungeonforge.api.weg_advancement_routes import downtime, event as record_event, student
from dungeonforge.game.weg_force import advance_scene
from dungeonforge.game.weg_navigation import require_resolved
from dungeonforge.rules import weg_engineering as rules
from dungeonforge.rules.weg_d6 import WEGD6Rules
from dungeonforge.rules.weg_engineering_models import D6CraftRepairRequest, D6CraftRepairProject, D6CraftRepairAttempt, D6CraftRepairManage

router = APIRouter(prefix="/api/weg-d6/engineering", tags=["Native craft repair projects"])


def event(*args, **kwargs):
    return record_event(*args, category="Craft Repair", **kwargs)


def craft_for(session, id):
    craft = next((item for item in session.vehicles if item.id == id), None)
    if not craft:
        raise ValueError("Select a saved party craft.")
    return craft


def project_for(session, id):
    for craft in session.vehicles:
        for project in craft.repair_projects:
            if project.id == id:
                return craft, project
    raise ValueError("The repair project is no longer available.")


@router.post("/quote")
def quote(req: D6CraftRepairRequest):
    try:
        session = native_session()
        return {"quote": rules.quote(craft_for(session, req.craft_id), req)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/begin")
def begin(req: D6CraftRepairRequest):
    original = native_session()
    session = original.model_copy(deep=True)
    try:
        downtime(session)
        require_resolved(session)
        if req.expected_updated_at != session.updated_at:
            raise ValueError("The adventure changed after this quote; review the current repair before buying parts.")
        craft = craft_for(session, req.craft_id)
        q = rules.quote(craft, req)
        paid = q.parts_cost
        if req.parts_item:
            part = next((item for item in session.character.inventory if item.name == req.parts_item and item.quantity > 0), None)
            if part is None:
                raise ValueError("The declared appropriate replacement parts are not in party inventory.")
            part.quantity -= 1
            if part.quantity == 0:
                session.character.inventory.remove(part)
            paid = 0
        else:
            if session.character.d6.credits < paid:
                raise ValueError(f"These parts cost {paid} credits; the party cannot afford them.")
            session.character.d6.credits -= paid
        project = D6CraftRepairProject(request=req, quote=q, paid_credits=paid, parts_source=req.parts_item or "credits")
        craft.repair_projects.append(project)
        return commit(original, session, event(f"{craft.name}: reserve parts for {q.key}; {paid} credits paid once, source {project.parts_source}. {req.reason.strip()}", changes={"repair_project": project.model_dump()}), "Begin craft repair", boost=False)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/attempt")
def attempt(req: D6CraftRepairAttempt):
    original = native_session()
    session = original.model_copy(deep=True)
    try:
        downtime(session)
        require_resolved(session)
        craft, project = project_for(session, req.project_id)
        if project.status != "pending":
            raise ValueError("Only a pending repair project can be attempted.")
        if rules.fingerprint(craft, project.request) != project.quote.fingerprint:
            raise ValueError("This system's damage changed after parts were reserved; cancel and review the actual new damage.")
        person = student(session, req.actor_id)
        from dungeonforge.game.weg_task_guards import require_available
        require_available(session, person.id)
        if not person.d6.can_act or person.d6.force.attempt:
            raise ValueError("The technician must be conscious and free of another Force activation.")
        if req.force_point and req.character_points or req.character_points > person.d6.character_points or req.force_point and person.d6.force_points < 1:
            raise ValueError("Choose available CP dice or a Force Point, never both.")
        standard = rules.attempt_minutes(project.quote.skill, len(project.attempts))
        minutes = req.minutes if req.minutes is not None else standard
        if minutes != standard and not req.timing_reason.strip():
            raise ValueError("The source permits customized repair times, but changing the standard attempt time requires a GM reason.")
        advance_scene(session, minutes * 12)
        if craft.damage == "destroyed" or not person.d6.can_act:
            note = {"actor_id": person.id, "minutes": minutes, "timing_reason": req.timing_reason.strip(),
                "cp": 0, "fp": False, "success": False, "interrupted": True,
                "reason": "Time passed; craft destruction or technician incapacitation interrupted the attempt."}
            project.attempts.append(note)
            return commit(original, session, event(note["reason"], success=False), "Interrupted craft repair", boost=False)
        WEGD6Rules.declare(person.d6, force_point=req.force_point)
        result = WEGD6Rules.roll_skill(person.d6, project.quote.skill, project.quote.difficulty, req.character_points)
        note = {"actor_id": person.id, "minutes": minutes, "success": result.success, "timing_reason": req.timing_reason.strip(), "roll": result.roll_result.model_dump(), "cp": req.character_points, "fp": req.force_point}
        project.attempts.append(note)
        if result.success:
            rules.repair(craft, project.request)
            project.status = "completed"
        result.summary = f"[WEG Craft Repair] {craft.name} {project.quote.key}, {minutes} minutes: " + result.summary + (" System repaired; other damage remains recorded." if result.success else " Repair failed; paid parts remain reserved for another attempt.")
        result.state_changes["repair_project"] = project.model_dump()
        return commit(original, session, result, "Attempt craft repair", boost=False)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/cancel")
def cancel(req: D6CraftRepairManage):
    original = native_session()
    session = original.model_copy(deep=True)
    try:
        downtime(session)
        craft, project = project_for(session, req.project_id)
        if project.status != "pending" or not req.reason.strip():
            raise ValueError("Choose a pending project and record why it is abandoned.")
        project.status = "cancelled"
        return commit(original, session, event(f"{craft.name}: repair {project.quote.key} abandoned; no automatic refund of purchased/reserved materials. {req.reason.strip()}"), "Cancel craft repair", boost=False)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
