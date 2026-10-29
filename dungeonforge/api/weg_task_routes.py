"""Transactional declared scene work, original Command coordination and task clocks."""
from fastapi import APIRouter, HTTPException

from dungeonforge.api.weg_advancement_routes import downtime, event as record_event
from dungeonforge.api.weg_force_routes import commit
from dungeonforge.api.weg_routes import native_session
from dungeonforge.game.weg_force import advance_scene
from dungeonforge.game.weg_navigation import require_resolved
from dungeonforge.rules import weg_force_effects as effects, weg_tasks as rules
from dungeonforge.rules.base import RuleEvaluationResult
from dungeonforge.rules.weg_d6 import D6Roller, WEGD6Rules
from dungeonforge.rules.weg_force import empty_roll
from dungeonforge.rules.weg_tasks_models import D6TaskAdvance, D6TaskManage, D6TaskProject, D6TaskRequest, D6TaskResolve


router = APIRouter(prefix="/api/weg-d6/tasks", tags=["Native declared scene tasks and Command"])


def event(*args, **kwargs):
    return record_event(*args, category="Scene Task", **kwargs)


def scene(session):
    downtime(session)
    require_resolved(session)


def project_for(session, id):
    project = next((item for item in session.d6_tasks.projects if item.id == id), None)
    if project is None or project.status != "pending":
        raise ValueError("Choose a pending saved task; completed, failed or cancelled stages cannot be rolled again.")
    return project


def fit_workers(session, project):
    for id in rules.involved(project.request):
        rules.available(rules.actor(session, id))


def interrupt_changed_clock(original, session, project):
    changed = [id for id in rules.involved(project.request)
        if project.actor_clocks.get(id) != rules.actor(session, id).d6.force.elapsed_rounds]
    if not changed:
        return None
    project.status = "interrupted"
    project.work_log.append({"step": project.current_step, "rounds": 0, "interrupted_actor_ids": changed,
        "reason": "Scene time advanced outside this project's declared exclusive work."})
    return commit(original, session, event(f"{project.label}: exclusive work was interrupted by external scene time; no new task time, roll or points spent.",
        success=False, changes={"task_project": project.model_dump()}), "Interrupted scene task", boost=False)


@router.get("/state")
def state():
    session = native_session().model_copy(deep=True)
    return {"actors": [{"id": person.id, "name": person.name, "d6": person.d6} for person in rules.roster(session).values()],
        "tasks": session.d6_tasks, "rules": {"source": "WEG40055 (1992), printed pp.30, 55, 58, 65, 68–70.",
            "command_counts": rules.COUNTS, "command_table": rules.COMMAND, "bands": rules.BANDS,
            "preparation_banned": sorted(rules.PREPARATION_BANNED), "combining_banned": sorted(rules.COMBINING_BANNED),
            "notes": rules.NOTES}}


