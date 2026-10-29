"""Personal equipment from WEG40055 (1992), never the 1996 revised catalog."""
import hashlib
import json
import math

from dungeonforge.rules.base import Item
from dungeonforge.rules.weg_d6 import WEGD6Rules, parse_code
from dungeonforge.rules.weg_equipment_models import EquipmentPurchaseQuote, EquipmentWorkQuote

SOURCE = "WEG40055 (1992), printed pp.65, 67–68, 86–87, 153–161."
LOCATIONS = ["head", "torso", "left_arm", "right_arm", "left_leg", "right_leg"]
AVAILABILITY = {"1": "Readily available throughout the Known Galaxy.", "2": "Normally found in large cities, spaceports, or on the world of origin.", "3": "Specialized; normally found only on the world of origin.", "4": "Rare and difficult to locate.", "F": "A fee or permit is often required.", "R": "Restricted; the relevant local license is normally required.", "X": "Normally illegal except for specially authorized people."}
NOTES = [
    "Availability and prices are local GM facts. The chart gives typical prices, not a guaranteed seller or automatic permission.",
    "Restricted goods may have an actual black-market source. Record that source and its price; choosing black market does not make possession legal.",
    "Lightsabers have no listed sale price. Stormtrooper armor is unavailable for sale in its description, while the cost chart lists 2,500 credits. These require explicit GM acquisition facts.",
    "Bowcasters are sold to Wookiees and are normally found on Kashyyyk. Quarrel and bowcaster power-pack prices are not printed.",
    "Asset and Droid prices are references. Personal purchases do not create a vehicle, starship, artillery emplacement, or fictional NPC crew.",
    "Armor protects its actual locations and sides. Overlapping armor profiles are rejected; the book does not supply a general armor-stacking rule.",
    "The personal repair tables cover armor and blasters. Unlisted procedures require an actual GM procedure rather than an invented repair skill.",
    "Parts costs round up to whole credits. Improvements select one armor protection profile or a blaster damage code; changing other properties is outside these tables.",
    "These work projects use actual party technicians. Commercially hiring someone else to improve an item costs at least twice the printed parts amount, and can cost more; no fictitious hired-service price or technician is created here.",
]
ITEMS = {}


def add(id, name, category, cost, availability, page, notes=(), **fields):
    item_type = "weapon" if category in {"blaster", "melee", "explosive"} else "armor" if category == "armor" else "consumable" if category in {"ammunition", "medical"} else "equipment"
    ITEMS[id] = {"id": id, "name": name, "category": category, "cost": cost,
        "availability": availability, "source": f"WEG40055 (1992), printed pp.{page}; price/availability p.161.",
        "notes": list(notes), "purchasable": True, "special_purchase": False,
        "wookiee_only": False, "item": {"name": name, "item_type": item_type,
            "catalog_id": id, "unit_cost": cost, "availability": availability,
            "source": f"WEG40055 (1992), printed pp.{page}, 161.",
            "description": " ".join(notes), **fields}}


