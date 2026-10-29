"""Rule-checked new custom templates and the four corebook Droid chassis."""
import uuid
from dungeonforge.rules.base import Character, Item
from dungeonforge.rules.weg_d6 import skill_key, parse_code
from dungeonforge.rules.weg_models import ATTRIBUTES, SKILL_ATTRIBUTES, D6Character
from dungeonforge.rules.weg_force_catalog import POWERS, training_errors
from dungeonforge.rules.weg_species import SPECIES
from dungeonforge.rules.weg_origin_models import D6Origin, D6DroidState


SOURCE = "WEG40055 (1992), printed pp.10–12, 15, 133–137, 158–160"
EXTRA_SKILLS = {"thrown_weapons": "dexterity", "glider": "mechanical", "primitive_construction": "technical", "agriculture": "knowledge", "ecology": "knowledge"}
SKILLS = {**SKILL_ATTRIBUTES, **EXTRA_SKILLS}
DROIDS = {
    "r2": {"name": "R2 Astromech Droid", "degree": 2, "attributes": ["1D", "1D", "2D", "1D", "1D", "2D"], "move": 5,
        "equipment": ["Three wheeled legs (one retractable)", "Heavy grasper (lifting 2D)", "Fine work grasper", "Extendable video sensor", "Arc welder (1D–5D, GM selects situation)", "Circular saw (4D)", "Video display", "Holographic projector/recorder", "Fire extinguisher", "Small cargo compartment", "Small tools"],
        "notes": ["Stores up to ten preprogrammed hyperspace jumps. Can attempt in-flight repairs as co-pilot.", "Communicates using electronic language; no automatic learned skills from the NPC block."]},
    "9g": {"name": "DeepSpace 9G Explorer Droid", "degree": 2, "attributes": ["1D"] * 6, "move": 10,
        "equipment": ["Repulsor unit (3m flight ceiling)", "Heavy grasper (lifting 4D)", "Holographic/audio recorder", "Long-range sensor (+2D search, 25–50m)", "Movement sensor (+2D search for moving objects)", "Atmosphere sensor (30 minutes)"],
        "notes": ["Sensor conditions must match the actual scene; the example NPC search 4D is not a PC starting skill."]},
    "k4": {"name": "K4 Security Droid", "degree": 4, "attributes": ["3D", "1D", "1D", "1D", "1D", "1D"], "move": 11,
        "equipment": ["Two auto-balance legs", "Two arms", "Body armor (+2D all locations)", "Internal blaster rifle (5D; ranges 5–30/100/200m)"],
        "notes": ["Security Droids and combat programming are regulated. The example 7D blaster/8D dodge skills are not inherited."]},
    "3po": {"name": "3PO Protocol Droid", "degree": 3, "attributes": ["1D", "3D", "1D", "1D", "1D", "1D"], "move": 8,
        "equipment": ["Humanoid body", "Human-range visual and audial sensors", "Vocabulator", "Broad-band receiver", "AA-1 VerboBrain", "TranLang III communication module"],
        "notes": ["Vocabulator can reproduce heard/programmed sounds. The example 10D languages and 6D cultures are not inherited."]},
}
GEAR = {
    "blaster_pistol": Item(name="Blaster Pistol", item_type="weapon", damage="4D", d6_skill="blaster", equipped=True),
    "heavy_blaster": Item(name="Heavy Blaster Pistol", item_type="weapon", damage="5D", d6_skill="blaster"),
    "blaster_rifle": Item(name="Blaster Rifle", item_type="weapon", damage="5D", d6_skill="blaster"),
    "knife": Item(name="Knife", item_type="weapon", damage="STR+1D", d6_skill="melee_combat", damage_type="physical"),
    "lightsaber": Item(name="Lightsaber", item_type="weapon", damage="5D", d6_skill="lightsaber", d6_difficulty=20),
    "comlink": Item(name="Comlink"), "medpac": Item(name="Medpac", item_type="consumable"),
    "datapad": Item(name="Datapad"), "glowrod": Item(name="Glowrod"),
    "blast_vest": Item(name="Blast Vest", item_type="armor", description="+1 pip energy; +1D physical on torso.", equipped=True),
    "droid_parts": Item(name="Replacement Droid parts", item_type="parts", description="GM-approved replacements for a Droid repair."),
    "survival_suit": Item(name="Vacuum survival suit", item_type="equipment", sealed_survival_suit=True),
}


