"""The 22 powers printed in WEG40055 (1992), PDF pp.136–141 / printed 147–152."""

from pydantic import BaseModel, Field

from dungeonforge.rules.weg_force_models import ForceSkill


RELATIONSHIP = {"close_relative": 0, "close_friend": 2, "friend": 5, "acquaintance": 7, "slight_acquaintance": 10, "met_once": 12, "reputation": 15, "stranger": 20, "alien_stranger": 30}
PROXIMITY = {"touching": 0, "line_of_sight": 2, "hidden_nearby": 5, "nearby_km": 7, "regional": 10, "same_planet": 15, "same_system": 20, "different_system": 30}


class ForcePower(BaseModel):
    id: str
    name: str
    skills: list[ForceSkill]
    prerequisites: list[str] = Field(default_factory=list)
    can_keep_up: bool = False
    preparation_rounds: int = 1
    target: str = "self"
    description: str
    profiles: dict[str, str] = Field(default_factory=dict)
    difficulty_notes: str
    source: str


def power(id, name, skills, description, notes, page, **kwargs):
    return ForcePower(id=id, name=name, skills=skills.split(), description=description, difficulty_notes=notes,
        source=f"WEG40055 (1992), printed p.{page}, PDF p.{page - 11}", **kwargs)


POWERS = {p.id: p for p in [
    power("absorb_dissipate_energy", "Absorb / Dissipate Energy", "control", "Dissipate an environmental energy source, or prepare a Control reaction before an incoming personal energy attack.", "Control 5/10/15/20 by source; attacks require 15 + the actual incoming damage roll.", 148, can_keep_up=True,
        profiles={"sunburn": "Sunburn · Very Easy", "intense_sun": "Intense sun · Easy", "solar_wind": "Solar wind · Moderate", "radiation_storm": "Radiation storm · Difficult", "attack": "Incoming attack · use Prepare reaction"}),
    power("accelerate_healing", "Accelerate Healing", "control", "Grant two natural healing rolls for the current day, each with +2. Injuries remain until a healing roll improves them.", "Control 10 wounded, 15 incapacitated, 20 mortally wounded; one minute.", 148, preparation_rounds=12),
    power("control_pain", "Control Pain", "control", "Suppress injury and stun penalties from the following round without healing the injury or preventing mortal death checks.", "Control 5 wounded/stunned, 10 incapacitated, 20 mortally wounded.", 148, can_keep_up=True),
    power("emptiness", "Emptiness", "control", "Enter immobile, oblivious meditation; successful exit grants a temporary Force bonus equal to 6 minus Dark Side Points.", "Control 15 to enter, 20 to exit; declare a duration. Dark Side-consumed characters cannot use it.", 148, prerequisites=["hibernation_trance"]),
    power("hibernation_trance", "Hibernation Trance", "control", "Voluntarily enter a deep trance with declared waking conditions; skills and other powers cannot be used while asleep.", "Control 20. Declare waking duration or stimulus; supplies and survival are GM adjudicated.", 148, can_keep_up=True),
    power("reduce_injury", "Reduce Injury", "control", "Immediately reduce a newly suffered incapacitating, mortal, or killing injury to wounded at a cost of one Force Point.", "Control 15 incapacitated, 20 mortal, 30 killed. A killing injury also requires a recorded permanent injury.", 149, prerequisites=["control_pain"], target="reaction"),
    power("remain_conscious", "Remain Conscious", "control", "After a qualifying injury, make this the next round's first action, then perform at most one further declared action before collapsing.", "Control 10 stun-unconsciousness, 15 incapacitated, 20 mortally wounded.", 149, prerequisites=["control_pain"], target="reaction"),
    power("resist_stun", "Resist Stun", "control", "Prepare before injury to ignore stun results; an unconscious result drops the power and becomes a stun instead.", "Control 15; one minute, before any damage.", 149, can_keep_up=True, preparation_rounds=12),
    power("life_detection", "Life Detection", "sense", "Detect living sentients within ten meters. Opposed free detection checks can reveal additional identity information.", "Sense 5 for Force-sensitive/trained targets, otherwise 15; relationship modifier.", 149, can_keep_up=True, target="person"),
    power("life_sense", "Life Sense", "sense", "Sense a specific person's presence, identity, and physical condition. A target can conceal identity with Control.", "Sense 5 + proximity + relationship; add a resisting target's Control total.", 149, prerequisites=["life_detection"], can_keep_up=True, target="person"),
    power("magnify_senses", "Magnify Senses", "sense", "Enhance normal sensory reach. The GM supplies what can be perceived; the power does not reveal hidden scene facts automatically.", "Sense 5 + proximity; three rounds.", 150, preparation_rounds=3, target="scene"),
    power("receptive_telepathy", "Receptive Telepathy", "sense", "Read surface thoughts and emotions; sufficient success permits a separate full round probing memories from the last day.", "Sense 5 if willing, otherwise opposed Perception/Control; add proximity and relationship. No Droids.", 150, prerequisites=["life_sense"], can_keep_up=True, target="person"),
    power("sense_force", "Sense Force", "sense", "Sense the strength and light/dark tendency of an area or object, not the presence of individual sentients.", "Sense 15 for an area or 20 for detail, plus proximity.", 150, target="scene", profiles={"area": "Area · Moderate", "detail": "Specific object / detail · Difficult"}),
    power("injure_kill", "Injure / Kill", "alter", "Against a touched target, use the Alter total as damage and the opposing Control/Perception total as resistance.", "Alter must strictly exceed resistance. In combat a successful brawling touch in the same round is required. Use awards a Dark Side Point.", 150, prerequisites=["life_sense"], target="person"),
    power("telekinesis", "Telekinesis", "alter", "Move one visible object or living target; separate objects require separate activations. Attacking with an object needs an additional Control action.", "Alter 5/10/15/20/30/31 by mass, +5 per extra 10m/round, +maneuver and proximity; unwilling living targets add resistance.", 151, can_keep_up=True, target="object"),
    power("lightsaber_combat", "Lightsaber Combat", "control sense", "Add Sense to lightsaber attack/parry pools and choose Control dice to add/subtract from saber damage. Failure locks this power for the battle.", "Control 15, Sense 10. Uses the main rules paragraph; the book's worked example reverses Control and Sense.", 151, can_keep_up=True),
    power("projective_telepathy", "Projective Telepathy", "control sense", "Send thoughts and emotions to another mind; communication does not control the recipient.", "Control 5 + proximity (+5–10 if silent); Sense 5 or resistance, +relationship.", 152, prerequisites=["receptive_telepathy"], target="person"),
    power("accelerate_another_healing", "Accelerate Another's Healing", "control alter", "Grant another person the same two +2 healing rolls for the day; physical contact is required for each healing roll.", "Control 5 +relationship; Alter 5; one minute; touch for healing rolls.", 152, prerequisites=["control_another_pain"], preparation_rounds=12, target="person"),
    power("control_another_pain", "Control Another's Pain", "control alter", "Suppress another person's pain with the same injury restrictions as Control Pain; upkeep belongs to the caster.", "Control 5 +proximity +relationship; Alter 10 wounded, 15 incapacitated, 20 mortal.", 152, prerequisites=["control_pain"], can_keep_up=True, target="person"),
    power("return_another_consciousness", "Return Another to Consciousness", "control alter", "Give another person the limited conscious action allowed by Remain Conscious; this does not heal wounds.", "Control 10 +proximity +relationship; Alter 10 incapacitated or 20 mortal.", 152, prerequisites=["remain_conscious"], target="person"),
    power("transfer_force", "Transfer Force", "control alter", "Spend one Force Point to place a willing, touched mortal patient into life-preserving hibernation for up to six weeks.", "Control 10 +proximity +relationship; Alter 15; one minute. Further injury ends stabilization. The spent point is owed back at adventure end.", 152, prerequisites=["control_another_pain"], preparation_rounds=12, target="person"),
    power("affect_mind", "Affect Mind", "control sense alter", "Resolve a declared illusion, memory change, or mistaken conclusion. The GM determines the fictional result; it never deals physical damage.", "Control 5 perception / 10 memory / 15 conclusion +proximity; Sense resistance; Alter 5–30 by complexity. No Droids or recording devices.", 152, target="person", profiles={"perception": "Perception / illusion", "memory": "Memory", "conclusion": "Conclusion / mind trick"}),
]}


def automatic_known_powers(state):
    known = list(state.force.known_powers)
    if state.origin.force_tradition == "tyia" and int(state.force_skills["control"].split("D")[0]) >= 1:
        for id in ("hibernation_trance", "emptiness"):
            if id not in known:
                known.append(id)
    return known


def training_errors(state):
    errors = []
    known = set(state.force.known_powers)
    for id in known:
        spec = POWERS.get(id)
        if spec is None:
            errors.append(f"Unknown 1992 Force power '{id}'.")
            continue
        for skill in spec.skills:
            if int(state.force_skills[skill].split("D")[0]) < 1:
                errors.append(f"{spec.name} requires trained {skill}.")
        missing = set(spec.prerequisites) - known
        if missing:
            errors.append(f"{spec.name} requires: {', '.join(POWERS[id].name for id in sorted(missing))}.")
    if known and not state.force_sensitive:
        errors.append("Force powers require Force sensitivity.")
    return errors
