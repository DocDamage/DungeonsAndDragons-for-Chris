"""Saved native organic care, without creating a tank or inventing medical prices."""
from fastapi import APIRouter, HTTPException

from dungeonforge.api.weg_routes import native_session
from dungeonforge.api.weg_force_routes import commit
from dungeonforge.api.weg_advancement_routes import downtime, event, student
from dungeonforge.game.weg_force import advance_scene
from dungeonforge.game.weg_navigation import require_resolved
from dungeonforge.game.weg_task_guards import require_available
from dungeonforge.rules import weg_medical as rules
from dungeonforge.rules.dice import DiceRoller
from dungeonforge.rules.weg_d6 import WEGD6Rules, parse_code, skill_key
from dungeonforge.rules.weg_models import D6RoundState
from dungeonforge.rules.weg_medical_models import BactaStart, NaturalCareStart, MedicalAdvance, MedicalProjectRequest, MedicalProject

router = APIRouter(prefix="/api/weg-d6/medical", tags=["Native organic medical care"])


def working(req):
    original = native_session()
    session = original.model_copy(deep=True)
    downtime(session)
    require_resolved(session)
    if req.expected_updated_at != session.updated_at or not req.reason.strip():
        raise ValueError("Review the current adventure and record the actual medical procedure.")
    return original, session


def start_patient(session, req):
    patient = rules.living_patient(session, req.patient_id)
    if getattr(req, "mode", None) != "work":
        require_available(session, patient.id)
    if rules.active_project(session, patient.id):
        raise ValueError("This patient already has a saved active medical procedure.")
    if len(session.d6_medical.projects) >= 1000:
        raise ValueError("The saved medical ledger has reached 1,000 procedures.")
    return patient


def saved(original, session, project, summary, *, success=True, roll=None, changes=None):
    result = event(summary, success=success, category="Medical", changes={"project_id": project.id, "patient_id": project.patient_id, **(changes or {})})
    if roll is not None:
        result.roll_result = roll
    return commit(original, session, result, "Medical care", boost=False)


@router.get("/catalog")
def catalog():
    return {"source": rules.SOURCE, "rounds_per_day": rules.DAY,
        "bacta": [{"wound": wound, "duration_dice": dice, "unit": "days" if unit == rules.DAY else "hours"} for wound, (dice, unit) in rules.BACTA.items()],
        "natural": [{"wound": wound, "days": days} for wound, days in rules.NATURAL_DAYS.items()],
        "notes": ["A real available bacta tank and actual local permission are GM facts. No tank, doctor, price or fee is invented by treatment.",
            "Trained Medicine uses Very Easy (1–5). Without Medicine, actual First Aid or Technical is Heroic (31+); failure increases the patient's wound level by two.",
            "Successful bacta heals after the saved plain-dice duration. Actual GM setup/initial monitoring minutes pass within that treatment clock; the source specifies Medicine takes minutes or hours. The patient stays in actual treatment; interruption or a changed injury requires reassessment.",
            "Natural healing uses actual Strength with all mishaps as penalties. Work, exercise or adventuring subtracts 1D; virtually nothing for twice the period adds 1D.",
            "Ordinary medicines may add 1D and/or shorten recovery by as much as half. Actual exceptional effects require explicit GM regimen facts and real inventory doses. The source supplies no general doctor-care bonus.",
            "Medicines may increase a doctor's trained Medicine; no fixed bonus is printed. An actual GM-confirmed inventory dose is consumed per setup attempt, including failure. External dose dice are added after Force Point doubling as an explicit convention; the source does not specify this interaction.",
            "Untreated mortal wounds continue their normal death checks; a natural-care plan does not stabilize anyone. Care clocks advance with the shared scene and fleet."]}


