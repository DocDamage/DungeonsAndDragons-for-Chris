"""Small, editable WEG40055 craft catalog; no R&E scale/stat substitutions."""

from dungeonforge.rules.weg_vehicle_models import D6Vehicle, D6VehicleWeapon


def weapon(id, name, damage, fire_control="2D", *, pilot_operated=True, **kwargs):
    system = kwargs.pop("system", {"missile": "torpedo", "ion": "ion", "tractor": "tractor"}.get(kwargs.get("kind"), "laser"))
    return D6VehicleWeapon(id=id, name=name, damage=damage, fire_control=fire_control, system=system, pilot_operated=pilot_operated, **kwargs)


def vehicle_presets():
    presets = {
        "yt1300": D6Vehicle(name="Stock YT-1300 Transport", hull="4D", maneuverability="0D", shields="0D", space_move=4, atmosphere_move=280,
            weapons=[weapon("laser", "Laser cannon (turret)", "4D", arcs=["front", "back", "left", "right"])],
            source="WEG40055, PDF p.114 / printed p.121; atmosphere Move uses the p.110 conversion table (4 → 280m)."),
        "ghtroc": D6Vehicle(name="Ghtroc 720 Freighter", hull="3D+2", maneuverability="1D", shields="1D", space_move=3, atmosphere_move=260,
            weapons=[weapon("laser", "Double laser cannon", "4D", "1D+2")], source="WEG40055, PDF p.114 / printed p.121."),
        "xwing": D6Vehicle(name="X-wing", hull="4D", maneuverability="3D", shields="1D", space_move=8, atmosphere_move=365, piloting_skill="starfighter_piloting",
            weapons=[weapon("laser", "Fire-linked laser cannons", "6D", "3D"), weapon("torpedo", "Proton torpedoes", "9D", kind="missile", ammo=6, space_ranges=(1, 1, 3, 7), atmosphere_ranges=(30, 100, 300, 700))],
            source="WEG40055, PDF pp.109–110 / printed pp.115–116. Torpedo ammunition: scenario load of six (GM editable)."),
        "ywing": D6Vehicle(name="Y-wing", hull="4D", maneuverability="2D", shields="1D+2", space_move=7, atmosphere_move=350, piloting_skill="starfighter_piloting",
            weapons=[weapon("laser", "Fire-linked laser cannons", "5D"), weapon("ion", "Light ion cannons (turret)", "4D", "3D", pilot_operated=False, kind="ion", system="ion", arcs=["front", "back", "left", "right"], space_ranges=(1, 3, 7, 36), atmosphere_ranges=(100, 300, 700, 3600)), weapon("torpedo", "Proton torpedoes", "9D", kind="missile", ammo=6, space_ranges=(1, 1, 3, 7), atmosphere_ranges=(50, 100, 300, 700))],
            source="WEG40055, PDF p.110 / printed p.116. Torpedo ammunition: scenario load of six (GM editable)."),
        "tie_fighter": D6Vehicle(name="TIE/ln Fighter", hull="2D", maneuverability="2D", space_move=10, atmosphere_move=415, piloting_skill="starfighter_piloting",
            weapons=[weapon("laser", "Fire-linked laser cannons", "5D")], source="WEG40055, PDF p.110 / printed p.117."),
        "airspeeder": D6Vehicle(name="Rebel Combat Airspeeder", kind="vehicle", scale="speeder", hull="3D", maneuverability="3D", space_move=0, atmosphere_move=350, piloting_skill="repulsorlift_operation",
            weapons=[weapon("laser", "Double laser cannon", "4D+2", skill="vehicle_blasters", atmosphere_ranges=(50, 300, 800, 1500))],
            source="WEG40055, PDF pp.96–97 / printed pp.99–100. Harpoon/tow-cable tactics require GM adjudication."),
        "atst": D6Vehicle(name="Imperial AT-ST", kind="vehicle", scale="walker", hull="3D", maneuverability="1D", space_move=0, atmosphere_move=30, piloting_skill="walker_operation",
            weapons=[weapon("blaster", "Twin blaster cannon", "4D", "1D", skill="vehicle_blasters", atmosphere_ranges=(50, 200, 1000, 2000))], source="WEG40055, PDF p.100 / printed p.103. One representative cannon."),
        "corvette": D6Vehicle(name="Corellian Corvette", scale="capital", hull="4D", maneuverability="2D", shields="2D", space_move=6, atmosphere_move=330, piloting_skill="capital_ship_piloting",
            weapons=[weapon("turbolaser", "Forward double turbolaser", "4D+2", "3D", skill="capital_ship_gunnery", scale="starfighter", space_ranges=(3, 15, 35, 75), atmosphere_ranges=(6000, 30000, 70000, 150000))],
            source="WEG40055, PDF p.112 / printed p.119. One forward emplacement; stations represent the operating crew, not the full complement."),
        "star_destroyer": D6Vehicle(name="Imperial I Star Destroyer", scale="capital", hull="7D", maneuverability="1D", shields="3D", space_move=6, atmosphere_move=0, piloting_skill="capital_ship_piloting",
            weapons=[weapon("turbolaser", "Forward turbolaser battery", "5D", "4D", skill="capital_ship_gunnery", space_ranges=(3, 15, 36, 75), atmosphere_ranges=(6000, 15000, 72000, 150000)), weapon("ion", "Forward ion cannon", "3D", "2D+2", kind="ion", system="ion", skill="capital_ship_gunnery", space_ranges=(1, 10, 25, 50), atmosphere_ranges=(2000, 20000, 50000, 100000)), weapon("tractor", "Forward tractor beam", "6D", "4D", kind="tractor", system="tractor", skill="capital_ship_gunnery", space_ranges=(1, 5, 15, 30), atmosphere_ranges=(2000, 10000, 30000, 60000))],
            source="WEG40055, PDF pp.111–112 / printed pp.118–119. Representative forward stations; massed battery/command bonuses are GM adjudicated."),
    }
    equipment = {"yt1300": (2, 12, True, 100000), "ghtroc": (2, 15, True, 98500),
        "xwing": (1, None, False, 0), "ywing": (1, None, False, 0), "corvette": (2, None, True, 3500000),
        "star_destroyer": (2, 8, True, 0)}
    for id, (main, backup, nav, value) in equipment.items():
        craft = presets[id]
        craft.hyperdrive_multiplier, craft.backup_hyperdrive, craft.nav_computer, craft.purchase_value = main, backup, nav, value
    return presets
