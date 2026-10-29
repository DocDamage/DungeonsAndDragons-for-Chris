"""Source metadata for newly constructed starter gear; never upgrades saved inventory."""
from dungeonforge.rules.base import Item
from dungeonforge.rules.weg_equipment import make_item


STARTER_CATALOG = {
    "blaster_pistol": "blaster_dl18", "heavy_blaster": "heavy_blaster_dl44", "blaster_rifle": "blaster_rifle",
    "knife": "knife", "lightsaber": "lightsaber", "comlink": "personal_comlink", "medpac": "medpac",
    "datapad": "datapad", "glowrod": "glowrod", "blast_vest": "blast_vest", "survival_suit": "vacuum_survival_suit",
}
TEMPLATE_CATALOG = {
    "Blaster Pistol": "blaster_dl18", "Heavy Blaster Pistol": "heavy_blaster_dl44", "Blaster Rifle": "blaster_rifle",
    "Light Repeating Blaster": "light_repeating_blaster", "Hold-out Blaster": "holdout_q2", "Sporting Blaster": "sporting_defender",
    "Wookiee Bowcaster": "bowcaster", "Knife": "knife", "Lightsaber": "lightsaber", "Vibroblade": "vibroblade",
    "Black Powder Pistol": "black_powder_pistol", "Comlink": "personal_comlink", "Medpac": "medpac",
    "Datapad": "datapad", "Datapad of game rules": "datapad", "Vacuum survival suit": "vacuum_survival_suit",
}


def fresh_item(prototype, *, catalog_id=None, template_source=""):
    catalog_id = catalog_id or TEMPLATE_CATALOG.get(prototype.name)
    if catalog_id:
        result = make_item(catalog_id)
        # Explicit printed statistics override the generic equipment profile. Unset
        # metadata, including finite ammunition and location coverage, stays source-defined.
        overrides = prototype.model_dump(exclude_unset=True, exclude_none=True,
            exclude={"id", "item_type", "description", "catalog_id", "unit_cost", "availability", "source", "equipped_by"})
        result = Item(**{**result.model_dump(), **overrides})
        if prototype.description:
            result.description = " ".join(filter(None, [result.description, prototype.description]))
        if prototype.damage:
            result.original_damage = prototype.damage
    else:
        result = Item(**prototype.model_dump(exclude={"id"}))
    if template_source:
        result.source = " ".join(filter(None, [result.source, template_source]))
    if prototype.name == "Protective vest" and template_source:
        result.item_type, result.equipped = "armor", True
        result.armor_energy = result.armor_physical = "0D+2"
        result.original_armor_energy = result.original_armor_physical = "0D+2"
        result.armor_locations, result.armor_sides = ["torso"], ["front", "back"]
    elif prototype.name == "Cybernetic left arm" and template_source:
        result.item_type, result.equipped = "armor", True
        result.armor_energy = result.armor_physical = "1D"
        result.original_armor_energy = result.original_armor_physical = "1D"
        result.armor_locations, result.armor_sides = ["left_arm"], ["front", "back"]
    return result
