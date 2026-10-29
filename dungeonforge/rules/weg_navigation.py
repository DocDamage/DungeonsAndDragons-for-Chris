"""1992 astrogation tables, printed pp.110–112, not R&E travel rules."""
import math
from dungeonforge.rules.weg_navigation_models import D6NavigationQuote

SYSTEMS = ["Alderaan", "Bespin", "Celanon", "Corellia", "Coruscant", "Dagobah", "Dantooine", "Endor", "Gamorr", "Lianna", "Sullust", "Tatooine"]
# Upper triangle transcribed from the printed p.112 gazetteer and visually checked.
ROWS = [
    "8h 2d12h 6h 16h 1d6h 13h 18h 7d12h 13d4h 8d21h 7h",
    "2d20h 6h 6d14h 1d3h 22h 1d8h 3d3h 18d12h 11d4h 16h",
    "8h 13h 16d5h 1d22h 2d17h 8d9h 14h 15h 4d6h",
    "4h 1d7h 12h 17h 10d14h 15h 19h 4h",
    "12d14h 19h 6d12h 16d3h 12d14h 8d2h 22d14h",
    "1d8h 4d1h 27d8h 31d15h 3d6h 1d4h",
    "21h 3d14h 19h 5d6h 20h", "14d5h 18d2h 19h 1d",
    "23d4h 3d2h 1d16h", "3d12h 2d3h", "1d14h",
]


def hours(value):
    days, sep, remainder = value.partition('d')
    return int(days) * 24 + int(remainder.removesuffix('h') or 0) if sep else int(value.removesuffix('h'))


ROUTES = [{"origin": SYSTEMS[i], "destination": SYSTEMS[i + j + 1], "hours": hours(value), "printed_duration": value} for i, row in enumerate(ROWS) for j, value in enumerate(row.split())]
FACTORS = {"major": 1, "common": 1.1, "light": 1.25, "infrequent": 1.5, "old": 2, "unexplored": 2.5}
TERMINAL = {"arrived", "aborted", "interrupted", "off_course", "abandoned"}


def route_hours(origin, destination):
    key = {origin.strip().lower(), destination.strip().lower()}
    return next((item["hours"] for item in ROUTES if {item["origin"].lower(), item["destination"].lower()} == key), None)


def active(session):
    return next((item for item in reversed(session.d6_navigation.journeys) if item.status not in TERMINAL), None)


def quote(craft, req, has_astromech=False):
    if craft.kind != "starship" or craft.damage in {"destroyed", "severely_damaged"} or craft.hull_breached:
        raise ValueError("Choose a spaceworthy starship; severe damage or a breached hull prevents jumping.")
    if craft.controls_dead or craft.generator_shutdown or craft.drives_disabled or craft.destruction_countdown is not None or craft.airborne:
        raise ValueError("The ship must be in space with working controls, power and sublight drives, free of a destruction countdown.")
    multiplier = craft.backup_hyperdrive if req.backup else craft.hyperdrive_multiplier
    if multiplier is None or not req.backup and craft.hyperdrive_disabled:
        raise ValueError("This selected hyperdrive is absent or disabled; repair it or select an installed backup.")
    if not req.boarding_confirmed or req.clearance_units < 50:
        raise ValueError("Confirm the party is aboard and the actual clearance is at least 50 space units from the planet.")
    origin, destination = req.origin.strip(), req.destination.strip()
    if not origin or not destination or origin.lower() == destination.lower() or not req.reason.strip():
        raise ValueError("Record distinct actual origin/destination systems and the GM's route facts.")
    if craft.location and craft.location.lower() != origin.lower():
        raise ValueError(f"This ship is recorded at {craft.location}; use that origin or correct its actual location first.")
    base = req.base_hours if req.base_hours is not None else route_hours(origin, destination)
    if base is None:
        raise ValueError("This route is outside the gazetteer; the GM must supply its base travel duration.")
    navigation = (craft.nav_computer and not craft.nav_computer_disabled) or has_astromech
    damage = 5 if craft.damage == "lightly_damaged" else 10 if craft.damage == "heavily_damaged" else 0
    difficulty = req.base_difficulty + req.obstacles + damage + (0 if navigation else 30)
    duration = base * FACTORS[req.route_type] * multiplier
    if req.hasty:
        difficulty *= 2
        duration *= 2
    if not navigation:
        duration *= 2
    difficulty = max(1, difficulty - req.extra_hours)
    duration += damage + req.extra_hours
    if duration <= 0 or not 1 <= difficulty <= 1000:
        raise ValueError("The adjusted route must retain a positive duration and a difficulty from 1 to 1000.")
    return D6NavigationQuote(difficulty=difficulty, hours=round(duration, 6), rounds=math.ceil(duration * 720), has_navigation=navigation, multiplier=multiplier,
        notes=["Route frequency and hyperdrive multiply base duration; hasty entry doubles the subtotal difficulty and duration. Actual-hour adjustments apply last.",
            "A miss of exactly ten is omitted by the printed rules. The engine holds it for an explicit GM choice, without rerolling astrogation."])
