"""Read-only narrative ledger for actual organic medical procedures."""
import json
from typing import TYPE_CHECKING

from dungeonforge.rules import weg_medical as medical

if TYPE_CHECKING:
    from dungeonforge.game.models import GameSession


def build_medical_context(session: "GameSession", *, max_projects=12) -> str:
    if session.edition != "weg_d6" or not session.d6_medical.projects:
        return ""
    people = medical.members(session)
    protected = medical.protected_actor_ids(session)
    busy = medical.busy_actor_ids(session)
    projects = sorted(session.d6_medical.projects, key=lambda item: item.status not in medical.ACTIVE)
    lines = ["### WEG D6 MEDICAL CARE — SAVED PROCEDURES",
        medical.SOURCE,
        "These rolls, doses and elapsed rounds are already recorded. Pending/ready care has not granted a future healing result. Treatment does not create a tank, clinician, permission, medicine, fee or credit payment."]
    for project in projects[:max(0, max_projects)]:
        person = people.get(project.patient_id)
        name = person.name if person else project.patient_id
        lines.append(f"- {json.dumps(name, ensure_ascii=False)} [{project.patient_id}]: {project.kind}, {project.status}, procedure {project.id}; original injury {project.initial_wound}; actual current wound {person.d6.wound if person else 'patient missing'}.")
        lines.append(f"  Shared scene clock: {project.elapsed_rounds}/{project.required_rounds} rounds accounted for, {project.remaining_rounds} remaining (12 rounds/minute; 720/hour;17280/day). Reserved from ordinary actions: {project.patient_id in busy}.")
        lines.append(f"  Actual GM care facts: {json.dumps(project.reason, ensure_ascii=False)}.")
        if project.kind == "bacta":
            operator = people.get(project.operator_id)
            lines.append(f"  Actual tank/facility {json.dumps(project.facility, ensure_ascii=False)}; tank confirmed {project.tank_confirmed}; recorded local permission {project.legal_basis}, confirmed {project.permission_confirmed}. Operator {operator.name if operator else project.operator_id}; {project.skill} difficulty {project.difficulty}, trained Medicine {project.trained}.")
            if project.treatment_roll:
                lines.append(f"  Setup roll ALREADY MADE: total {project.treatment_roll.get('total')} vs {project.difficulty}; {project.character_points} CP and {int(project.force_point)} FP already spent. Actual procedure/initial monitoring {project.setup_minutes} minutes passed" + (" within the successful treatment clock." if project.duration_roll else " for the failed setup procedure."))
            if project.duration_roll:
                expression, unit = medical.BACTA[project.initial_wound]
                lines.append(f"  Plain source duration ALREADY ROLLED: {expression} -> {project.duration_roll.get('total')} {'days' if unit == medical.DAY else 'hours'}; never reroll on load or narration.")
            if project.medicine:
                dose = project.medicine
                pips = dose.get("pool_pips")
                shown_pips = f"{pips:+d}" if isinstance(pips, int) else " (pips not recorded)"
                lines.append(f"  Actual operator medicine ALREADY CONSUMED ONCE: {dose.get('quantity')} x {json.dumps(dose.get('name'), ensure_ascii=False)} [{dose.get('item_id')}]; native operator pool {dose.get('pool_dice')}D{shown_pips}, external dose +{dose.get('bonus_dice')}D. GM effect facts {json.dumps(dose.get('facts', ''), ensure_ascii=False)}. Convention: {dose.get('convention')}. The setup attempt, including a failed attempt, consumes this actual dose; loading or advancing care consumes no further dose or credits.")
            lines.append(f"  Ongoing successful actual bacta currently protects this original injury from untreated mortality: {project.patient_id in protected}. Interrupted/cancelled/failed care grants no such protection.")
        else:
            modifier = -1 if project.care_mode == "work" else 1 if project.care_mode == "easy" else 0
            lines.append(f"  Actual prescribed activity {project.care_mode}; healing Strength workload modifier {modifier:+d}D. Rest/easy patients remain reserved; work patients may act with the saved -1D healing consequence. Natural care does not stabilize mortal wounds.")
            if project.medicine:
                dose = project.medicine
                lines.append(f"  Actual medicine ALREADY CONSUMED ONCE: {dose.get('quantity')} x {json.dumps(dose.get('name'), ensure_ascii=False)} [{dose.get('item_id')}]; healing +{dose.get('bonus_dice', 0)}D, recovery factor {dose.get('time_factor', 1)}; exceptional GM regimen {dose.get('exceptional', False)}. Resolving this saved care roll does not consume another dose or charge credits. Regimen facts: {json.dumps(dose.get('facts', ''), ensure_ascii=False)}.")
            if project.status == "ready":
                lines.append("  Full saved period passed; roll actual Strength using the saved care/medicine modifiers and mishaps as penalties. No healing roll has happened yet.")
        if project.outcome:
            lines.append(f"  Saved outcome: {json.dumps(project.outcome, ensure_ascii=False)}.")
        for entry in project.history[-3:]:
            actual_roll = entry.get("roll")
            lines.append(f"  History {entry.get('operation')}: {json.dumps(entry.get('summary', ''), ensure_ascii=False)}" + (f"; saved roll total {actual_roll.get('total')}." if isinstance(actual_roll, dict) else "."))
    if len(projects) > max_projects:
        lines.append(f"{len(projects) - max(0, max_projects)} additional saved medical procedures omitted; consult the actual medical ledger.")
    return "\n".join(lines)
