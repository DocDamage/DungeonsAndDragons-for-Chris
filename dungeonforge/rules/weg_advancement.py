"""1992 WEG40055 advancement, printed pp.10–15 and 145–147.

Training weeks follow the explicit seven-day example on printed p.14. A
Standard Month is 35 days (printed p.132). Standalone power study duration is
GM supplied because the book gives a CP cost but no separate duration.
"""
from dataclasses import dataclass
import math

from dungeonforge.rules.weg_d6 import D6Roller, WEGD6Rules, parse_code, skill_key
from dungeonforge.rules.weg_models import ATTRIBUTES, SKILL_ATTRIBUTES
from dungeonforge.rules.weg_force_catalog import POWERS, training_errors, automatic_known_powers
from dungeonforge.rules.weg_advancement_models import D6TrainingQuote, D6PowerGrant

FORCE_SKILLS = {"control", "sense", "alter"}
WEEK = 7
MONTH = 35


def pips(code):
    dice, extra = parse_code(code)
    return dice * 3 + extra


def code(value):
    if not 0 <= value <= 152:
        raise ValueError("Advancement exceeds the supported 50D+2 sheet limit.")
    dice, extra = divmod(value, 3)
    return f"{dice}D" + (f"+{extra}" if extra else "")


@dataclass
class Trainer:
    id: str
    name: str
    attributes: dict
    skills: dict
    skill_attributes: dict
    specialization_parents: dict
    force_skills: dict
    known_powers: list
    full_time: bool = False
    studying_with_master: bool = False
    person: object = None

    def rating(self, skill):
        if skill in FORCE_SKILLS:
            return pips(self.force_skills.get(skill, "0D"))
        if skill in ATTRIBUTES:
            return pips(self.attributes.get(skill, "0D"))
        if skill in self.skills:
            return pips(self.skills[skill])
        parent = self.specialization_parents.get(skill)
        attribute = self.skill_attributes.get(skill) or SKILL_ATTRIBUTES.get(skill) or self.skill_attributes.get(parent) or SKILL_ATTRIBUTES.get(parent)
        return pips(self.attributes.get(attribute, "0D"))


def teacher_qualifies(teacher, key, target, *, parent=None, force=False):
    if teacher is None:
        return
    if force:
        if teacher.studying_with_master:
            raise ValueError("A Jedi studying with a master cannot take a pupil.")
        if teacher.rating(key) < max(9, target):
            raise ValueError(f"The instructor needs at least 3D and the student's target {code(target)} in {key}.")
    elif key in ATTRIBUTES:
        if teacher.rating(key) < target:
            raise ValueError("The instructor's attribute must equal or exceed the student's new attribute.")
    else:
        basic = parent or key
        choices = [teacher.rating(basic)]
        choices += [teacher.rating(name) for name, base in teacher.specialization_parents.items() if base == basic]
        if max(choices) < target:
            raise ValueError(f"The instructor needs {code(target)} in the basic skill or one of its specializations.")


def learn_powers(state, power_ids, *, skill=None, teacher=None, require_known=False):
    """Validate the entire selected set before changing any learned powers."""
    if len(power_ids) != len(set(power_ids)):
        raise ValueError("Choose each new power only once.")
    already_known = automatic_known_powers(state)
    for id in power_ids:
        spec = POWERS.get(id)
        if not spec or id in already_known:
            raise ValueError("Choose an unlearned power from the 1992 corebook.")
        if skill and skill not in spec.skills:
            raise ValueError(f"{spec.name} does not use the Force skill being trained.")
        if require_known and (teacher is None or id not in teacher.known_powers):
            raise ValueError("The instructor must know each included Force power.")
        if require_known:
            for required_skill in spec.skills:
                teacher_qualifies(teacher, required_skill, pips(state.force_skills[required_skill]), force=True)
    trial = state.model_copy(deep=True)
    trial.force.known_powers = already_known
    trial.force.known_powers.extend(power_ids)
    errors = training_errors(trial)
    if errors:
        raise ValueError(" ".join(errors))
    return trial.force.known_powers


