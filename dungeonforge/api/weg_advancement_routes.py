"""Transactional CP spending and explicit intensive downtime, never passive XP."""
from fastapi import APIRouter, HTTPException

from dungeonforge.api.weg_routes import native_session
from dungeonforge.api.weg_force_routes import commit
from dungeonforge.game import weg_force as world
from dungeonforge.rules import weg_advancement as rules
from dungeonforge.rules.base import RuleEvaluationResult
from dungeonforge.rules.weg_d6 import skill_key
from dungeonforge.rules.weg_models import ATTRIBUTES, D6Character, normalize_code
from dungeonforge.rules.weg_force import empty_roll
from dungeonforge.rules.weg_force_catalog import POWERS, training_errors
from dungeonforge.rules import weg_force_effects as effects
from dungeonforge.rules import weg_rewards as reward_rules
from dungeonforge.game.weg_rewards import synchronize as sync_rewards
from dungeonforge.rules.weg_reward_models import AdventureRewardRequest, AdventureRewardRecord
from dungeonforge.rules.weg_advancement_models import (
    D6AdventureRequest, D6AdvancementActorRequest, D6AwardRequest, D6Instructor,
    D6PowerGrantRequest, D6StudyRequest, D6TrainingProject, D6TrainingRequest,
)

router = APIRouter(prefix="/api/weg-d6/advancement", tags=["Native WEG advancement and Force training"])


def working():
    original = native_session()
    return original, original.model_copy(deep=True)


def downtime(session):
    if (session.encounter and session.encounter.active) or session.vehicle_encounter:
        raise ValueError("End the personal or craft encounter before training, awards, or recording an adventure boundary.")


def people(session):
    return {person.id: person for person in [session.character, *session.character.companions] if person.d6}


def student(session, id=None):
    person = people(session).get(id or session.character.id)
    if person is None:
        raise ValueError("Choose a native party member as the student.")
    return person


def fit_to_study(person):
    state = person.d6
    if state.corruption.pending_demand or state.corruption.dead or state.wound not in {"healthy", "wounded"} or state.unconscious_rounds or effects.sleeping(state) or state.force.attempt:
        raise ValueError(f"{person.name} must be conscious, free of a pending Force activation/trance, and well enough for intensive study.")


def trainer(session, id, student_id):
    if not id:
        return None
    if id == student_id:
        raise ValueError("Self-study does not qualify as having an instructor.")
    person = people(session).get(id)
    if person:
        from dungeonforge.game.weg_task_guards import require_available
        require_available(session, person.id)
        fit_to_study(person)
        state = person.d6
        project = state.advancement.project
        return rules.Trainer(id, person.name, state.attributes, state.skills, state.skill_attributes, state.specialization_parents,
            state.force_skills, state.force.known_powers, studying_with_master=bool(project and project.quote.kind in {"force_skill", "force_power"} and project.quote.teacher_id), person=state)
    record = next((item for item in session.d6_advancement.instructors if item.id == id), None)
    if not record:
        raise ValueError("The selected instructor is no longer available. Register or restore that instructor before study.")
    if record.corruption.dead or record.corruption.pending_demand:
        raise ValueError("The instructor must be alive and free of a Dark Side demand.")
    return rules.Trainer(record.id, record.name, record.attributes, record.skills, record.skill_attributes, record.specialization_parents,
        record.force_skills, record.known_powers, record.full_time, record.studying_with_master, record)


def capacity(session, teacher, student_id, kind):
    if not teacher or teacher.full_time or kind not in {"force_skill", "force_power"}:
        return
    for person in people(session).values():
        project = person.d6.advancement.project
        if person.id != student_id and project and project.quote.teacher_id == teacher.id and project.quote.kind in {"force_skill", "force_power"}:
            raise ValueError("This Jedi already has a pupil in training. A GM-recorded full-time NPC instructor may teach a small group.")


def event(summary, *, success=True, changes=None, category="Advancement"):
    return RuleEvaluationResult(action_type=category.lower().replace(" ", "_"), success=success, roll_result=empty_roll(f"{category} record"), summary=f"[WEG D6 {category}] {summary}", state_changes=changes or {})