add("breath_mask", "Breath Mask", "gear", 50, "1", "153", ["Filters normally last one hour of continuous use. Provides no protection from cold or vacuum."])
add("personal_comlink", "Personal Comlink", "gear", 25, "1", "153", ["About 50 km or low orbit in clear conditions; local interference can reduce range."])
add("military_comlink", "Military Comlink", "gear", 100, "2,R", "153", ["Military communications equipment; actual frequencies and encryption are scene facts."])
add("vehicle_comlink", "Vehicle Comlink", "gear", 300, "1", "153", ["Vehicle-mounted communications; about 200 km under appropriate conditions."])
add("datapad", "Datapad", "gear", 100, "1", "153", ["Portable data storage and retrieval. A datapad cannot calculate an astrogation route."])
add("glowrod", "Glowrod", "gear", 10, "1", "153", ["Typical personal range up to 50 m. The source lists replaceable energy cells lasting 50 hours; other designs vary."])
add("macrobinoculars", "Macrobinoculars", "gear", 100, "1", "153", ["Typical magnification reaches 1 km. +3D to appropriate Perception/search checks beyond 100 m. Weapon integration needs actual software, a steady sniper position and a preparation round; then +3D at medium/long range only."])
add("medpac", "Medpac", "medical", 100, "1", "153", ["A single-use first-aid kit. Use the native medpac/First Aid procedure; buying one does not heal anyone."])
add("recording_rod", "Recording Rod", "gear", 30, "1", "153", ["Reusable sound recording, normally up to 100 hours."])
add("vacuum_survival_suit", "Vacuum Survival Suit", "gear", None, "GM", "169–170", ["Vacuum suits appear in the character templates; no price is printed in the equipment cost chart. GM confirms the actual sealed suit and its cost."], sealed_survival_suit=True)
add("medicine", "GM-assessed Medicines", "medical", None, "GM", "67", ["The GM records the actual medicine, dose, price and effect. The source describes possible healing bonuses or shorter recovery; this purchase grants no automatic healing bonus."])
add("standard_blaster_power_pack", "Standard Blaster Power Pack", "ammunition", 25, "GM", "154–155", ["A full compatible pack; shot capacity depends on the actual blaster. Confirm compatibility with the seller."])
add("q2_power_pack", "Q2 Hold-out Power Pack", "ammunition", 25, "GM", "154", ["Q2 hold-out blasters use their own custom pack, not a standard pistol pack."])
add("bowcaster_power_pack", "Bowcaster Power Pack", "ammunition", None, "GM", "155", ["Powers 50 shots. The corebook does not print this pack's price or identify it as a standard blaster pack."])
add("bowcaster_quarrels", "Six Bowcaster Quarrels", "ammunition", None, "GM", "155", ["One six-quarrel reload. A Moderate Strength total is separately required to reload the bowcaster."])

for id, name, price, avail, damage, capacity, ranges, page, notes in [
    ("holdout_q2", "Merr-Sonn Q2 Hold-out Blaster", 275, "2,R or X", "3D", 6, (3, 4, 8, 12), "154", ["Custom Q2 power packs; local restrictions vary."]),
    ("sporting_defender", "Defender Sporting Blaster", 350, "1,F", "3D+1", 50, (3, 10, 30, 60), "154", []),
    ("blaster_dl18", "BlasTech DL-18 Blaster Pistol", 500, "1,F,R or X", "4D", 100, (3, 10, 30, 120), "154", []),
    ("heavy_blaster_dl44", "BlasTech DL-44 Heavy Blaster Pistol", 750, "2,R or X", "5D", 25, (3, 7, 25, 50), "154", []),
    ("blaster_carbine", "QuickSnap 36T Blaster Carbine", 900, "2 (backwater:1),F,R or X", "5D", 100, (3, 25, 50, 250), "154", ["Long-range attacks increase difficulty by +5."]),
    ("blaster_rifle", "Stormtrooper One Blaster Rifle", 1000, "2,X", "5D", 100, (3, 30, 100, 300), "154", ["Using the stock and scope for a full aiming round grants +1D to the blaster roll."]),
    ("sporting_rifle", "Light Sport Hunter Sporting Blaster Rifle", 900, "2,R", "4D+1", 100, (3, 40, 120, 350), "155", ["Using the stock and scope for a full aiming round grants +1D to the blaster roll."]),
    ("light_repeating_blaster", "BlasTech T-21 Light Repeating Blaster", 2000, "2,X", "6D", 25, (3, 50, 120, 300), "155", ["May use an actual connected generator instead of its 25-shot pack."]),
]:
    add(id, name, "blaster", price, avail, page, notes, damage=damage, original_damage=damage,
        d6_skill="blaster", d6_can_stun=True, ammo=capacity, ammo_capacity=capacity,
        ammo_type="blaster_power_pack", reload_catalog_id="q2_power_pack" if id == "holdout_q2" else "standard_blaster_power_pack", d6_ranges=ranges)