@router.post("/bacta-start")
def bacta_start(req: BactaStart):
    try:
        original, session = working(req)
        patient = start_patient(session, req)
        doctor = student(session, req.operator_id)
        require_available(session, doctor.id)
        if not req.tank_confirmed or not req.permission_confirmed or not req.facility.strip():
            raise ValueError("Confirm the actual available bacta tank, facility and relevant license or explicit GM exception.")
        state = doctor.d6
        if not state.can_act or state.force.attempt:
            raise ValueError("The actual operator must be conscious, available and free of a pending Force activation.")
        trained = any(skill_key(key) == "medicine" and parse_code(value)[0] > 0 for key, value in state.skills.items())
        skill = "medicine" if trained else req.untrained_skill
        difficulty = req.difficulty if req.difficulty is not None else 5 if trained else 31
        if trained and not 1 <= difficulty <= 5 or not trained and difficulty < 31:
            raise ValueError("Use Very Easy 1–5 for trained Medicine, or an actual Heroic difficulty of at least31 for untrained First Aid/Technical.")
        if req.force_point and req.character_points:
            raise ValueError("Character Points and a Force Point cannot combine.")
        state.round_state = D6RoundState()
        WEGD6Rules.declare(state, force_point=req.force_point)
        dose = rules.doctor_medicine(session, req, trained)
        check = rules.roll_operator(state, skill, difficulty, req.character_points, dose)
        project = MedicalProject(kind="bacta", patient_id=patient.id, initial_wound=patient.d6.wound,
            operator_id=doctor.id, facility=req.facility.strip(), tank_confirmed=True, legal_basis=req.legal_basis,
            permission_confirmed=True, reason=req.reason.strip(), trained=trained, skill=skill, difficulty=difficulty,
            character_points=req.character_points, force_point=req.force_point, setup_minutes=req.setup_minutes,
            treatment_roll=check.roll_result.model_dump(), observed_injury=rules.injury_snapshot(patient.d6), medicine=dose)
        session.d6_medical.projects.append(project)
        if not check.success:
            project.status = "failed"
            advance_scene(session, req.setup_minutes * 12)
            if not trained:
                patient.d6.wound = "mortally_wounded" if patient.d6.wound == "wounded" else "dead"
                patient.d6.mortal_rounds, patient.d6.recovery_days = 0, 0
                patient.d6.round_state.blocked = True
                from dungeonforge.rules import weg_force_effects as effects
                effects.drop_on_injury(patient.d6)
            project.outcome = f"Bacta setup failed; patient {patient.d6.wound}." + (" Untrained failure increased injury two levels." if not trained else " No successful treatment or mortality protection began.")
            rules.record(session, project, "setup_failed", project.outcome)
            return saved(original, session, project, project.outcome, success=False, roll=check.roll_result, changes={"wound": patient.d6.wound})
        dice, unit = rules.BACTA[patient.d6.wound]
        duration = DiceRoller.roll(dice)
        project.duration_roll = duration.model_dump()
        project.required_rounds = project.remaining_rounds = duration.total * unit
        project.outcome = f"Actual bacta treatment begun at {project.facility}; {duration.total} {'days' if unit == rules.DAY else 'hours'} required, patient not yet healed."
        rules.record(session, project, "started", project.outcome, check=check.model_dump(), duration=duration.model_dump())
        advance_scene(session, req.setup_minutes * 12)
        return saved(original, session, project, project.outcome + f" GM procedure/initial monitoring time {req.setup_minutes} minutes passed within the shared clinical clock.", success=project.status in {"active", "completed"}, roll=check.roll_result,
            changes={"duration": duration.model_dump(), "required_rounds": project.required_rounds, "trained": trained})
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/natural-start")
def natural_start(req: NaturalCareStart):
    try:
        original, session = working(req)
        patient = start_patient(session, req)
        medicine = rules.medicine(session, req)
        rounds = rules.natural_period(patient.d6.wound, req.mode, medicine.get("time_factor", 1))
        project = MedicalProject(kind="natural", patient_id=patient.id, initial_wound=patient.d6.wound,
            required_rounds=rounds, remaining_rounds=rounds, reason=req.reason.strip(), care_mode=req.mode, medicine=medicine)
        session.d6_medical.projects.append(project)
        summary = f"{patient.name}: saved {req.mode} care for {rounds / rules.DAY:g} days; no healing roll or immediate wound change."
        rules.record(session, project, "started", summary, medicine=medicine)
        return saved(original, session, project, summary)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/advance")
def advance(req: MedicalAdvance):
    try:
        original, session = working(req)
        if not any(project.status == "active" for project in session.d6_medical.projects):
            raise ValueError("Begin an actual saved medical procedure before advancing its care time.")
        advance_scene(session, req.rounds)
        result = event(f"Advanced the shared scene and fleet {req.rounds} rounds for actual medical care. {req.reason.strip()}", category="Medical",
            changes={"rounds": req.rounds, "projects": [{"id": project.id, "status": project.status, "remaining_rounds": project.remaining_rounds} for project in session.d6_medical.projects]})
        return commit(original, session, result, "Advance medical care", boost=False)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def project_for(session, id):
    project = next((project for project in session.d6_medical.projects if project.id == id), None)
    if project is None:
        raise ValueError("Choose an actual saved medical procedure.")
    return project


@router.post("/natural-resolve")
def natural_resolve(req: MedicalProjectRequest):
    try:
        original, session = working(req)
        project = project_for(session, req.project_id)
        if project.kind != "natural" or project.status != "ready" or project.remaining_rounds:
            raise ValueError("The full saved natural-care period must pass before its Strength roll.")
        patient = rules.valid_patient(session, project)
        if patient is None:
            raise ValueError("The actual injury changed; cancel this stale care plan and reassess.")
        roll, old, new, modifier, bonus = rules.resolve_natural(patient.d6, project)
        project.status = "completed"
        project.outcome = f"Natural healing Strength {roll.total}: {old} → {new}; care modifier {modifier:+d}D, actual medicine {bonus:+d}D. {req.reason.strip()}"
        rules.record(session, project, "resolved", project.outcome, roll=roll.model_dump(), old_wound=old, wound=new)
        return saved(original, session, project, project.outcome, success=new != "dead" and (new == "healthy" or list(rules.NATURAL_DAYS).index(new) < list(rules.NATURAL_DAYS).index(old)),
            roll=roll, changes={"wound": new, "care_modifier_dice": modifier, "medicine_bonus_dice": bonus})
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/cancel")
def cancel(req: MedicalProjectRequest):
    try:
        original, session = working(req)
        project = project_for(session, req.project_id)
        if project.status not in rules.ACTIVE:
            raise ValueError("This saved medical procedure is already finished.")
        project.status, project.outcome = "cancelled", req.reason.strip()
        rules.record(session, project, "cancelled", req.reason.strip())
        return saved(original, session, project, "Actual care cancelled; no healing, medicine refund or further mortality protection granted. " + req.reason.strip())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