def archive(person, project):
    person.d6.advancement.history.append(project)
    person.d6.advancement.project = None


@router.get("/state")
def state():
    session = native_session().model_copy(deep=True)
    sync_rewards(session)
    members = people(session)
    return {"campaign": session.d6_advancement, "actors": [{"id": person.id, "name": person.name, "race": person.race, "d6": person.d6} for person in members.values()],
        "rules": {"training_week_days": rules.WEEK, "standard_month_days": rules.MONTH,
            "notes": ["Training weeks use the explicit seven-day example on printed p.14; Standard Months are 35 days (p.132).", "Advanced training follows the 4D / 7D bands; the later 'above 6D' example conflicts with those bands.", "Standalone Force power study duration is GM supplied. Unaided bundled power research uses the standalone 10 CP rate.", "Failed attribute CP remain suspended until the next adventure, when the GM may release them; no automatic increase or refund.", "This workflow covers standard organic-character advancement, not Droid programming, Tyia, or other species-specific exceptions."]}}


@router.post("/instructor")
def save_instructor(req: D6Instructor):
    original, session = working()
    try:
        downtime(session)
        if req.id in people(session):
            raise ValueError("Party members already use their live sheets as instructors; do not overwrite their identity.")
        if any(key not in ATTRIBUTES for key in [*req.attributes, *req.skill_attributes.values()]):
            raise ValueError("Instructor attributes and governing attributes must use the six native names.")
        if any(key not in rules.FORCE_SKILLS for key in req.force_skills):
            raise ValueError("Instructor Force skills must be Control, Sense, or Alter.")
        req.name = req.name.strip()
        if not req.name:
            raise ValueError("Name the GM-approved instructor.")
        req.attributes = {key: normalize_code(value) for key, value in req.attributes.items()}
        req.skills = {skill_key(key): normalize_code(value) for key, value in req.skills.items()}
        req.force_skills = {key: normalize_code(value) for key, value in req.force_skills.items()}
        req.skill_attributes = {skill_key(key): value for key, value in req.skill_attributes.items()}
        req.specialization_parents = {skill_key(key): skill_key(value) for key, value in req.specialization_parents.items()}
        if any(key == value or value in req.specialization_parents for key, value in req.specialization_parents.items()):
            raise ValueError("Instructor specializations must name a basic parent without cycles.")
        trial = D6Character(force_sensitive=any(rules.pips(value) for value in req.force_skills.values()), force_skills=req.force_skills)
        trial.force.known_powers = req.known_powers
        errors = training_errors(trial)
        if errors:
            raise ValueError(" ".join(errors))
        index = next((i for i, item in enumerate(session.d6_advancement.instructors) if item.id == req.id), None)
        if index is None:
            if len(session.d6_advancement.instructors) >= 50:
                raise ValueError("The instructor roster supports up to fifty NPCs.")
            session.d6_advancement.instructors.append(req)
        else:
            previous = session.d6_advancement.instructors[index]
            req.dark_side_points, req.dark_side_consumed = previous.dark_side_points, previous.dark_side_consumed
            req.corruption, req.character_points, req.force_points = previous.corruption, previous.character_points, previous.force_points
            session.d6_advancement.instructors[index] = req
        return commit(original, session, event(f"GM records instructor {req.name}. Ratings and known powers are recorded; no student receives training or points."), f"Instructor: {req.name}", boost=False)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/quote")
def quote(req: D6TrainingRequest):
    session = native_session()
    try:
        person = student(session, req.actor_id)
        teacher = trainer(session, req.teacher_id, person.id)
        result = rules.quote(person.d6, req, session.d6_advancement.adventure, teacher, person.race)
        return {"quote": result, "affordable": person.d6.character_points >= result.cp_cost}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/start")