add("e_web", "BlasTech E-Web Heavy Repeating Blaster", "blaster", 5000, "2,X", "155", ["Must be mounted on its tripod and fed by an actual power generator. Source fire rate: one shot per round."], damage="8D", original_damage="8D", d6_skill="blaster", d6_can_stun=True, d6_ranges=(3, 75, 200, 500), d6_fire_rate=1, requires_generator=True)
add("bowcaster", "Wookiee Bowcaster", "weapon", 900, "3,R", "155", ["Sold to Wookiees; normally available on Kashyyyk. Six quarrels and 50 power shots. Reload requires Moderate Strength. More than one shot in a round requires an Easy Strength free action."], item_type="weapon", damage="4D", original_damage="4D", d6_skill="bowcaster", d6_ranges=(3, 10, 30, 50), d6_fire_rate=1, ammo=6, ammo_capacity=6, ammo_type="bowcaster_quarrel", reload_catalog_id="bowcaster_quarrels", power_ammo=50, power_ammo_capacity=50, power_reload_catalog_id="bowcaster_power_pack")
ITEMS["bowcaster"]["wookiee_only"] = True
for id, name, cost, avail, damage, ranges, radius, blast, scale in [
    ("fragmentation_grenade", "Fragmentation Grenade", 200, "1,R", "5D", (3, 7, 20, 40), [0, 2, 4, 6, 10], ["5D", "4D", "3D", "2D"], "character"),
    ("thermal_detonator", "Thermal Detonator", 2000, "2,X", "10D", (3, 4, 7, 12), [0, 2, 8, 12, 20], ["10D", "8D", "5D", "2D"], "character"),
    ("anti_vehicle_mine", "Anti-vehicle Mine", 750, "2,X", "5D", None, [0, 2, 4, 6, 10], ["5D", "4D", "3D", "2D"], "speeder"),
]:
    add(id, name, "explosive", cost, avail, "156", ["Single-use explosive; use actual blast distance and the printed damage bands, not full damage for everyone in the area."], damage=damage, original_damage=damage, d6_skill="demolitions" if id == "anti_vehicle_mine" else "grenade", damage_type="physical", ammo=1, ammo_capacity=1, d6_ranges=ranges, d6_scale=scale)
    ITEMS[id]["blast_radius"], ITEMS[id]["blast_damage"] = radius, blast
ITEMS["anti_vehicle_mine"]["notes"].append("The setter's Demolitions total is the mine's Hide and attack total. A previously declared normal Dodge exceeding that total moves the victim one blast band outward; a successful previously declared full Dodge escapes the entire radius.")
ITEMS["fragmentation_grenade"]["notes"].append("The GM supplies actual trigger and visibility facts. A throw at an unseen landing point increases difficulty by +5 to +10; a missed grenade scatters under the source procedure.")
ITEMS["thermal_detonator"]["notes"].append("The GM supplies the actual trigger/timer. The damage bands, not the throw range, determine damage to each person in the explosion.")
for id, name, cost, avail, damage, maximum, skill, difficulty, ranges in [
    ("knife", "Knife", 25, "1", "STR+1D", "6D", "melee_combat", 5, None),
    ("throwing_knife", "Throwing Knife", 35, "1", "STR+1D", "6D", "thrown_weapons", None, (2, 3, 5, 10)),
    ("vibroaxe", "Vibroaxe", 500, "2,R", "STR+3D+1", "7D", "melee_combat", 15, None),
    ("vibroblade", "Vibroblade", 250, "2,F", "STR+3D", "6D+2", "melee_combat", 15, None),
    ("lightsaber", "Lightsaber", None, "4,X", "5D", None, "lightsaber", 20, None),
]:
    add(id, name, "melee", cost, avail, "156–157", ["Throwing knives may also be used as normal melee knives."] if id == "throwing_knife" else [], damage=damage, original_damage=damage, d6_damage_max=maximum, d6_skill=skill, d6_difficulty=difficulty, d6_ranges=ranges, damage_type="energy" if id == "lightsaber" else "physical")