def quote(state, req, adventure, teacher=None, race="Human", *, check_limit=True):
    if state.droid:
        raise ValueError("Use Droid engineering for software and hardware work; organic study times and Force training do not apply to Droids.")
    key = skill_key(req.key)
    kind = req.kind
    old, new, attribute, parent = "", "", None, None
    base_cp, days, minimum, slots, additional_days = 0, 0, 1, 0, 0
    notes, eligible = [], []
    maximum = None
    is_force = kind in {"force_skill", "force_power"}
    if req.powers and kind != "force_skill":
        raise ValueError("Included powers are selected only with Force skill training; use Force power training for a separate power.")
    if req.power_days_saved and kind != "force_skill":
        raise ValueError("Additional power time reductions apply only to a power bundled with a Force skill increase.")
    if kind in {"skill", "advanced", "specialization"}:
        if not key or key in ATTRIBUTES or key in FORCE_SKILLS:
            raise ValueError("Enter a skill name; attributes and Force skills use their own training options.")
        if kind == "advanced":
            if key != "medicine":
                raise ValueError("Medicine is the advanced skill supplied by this corebook; other advanced skills need GM rules.")
            first_aid, _ = WEGD6Rules.skill_code(state, "first_aid")
            if pips(first_aid) < 15:
                raise ValueError("Medicine requires at least 5D in First Aid before study begins.")
            if teacher and key not in teacher.skills:
                raise ValueError("The instructor must actually possess the advanced Medicine skill.")
            attribute = "technical"
            old = state.skills.get(key, "0D")
            new = code(pips(old) + 1) if key in state.skills else "1D"
            base_cp = 2 * max(1, parse_code(old)[0])
        elif kind == "specialization":
            parent = state.specialization_parents.get(key) or skill_key(req.parent_skill or "")
            if not parent or parent == key or parent in state.specializations or parent in FORCE_SKILLS or parent in ATTRIBUTES or parent in state.advanced_skills:
                raise ValueError("Choose an ordinary basic skill as the specialization's parent.")
            if (key in state.skills and key not in state.specializations) or key in SKILL_ATTRIBUTES:
                raise ValueError("A basic skill cannot be relabeled as a cheaper specialization.")
            if req.parent_skill and skill_key(req.parent_skill) != parent:
                raise ValueError("This specialization already belongs to a different basic skill.")
            old, attribute = WEGD6Rules.skill_code(state, key if key in state.skills else parent)
            new = code(pips(old) + 1)
            base_cp = max(1, math.ceil(parse_code(old)[0] / 2))
        else:
            if key in state.advanced_skills or key in state.specializations:
                raise ValueError("Use the advanced skill or specialization training option for this skill.")
            attribute = state.skill_attributes.get(key) or SKILL_ATTRIBUTES.get(key) or req.attribute
            if attribute not in ATTRIBUTES:
                raise ValueError("Assign a new custom skill to one of the six native attributes.")
            if key not in SKILL_ATTRIBUTES and key not in state.skills and teacher is None:
                raise ValueError("A new unusual/custom skill requires a suitable instructor and GM-confirmed facilities.")
            old = state.skills.get(key, state.attributes[attribute])
            new = code(pips(old) + 1)
            base_cp = max(1, parse_code(old)[0])
        days = 3 if pips(old) <= 12 else WEEK if pips(old) <= 21 else 2 * WEEK
        if kind == "advanced":
            days *= 3
        if teacher is None:
            days *= 2
        teacher_qualifies(teacher, key, pips(new), parent=parent)
    elif kind == "attribute":
        if key not in ATTRIBUTES:
            raise ValueError("Choose one of the six native attributes.")
        if any(item.status == "suspended" and item.quote.key == key and adventure <= (item.finished_adventure or item.started_adventure) for item in state.advancement.history):
            raise ValueError("This attribute's failed increase is suspended until after the next adventure.")
        old, new = state.attributes[key], code(pips(state.attributes[key]) + 1)
        maximum = state.species_attribute_maximums.get(key) or ("4D" if race.lower() == "human" else None)
        if maximum is None or pips(maximum) < 3:
            raise ValueError("Record this species' attribute maximum in the GM sheet before attribute training.")
        base_cp = parse_code(old)[0] * 10
        days = (2 if pips(old) <= 12 else 6) * MONTH * (1 if teacher else 2)
        teacher_qualifies(teacher, key, pips(new))
        for name, value in state.skills.items():
            parent_skill = state.specialization_parents.get(name)
            governed_by = state.skill_attributes.get(name) or SKILL_ATTRIBUTES.get(name) or state.skill_attributes.get(parent_skill) or SKILL_ATTRIBUTES.get(parent_skill)
            if governed_by == key and name not in state.advanced_skills:
                code(pips(value) + 1)
        notes.append("At completion, roll unmodified current attribute against the species maximum; ties succeed. All governed skills and specializations rise one pip, except advanced skills.")
    elif kind == "force_skill":
        if key not in FORCE_SKILLS or not state.force_sensitive:
            raise ValueError("Force skill study requires Force sensitivity and Control, Sense, or Alter.")
        old = state.force_skills[key]
        initial = parse_code(old)[0] == 0
        if initial and teacher is None:
            raise ValueError("Learning a new Force skill requires an instructor with at least 3D in that skill.")
        new = "1D" if initial else code(pips(old) + 1)
        teacher_qualifies(teacher, key, pips(new), force=True)
        base_cp = 20 if initial else parse_code(old)[0] * (1 if teacher else 2)
        days = 10 * WEEK if initial else WEEK if teacher else MONTH
        minimum = 1 if teacher else WEEK
        slots = 3 if initial else 1 if teacher else 0
        trial = state.model_copy(deep=True)
        trial.force_skills[key] = new
        trial.force.known_powers = automatic_known_powers(trial)
        eligible = [id for id, spec in POWERS.items() if key in spec.skills and id not in trial.force.known_powers and teacher and id in teacher.known_powers]
        if initial and key == "control" and state.origin.force_tradition == "tyia":
            notes.append("Tyia automatically grants Hibernation Trance and Emptiness when Control is learned, plus the three additional ordinary Control choices.")
        if (initial and len(req.powers) > 3) or (not initial and len(req.powers) > 1):
            raise ValueError("Initial Force training includes up to three powers; a pip increase permits one new power.")
        if req.powers:
            learn_powers(trial, req.powers, skill=key, teacher=teacher, require_known=bool(teacher and (initial or all(id in teacher.known_powers for id in req.powers))))
            if not initial and (teacher is None or req.powers[0] not in teacher.known_powers):
                base_cp += 5 if teacher else 10
                additional_days = WEEK
                slots = 0
                notes.append("The selected power is independently researched: +5 CP with a skill instructor, +10 CP without one, and one additional training week.")
        if req.power_days_saved > max(0, additional_days - 1):
            raise ValueError("There is no reducible additional power-study week for this selection.")
        if initial:
            notes.append("The skill begins at 1D only after study; three included power selections are recorded. Unselected choices remain tied to this instructor, not usable powers.")
        elif teacher is None:
            notes.append("Unaided Force skill improvement doubles the CP cost and requires a month; extra CP can reduce it to one week.")
    elif kind == "force_power":
        spec = POWERS.get(key)
        if not spec:
            raise ValueError("Choose a Force power in the 1992 corebook.")
        learn_powers(state, [key])
        if teacher:
            for skill in spec.skills:
                teacher_qualifies(teacher, skill, pips(state.force_skills[skill]), force=True)
        base_cp = 5 if teacher and key in teacher.known_powers else 10
        days = req.gm_study_days
        notes.append("Standalone power study time is set by the GM; the corebook states the 5/10 CP cost without a separate duration. No Force skill pip is gained.")
        old, new = "Unlearned", spec.name
    elif kind == "sensitivity":
        if state.force_sensitive:
            raise ValueError("This character is already Force sensitive.")
        if "droid" in race.lower():
            raise ValueError("Droids cannot gain Force sensitivity through this organic-character rule.")
        key, old, new, base_cp = "force_sensitive", "No", "Yes (+1 Force Point)", 20
        notes.append("Sensitivity is permanent and grants one Force Point immediately; it does not grant Force skills or powers.")
    elif kind == "move":
        maximum_move = state.move_maximum or (12 if race.lower() == "human" else None)
        if maximum_move is None:
            raise ValueError("Record the species' maximum Move in the GM sheet first.")
        if state.move >= maximum_move:
            raise ValueError("Move is already at the species maximum.")
        key, old, new, base_cp = "move", str(state.move), str(state.move + 1), state.move
        notes.append("Move increases one meter per purchase and cannot exceed the species maximum. The corebook gives no training duration for this purchase.")
    if kind in {"skill", "specialization", "advanced", "force_skill"} and check_limit and state.advancement.improved.get(f"{kind}:{key}") == adventure:
        raise ValueError("This skill has already been advanced one pip for this adventure. Record the next adventure before increasing it again.")
    if kind == "attribute" or days == 0:
        if req.days_saved:
            raise ValueError("Extra Character Points cannot shorten attribute training or an immediate purchase.")
    elif req.days_saved > days - minimum:
        raise ValueError(f"Training cannot be reduced below {minimum} day(s).")
    days = days - req.days_saved + additional_days - req.power_days_saved
    if is_force and teacher and teacher.studying_with_master:
        raise ValueError("A Jedi currently studying with a master cannot teach Force training.")
    return D6TrainingQuote(kind=kind, key=key, old_code=old, new_code=new, attribute=attribute, parent_skill=parent,
        cp_cost=base_cp + req.days_saved + req.power_days_saved, base_cp=base_cp, days=days,
        teacher_id=teacher.id if teacher else None, teacher_name=teacher.name if teacher else None,
        powers=req.powers if kind == "force_skill" else [key] if kind == "force_power" else [],
        power_slots=slots, eligible_powers=eligible, species_maximum=maximum, notes=notes,
        source="WEG40055 (1992), printed pp.10–15, 132–133, 145–147")