def start(req: D6TrainingRequest):
    original, session = working()
    try:
        downtime(session)
        person = student(session, req.actor_id)
        from dungeonforge.game.weg_task_guards import require_available
        require_available(session, person.id)
        fit_to_study(person)
        if "droid" in person.race.lower():
            raise ValueError("Droid training uses programming rules and GM-set times; this workflow implements standard organic training.")
        if person.d6.advancement.project:
            raise ValueError("Complete or cancel the student's current intensive study project first.")
        teacher = trainer(session, req.teacher_id, person.id)
        capacity(session, teacher, person.id, req.kind)
        q = rules.quote(person.d6, req, session.d6_advancement.adventure, teacher, person.race)
        if person.d6.character_points < q.cp_cost:
            raise ValueError(f"Training costs {q.cp_cost} Character Points; only {person.d6.character_points} remain.")
        if req.kind == "sensitivity" and person.d6.force_points >= 1_000_000:
            raise ValueError("Force Point storage limit reached.")
        person.d6.character_points -= q.cp_cost
        project = D6TrainingProject(request=req, quote=q, started_adventure=session.d6_advancement.adventure)
        if q.kind in {"skill", "advanced", "specialization", "force_skill"}:
            person.d6.advancement.improved[f"{q.kind}:{q.key}"] = session.d6_advancement.adventure
        person.d6.advancement.project = project
        summary = f"{person.name} pays {q.cp_cost} CP to study {q.key.replace('_', ' ')}: {q.old_code} → {q.new_code}; {q.days} intensive day(s), " + (f"instructor {teacher.name}." if teacher else "self-study.")
        if not q.days:
            summary += " " + rules.complete(person.d6, project, session.d6_advancement.adventure, teacher)
            archive(person, project)
        elif teacher and q.kind in {"force_skill", "force_power"} and person.d6.dark_side_points:
            summary += " Teaching this student will award the instructor one Dark Side Point when instruction starts."
        return commit(original, session, event(summary), f"{person.name}: start {q.key} training", boost=False)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/study")
def study(req: D6StudyRequest):
    original, session = working()
    try:
        downtime(session)
        ids = req.actor_ids or [session.character.id]
        if len(ids) != len(set(ids)):
            raise ValueError("Choose each student only once; shared study time passes only once.")
        selected = [student(session, id) for id in ids]
        from dungeonforge.game.weg_task_guards import require_available
        require_available(session, *ids)
        instructors = {}
        for person in selected:
            fit_to_study(person)
            project = person.d6.advancement.project
            if not project or project.status != "studying":
                raise ValueError(f"{person.name} has no active intensive study project.")
            if req.days > project.quote.days - project.days_completed:
                raise ValueError(f"{person.name} needs only {project.quote.days - project.days_completed} more day(s); record no more than that amount.")
            teacher = trainer(session, project.quote.teacher_id, person.id)
            capacity(session, teacher, person.id, project.quote.kind)
            current = rules.quote(person.d6, project.request, session.d6_advancement.adventure, teacher, person.race, check_limit=False)
            if current.old_code != project.quote.old_code or current.new_code != project.quote.new_code or current.attribute != project.quote.attribute or current.species_maximum != project.quote.species_maximum:
                raise ValueError("The student's rank or governing attribute changed during study; cancel or resolve the GM adjustment first.")
            if project.quote.kind == "force_skill" and project.quote.power_slots > 0:
                trial = person.d6.model_copy(deep=True, update={"force_skills": {**person.d6.force_skills, project.quote.key: project.quote.new_code}})
                rules.learn_powers(trial, project.quote.powers, skill=project.quote.key, teacher=teacher, require_known=True)
            if project.quote.kind == "force_power" and project.quote.base_cp == 5 and (teacher is None or project.quote.key not in teacher.known_powers):
                raise ValueError("This power was priced as instructor-taught; the instructor must still know it.")
            instructors[person.id] = teacher
        # Quiet time is real scene time; stuns, Force effects, mortality and craft
        # countdowns advance once even when several selected students study.
        world.advance_scene(session, req.days * 17280)
        summaries, completed_attributes = [], []
        for person in selected:
            project = person.d6.advancement.project
            teacher = instructors[person.id]
            if person.d6.wound not in {"healthy", "wounded"} or person.d6.unconscious_rounds:
                summaries.append(f"{person.name}'s study was interrupted by injury; time passed but no intensive days were credited.")
                continue
            if teacher and isinstance(teacher.person, D6Character) and (teacher.person.wound not in {"healthy", "wounded"} or teacher.person.unconscious_rounds):
                summaries.append(f"{person.name}'s instructor was injured during downtime; time passed but no intensive days were credited.")
                continue
            if teacher and project.quote.kind in {"force_skill", "force_power"} and person.d6.dark_side_points and not project.teacher_dark_side_awarded:
                from dungeonforge.rules.weg_dark_side import gain_point
                gain_point(teacher.person, f"Teaching {person.name}, who has Dark Side Points.", "force_teaching")
                project.teacher_dark_side_awarded = True
                summaries.append(f"{teacher.name} receives one Dark Side Point for teaching a student with Dark Side Points.")
            project.days_completed += req.days
            if project.days_completed == project.quote.days:
                note = rules.complete(person.d6, project, session.d6_advancement.adventure, teacher)
                if project.quote.kind == "attribute":
                    completed_attributes.append(project)
                summaries.append(f"{person.name}: {note}")
                archive(person, project)
            else:
                summaries.append(f"{person.name}: {project.days_completed}/{project.quote.days} intensive days completed; rank unchanged.")
        result = event(f"{req.days} day(s) passed. " + " ".join(summaries))
        for last in completed_attributes:
            if last.student_roll:
                from dungeonforge.rules.dice import RollResult
                result.roll_result = RollResult.model_validate(last.student_roll)
                result.resistance_roll = RollResult.model_validate(last.maximum_roll)
                result.success = last.status != "suspended"
        return commit(original, session, result, "Intensive training", boost=False)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/cancel")