def pips(value):
    dice, extra = parse_code(value)
    return dice * 3 + extra


def code(value):
    dice, extra = divmod(value, 3)
    return f"{dice}D" + (f"+{extra}" if extra else "")


def attributes_for(spec, force_skills=0):
    """A legal starting allocation for the form; players can redistribute it."""
    values = {key: pips(value) for key, value in spec["minimums"].items()}
    remaining = (spec["attribute_dice"] - force_skills) * 3 - sum(values.values())
    while remaining > 0:
        changed = False
        for key in ATTRIBUTES:
            if values[key] < pips(spec["maximums"][key]) and remaining:
                values[key] += 1
                remaining -= 1
                changed = True
        if not changed:
            raise ValueError("This species cannot fit the attribute budget.")
    return {key: code(value) for key, value in values.items()}


def catalog():
    return {"species": [{**item, "suggested_attributes": attributes_for(item)} for item in SPECIES.values()],
        "droids": [{"id": id, **item, "pc_attributes": {key: code(pips(value) + 3) for key, value in zip(ATTRIBUTES, item["attributes"])}} for id, item in DROIDS.items()],
        "skills": SKILLS, "equipment": [{**item.model_dump(exclude={"id"}), "id": id} for id, item in GEAR.items()], "source": SOURCE}


