"""Native repair tables; the 1992 book does not supply starship modification rules."""
import json
from dungeonforge.rules.weg_engineering_models import D6CraftRepairQuote


def attempt_minutes(skill, attempts):
    """Repeated attempts use the selected repair skill's printed time schedule."""
    if skill == "blaster_repair":
        schedule = (15, 60, 120)
    elif skill == "walker_repair":
        schedule = (15, 360, 1440, 2880)
    else:
        schedule = (15, 60, 1440, 2880)
    return schedule[min(attempts, len(schedule) - 1)]


def weapon_for(craft, id):
    item = next((item for item in craft.weapons if item.id == id), None)
    if item is None:
        raise ValueError("Select an actual mounted weapon.")
    return item


def fingerprint(craft, req):
    if req.system == "weapon":
        weapon = weapon_for(craft, req.weapon_id)
        state = [weapon.status, weapon.repair_damage]
    else:
        fields = {"maneuverability": ["maneuverability_lost"], "moves": ["speed_losses"], "shields": ["shields_lost"],
            "drives": ["drives_disabled"], "hyperdrive": ["hyperdrive_disabled"],
            "generator": ["generator_shutdown", "destruction_countdown", "destruction_cause"],
            "controls": ["controls_dead"], "weapons": ["weapons_disabled"], "nav_computer": ["nav_computer_disabled"],
            "escape_pods": ["escape_pods_disabled"]}[req.system]
        state = [getattr(craft, field) for field in fields]
    return json.dumps([craft.damage == "destroyed", req.system, state])


def quote(craft, req):
    if craft.damage == "destroyed":
        raise ValueError("A destroyed craft cannot be restored by a standard repair project.")
    if not req.reason.strip():
        raise ValueError("Record the actual damage, parts and repair facilities.")
    key = req.system + (":" + str(req.weapon_id) if req.system == "weapon" else "")
    if any(project.status == "pending" and project.quote.key == key for project in craft.repair_projects):
        raise ValueError("This system already has a paid repair project; attempt or cancel it first.")
    skill = "capital_starship_repair" if craft.scale in {"capital", "death_star"} else "starfighter_repair" if craft.piloting_skill == "starfighter_piloting" else "space_transports_repair"
    if craft.kind == "vehicle":
        skill = {"walker_operation": "walker_repair", "ground_vehicle_operation": "ground_vehicle_repair", "hover_vehicle_operation": "hover_vehicle_repair"}.get(craft.piloting_skill, "repulsorlift_repair")
    amount, percent, band, notes = 0, None, None, []
    if req.system == "maneuverability":
        amount = craft.maneuverability_lost
        band, percent = ((6, 10), 10) if amount == 1 else ((11, 15), 15) if amount == 2 else ((16, 20), 20)
    elif req.system == "moves":
        amount = craft.speed_losses
        band, percent = ((6, 10), 10) if amount == 1 else ((11, 15), 15) if amount == 2 else ((16, 20), 20) if amount == 3 else ((21, 30), 25)
    elif req.system == "shields":
        amount = craft.shields_lost
        band, percent = ((6, 10), 5) if amount == 1 else ((11, 15), 5) if amount == 2 else ((16, 20), 5) if amount == 3 else ((21, 30), 10)
    elif req.system == "drives":
        amount, band, percent = int(craft.drives_disabled), (16, 20), 35
    elif req.system == "generator":
        if craft.destruction_countdown is not None:
            raise ValueError("Shut down the overloaded generator before lengthy repair work; an active countdown cannot be repaired away.")
        amount, band, percent = int(craft.generator_shutdown), (16, 20), 35
    elif req.system == "hyperdrive":
        amount, band = int(craft.hyperdrive_disabled), (11, 15)
        notes.append("The book specifies Moderate but no parts price for hyperdrive repair; the actual price needs a GM ruling.")
    elif req.system == "weapon":
        weapon = weapon_for(craft, req.weapon_id)
        amount = int(weapon.status != "operational" or weapon.repair_damage != "intact")
        level = weapon.repair_damage if weapon.repair_damage != "intact" else req.assessed_damage
        if weapon.status == "destroyed" or level == "destroyed":
            if not req.replacement:
                raise ValueError("A destroyed weapon cannot be repaired; record a purchased replacement instead.")
            band, percent = None, 100
            notes.append("Replacement installation difficulty is a GM ruling; the destroyed weapon itself is not repaired.")
        else:
            band, percent = {"lightly_damaged": ((6, 10), 15), "heavily_damaged": ((11, 15), 25), "severely_damaged": ((21, 30), 35)}[level]
        skill = "capital_starship_weapon_repair" if craft.scale in {"capital", "death_star"} else "starship_weapon_repair" if craft.kind == "starship" else "blaster_repair"
    else:
        amount = int(getattr(craft, {"controls": "controls_dead", "weapons": "weapons_disabled", "nav_computer": "nav_computer_disabled", "escape_pods": "escape_pods_disabled"}[req.system]))
        notes.append("This system lacks a specific repair cost/difficulty table; record the GM's actual procedure.")
    if not amount:
        raise ValueError("This selected system has no recorded damage to repair.")
    if band:
        difficulty = req.gm_difficulty if req.gm_difficulty is not None else band[1]
        if not band[0] <= difficulty <= band[1]:
            raise ValueError(f"The source repair band is {band[0]}–{band[1]} for this damage.")
    else:
        if req.gm_difficulty is None:
            raise ValueError("Record a GM repair/installation difficulty for this unlisted system procedure.")
        difficulty = req.gm_difficulty
    if percent is not None:
        base = req.asset_value or (weapon_for(craft, req.weapon_id).purchase_value if req.system == "weapon" else craft.purchase_value)
        if not base:
            raise ValueError("Record the actual craft/weapon value used by the source's percentage-parts table.")
        cost = (base * percent + 99) // 100
    else:
        if req.gm_cost is None:
            raise ValueError("Record the GM-approved parts cost for this unlisted cost.")
        cost = req.gm_cost
    return D6CraftRepairQuote(craft_id=craft.id, key=key, skill=skill, difficulty=difficulty, parts_cost=cost, percent=percent,
        fingerprint=fingerprint(craft, req), notes=notes)


