"""Saved software/hardware work, with explicit GM task times and actual rolls."""
from fastapi import APIRouter, HTTPException
from dungeonforge.api.weg_routes import native_session
from dungeonforge.api.weg_force_routes import commit
from dungeonforge.api.weg_advancement_routes import downtime, event, student
from dungeonforge.game.weg_force import advance_scene
from dungeonforge.rules.weg_droid_models import D6DroidWork
from dungeonforge.rules.weg_d6 import WEGD6Rules, skill_key, D6Roller
from dungeonforge.rules.weg_creation import pips, code, SKILLS
from dungeonforge.rules.weg_models import ATTRIBUTES

router = APIRouter(prefix="/api/weg-d6/droids", tags=["Native Droid programming and repairs"])


@router.post("/work")
def work(req: D6DroidWork):
    original = native_session()
    session = original.model_copy(deep=True)
    try:
        downtime(session)
        target = student(session, req.actor_id)
        from dungeonforge.game.weg_task_guards import require_available
        require_available(session, target.id)
        state = target.d6
        if not state.droid or state.droid.destroyed:
            raise ValueError("Choose a native Droid whose chassis is salvageable.")
        if not req.reason.strip():
            raise ValueError("Record the GM-approved task, facilities, materials and duration.")
        if req.credits > session.character.d6.credits:
            raise ValueError("The party cannot afford the recorded software, parts or labor cost.")
        if state.advancement.project or state.corruption.pending_demand:
            raise ValueError("Resolve the Droid's existing study project or pending demand before engineering work.")
        key = skill_key(req.skill)
        parent = state.specialization_parents.get(key) or (skill_key(req.parent_skill) if req.parent_skill else None)
        if parent and (parent == key or parent in state.specializations or parent in {*ATTRIBUTES, "control", "sense", "alter", "medicine"} or key in SKILLS or key in state.skills and key not in state.specializations):
            raise ValueError("A specialization must name a distinct ordinary basic parent; do not relabel an existing basic skill.")
        attribute = state.skill_attributes.get(key) or SKILLS.get(key) or state.skill_attributes.get(parent) or SKILLS.get(parent) or req.attribute
        kind = "advanced" if key == "medicine" else "specialization" if parent else "skill"
        cp, new = 0, None
        if req.operation in {"learn", "refine", "cartridge"}:
            if key in {*ATTRIBUTES, "control", "sense", "alter"} or not key or attribute not in ATTRIBUTES:
                raise ValueError("Choose a basic skill and its governing native attribute.")
            if key == "medicine":
                first_aid, _ = WEGD6Rules.skill_code(state, "first_aid")
                if pips(first_aid) < 15:
                    raise ValueError("Droid Medicine requires at least 5D in First Aid.")
            if req.operation == "learn":
                if key in state.skills:
                    raise ValueError("This skill is already installed; refine it instead.")
                if not req.software_available:
                    raise ValueError("New Droid skills require an introductory software package or equivalent teaching program.")
                basis = state.skills.get(parent, state.attributes[attribute]) if parent else state.attributes[attribute]
                new = 3 if key == "medicine" else pips(basis) + 1
                cp = 2 if key == "medicine" else max(1, (pips(basis) // 3 + 1) // 2) if parent else pips(basis) // 3
            elif req.operation == "refine":
                if key not in state.skills:
                    raise ValueError("A Droid cannot refine an uninstalled skill; install its basic principles first.")
                new, cp = pips(state.skills[key]) + 1, pips(state.skills[key]) // 3
                cp = cp * 2 if key == "medicine" else max(1, (cp + 1) // 2) if parent else cp
            else:
                if not req.software_available:
                    raise ValueError("Record the purchased, compatible skill cartridge before installing it.")
                new = pips(req.cartridge_rating)
                if new <= pips(state.skills.get(key, "0D" if key == "medicine" else state.skills.get(parent, state.attributes[attribute]))):
                    raise ValueError("The cartridge must improve this skill above its current rating.")
            if new > 39:
                raise ValueError("Droid skills have a technology limit of 13D.")
            if req.operation in {"learn", "refine"} and state.advancement.improved.get(f"{kind}:{key}") == session.d6_advancement.adventure:
                raise ValueError("This skill has already improved a pip this adventure.")
            if state.character_points < cp:
                raise ValueError(f"The Droid needs {cp} Character Points to process this improvement.")
        if req.operation != "repair" and not state.can_act:
            raise ValueError("Repair and reactivate the Droid before programming or refinement.")
        parts = None
        if req.operation in {"repair", "attachment"}:
            parts = next((item for item in session.character.inventory if item.name == req.parts_item and item.quantity >= req.parts_quantity), None)
            if not parts:
                raise ValueError("Select enough replacement parts or the attachment from party inventory.")
        if req.operation == "repair" and state.wound == "healthy" and not state.unconscious_rounds and not state.stun_count:
            raise ValueError("This Droid is already operational and undamaged.")
        if req.operation == "task" and not req.task.strip():
            raise ValueError("Describe the specific task to program.")
        if req.operation == "attachment" and not req.attachment.strip():
            raise ValueError("Name the actual attachment and required software.")
        programmer = None
        if req.operation == "refine" and (req.force_point or req.character_points):
            raise ValueError("Refinement processes the Droid's paid CP; it is not a technician's bonus-dice roll.")
        if req.operation != "refine":
            programmer = student(session, req.programmer_id)
            require_available(session, programmer.id)
            if programmer.id == target.id:
                raise ValueError("Use another qualified programmer/technician for new software or hardware work.")
            if not programmer.d6.can_act or programmer.d6.force.attempt:
                raise ValueError("The technician must be conscious and free of another Force activation.")
            if req.character_points > programmer.d6.character_points or req.force_point and programmer.d6.force_points < 1 or req.force_point and req.character_points:
                raise ValueError("The technician needs the selected points and cannot combine CP dice with an FP.")
            if req.operation not in {"repair"} and not req.computer_connected:
                raise ValueError("Programming needs a computer/datapad connected directly to the Droid's memory.")
            if req.operation == "learn":
                if parent:
                    teacher_code = programmer.d6.skills.get(key) or programmer.d6.skills.get(parent) or programmer.d6.attributes[attribute]
                else:
                    teacher_code, _ = WEGD6Rules.skill_code(programmer.d6, key)
                if pips(teacher_code) < new + 6:
                    raise ValueError(f"The programmer needs at least {code(new + 6)} in the new skill (2D above the Droid's initial rating).")
        base = req.difficulty
        if req.operation == "learn" and not 16 <= base <= 20:
            raise ValueError("Teaching rudimentary skill use is Difficult (16–20), before modifiers.")
        if req.operation == "wipe" and not 6 <= base <= 10:
            raise ValueError("A normal memory wipe is Easy (6–10), before modifiers.")
        if req.operation == "repair":
            minimum_minutes = (15, 60, 120)[min(2, state.droid.repair_attempts)]
            if req.minutes < minimum_minutes:
                raise ValueError(f"This repair attempt requires at least {minimum_minutes} minutes (15 minutes, then one hour, then two hours).")
            bands = {"healthy": (6, 10), "wounded": (6, 10), "incapacitated": (16, 20), "mortally_wounded": (21, 30), "dead": (31, 1000)}
            low, high = bands[state.wound]
            if not low <= base <= high:
                raise ValueError(f"This damage requires a repair difficulty of {low}–{high} before modifiers.")
        if req.hardwire and req.operation not in {"learn", "cartridge"}:
            raise ValueError("Hardwiring applies to installing basic skills or skill cartridges.")
        difficulty = base + req.difficulty_modifier + (30 if req.hardwire else 0)
        if difficulty > 1000:
            raise ValueError("The modified task exceeds the supported difficulty range.")
        # Times and commercial prices are GM supplied because the corebook varies them by task.
        advance_scene(session, req.minutes * 12)
        success, roll = True, None
        if programmer:
            if not programmer.d6.can_act:
                result = event("Time passed, but the technician was incapacitated before work finished; no installation, CP or credits charged.", success=False)
                return commit(original, session, result, "Interrupted Droid work", boost=False)
            WEGD6Rules.declare(programmer.d6, force_point=req.force_point)
            dice, extra = WEGD6Rules.validate_action(programmer.d6, "droid_repair" if req.operation in {"repair", "attachment"} else "droid_programming", req.character_points)
            roll = D6Roller.values(dice, extra, req.character_points)
            programmer.d6.character_points -= req.character_points
            programmer.d6.round_state.character_points_spent = bool(req.character_points)
            success = roll.total + req.roll_bonus >= difficulty
        old = state.skills.get(key) if new is not None else state.wound
        session.character.d6.credits -= req.credits
        if req.operation == "repair":
            state.droid.repair_attempts += 1
        if success:
            if new is not None:
                state.character_points -= cp
                state.skills[key], state.skill_attributes[key] = code(new), attribute
                if parent:
                    if key not in state.specializations:
                        state.specializations.append(key)
                    state.specialization_parents[key] = parent
                if req.operation in {"learn", "refine"}:
                    state.advancement.improved[f"{kind}:{key}"] = session.d6_advancement.adventure
                if req.hardwire:
                    state.droid.hardwired_skills[key] = code(new)
                    if parent:
                        state.droid.hardwired_specializations[key] = parent
            elif req.operation == "task":
                state.droid.tasks.append(req.task.strip())
            elif req.operation == "wipe":
                state.skills = dict(state.droid.hardwired_skills)
                state.specializations = list(state.droid.hardwired_specializations)
                state.specialization_parents = dict(state.droid.hardwired_specializations)
                state.droid.tasks.clear()
                state.droid.route_memory.clear()
                state.droid.memory_wipes += 1
            elif req.operation == "repair":
                state.droid.repair_attempts = 0
                state.wound, state.unconscious_rounds, state.mortal_rounds = "healthy", 0, 0
                state.stun_count, state.stun_durations, state.stun_expiries = 0, [], []
                state.round_state.blocked = False
            elif req.operation == "attachment":
                state.droid.equipment.append(req.attachment.strip())
            if parts:
                parts.quantity -= req.parts_quantity
                if parts.quantity == 0:
                    session.character.inventory.remove(parts)
        record = {"operation": req.operation, "skill": key, "old": old, "new": code(new) if success and new is not None else None,
            "cp_spent": cp if success else 0, "credits": req.credits, "minutes": req.minutes, "success": success,
            "reason": req.reason.strip(), "adventure": session.d6_advancement.adventure,
            "technician_cp": req.character_points, "technician_fp": req.force_point,
            "difficulty": difficulty if programmer else None, "roll": roll.model_dump() if roll else None, "roll_bonus": req.roll_bonus}
        state.droid.work_history.append(record)
        result = event(f"{target.name}: {req.operation} {'completed' if success else 'failed'} in {req.minutes} minutes. " +
            (f"{key}: {old or state.attributes[attribute]} → {code(new)}; {cp} CP. " if success and new is not None else "") +
            (f"Roll {roll.total} + GM modifier {req.roll_bonus} vs {difficulty}. " if roll else "") + f"Cost {req.credits} credits. {req.reason.strip()}", success=success, changes={"droid_work": record})
        if roll:
            result.roll_result = roll
            result.target_value = difficulty
        return commit(original, session, result, "Droid engineering", boost=False)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
