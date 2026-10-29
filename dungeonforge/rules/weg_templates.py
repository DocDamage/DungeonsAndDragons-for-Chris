"""The sixteen unnumbered character templates in WEG40055, PDF pp.157–164."""
import uuid

from pydantic import BaseModel, Field, StrictInt

from dungeonforge.rules import weg_creation as creation
from dungeonforge.rules.base import Companion, Item
from dungeonforge.rules.weg_creation_models import D6CreationRequest, D6SpecializationChoice
from dungeonforge.rules.weg_force_catalog import POWERS, training_errors
from dungeonforge.rules.weg_models import ATTRIBUTES, D6Character
from dungeonforge.rules.weg_origin_models import D6DroidState
from dungeonforge.rules.weg_species import SPECIES
from dungeonforge.rules.weg_vehicle_models import D6Vehicle, D6VehicleWeapon
from dungeonforge.rules.weg_starting_powers import slot_balance, save_grants


SOURCE = "WEG40055 (1992), unnumbered character templates, PDF pp.157–164; printed pp.10–12, 146."
ALIASES = "Printed shorthand uses native keys: starship repair → space_transports_repair; starship/weapon repair → starship_weapon_repair; language → languages."


class D6TemplateRequest(BaseModel):
    model_config = {"extra": "forbid"}
    template_id: str
    name: str = Field(min_length=1, max_length=120)
    skill_dice: dict[str, StrictInt] = Field(default_factory=dict)
    specializations: list[D6SpecializationChoice] = Field(default_factory=list, max_length=3)
    powers: list[str] = Field(default_factory=list, max_length=22)
    force_sensitive: bool | None = None
    owner: str = Field("", max_length=120)
    background: str = Field("", max_length=4000)
    gm_approval: str = Field(min_length=1, max_length=2000)
    survival_gear: list[str] = Field(default_factory=list, max_length=20)
    pet_alive: bool = True
    include_medic: bool = False
    expected_updated_at: float | None = None


class D6StartingPowerChoice(BaseModel):
    model_config = {"extra": "forbid"}
    actor_id: str | None = None
    grant_id: str
    power_id: str
    reason: str = Field(min_length=1, max_length=1000)
    expected_updated_at: float | None = None


def item(name, *, quantity=1, damage=None, skill=None, description="", physical=False, suit=False):
    return Item(name=name, quantity=quantity, damage=damage, d6_skill=skill,
        item_type="weapon" if damage else "equipment", damage_type="physical" if physical else "energy",
        description=description, sealed_survival_suit=suit)