def cancel(req: D6AdvancementActorRequest):
    original, session = working()
    try:
        downtime(session)
        person = student(session, req.actor_id)
        project = person.d6.advancement.project
        if not project:
            raise ValueError("No active study project to cancel.")
        project.status = "cancelled"
        project.finished_adventure = session.d6_advancement.adventure
        archive(person, project)
        return commit(original, session, event(f"{person.name} abandons {project.quote.key} study. Spent CP and study days are not refunded; the adventure's skill increase reservation remains used."), "Cancel training", boost=False)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/release-suspended")
def release(req: D6AdvancementActorRequest):
    original, session = working()
    try:
        downtime(session)
        person = student(session, req.actor_id)
        project = next((item for item in person.d6.advancement.history if item.id == req.project_id and item.status == "suspended"), None)
        if not project or session.d6_advancement.adventure <= (project.finished_adventure or project.started_adventure):
            raise ValueError("Suspended attribute CP may be released by the GM only after the next adventure boundary.")
        if person.d6.character_points + project.quote.cp_cost > 1_000_000:
            raise ValueError("Character Point storage limit reached.")
        person.d6.character_points += project.quote.cp_cost
        project.status = "released"
        return commit(original, session, event(f"GM releases {project.quote.cp_cost} suspended CP to {person.name} after the next adventure; no attribute increase is granted."), "Release suspended CP", boost=False)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/claim-power")
def claim_power(req: D6PowerGrantRequest):
    original, session = working()
    try:
        downtime(session)
        person = student(session, req.actor_id)
        fit_to_study(person)
        grant = next((item for item in person.d6.advancement.power_grants if item.id == req.grant_id and item.remaining), None)
        if not grant or req.power_id not in grant.allowed_powers:
            raise ValueError("Select an unspent included power choice offered by that completed course.")
        teacher = trainer(session, grant.teacher_id, person.id)
        capacity(session, teacher, person.id, "force_power")
        rules.teacher_qualifies(teacher, grant.skill, rules.pips(person.d6.force_skills[grant.skill]), force=True)
        person.d6.force.known_powers = rules.learn_powers(person.d6, [req.power_id], skill=grant.skill, teacher=teacher, require_known=True)
        course = next((item for item in person.d6.advancement.history if item.id == grant.project_id), None)
        if person.d6.dark_side_points and course and not course.teacher_dark_side_awarded:
            from dungeonforge.rules.weg_dark_side import gain_point
            gain_point(teacher.person, f"Teaching {person.name}, who has Dark Side Points.", "force_teaching")
            course.teacher_dark_side_awarded = True
        grant.remaining -= 1
        return commit(original, session, event(f"{person.name} selects {POWERS[req.power_id].name} from an included {grant.skill} course choice taught by {teacher.name}. No extra CP or skill pip is granted."), "Select included Force power", boost=False)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/award")