def build(req, *, stock_template=None):
    if not req.name.strip() or not req.occupation.strip() or not req.gm_approval.strip():
        raise ValueError("Name the character and occupation, and record the GM's template/equipment approval.")
    if len(req.force_skills) != len(set(req.force_skills)) or set(req.force_skills) - {"control", "sense", "alter"}:
        raise ValueError("Choose each Force skill at most once: Control, Sense or Alter.")
    if len(req.powers) != len(set(req.powers)) or set(req.powers) - set(POWERS):
        raise ValueError("Choose unique Force powers from the 1992 catalog.")
    custom = req.custom_species
    if custom is not None and (stock_template is not None or req.species_id != "custom" or req.droid_model):
        raise ValueError("A GM-defined species uses the custom species option; it cannot replace a printed species, stock template or Droid chassis.")
    if req.species_id == "custom" and custom is None:
        raise ValueError("Record the complete GM-approved custom species before allocating its template.")
    move_maximum = None
    if stock_template is not None:
        from dungeonforge.rules.weg_templates import TEMPLATES
        if TEMPLATES.get(stock_template.get("id")) is not stock_template:
            raise ValueError("Stock template statistics must come from the trusted printed catalog.")
        if req.species_id != stock_template["species_id"] or req.droid_model != stock_template.get("droid_model"):
            raise ValueError("Use the species and Droid model printed on the selected template.")
        if req.attributes != stock_template["attributes"] or set(req.force_skills) != set(stock_template["force_skills"]):
            raise ValueError("A stock template retains its printed attributes and initial Force skills; use custom creation to redistribute dice.")
        policy = stock_template["force_policy"]
        if policy == "no" and req.force_sensitive or policy == "yes" and not req.force_sensitive:
            raise ValueError("Respect the Yes/No Force sensitivity printed on this template.")
        if req.droid_model and not req.owner.strip():
            raise ValueError("A Droid PC needs an owner or companion who acts as its owner.")
        attributes = dict(stock_template["attributes"])
        budget, skill_budget, move = stock_template["attribute_budget"], stock_template["skill_budget"], stock_template["move"]
        spec = SPECIES.get(req.species_id)
        maximums = dict(spec["maximums"]) if spec else {}
        move_maximum = spec["move_maximum"] if spec else None
        species_name, notes = stock_template["species_name"], list(stock_template["notes"])
        bonus_skills = list(spec["creation_bonus_skills"]) if spec else []
        model = DROIDS.get(req.droid_model) if req.droid_model else None
    elif req.droid_model:
        model = DROIDS.get(req.droid_model)
        if model is None or req.species_id != "droid":
            raise ValueError("Choose a corebook Droid chassis and the Droid species type.")
        if req.force_sensitive or req.force_skills or req.powers:
            raise ValueError("Droids may not be Force-sensitive or have Force skills or powers.")
        if not req.owner.strip():
            raise ValueError("A Droid PC needs an owner or companion who acts as its owner.")
        attributes = {key: code(pips(value) + 3) for key, value in zip(ATTRIBUTES, model["attributes"])}
        if req.attributes and req.attributes != attributes:
            raise ValueError("A Droid PC adds exactly 1D to each chassis attribute; those dice cannot be redistributed.")
        budget, skill_budget, move, maximums = sum(pips(value) for value in attributes.values()) // 3, 10, model["move"], {}
        species_name, notes, bonus_skills = model["name"], list(model["notes"]), []
    else:
        if custom is not None:
            from dungeonforge.rules.weg_custom_species import profile
            spec = profile(custom)
        else:
            spec = SPECIES.get(req.species_id)
        if spec is None:
            raise ValueError("Choose a catalog species; custom species need a separately approved species record.")
        if set(req.attributes) != set(ATTRIBUTES):
            raise ValueError("Allocate all six attributes.")
        attributes = dict(req.attributes)
        budget, skill_budget, move, maximums = spec["attribute_dice"], 7, spec["move"], spec["maximums"]
        for key, value in attributes.items():
            if not pips(spec["minimums"][key]) <= pips(value) <= pips(spec["maximums"][key]):
                raise ValueError(f"{key.title()} must be {spec['minimums'][key]}–{spec['maximums'][key]} at creation.")
        if sum(pips(value) for value in attributes.values()) + 3 * len(req.force_skills) != budget * 3:
            raise ValueError(f"Allocate exactly {budget}D across attributes and initial 1D Force skills.")
        species_name, notes, bonus_skills = spec["name"], list(spec["notes"]), spec["creation_bonus_skills"]
        move_maximum = spec["move_maximum"]
    if req.force_skills and not req.force_background.strip() and stock_template is None:
        raise ValueError("Starting Force skills require a plausible previous teacher/training background.")
    allocation = {skill_key(key): value for key, value in req.skill_dice.items() if value}
    if len(allocation) != len([value for value in req.skill_dice.values() if value]):
        raise ValueError("Do not allocate the same skill under different spellings.")
    if any(not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= 2 for value in allocation.values()):
        raise ValueError("Allocate 1D or 2D per starting skill, before species bonuses.")
    if sum(allocation.values()) + bool(req.specializations) != skill_budget:
        raise ValueError(f"Allocate exactly {skill_budget}D to skills; one specialization package costs 1D.")
    if req.specializations and len(req.specializations) != 3:
        raise ValueError("The 1D specialization package grants exactly three distinct specializations at +1D.")
    if stock_template is not None:
        allowed = set(stock_template["skills"]) | set(stock_template["force_skills"])
        if set(allocation) - allowed or any(skill_key(choice.parent) not in stock_template["skills"] for choice in req.specializations):
            raise ValueError("Beginning stock-template skills and specialization parents must be listed on that printed template.")
    skills, governing = {}, {**SKILLS, **{skill_key(key): value for key, value in req.skill_attributes.items()}}
    if any(value not in ATTRIBUTES for value in governing.values()):
        raise ValueError("Custom skills must use one of the six attributes.")
    force = {key: "1D" if key in req.force_skills else "0D" for key in ("control", "sense", "alter")}
    for key, dice in allocation.items():
        if key in force:
            if key not in req.force_skills:
                raise ValueError("Purchase an initial Force skill with attribute dice before allocating skill dice to it.")
            force[key] = code(3 + dice * 3)
            continue
        if key not in governing or key in ATTRIBUTES:
            raise ValueError(f"Define the template skill and governing attribute for {key}.")
        if req.species_id == "ewok" and key != "glider" and (key.endswith("_repair") and key != "droid_repair" and key != "computer_programming_repair" and key != "armor_repair" and key != "blaster_repair" or key in {"repulsorlift_operation", "walker_operation", "ground_vehicle_operation", "swoop_operation", "space_transports", "starfighter_piloting", "capital_ship_piloting", "starship_gunnery", "starship_shields", "capital_ship_gunnery", "capital_ship_shields"}):
            raise ValueError("Beginning Ewoks cannot allocate vehicle/starship operation or repair skills (except glider).")
        skills[key] = code((0 if key == "medicine" else pips(attributes[governing[key]])) + dice * (6 if key in bonus_skills else 3))
    if "medicine" in skills and pips(skills.get("first_aid", attributes["technical"])) < 15:
        raise ValueError("Beginning Medicine requires at least 5D in First Aid.")
    parents = {}
    for choice in req.specializations:
        key, parent = skill_key(choice.name), skill_key(choice.parent)
        if key in skills or key in ATTRIBUTES or key in force or key in parents or parent in parents or parent in force or parent == "medicine" or parent not in governing:
            raise ValueError("Choose three distinct specializations of basic template skills.")
        parents[key] = parent
        skills[key] = code(pips(skills.get(parent, attributes[governing[parent]])) + 3)
        governing[key] = governing[parent]
    state = D6Character(species_id=custom.id if custom else req.species_id, attributes=attributes, skills=skills,
        skill_attributes={key: governing[key] for key in skills}, specializations=list(parents), specialization_parents=parents,
        species_attribute_maximums=maximums, move=move, move_maximum=move_maximum,
        force_sensitive=req.force_sensitive or bool(req.force_skills), force_skills=force,
        force_points=2 if req.force_sensitive or req.force_skills else 1, character_points=5, credits=req.credits)
    state.force.known_powers = list(dict.fromkeys([*(stock_template.get("automatic_powers", []) if stock_template else []), *req.powers]))
    errors = training_errors(state)
    if errors:
        raise ValueError(" ".join(errors))
    # Allocate each selected power to one of its skills, with three initial slots per skill.
    def fit(index, slots):
        if index == len(req.powers):
            return True
        return any(slots.get(skill, 0) > 0 and fit(index + 1, {**slots, skill: slots[skill] - 1}) for skill in POWERS[req.powers[index]].skills)
    if not fit(0, {key: 3 for key in req.force_skills}):
        raise ValueError("Each starting Force skill supplies three power choices; assign powers within those slots.")
    if len(req.equipment) != len(set(req.equipment)) or set(req.equipment) - set(GEAR):
        raise ValueError("Select distinct items from the starter equipment list.")
    from dungeonforge.rules.weg_creation_equipment import fresh_item, STARTER_CATALOG
    inventory = [fresh_item(GEAR[id], catalog_id=STARTER_CATALOG.get(id)) for id in req.equipment]
    if req.droid_model:
        state.droid = D6DroidState(model=req.droid_model, owner=req.owner.strip(), degree=model["degree"], equipment=model["equipment"])
        if req.droid_model == "k4":
            state.armor_energy = state.armor_physical = "2D"
            inventory.append(fresh_item(Item(name="Internal Blaster Rifle", item_type="weapon", damage="5D", d6_skill="blaster",
                d6_ranges=(5, 30, 100, 200), equipped=True), catalog_id="blaster_rifle"))
    elif "blast_vest" in req.equipment:
        # Location coverage is adjudicated in the armor controls; the torso values are recorded here.
        state.armor_energy, state.armor_physical = "0D+1", "1D"
    selected = False
    for item in inventory:
        if item.item_type == "weapon":
            item.equipped = not selected
            selected = True
    state.origin = D6Origin(method="GM-defined alien species template" if custom else "Stock template" if stock_template else "Droid chassis" if req.droid_model else "Custom template", species_id=state.species_id,
        attribute_budget=budget, skill_budget=skill_budget, skill_dice=allocation, specializations=parents,
        background=req.background.strip(), gm_approval=req.gm_approval.strip(), source=stock_template["source"] if stock_template else spec["source"] if custom else SOURCE,
        custom_species=custom.model_copy(deep=True) if custom else None)
    state.origin.starting_force_skills = list(req.force_skills)
    if req.force_background.strip():
        state.origin.background += "\nForce training: " + req.force_background.strip()
    character = Character(id=f"hero_{uuid.uuid4().hex[:12]}", name=req.name.strip(), race=species_name, class_name=req.occupation.strip(), edition="weg_d6",
        d6=state, inventory=inventory, gold=0, notes=state.origin.background)
    for gear in character.inventory:
        gear.equipped_by = character.id
    if stock_template is None:
        from dungeonforge.rules.weg_starting_powers import save_grants
        save_grants(character, req.powers, req.force_skills, "custom")
    return character, notes