def complete(state, project, adventure, teacher=None):
    q = project.quote
    kind, key = q.kind, q.key
    project.status = "completed"
    project.finished_adventure = adventure
    if kind == "attribute":
        if state.attributes[key] != q.old_code:
            raise ValueError("The attribute changed during study; resolve the course or GM adjustment before completion.")
        student = D6Roller.roll(q.old_code)
        maximum = D6Roller.roll(q.species_maximum)
        project.student_roll, project.maximum_roll = student.model_dump(), maximum.model_dump()
        if student.total > maximum.total:
            project.status = "suspended"
            return f"Attribute check {student.total} > species maximum roll {maximum.total}: no increase. {q.cp_cost} CP remain suspended until after the next adventure."
        state.attributes[key] = q.new_code
        for name, value in list(state.skills.items()):
            parent = state.specialization_parents.get(name)
            attribute = state.skill_attributes.get(name) or SKILL_ATTRIBUTES.get(name) or state.skill_attributes.get(parent) or SKILL_ATTRIBUTES.get(parent)
            if attribute == key and name not in state.advanced_skills:
                state.skills[name] = code(pips(value) + 1)
    elif kind in {"skill", "advanced", "specialization"}:
        state.skills[key] = q.new_code
        state.skill_attributes[key] = q.attribute
        if kind == "advanced" and key not in state.advanced_skills:
            state.advanced_skills.append(key)
        if kind == "specialization":
            if key not in state.specializations:
                state.specializations.append(key)
            state.specialization_parents[key] = q.parent_skill
    elif kind == "force_skill":
        trial = state.model_copy(deep=True)
        trial.force_skills[key] = q.new_code
        known = learn_powers(trial, q.powers, skill=key, teacher=teacher, require_known=q.power_slots > 0)
        state.force_skills[key] = q.new_code
        state.force.known_powers = known
        remaining = q.power_slots - len(q.powers)
        if remaining > 0 and teacher:
            state.advancement.power_grants.append(D6PowerGrant(skill=key, remaining=remaining, teacher_id=teacher.id,
                allowed_powers=q.eligible_powers, project_id=project.id))
    elif kind == "force_power":
        state.force.known_powers = learn_powers(state, [key])
    elif kind == "sensitivity":
        state.force_sensitive = True
        state.force_points += 1
    elif kind == "move":
        state.move += 1
    if kind in {"skill", "advanced", "specialization", "force_skill"}:
        state.advancement.improved[f"{kind}:{key}"] = adventure
    return f"{key.replace('_', ' ').title()}: {q.old_code} → {q.new_code}. Training complete; {q.cp_cost} CP already paid."