ITEMS["lightsaber"]["special_purchase"] = True
add("gaderffii", "Gaderffii", "melee", None, "GM", "167", ["Weapons reference chart: STR+1D, difficulty 5. No sale price or damage maximum is supplied in that chart."], damage="STR+1D", original_damage="STR+1D", d6_skill="melee_combat", d6_difficulty=5, damage_type="physical")
add("black_powder_pistol", "Black Powder Pistol", "weapon", None, "GM", "169", ["Character template lists 3D damage. Price, range and ammunition metadata require actual GM statistics; this does not create unlimited ammunition."], item_type="weapon", damage="3D", original_damage="3D", d6_skill="firearms", damage_type="physical")
ITEMS["black_powder_pistol"].update(category="template_reference", purchasable=False)
for id, name, cost, avail, energy, physical, dexterity, locations, sides, notes in [
    ("blast_helmet", "Blast Helmet", 300, "1", "0D+1", "1D", 0, ["head"], ["front", "back"], ["Head protection only, front and back."]),
    ("blast_vest", "Blast Vest", 300, "1", "0D+1", "1D", 0, ["torso"], ["front"], ["Torso protection from the front only; no back protection is printed."]),
    ("bounty_hunter_armor", "Corellian PowerSuit", 2500, "2,R", "1D", "2D", 1, LOCATIONS, ["front", "back"], ["Full body armor; −1D to Dexterity skills. Adds +1D to lifting, applied only for actual lifting."]),
    ("stormtrooper_armor", "Stormtrooper Armor", 2500, "3,X", "1D", "2D", 1, LOCATIONS, ["front", "back"], ["Description says unavailable for sale; the cost chart nevertheless lists 2,500 credits. Record actual GM acquisition facts. Helmet comlink; MFTAS adds +2D to Perception in darkness/smoke/obscured visibility, and +2D to ranged weapon skills against targets moving more than10m in a round. Climate-controlled body glove helps in moderately hot/cold conditions. These are conditional effects, not an always-on targeting bonus."]),
]:
    add(id, name, "armor", cost, avail, "157–158", notes, armor_energy=energy, armor_physical=physical,
        original_armor_energy=energy, original_armor_physical=physical,
        armor_dexterity_penalty=dexterity, armor_locations=locations, armor_sides=sides)
ITEMS["stormtrooper_armor"]["special_purchase"] = True

ASSETS = [
    ("airspeeder", "Airspeeder", "1,F", 15000, 10000), ("cloud_car", "Cloud Car", "2,F", 75000, 18000),
    ("landspeeder", "Landspeeder", "1,F", 10000, 2000), ("sail_barge", "Sail Barge", "2,F", 250000, 50000),
    ("skiff", "Skiff", "1,F", 25000, 6000), ("speeder_bike", "Speeder Bike", "2,F", 5000, 1000),
    ("swoop", "Swoop", "2,F", 7000, 1500), ("atgar_tower", "Atgar 1.4 FD P-Tower", "2,R or X", 10000, 2000),
    ("ion_cannon", "KDY v-150 Ion Cannon", "3,X", 500000, 100000),
    ("starfighter", "Starfighter (150,000+)", "2,R or X", 150000, None),
    ("corvette", "Corellian Corvette", "2,R", 3500000, 1500000),
    ("yt1300", "Stock YT-1300 Transport", "2,F", 100000, 25000),
    ("ghtroc", "Stock Ghtroc Freighter", "3,F", 98500, 23000),
    ("scout", "Sienar Lone Scout", "2,F", 125000, 30000),
    ("droid_degree_1", "First-degree Droid", "2", 5000, None), ("droid_degree_2", "Second-degree Droid", "2", 4000, None),
    ("droid_degree_3", "Third-degree Droid", "2", 3000, None), ("droid_degree_4", "Fourth-degree Droid", "2", 5000, None),
    ("droid_degree_5", "Fifth-degree Droid", "2", 1000, None), ("r2", "R2 Astromech Droid", "2", 4525, None),
    ("9g", "DeepSpace 9G Explorer Droid", "2", 6700, None), ("k4", "K4 Security Droid", "2,R or X", 7500, None),
    ("3po", "3PO Human-cyborg Relations Droid", "2", 3000, None),
]
for id, name, availability, cost, used in ASSETS:
    ITEMS[f"asset_{id}"] = {"id": f"asset_{id}", "name": name, "category": "asset_reference", "cost": cost,
        "used_cost": used, "availability": availability, "purchasable": False,
        "source": "WEG40055 (1992), printed p.161.", "notes": ["Price reference only. Actual craft, artillery or NPC acquisition requires its full source statistics and the appropriate native workflow."], "item": None}
