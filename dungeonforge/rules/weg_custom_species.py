"""Translate an explicitly approved new species into ordinary creation constraints."""
from dungeonforge.rules.weg_custom_species_models import D6CustomSpecies, SOURCE


def profile(record):
    record = D6CustomSpecies.model_validate(record.model_dump())
    return {"id": record.id, "name": record.name, "attribute_dice": record.average_attribute_dice + 6,
        "minimums": dict(record.minimums), "maximums": dict(record.maximums),
        "move": record.move, "move_maximum": record.move_maximum, "creation_bonus_skills": [],
        "source": f"{SOURCE} GM species write-up: {record.source}",
        "notes": [f"GM-defined {record.name}: average {record.average_attribute_dice}D + 6D player allowance; 7D starting skills.",
                  "The printed 12D average and 1D–5D limits are design guidelines; this record uses the GM's explicit budget and all six bounds.",
                  "Species abilities, disadvantages, breathing needs and story factors remain saved GM rulings. Prose does not grant automatic dice, equipment, immunities or known powers.",
                  f"GM balance rationale: {record.gm_rationale}"]}


def summary(record):
    bounds = ", ".join(f"{key} {record.minimums[key]}–{record.maximums[key]}" for key in record.minimums)
    return (f"{record.name} [{record.id}]; average {record.average_attribute_dice}D + 6D PC allowance; bounds {bounds}; "
            f"Move {record.move}/{record.move_maximum}. Concept: {record.concept} Biology: {record.biology} "
            f"Breathing/environment: {record.breathing_needs} Culture/technology: {record.culture} "
            f"GM abilities/procedures: {record.special_abilities} Disadvantages: {record.disadvantages} "
            f"Story factors: {record.story_factors} GM balance ruling: {record.gm_rationale} "
            f"Write-up: {record.source} Rules: {SOURCE} Prose alone grants no automatic bonuses, equipment, immunity or powers.")