def repair(craft, req):
    if craft.damage == "destroyed":
        raise ValueError("A destroyed craft cannot be restored by a standard repair project.")
    if req.system == "weapon":
        weapon = weapon_for(craft, req.weapon_id)
        if (weapon.status == "destroyed" or weapon.repair_damage == "destroyed") and not req.replacement:
            raise ValueError("A destroyed weapon cannot be repaired; record a purchased replacement instead.")
        weapon.status, weapon.repair_damage = "operational", "intact"
    elif req.system == "generator":
        if craft.destruction_countdown is not None:
            raise ValueError("Shut down the overloaded generator before lengthy repair work; an active countdown cannot be repaired away.")
        craft.generator_shutdown = False
        craft.destruction_cause = None
    else:
        field = {"maneuverability": "maneuverability_lost", "moves": "speed_losses", "shields": "shields_lost", "drives": "drives_disabled",
            "hyperdrive": "hyperdrive_disabled", "controls": "controls_dead", "weapons": "weapons_disabled", "nav_computer": "nav_computer_disabled", "escape_pods": "escape_pods_disabled"}[req.system]
        setattr(craft, field, 0 if req.system in {"maneuverability", "moves", "shields"} else False)
    remaining = craft.maneuverability_lost or craft.speed_losses or craft.shields_lost or craft.drives_disabled or craft.hyperdrive_disabled or craft.controls_dead or craft.weapons_disabled or craft.generator_shutdown or craft.hull_breached or craft.nav_computer_disabled or craft.escape_pods_disabled or craft.destruction_countdown is not None or any(item.status != "operational" or item.repair_damage != "intact" for item in craft.weapons)
    if not remaining:
        craft.damage = "intact"
    craft.damage_log.append(f"Completed native {req.system} repair. Other damaged systems retain their damage.")
