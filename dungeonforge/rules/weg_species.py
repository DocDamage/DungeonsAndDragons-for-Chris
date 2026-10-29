"""WEG40055 1992: printed pp.133–137; no R&E species statistics."""
from dungeonforge.rules.weg_models import ATTRIBUTES


def species(name, dice, bounds, move, notes=(), bonuses=(), source="133–137"):
    return {"id": name.lower().replace(" ", "_").replace("'", ""), "name": name,
        "attribute_dice": dice + 6, "minimums": dict(zip(ATTRIBUTES, (item.split('/')[0] for item in bounds.split()))),
        "maximums": dict(zip(ATTRIBUTES, (item.split('/')[1] for item in bounds.split()))),
        "move": move[0], "move_maximum": move[1], "notes": list(notes), "creation_bonus_skills": list(bonuses),
        "source": f"WEG40055 (1992), printed pp.{source}"}


SPECIES = {item["id"]: item for item in [
    species("Human", 12, "2D/4D 2D/4D 2D/4D 2D/4D 2D/4D 2D/4D", (10, 12), source="15, 133"),
    species("Ewok", 12, "1D+2/4D+2 1D/3D 1D+2/3D+2 2D/4D+2 1D/3D 1D/2D+2", (7, 9),
        ["Creation: hide, search and sneak receive twice the allocated skill dice.", "Beginning vehicle/starship operation and repair skills are forbidden, except glider.", "Scent tracking adds 1D to search. Primitive construction and glider are native skills.", "Human protectiveness can also be condescending."], ["hide", "search", "sneak"], "133–134"),
    species("Gamorrean", 11, "2D/4D 1D/2D 1D/1D+2 1D/3D 3D/5D 1D/1D+2", (7, 10),
        ["Creation: melee combat, brawling and thrown weapons receive twice the allocated skill dice.", "May immediately retry a failed stamina check once.", "Understands Basic but cannot speak it. Droid distrust, a reputation for brutality, and slavery are story factors."], ["melee_combat", "brawling", "thrown_weapons"], "134–135"),
    species("Ithorian", 12, "1D/3D 2D+2/5D 1D/2D 1D+1/4D 1D/3D 1D/2D+1", (10, 12),
        ["Agriculture and ecology are Knowledge skills. Herd-ship contacts are a story factor."], source="135"),
    species("Mon Calamari", 12, "1D/3D+1 1D/4D 1D+1/3D+1 1D/3D 1D/3D 1D+1/4D", (9, 12),
        ["Moist environments: +1D to Dexterity, Perception and Strength checks; very dry environments: -1D.", "The environment effect is psychological. Imperial persecution is a story factor."], source="135"),
    species("Rodian", 12, "1D+2/4D+2 1D/3D 1D/2D+2 1D/3D+2 1D/4D+1 1D/2D+1", (10, 12),
        ["Distrust outside criminal circles is a story factor; no automatic bounty-hunting bonus."], source="136"),
    species("Sullustan", 12, "1D/3D 1D/2D+2 2D/4D+1 1D/3D+1 1D/2D+2 1D/3D+2", (10, 12),
        ["Low-light vision or hearing checks: +2D to Perception/search.", "Never gets lost in an area already visited. Astrogation to a visited place gains +1D."], source="136"),
    species("Twi'lek", 11, "1D/3D 1D/4D 1D/2D+1 2D/4D+2 1D/3D 1D/3D", (10, 12),
        ["Fluent secret tentacle language with other Twi'leks."], source="137"),
    species("Wookiee", 12, "1D/3D+2 1D/2D+1 1D/3D+2 1D/2D+1 2D+2/6D 1D/3D+1", (11, 15),
        ["Climbing claws: +2D on climbing checks. Using them as weapons is dishonorable.", "Rage requires perceived immediate deadly danger to self or a life-debt companion: +2D brawling damage, -2D to non-Strength checks.", "After enemies are controlled, Moderate Perception with the rage penalty is required to calm down.", "Understands Basic but cannot speak it. Loyalty, Imperial enslavement and reputation are story factors."], source="137"),
]}


def check_bonus(state, skill, attribute):
    identity, context = state.species_id, state.species_context
    bonus = 0
    if identity == "mon_calamari" and attribute in {"dexterity", "perception", "strength"}:
        bonus += {"moist": 1, "dry": -1, "neutral": 0}[context.environment]
    if identity == "ewok" and skill == "search" and context.scent_tracking:
        bonus += 1
    if identity == "wookiee" and skill == "climbing_jumping" and context.climbing_claws:
        bonus += 2
    if identity == "sullustan":
        if skill in {"perception", "search"} and context.enhanced_senses:
            bonus += 2
        if skill == "astrogation" and context.familiar_destination:
            bonus += 1
    return bonus


def check_penalty(state, attribute):
    return 2 if state.species_id == "wookiee" and state.species_context.berserk and attribute != "strength" else 0