ITEMS["asset_bacta_treatment"] = {"id": "asset_bacta_treatment", "name": "Bacta Tank / Treatment", "category": "asset_reference", "cost": None, "availability": "GM", "purchasable": False,
    "source": "WEG40055 (1992), printed p.67.", "notes": ["No price is printed here. A Very Easy Medicine total operates the tank; an untrained operator requires Heroic First Aid/Technical, with severe failure consequences. This catalog does not grant treatment or an invented portable tank."], "item": None}


def catalog():
    return {"items": list(ITEMS.values()), "availability_codes": AVAILABILITY, "notes": NOTES, "source": SOURCE,
        "repair_table": [{"damage": key, "percent": percent, "difficulty_min": low, "difficulty_max": high} for key, percent, low, high in [("lightly_damaged", 15, 6, 10), ("heavily_damaged", 25, 11, 15), ("severely_damaged", 35, 21, 30)]],
        "improvement_table": [{"pips": i, "percent": percent, "difficulty_min": low, "difficulty_max": high} for i, (percent, low, high) in enumerate([(15, 6, 10), (25, 11, 15), (30, 16, 20), (35, 21, 30), (50, 31, 1000)], 1)]}


def pips(value):
    dice, extra = parse_code(value)
    return dice * 3 + extra


def code(value):
    dice, extra = divmod(max(0, value), 3)
    return f"{dice}D" + (f"+{extra}" if extra else "")


def quote_purchase(req, actor):
    entry = ITEMS.get(req.catalog_id)
    if not entry or not entry["purchasable"]:
        raise ValueError("Choose personal equipment; asset prices are references, not fictional inventory acquisitions.")
    if not req.availability_confirmed or not req.reason.strip():
        raise ValueError("Record the actual seller, stock and local availability before purchasing.")
    availability = entry["availability"]
    restricted = "R" in availability or "X" in availability
    if restricted and req.legal_basis not in {"licensed", "authorized", "black_market"}:
        raise ValueError("Record the actual license/authorization or black-market source for these restricted goods.")
    if req.legal_basis in {"licensed", "authorized"} and not req.permit_confirmed:
        raise ValueError("Confirm the actual relevant permit or authorization; none is created automatically.")
    if "X" in availability and "R or X" not in availability and req.legal_basis == "licensed":
        raise ValueError("Normally illegal equipment requires actual special authorization or a recorded black-market acquisition.")
    if entry.get("special_purchase") and not req.special_acquisition_confirmed:
        raise ValueError("This item is unavailable in ordinary sales or has conflicting source prices. Confirm the actual exceptional acquisition.")
    if entry.get("wookiee_only") and actor.d6.species_id != "wookiee" and actor.race.lower() != "wookiee":
        raise ValueError("The printed bowcaster seller restriction is Wookiee-only. Select the actual Wookiee purchaser.")
    price = req.unit_price if req.unit_price is not None else entry["cost"]
    if price is None:
        raise ValueError("No price is printed for this item; the GM must record its actual cost.")
    return EquipmentPurchaseQuote(catalog_id=req.catalog_id, name=entry["name"], quantity=req.quantity,
        unit_price=price, total=price * req.quantity, availability=availability,
        notes=entry["notes"] + (["Actual GM price differs from the source chart."] if req.unit_price is not None and req.unit_price != entry["cost"] else []), source=entry["source"])


def make_item(catalog_id, unit_cost=None):
    fields = dict(ITEMS[catalog_id]["item"])
    if unit_cost is not None:
        fields["unit_cost"] = unit_cost
    return Item(**fields)


