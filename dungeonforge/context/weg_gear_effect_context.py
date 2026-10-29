"""Source gear facts and actual preparation proof for narrative context."""
import json

from dungeonforge.rules import weg_gear_effects as gear


def build_gear_effect_context(session) -> str:
    if session.edition != "weg_d6":
        return ""
    working = session.model_copy(deep=True)
    gear.refresh(working)
    names = {person.id: person.name for person in [working.character, *working.character.companions]}
    if working.encounter:
        names.update({person.id: person.name for person in working.encounter.combatants})
    lines = []
    for actor_id, (state, _) in gear.roster(working).items():
        facts = state.gear_context
        if not (facts.powersuit_id or facts.mftas_id or facts.macro_item_id or facts.preparation):
            continue
        if not lines:
            lines = ["### CONDITIONAL PERSONAL EQUIPMENT", gear.SOURCE,
                "Equipment bonuses are derived by native checks from actual objects; narration cannot grant a bonus, extend weapon range or invent completed preparation. External gear dice are not Force Point doubled."]
        lines.append(f"{names.get(actor_id, actor_id)} [{actor_id}]: actual GM facts {json.dumps(facts.reason, ensure_ascii=False)}.")
        if facts.powersuit_id:
            item = gear.actual(facts, facts.powersuit_id)
            valid = gear.armor_function(facts, facts.powersuit_id, "bounty_hunter_armor", facts.powersuit_functional, facts.powersuit_reviewed_damage)
            lines.append(f"  PowerSuit [{facts.powersuit_id}]: actual item {item.name if item else 'missing/ambiguous'}, current source function valid {valid}; reviewed damage {facts.powersuit_reviewed_damage}, actual damage {item.armor_damage_state if item else 'missing'}. Printed +1D applies to lifting only, never general Strength, melee damage or resistance.")
        if facts.mftas_id:
            item = gear.actual(facts, facts.mftas_id)
            valid = gear.armor_function(facts, facts.mftas_id, "stormtrooper_armor", facts.mftas_functional, facts.mftas_reviewed_damage, helmet=True)
            lines.append(f"  MFTAS [{facts.mftas_id}]: actual worn head-covering source function valid {valid}; reviewed damage {facts.mftas_reviewed_damage}, actual damage {item.armor_damage_state if item else 'missing'}. +2D literal Perception attribute in obscured visibility; +2D ranged weapon skills only against the confirmed target moving more than10m in this round.")
        lines.append(f"  Next-action conditions current {gear.current_facts(facts)}; saved encounter {facts.observed_encounter_id}, round {facts.observed_round}, action history index {facts.observed_history_index}. Obscured visibility {facts.visibility_obscured}; appropriate visual task confirmed {facts.visual_task_confirmed}, exact skill {facts.visual_skill}; actual target {json.dumps(facts.target_id, ensure_ascii=False)}, distance {facts.view_distance_m}m, movement {facts.target_movement_m}m/round. Reconfirm expired conditions before another action.")
        if facts.macro_item_id:
            item = gear.actual(facts, facts.macro_item_id)
            lines.append(f"  Macrobinoculars [{facts.macro_item_id}]: actual source instrument function valid {gear.macro_function(facts)}; use {facts.macro_mode}, actual model range {facts.macro_model_range_m}m, actual current condition {item.weapon_damage_state if item else 'missing'}. Appropriate visual Perception/search task beyond100m only: +3D; normal modifiers remain.")
            lines.append(f"  Actual linked blaster [{facts.linked_weapon_id}]; software confirmed {facts.software_confirmed}, facts {json.dumps(facts.software_facts, ensure_ascii=False)}; steady sniper rest {facts.steady_rest}, same position maintained {facts.position_maintained}. Linked +3D requires real preparation and native medium/long range, not point-blank/short or beyond the actual blaster's range.")
        if facts.preparation:
            prep = facts.preparation
            lines.append(f"  Saved preparation proof: actual server action-history witness verified {facts._preparation_verified}, index {prep.history_index}, nonce {prep.nonce}; macro [{prep.macro_item_id}], weapon [{prep.weapon_id}], target {json.dumps(prep.target_id, ensure_ascii=False)}, encounter {prep.encounter_id}, preparation round {prep.round_number}, completed elapsed round {prep.completed_elapsed_round}. A saved object without its matching real action witness grants nothing; changed target/weapon/position requires reassessment.")
    return "\n".join(lines)