def template(id, name, page, species, attributes, groups, *, force=(), policy="choice", move=10,
             credits=0, gear=(), notes=(), craft=None, debt=0, automatic=(), tradition="standard", droid=None, dsp=0):
    attributes = dict(zip(ATTRIBUTES, attributes.split()))
    skills = {key: attribute for attribute, names in zip(ATTRIBUTES, groups) for key in names.split()}
    budget = (sum(creation.pips(value) for value in attributes.values()) + 3 * len(force)) // 3
    skill_budget = 10 if droid else 7
    candidates = list(skills)
    suggestion = {key: 2 for key in candidates[:skill_budget // 2]}
    if skill_budget % 2:
        suggestion[candidates[skill_budget // 2]] = 1
    return {"id": id, "name": name, "pdf_page": page, "source": f"WEG40055 (1992), unnumbered {name} template, PDF p.{page}.",
        "species_id": species, "species_name": SPECIES[species]["name"] if species in SPECIES else {"revwien": "Revwien", "iotran": "Iotran", "near_human": "Near-Human", "droid": "3PO Protocol Droid"}[species],
        "attributes": attributes, "attribute_budget": budget, "skill_budget": skill_budget, "skills": skills,
        "suggested_skill_dice": suggestion, "force_skills": list(force), "force_policy": policy, "move": move,
        "credits": credits, "gear": list(gear), "notes": [*notes, ALIASES], "craft": craft, "debt": debt,
        "automatic_powers": list(automatic), "force_tradition": tradition, "droid_model": droid, "dark_side_points": dsp}


TEMPLATES = {entry["id"]: entry for entry in [
    template("alien_force_student", "Alien Force Student", 157, "revwien", "2D+1 3D+1 2D 2D+1 3D 2D", (
        "blaster dodge melee_combat running thrown_weapons", "alien_species intimidation languages survival",
        "beast_riding repulsorlift_operation space_transports swoop_operation", "bargain hide investigation persuasion sneak",
        "brawling stamina", "droid_programming droid_repair first_aid"), force=("control", "sense", "alter"), policy="yes", credits=250,
        gear=[item("Tyia amulet", description="Representative of the printed Tyia philosophy.")], automatic=("hibernation_trance", "emptiness"), tradition="tyia",
        notes=["Tyia: automatic Hibernation Trance and Emptiness, plus three additional Control choices; three choices for each other initial Force skill.",
               "Printed p.146: Emptiness is Easy; Alter difficulties increase one level; every power needs at least one minute.",
               "Revwien species ranges are not printed here. This flow uses the fixed template, without inventing redistribution limits."]),
    template("bounty_hunter", "Bounty Hunter", 157, "iotran", "4D 2D+2 2D+2 3D 3D+2 2D", (
        "blaster dodge grenade melee_combat melee_parry", "alien_species languages streetwise survival",
        "astrogation beast_riding space_transports starship_gunnery starship_shields", "command investigation search sneak",
        "brawling climbing_jumping lifting stamina", "armor_repair blaster_repair space_transports_repair starship_weapon_repair"), policy="no", credits=1000,
        gear=[item("Jet pack", description="10 bursts; each lasts one Move: 100m horizontally or 30m vertically."),
              item("Protective vest", description="+2 Strength resistance at torso front/back only; no blanket armor bonus."), item("Medpac", quantity=2),
              item("Heavy Blaster Pistol", damage="5D", skill="blaster"), item("Light Repeating Blaster", damage="6D", skill="blaster"),
              item("Hold-out Blaster", damage="3D", skill="blaster"), item("Knife", damage="STR+1D", skill="melee_combat", physical=True)],
        notes=["Iotran template statistics are fixed; no unprinted species bounds or special abilities are granted.", "Location-specific vest protection requires the actual covered hit location."]),
    template("brash_pilot", "Brash Pilot", 158, "human", "3D 2D 4D 3D 3D 3D", (
        "blaster brawling_parry dodge melee_combat vehicle_blasters", "intimidation planetary_systems value willpower",
        "astrogation communications sensors space_transports starfighter_piloting starship_gunnery", "command con gambling persuasion search",
        "brawling stamina swimming", "blaster_repair droid_repair repulsorlift_repair starfighter_repair"), credits=1000, craft="xwing",
        gear=[item("New Republic / Rebel Alliance uniform"), item("Medpac"), item("Vacuum survival suit", suit=True), item("Blaster Pistol", damage="4D", skill="blaster")]),
    template("curious_explorer", "Curious Explorer", 158, "near_human", "2D+1 3D+2 3D 4D 2D 3D", (
        "blaster dodge firearms pick_pocket thrown_weapons", "alien_species bureaucracy languages planetary_systems survival",
        "archaic_starship_piloting beast_riding sensors", "bargain hide investigation search", "lifting swimming",
        "demolitions first_aid ground_vehicle_repair security"), policy="no",
        gear=[item("Blaster Pistol", damage="4D", skill="blaster"), item("Black Powder Pistol", damage="3D", skill="firearms", physical=True),
              item("Sword", damage="STR+1D+2", skill="melee_combat", physical=True)],
        notes=["The fixed Near-Human template supplies no extra species powers or species redistribution ranges."]),
    template("cyborged_pirate", "Cyborged Pirate", 159, "human", "3D+2 2D 3D+2 3D 2D+2 3D", (
        "blaster blaster_artillery brawling_parry dodge grenade melee_combat", "business intimidation languages streetwise value",
        "astrogation capital_ship_gunnery repulsorlift_operation space_transports starship_gunnery starship_shields",
        "bargain command con forgery gambling", "brawling stamina", "armor_repair blaster_repair demolitions droid_repair security"), credits=2000,
        gear=[item("Flashy clothes, rings and trinkets"), item("Cybernetic left arm", description="+1D Strength resistance for hits to the left arm only."),
              item("Comlink"), item("Vacuum survival suit", suit=True), item("Blaster Pistol", damage="4D", skill="blaster")],
        notes=["The cybernetic arm does not increase all Strength rolls or give blanket armor protection."]),
    template("cynical_scout", "Cynical Scout", 159, "ithorian", "2D+2 5D 2D 3D 3D 2D+1", (
        "blaster brawling_parry dodge melee_combat melee_parry running", "alien_species languages law_enforcement planetary_systems survival",
        "astrogation communications sensors space_transports starship_gunnery starship_shields", "con forgery persuasion sneak", "stamina",
        "computer_programming_repair security space_transports_repair starship_weapon_repair"), craft="lone_scout",
        gear=[item("Blaster Pistol", damage="4D", skill="blaster"), item("Blaster Rifle", damage="5D", skill="blaster"),
              item("Vibroblade", damage="STR+1D+2", skill="melee_combat", physical=True)],
        notes=["The printed template allows reasonable survival gear; the GM must name the actual items. The printed vibroblade damage is retained."]),
    template("ewok_warrior", "Ewok Warrior", 160, "ewok", "3D+2 2D 3D+2 4D+1 1D+2 2D+2", (
        "bows brawling_parry dodge melee_combat melee_parry thrown_weapons", "languages survival willpower", "beast_riding glider",
        "bargain con hide search sneak", "climbing_jumping stamina swimming", "demolitions first_aid primitive_construction"), move=8,
        gear=[item("Leather backpack with shiny objects"), item("Spear", damage="STR+1D", skill="melee_combat", physical=True)],
        notes=["Printed Ewok creation bonuses double allocated Hide, Search and Sneak dice. Vehicle/starship starting restrictions remain in force."]),
    template("failed_jedi", "Failed Jedi", 160, "human", "2D+2 3D+1 2D 3D+1 2D+2 2D", (
        "blaster dodge lightsaber running", "alien_species intimidation languages planetary_systems survival willpower",
        "astrogation beast_riding repulsorlift_operation space_transports starship_shields", "bargain command investigation persuasion search sneak",
        "brawling climbing_jumping stamina swimming", "computer_programming_repair droid_programming droid_repair first_aid"),
        force=("control", "sense"), policy="yes", credits=250, dsp=1,
        gear=[item("Robes"), item("Bottle of liquor"), item("Lightsaber", damage="5D", skill="lightsaber")],
        notes=["Starts with the printed 1 Dark Side Point, Control/Sense at 1D and six earned starting power choices. No new in-play corruption gain is fabricated."]),
    template("gambler", "Gambler", 161, "human", "3D+2 3D 2D+1 4D 2D+2 2D+1", (
        "blaster brawling_parry dodge melee_combat melee_parry", "alien_species bureaucracy business languages streetwise value",
        "astrogation repulsorlift_operation space_transports starship_gunnery", "bargain con forgery gambling persuasion", "brawling lifting stamina",
        "droid_programming droid_repair first_aid repulsorlift_repair"), credits=1000,
        gear=[item("Sabacc cards"), item("Datapad of game rules"), item("A week's expensive clothes"), item("Hold-out Blaster", damage="3D+2", skill="blaster")],
        notes=["The template's hold-out blaster is 3D+2; it is retained instead of silently substituting the generic weapons chart."]),
    template("kid", "Kid", 161, "human", "3D+2 2D+2 3D 3D+2 2D+1 2D+2", (
        "blaster dodge melee_combat melee_parry missile_weapons pick_pocket", "languages streetwise survival",
        "beast_riding ground_vehicle_operation repulsorlift_operation", "bargain con hide search sneak", "climbing_jumping stamina swimming",
        "computer_programming_repair droid_programming droid_repair first_aid repulsorlift_repair"), move=8, credits=25,
        gear=[item("Fizzyglug", quantity=2), item("Bag of candy"), item("Small stone"), item("String")],
        notes=["Printed age is 12 and Move is 8. The player chooses whether the small pet is alive or dead; no creature combat sheet is invented."]),
    template("new_republic_bureaucrat", "New Republic Bureaucrat", 162, "human", "2D 4D 3D 3D+2 2D+1 3D", (
        "blaster brawling_parry dodge melee_combat running vehicle_blasters", "bureaucracy business intimidation law_enforcement planetary_systems value",
        "astrogation communications repulsorlift_operation space_transports starship_gunnery starship_shields",
        "bargain command con investigation persuasion search", "brawling climbing_jumping stamina swimming",
        "computer_programming_repair droid_programming droid_repair first_aid"), credits=4000, craft="landspeeder",
        gear=[item("Average clothes"), item("Comlink"), item("Sporting Blaster", damage="3D+2", skill="blaster")]),
    template("protocol_droid", "Protocol Droid", 162, "droid", "1D 3D 1D 1D 1D 1D", (
        "brawling_parry dodge melee_parry running", "alien_species bureaucracy cultures languages planetary_systems",
        "astrogation communications repulsorlift_operation sensors starship_shields", "bargain investigation persuasion search", "stamina",
        "computer_programming_repair droid_programming droid_repair first_aid"), move=7, droid="3po", policy="no",
        notes=["The printed Protocol Droid template has 8D attributes, 10D skill allocation and Move 7. Custom chassis creation still adds 1D per chassis attribute.",
               "Life-preservation programming prevents injury to sentients, even in self-defense. An owner is required; no NPC 10D Languages rating is inherited."]),
    template("smuggler", "Smuggler", 163, "human", "3D+1 2D+1 3D+2 3D 3D 2D+2", (
        "blaster dodge grenade melee_combat running vehicle_blasters", "alien_species languages planetary_systems streetwise value",
        "astrogation sensors space_transports starfighter_piloting starship_gunnery starship_shields swoop_operation",
        "bargain con forgery gambling persuasion search sneak", "brawling climbing_jumping lifting stamina swimming",
        "blaster_repair first_aid repulsorlift_repair space_transports_repair starship_weapon_repair"), credits=2000, craft="yt1300", debt=25000,
        gear=[item("Comlink"), item("Heavy Blaster Pistol", damage="5D", skill="blaster")],
        notes=["The printed 25,000-credit crime-boss debt is recorded as an obligation; it does not subtract from the 2,000 starting credits."]),
    template("sullustan_trader", "Sullustan Trader", 163, "sullustan", "2D+1 2D+2 4D+1 3D 2D 3D+2", (
        "blaster dodge running vehicle_blasters", "alien_species bureaucracy languages planetary_systems streetwise survival",
        "astrogation repulsorlift_operation sensors space_transports starfighter_piloting starship_gunnery starship_shields",
        "bargain con hide persuasion search sneak", "brawling climbing_jumping lifting stamina",
        "computer_programming_repair droid_programming droid_repair first_aid space_transports_repair"), craft="yt1300", debt=6000,
        gear=[item("Datapad"), item("Comlink"), item("Blaster Pistol", damage="4D", skill="blaster")],
        notes=["The 6,000-credit ship debt remains an obligation. No unprinted cash is added. Existing Sullustan scene abilities apply."]),
    template("wookiee_first_mate", "Wookiee First Mate", 164, "wookiee", "2D+2 2D 3D 2D 5D 3D+1", (
        "bowcaster brawling_parry dodge grenade melee_combat melee_parry running", "alien_species intimidation planetary_systems streetwise survival value",
        "astrogation beast_riding repulsorlift_operation sensors space_transports starship_gunnery starship_shields", "bargain con persuasion search",
        "brawling climbing_jumping lifting stamina swimming", "blaster_repair droid_programming droid_repair first_aid repulsorlift_repair space_transports_repair"), credits=250,
        gear=[item("Wookiee Bowcaster", damage="4D", skill="bowcaster")],
        notes=["The printed template Move is 10. Climbing claws and conditional berserker rage use the existing species controls."]),
    template("young_jedi", "Young Jedi", 164, "human", "2D 2D 2D 2D 2D 2D", (
        "blaster dodge melee_combat melee_parry running vehicle_blasters", "alien_species languages planetary_systems survival willpower",
        "astrogation beast_riding repulsorlift_operation space_transports starship_shields", "bargain command hide investigation persuasion search sneak",
        "brawling climbing_jumping stamina swimming", "blaster_repair droid_repair first_aid repulsorlift_repair security"),
        force=("control", "sense", "alter"), policy="yes", credits=500,
        gear=[item("Clothing", quantity=2), item("Blaster Pistol", damage="4D", skill="blaster")],
        notes=["The source prints six 2D attributes and three 1D Force skills (15D total). This fixed template is not silently increased to 18D.",
               "Nine earned starting Force power choices; no starting lightsaber. The equipment R2 uses its printed NPC block, not a player creation budget."]),
]}


def catalog():
    return {"templates": [{**entry, "gear": [gear.model_dump() for gear in entry["gear"]]} for entry in TEMPLATES.values()],
        "powers": [power.model_dump() for power in POWERS.values()], "source": SOURCE,
        "notes": ["Template attributes, Force skills, Move, printed equipment and exceptions remain fixed; only listed beginning skills can receive the skill budget.",
                  "Unselected earned starting powers remain explicit saved slots; they grant no skill rank, CP, training time or usable power until selected."]}


def build(req):
    profile = TEMPLATES.get(req.template_id)
    if profile is None:
        raise ValueError("Choose one of the sixteen printed 1992 templates.")
    if set(req.powers) & set(profile["automatic_powers"]):
        raise ValueError("Tyia automatic powers are already granted and must not consume or duplicate a starting choice.")
    if req.survival_gear and req.template_id != "cynical_scout":
        raise ValueError("Additional reasonable survival gear belongs to the Cynical Scout's printed equipment allowance.")
    if any(not name.strip() or len(name) > 120 for name in req.survival_gear):
        raise ValueError("Name each actual GM-approved survival item (up to 120 characters).")
    sensitive = profile["force_policy"] == "yes" if req.force_sensitive is None else req.force_sensitive
    request = D6CreationRequest(name=req.name, occupation=profile["name"], species_id=profile["species_id"], droid_model=profile["droid_model"],
        owner=req.owner, attributes=profile["attributes"], force_skills=profile["force_skills"], force_sensitive=sensitive,
        skill_dice=req.skill_dice, skill_attributes=profile["skills"], specializations=req.specializations, powers=req.powers,
        background=req.background, gm_approval=req.gm_approval, credits=profile["credits"], equipment=[], include_medic=req.include_medic)
    character, notes = creation.build(request, stock_template=profile)
    state = character.d6
    state.origin.template_id, state.origin.force_tradition = req.template_id, profile["force_tradition"]
    state.dark_side_points = profile["dark_side_points"]
    from dungeonforge.rules.weg_creation_equipment import fresh_item
    character.inventory = [fresh_item(gear, template_source=profile["source"]) for gear in profile["gear"]]
    character.inventory.extend(item(name.strip(), description="Actual GM-approved Cynical Scout survival gear.") for name in req.survival_gear)
    if req.template_id == "kid":
        character.inventory.append(item("Small pet", description="Alive" if req.pet_alive else "Dead"))
    if state.droid and req.template_id == "protocol_droid":
        state.droid.tasks.append("Life-preservation programming: cannot injure sentients, even in self-defense.")
    if profile["debt"]:
        obligation = f"Printed starting obligation: {profile['debt']} credits owed {'to a crime boss' if req.template_id == 'smuggler' else 'on the ship'}; starting cash remains {profile['credits']} credits."
        state.origin.background = (state.origin.background + "\n" + obligation).strip()
    chosen_weapon = False
    for gear in character.inventory:
        gear.equipped_by = character.id
        if gear.item_type == "weapon":
            gear.equipped = not chosen_weapon
            chosen_weapon = True
    save_grants(character, req.powers, profile["force_skills"], req.template_id, profile["automatic_powers"])
    character.notes = state.origin.background
    return character, notes


def eligible_starting_powers(person, grant):
    state = person.d6
    if not state:
        return []
    printed = TEMPLATES.get(state.origin.template_id)
    ordinary = state.origin.method in {"Custom template", "GM-defined alien species template"} and state.origin.skill_budget == 7
    origin_key = printed["id"] if printed else "custom" if ordinary else None
    initial_skills = state.origin.starting_force_skills or (printed["force_skills"] if printed else [])
    if (not origin_key or grant.teacher_id != f"starting:{origin_key}" or grant.skill not in initial_skills
            or grant.project_id != f"origin:{person.id}" or not 0 < grant.remaining <= 3):
        return []
    eligible = []
    for power_id in grant.allowed_powers:
        power = POWERS.get(power_id)
        if not power or grant.skill not in power.skills or power_id in state.force.known_powers:
            continue
        trial = state.model_copy(deep=True)
        trial.force.known_powers.append(power_id)
        if not training_errors(trial):
            eligible.append(power_id)
    return eligible


def choose_starting_power(person, grant_id, power_id):
    grant = next((entry for entry in person.d6.advancement.power_grants if entry.id == grant_id), None)
    if not grant or power_id not in eligible_starting_powers(person, grant):
        raise ValueError("Use an actual unspent starting slot, trained required skills and already known prerequisites; powers cannot be duplicated.")
    person.d6.force.known_powers.append(power_id)
    grant.remaining -= 1


def starting_craft(template_id):
    profile = TEMPLATES[template_id]
    key = profile["craft"]
    if not key:
        return []
    if key == "lone_scout":
        craft = D6Vehicle(name="Sienar Ships Lone Scout-A", hull="4D", maneuverability="0D", shields="1D", space_move=5,
            atmosphere_move=295, hyperdrive_multiplier=2, backup_hyperdrive=15, nav_computer=True,
            source="WEG40055 (1992), printed pp.122–123 / PDF pp.115–116; stock Cynical Scout template.",
            weapons=[D6VehicleWeapon(id="laser", name="Laser cannon", damage="4D", fire_control="0D", space_ranges=(1, 3, 12, 25), atmosphere_ranges=(100, 300, 1200, 2500))])
    elif key == "landspeeder":
        craft = D6Vehicle(name="Bureaucrat's Landspeeder", kind="vehicle", scale="speeder", piloting_skill="repulsorlift_operation",
            hull="3D", maneuverability="2D", shields="0D", space_move=0, atmosphere_move=120,
            source="WEG40055 (1992), New Republic Bureaucrat template, PDF p.162: Move 120, body 3D, maneuverability 2D.")
    else:
        from dungeonforge.game.weg_vehicle_presets import vehicle_presets
        craft = vehicle_presets()[key]
    craft.id, craft.occupied = f"craft_{uuid.uuid4().hex[:12]}", False
    return [craft]


def equipment_companions(template_id, character):
    if template_id != "young_jedi":
        return []
    chassis = creation.DROIDS["r2"]
    state = D6Character(species_id="droid", attributes=dict(zip(ATTRIBUTES, chassis["attributes"])), move=5,
        skills={"astrogation": "5D", "starfighter_piloting": "3D", "space_transports": "3D", "computer_programming_repair": "4D", "starfighter_repair": "5D"},
        character_points=0, force_points=0, credits=0,
        droid=D6DroidState(model="r2", owner=character.name, degree=2, equipment=list(chassis["equipment"])))
    state.origin.method, state.origin.source = "Printed equipment NPC", "WEG40055 (1992), printed p.158 / PDF p.147; Young Jedi equipment."
    return [Companion(id=f"r2_{uuid.uuid4().hex[:12]}", name="R2 Astromech", race="R2 Astromech Droid", class_name="Equipment companion", d6=state,
        attack_name="No armed attack recorded", damage="0", notes="Printed NPC equipment block; no PC allocation budget or unlisted personal CP/FP is granted.")]