def inventory_item(session, item_id):
    item = next((item for item in session.character.inventory if item.id == item_id and item.quantity > 0), None)
    if item is None:
        raise ValueError("Choose an actual, available party inventory item by its saved ID.")
    return item


def reload_requirements(session, actor_id, item_id, primary=True, power=False):
    """Validate the complete supply transaction before any roll or item mutation."""
    item = inventory_item(session, item_id)
    if item.item_type != "weapon" or item.equipped_by != actor_id:
        raise ValueError("Reload the actual weapon assigned to this actor.")
    if item.weapon_damage_state in {"severely_damaged", "destroyed"}:
        raise ValueError("This weapon is unusable; repair a salvageable weapon before reloading it.")
    if not primary and not power:
        raise ValueError("Choose an actual ammunition or power feed to reload.")
    if item.requires_generator and not item.generator_connected:
        raise ValueError("This weapon needs its actual connected generator.")
    changes = []
    supplies = []
    for requested, current, maximum, supply_id, label in [(primary, item.ammo, item.ammo_capacity, item.reload_catalog_id, "ammunition"), (power, item.power_ammo, item.power_ammo_capacity, item.power_reload_catalog_id, "power")]:
        if not requested:
            continue
        if maximum is None or supply_id is None:
            raise ValueError(f"No ordinary {label} reload is defined for this actual weapon.")
        if current is not None and current >= maximum:
            raise ValueError(f"This weapon's {label} feed is already full.")
        supply = next((candidate for candidate in session.character.inventory if candidate.catalog_id == supply_id and candidate.quantity > sum(used.id == candidate.id for used in supplies)), None)
        if supply is None:
            raise ValueError(f"No compatible {label} supply ({supply_id}) remains in actual inventory.")
        supplies.append(supply)
        changes.append((label, maximum))
    return item, supplies, changes


def reload_weapon(session, actor_id, item_id, primary=True, power=False):
    """Caller accounts for the source reload action/time, including a failed attempt."""
    item, supplies, changes = reload_requirements(session, actor_id, item_id, primary, power)
    result = {"success": True, "reloaded": [], "strength_check": None}
    if primary and item.catalog_id == "bowcaster":
        person = next((person for person in [session.character, *session.character.companions] if person.id == actor_id and person.d6), None)
        if person is None:
            raise ValueError("Choose the actual bowcaster user.")
        check = WEGD6Rules.roll_skill(person.d6, "strength", 15, action=False)
        result.update(success=check.success, strength_check=check.roll_result.model_dump())
        if not check.success:
            return item, result
    for supply in supplies:
        supply.quantity -= 1
    for label, maximum in changes:
        if label == "ammunition":
            item.ammo = maximum
        else:
            item.power_ammo = maximum
        result["reloaded"].append({"feed": label, "capacity": maximum})
    session.character.inventory = [candidate for candidate in session.character.inventory if candidate.quantity > 0]
    return item, result


def equipped_owner(session, item):
    return item.equipped_by or (session.character.id if item.equipped else None)


def mirror_armor(session, actor):
    armor = [item for item in session.character.inventory if equipped_owner(session, item) == actor.id and item.equipped and item.item_type == "armor" and item.armor_energy is not None and item.armor_physical is not None]
    if not armor:
        return
    def effective(item, profile):
        loss = {"intact": 0, "lightly_damaged": 1, "heavily_damaged": 3}.get(item.armor_damage_state)
        return 0 if loss is None else max(0, pips(getattr(item, profile)) - loss)
    actor.d6.armor_energy = code(max(effective(item, "armor_energy") for item in armor))
    actor.d6.armor_physical = code(max(effective(item, "armor_physical") for item in armor))
    actor.d6.dexterity_penalty = sum(item.armor_dexterity_penalty for item in armor)


def fingerprint(item):
    tracked = ("id", "quantity", "damage", "original_damage", "damage_modification_pips", "weapon_damage_state", "armor_energy", "armor_physical", "original_armor_energy", "original_armor_physical", "armor_modification_pips", "armor_damage_state", "unit_cost", "catalog_id")
    return hashlib.sha256(json.dumps({key: getattr(item, key) for key in tracked}, sort_keys=True).encode()).hexdigest()