def award(req: D6AwardRequest):
    original, session = working()
    try:
        downtime(session)
        person = student(session, req.actor_id)
        from dungeonforge.rules.weg_dark_side import fallen
        if req.points and fallen(person.d6):
            raise ValueError("Consumed characters do not receive adventuring CP awards; they receive one CP when they gain a Dark Side Point.")
        if not req.reason.strip() or person.d6.character_points + req.points > 1_000_000:
            raise ValueError("Record a reason and keep the CP balance within the supported limit.")
        person.d6.character_points += req.points
        return commit(original, session, event(f"GM awards {person.name} {req.points} Character Points. Reason: {req.reason.strip()}"), "GM Character Point award", boost=False)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/adventure")
def next_adventure(req: D6AdventureRequest):
    original, session = working()
    try:
        downtime(session)
        if not req.label.strip():
            raise ValueError("Name the completed adventure or new training window.")
        sync_rewards(session)
        if any(reward_rules.pending(person.d6, session.d6_advancement.adventure) for person in people(session).values()):
            raise ValueError("Review pending Force Point uses with Finish adventure & award rewards before opening the next adventure.")
        session.d6_advancement.adventure += 1
        session.d6_advancement.label = req.label.strip()
        for person in people(session).values():
            person.d6.rewards.starting_force_points = person.d6.force_points
            person.d6.rewards.baseline_known = True
        return commit(original, session, event(f"GM records adventure boundary {session.d6_advancement.adventure}: {req.label.strip()}. One-pip skill eligibility renews; CP, study time and Force Points are unchanged."), "Next adventure boundary", boost=False)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def reward_transaction(req):
    original, session = working()
    downtime(session)
    if req.adventure != session.d6_advancement.adventure:
        raise ValueError("This adventure has already closed or the review is stale. Refresh the reward review.")
    if req.expected_updated_at != session.updated_at:
        raise ValueError("The session changed after this review. Refresh and preview the current rewards before finishing.")
    if not req.next_label.strip():
        raise ValueError("Name the next adventure.")
    sync_rewards(session)
    members = people(session)
    ids = [item.actor_id for item in req.actors]
    if len(ids) != len(set(ids)) or set(ids) != set(members):
        raise ValueError("Review every native party member exactly once before closing the adventure.")
    records = [reward_rules.settle(members[item.actor_id].d6, item, req.adventure) for item in req.actors]
    record = AdventureRewardRecord(adventure=req.adventure, label=session.d6_advancement.label, actors=records)
    session.d6_advancement.rewards.append(record)
    session.d6_advancement.adventure += 1
    session.d6_advancement.label = req.next_label.strip()
    return original, session, record


@router.post("/reward-quote")
def reward_quote(req: AdventureRewardRequest):
    try:
        _, _, record = reward_transaction(req)
        return {"quote": record}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/finish-adventure")
def finish_adventure(req: AdventureRewardRequest):
    try:
        original, session, record = reward_transaction(req)
        summaries = []
        members = people(session)
        for item in record.actors:
            summaries.append(f"{members[item['actor_id']].name}: {item['force_returned']} FP returned, {item['zero_point_award']} zero-start heroic FP, {item['character_points_awarded']} adventuring CP; {item['force_converted']} excess FP converted to {item['conversion_cp']} CP. Balances {item['force_points']} FP / {item['character_points']} CP.")
        return commit(original, session, event(f"Adventure {record.adventure} ({record.label}) completed. " + " ".join(summaries), changes={"adventure_rewards": record.model_dump()}), "Finish adventure & award rewards", boost=False)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