@router.post("/quote")
def quote(req: D6TaskRequest):
    try:
        session = native_session().model_copy(deep=True)
        scene(session)
        return {"quote": rules.quote(session, req)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/begin")
def begin(req: D6TaskRequest):
    original = native_session()
    session = original.model_copy(deep=True)
    try:
        scene(session)
        if req.expected_updated_at != session.updated_at:
            raise ValueError("The adventure changed after this task review; preview the actual workers and procedure again.")
        q = rules.quote(session, req)
        project = D6TaskProject(label=req.label.strip(), reason=req.reason.strip(), request=req, quote=q,
            declarations=[{**item, "role": "worker", "exclusive": True} for item in q.participants],
            actor_clocks={id: rules.actor(session, id).d6.force.elapsed_rounds for id in rules.involved(req)})
        result = None
        if q.combined:
            commander = rules.actor(session, req.commander_id)
            WEGD6Rules.declare(commander.d6, actions=2 if req.commander_participates else 1, force_point=req.command_force_point)
            result = WEGD6Rules.roll_skill(commander.d6, "command", q.command_difficulty, req.command_character_points)
            count = rules.commanded(q.declared_count, q.average_skill, q.command_difficulty, result.roll_result.total)
            project.command = {"actor_id": commander.id, "name": commander.name,
                "difficulty": q.command_difficulty, "band": q.command_band, "average_skill": q.average_skill,
                "declared_count": q.declared_count, "table_count": q.table_count, "coordinated_count": count,
                "coordinated_ids": req.participant_ids[:count], "bonus_dice": rules.bonus(count),
                "success": result.success, "roll": result.roll_result.model_dump(),
                "cp": req.command_character_points, "fp": req.command_force_point,
                "participates": req.commander_participates}
            project.declarations.append({"actor_id": commander.id, "name": commander.name, "role": "commander",
                "skill": "command", "skill_code": WEGD6Rules.skill_code(commander.d6, "command")[0],
                "declared_actions": 2 if req.commander_participates else 1,
                "cp": req.command_character_points, "fp": req.command_force_point})
        session.d6_tasks.projects.append(project)
        summary = f"{project.label}: saved {len(q.steps)} required stage(s), actual workers and exclusive work declaration. "
        if project.command:
            summary += f"{project.command['name']} coordinated {project.command['coordinated_count']} of {q.declared_count}; source bonus +{project.command['bonus_dice']}D. Command points were spent once."
        else:
            summary += "Work advances only through this project's explicit scene clock."
        if result:
            result.summary = "[WEG Scene Task] " + summary + " " + result.summary
            result.state_changes["task_project"] = project.model_dump()
        else:
            result = event(summary, changes={"task_project": project.model_dump()})
        return commit(original, session, result, "Begin declared scene task", boost=False)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/advance")
def advance(req: D6TaskAdvance):
    original = native_session()
    session = original.model_copy(deep=True)
    try:
        scene(session)
        project = project_for(session, req.project_id)
        interrupted = interrupt_changed_clock(original, session, project)
        if interrupted:
            return interrupted
        fit_workers(session, project)
        if not req.reason.strip():
            raise ValueError("Record the actual uninterrupted work performed during this interval.")
        remaining = project.quote.steps[project.current_step].total_rounds - project.work_rounds
        if remaining <= 0:
            raise ValueError("This stage's declared work is finished; resolve its saved check before advancing another stage.")
        rounds = min(req.rounds, remaining)
        advance_scene(session, rounds)
        project.work_rounds += rounds
        project.elapsed_rounds += rounds
        project.actor_clocks = {id: rules.actor(session, id).d6.force.elapsed_rounds for id in rules.involved(project.request)}
        note = {"step": project.current_step, "rounds": rounds, "reason": req.reason.strip()}
        project.work_log.append(note)
        unavailable = [id for id in rules.involved(project.request)
            if not rules.actor(session, id).d6.can_act or rules.actor(session, id).d6.force.attempt]
        if unavailable:
            project.status = "interrupted"
            note["interrupted_actor_ids"] = unavailable
        result = event(f"{project.label}: {rounds} rounds passed once for the entire scene; stage {project.current_step + 1} has {project.work_rounds}/{project.quote.steps[project.current_step].total_rounds} rounds of work. Status {project.status}.",
            success=not unavailable, changes={"task_project": project.model_dump()})
        return commit(original, session, result, "Advance exclusive task work", boost=False)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def solo_roll(session, project, req):
    person = rules.actor(session, project.request.actor_id)
    step = project.request.steps[project.current_step]
    q = project.quote.steps[project.current_step]
    if req.character_points and req.force_point:
        raise ValueError("A task roll cannot combine Character Points and a Force Point.")
    WEGD6Rules.declare(person.d6, force_point=req.force_point)
    dice, pips = WEGD6Rules.validate_action(person.d6, q.skill, req.character_points)
    if step.mode == "prepared":
        dice += 1
    elif step.mode == "rushed":
        dice, pips = rules.half(dice, step), rules.half(pips, step)
    roll = D6Roller.values(dice, pips, req.character_points)
    person.d6.character_points -= req.character_points
    person.d6.round_state.character_points_spent = bool(req.character_points)
    effects.take_action(person.d6)
    effects.settle_consciousness(person.d6)
    return roll, {"actor_id": person.id, "name": person.name, "cp": req.character_points,
        "fp": req.force_point, "pool_dice": dice, "pool_pips": pips}


def group_roll(session, project, req):
    if req.character_points or req.force_point:
        raise ValueError("Personal points cannot be assigned to an aggregate combined roll; only the saved commander's own Command roll supports them.")
    task = project.request
    coordinated = project.command["coordinated_ids"]
    pools = []
    for id in task.participant_ids:
        person = rules.actor(session, id)
        participating_commander = task.commander_participates and id == task.commander_id
        WEGD6Rules.declare(person.d6, actions=2 if participating_commander else 1)
        if participating_commander:
            # Command and the worker's action are two actions within this scene.
            person.d6.round_state.actions_taken = 1
            person.d6.round_state.force_active = bool(project.command["fp"] and project.quote.steps[0].total_rounds == 1)
        if id in coordinated:
            dice, _ = WEGD6Rules.validate_action(person.d6, project.quote.steps[0].skill)
            pools.append(dice)
        effects.take_action(person.d6)
        effects.settle_consciousness(person.d6)
    average = sum(pools) // len(pools) if pools else 0
    dice = average + project.command["bonus_dice"]
    roll = D6Roller.values(dice) if pools else empty_roll("No workers successfully coordinated")
    return roll, {"actor_ids": coordinated, "average_skill": average, "bonus_dice": project.command["bonus_dice"],
        "pool_dice": dice, "pool_pips": 0, "cp": 0, "fp": False}


@router.post("/resolve")
def resolve(req: D6TaskResolve):
    original = native_session()
    session = original.model_copy(deep=True)
    try:
        scene(session)
        project = project_for(session, req.project_id)
        interrupted = interrupt_changed_clock(original, session, project)
        if interrupted:
            return interrupted
        fit_workers(session, project)
        q = project.quote.steps[project.current_step]
        if project.work_rounds < q.total_rounds:
            raise ValueError("Complete this stage's actual preparation and work time before resolving its check.")
        roll, spending = group_roll(session, project, req) if project.quote.combined else solo_roll(session, project, req)
        success = roll.total >= q.difficulty and (not project.quote.combined or bool(project.command["coordinated_ids"]))
        note = {"step": project.current_step, "skill": q.skill, "mode": q.mode, "difficulty": q.difficulty,
            "rounds": project.work_rounds, "success": success, "roll": roll.model_dump(), **spending}
        project.results.append(note)
        project.declarations.append({"role": "stage_resolution", "exclusive": True, **note})
        if not success:
            project.status = "failed"
        elif project.current_step + 1 == len(project.quote.steps):
            project.status = "completed"
        else:
            project.current_step += 1
            project.work_rounds = 0
        result = RuleEvaluationResult(action_type="skill_check", success=success, roll_result=roll, target_value=q.difficulty,
            summary=f"[WEG Scene Task] {project.label}, {q.skill.replace('_', ' ')}: {roll.breakdown} vs {q.difficulty}; {'success' if success else 'failed'}. Project {project.status}. This records the declared task check; paid repairs and other mechanical benefits use their dedicated workflow.",
            state_changes={"task_project": project.model_dump()})
        return commit(original, session, result, "Resolve declared task stage", boost=False)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/cancel")
def cancel(req: D6TaskManage):
    original = native_session()
    session = original.model_copy(deep=True)
    try:
        scene(session)
        project = project_for(session, req.project_id)
        if not req.reason.strip():
            raise ValueError("Record why this declared task was abandoned.")
        project.status = "cancelled"
        return commit(original, session, event(f"{project.label}: cancelled; recorded work and actual Command point costs remain. {req.reason.strip()}",
            changes={"task_project": project.model_dump()}), "Cancel scene task", boost=False)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