def quote_work(item, req):
    if item.quantity != 1:
        raise ValueError("Quote work for one actual physical item, not an ambiguous inventory stack.")
    entry = ITEMS.get(item.catalog_id, {})
    armor = item.item_type == "armor" and item.armor_energy is not None and item.armor_physical is not None
    blaster = item.item_type == "weapon" and (entry.get("category") == "blaster" or item.d6_skill == "blaster")
    if not armor and not blaster:
        raise ValueError("The printed personal work tables cover actual armor profiles and blasters, not an invented repair skill for other equipment.")
    damage = item.armor_damage_state if armor else item.weapon_damage_state
    if damage == "destroyed":
        raise ValueError("Destroyed armor and personal weapons cannot be repaired or improved with these rules.")
    value = req.asset_value or item.unit_cost
    if not value:
        raise ValueError("Record the actual original item value before pricing replacement parts.")
    old = new = None
    if req.operation == "repair":
        bands = {"lightly_damaged": (15, 6, 10), "heavily_damaged": (25, 11, 15), "severely_damaged": (35, 21, 30)}
        if damage not in bands:
            raise ValueError("This item has no recorded repairable damage.")
        percent, low, high = bands[damage]
    else:
        if damage != "intact":
            raise ValueError("Repair the actual damage before attempting an improvement.")
        if not 1 <= req.target_pips <= 5:
            raise ValueError("Choose an actual improvement of +1 through +5 pips from the original value.")
        percent, low, high = [(15, 6, 10), (25, 11, 15), (30, 16, 20), (35, 21, 30), (50, 31, 1000)][req.target_pips - 1]
        if armor:
            if req.armor_profile not in {"energy", "physical"}:
                raise ValueError("Record the actual armor protection profile being improved.")
            old = getattr(item, f"armor_{req.armor_profile}")
            original = getattr(item, f"original_armor_{req.armor_profile}") or old
            current = pips(old) - pips(original)
        else:
            old, original = item.damage, item.original_damage or item.damage
            if not old or old.upper().startswith("STR"):
                raise ValueError("The blaster improvement table needs an actual fixed damage code.")
            current = pips(old) - pips(original)
        if req.target_pips <= current:
            raise ValueError("The requested improvement must exceed the actual saved improvement from the original value.")
        new = code(pips(original) + req.target_pips)
    difficulty = req.gm_difficulty if req.gm_difficulty is not None else low if high == 1000 else high
    if not low <= difficulty <= high:
        raise ValueError(f"The source requires a difficulty in the {low}–{high} band for this work.")
    if not req.reason.strip():
        raise ValueError("Record the actual damage, tools, facilities and GM-approved procedure.")
    return EquipmentWorkQuote(item_id=item.id, item_name=item.name, operation=req.operation,
        skill="armor_repair" if armor else "blaster_repair", difficulty=difficulty,
        parts_cost=math.ceil(value * percent / 100), percent=percent, fingerprint=fingerprint(item), old_value=old, new_value=new,
        notes=["Parts are paid once per saved project; retries use those reserved parts.", "Standard attempts take 15 minutes, then one hour, then two hours; actual GM timing changes require a reason.", "Improvements are measured from the original code and stop at +1D+2. This does not improve range, ammo, or unrelated equipment functions."],
        source="WEG40055 (1992), printed pp.68, 86–87.")


def apply_work(item, project):
    request = project.request
    if request.operation == "repair":
        if item.item_type == "armor":
            item.armor_damage_state = "intact"
        else:
            item.weapon_damage_state = "intact"
    elif item.item_type == "armor":
        key = f"armor_{request.armor_profile}"
        original_key = f"original_{key}"
        if getattr(item, original_key) is None:
            setattr(item, original_key, getattr(item, key))
        setattr(item, key, project.quote.new_value)
        item.armor_modification_pips = max(item.armor_modification_pips, request.target_pips)
    else:
        item.original_damage = item.original_damage or item.damage
        item.damage = project.quote.new_value
        item.damage_modification_pips = request.target_pips
