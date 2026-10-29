"""Read-only context for the saved personal equipment and paid-parts ledger."""
import json
from typing import TYPE_CHECKING

from dungeonforge.rules.weg_equipment import code, equipped_owner, fingerprint
from dungeonforge.rules.weg_personal_equipment import armor_pips

if TYPE_CHECKING:
    from dungeonforge.game.models import GameSession


def build_equipment_context(session: "GameSession", *, max_items=40, max_receipts=6, max_projects=12) -> str:
    """Describe actual inventory identities; never create, reload or charge gear."""
    if session.edition != "weg_d6" or session.character.d6 is None:
        return ""
    people = {person.id: person for person in [session.character, *session.character.companions] if person.d6}
    state = session.d6_equipment
    inventory = {item.id: item for item in session.character.inventory if item.quantity > 0}
    pending_ids = {project.request.item_id for project in state.work_projects if project.status == "pending"}
    items = sorted(inventory.values(), key=lambda item: (not item.equipped, item.id not in pending_ids, item.name, item.id))
    lines = ["### WEG D6 PERSONAL EQUIPMENT — SAVED MECHANICAL STATE",
        "Source: WEG40055 (1992), printed pp.65–68, 86–87, 153–161.",
        f"Party wallet: {session.character.d6.credits} credits. Inventory IDs identify actual physical records, including after save/load.",
        "Ammunition, damage and paid parts below are already accounted for. Narration does not refill a weapon, repeat a payment, supply a permit or complete a pending roll."]
    for item in items[:max(0, max_items)]:
        owner = equipped_owner(session, item) if item.equipped else None
        fields = [f"{json.dumps(item.name, ensure_ascii=False)} [{item.id}]", f"quantity {item.quantity}",
            f"equipped by {people[owner].name if owner in people else owner}" if owner else "not equipped"]
        if item.catalog_id:
            fields.append(f"catalog {item.catalog_id}")
        if item.item_type == "weapon":
            fields += [f"damage {item.damage or 'GM-defined'}", f"weapon condition {item.weapon_damage_state}"]
            if item.original_damage is not None:
                fields.append(f"original damage {item.original_damage}; improvement +{item.damage_modification_pips} pips")
            fields.append(f"ammunition {item.ammo}/{item.ammo_capacity}" if item.ammo is not None and item.ammo_capacity is not None else "ammunition not recorded; do not assume a full supply")
            if item.power_ammo_capacity is not None:
                fields.append(f"separate power {item.power_ammo}/{item.power_ammo_capacity}")
            if item.reload_catalog_id:
                fields.append(f"reload supply catalog {item.reload_catalog_id}")
            if item.power_reload_catalog_id:
                fields.append(f"power supply catalog {item.power_reload_catalog_id}")
            if item.requires_generator or item.generator_connected:
                fields.append(f"generator required {item.requires_generator}; actually connected {item.generator_connected}")
            if item.d6_can_stun:
                fields.append(f"saved setting {'stun' if item.stun_mode else 'normal damage'}")
        if item.item_type == "armor" and item.armor_energy is not None and item.armor_physical is not None:
            fields += [f"armor condition {item.armor_damage_state}",
                f"listed energy +{item.armor_energy}, physical +{item.armor_physical}; effective energy +{code(armor_pips(item, 'energy'))}, physical +{code(armor_pips(item, 'physical'))}",
                f"Dexterity penalty -{item.armor_dexterity_penalty}D",
                f"coverage {','.join(item.armor_locations)}; sides {','.join(item.armor_sides)}"]
            if item.original_armor_energy is not None or item.original_armor_physical is not None:
                fields.append(f"original energy {item.original_armor_energy or item.armor_energy}, physical {item.original_armor_physical or item.armor_physical}; improvement ceiling +5 pips from each original profile")
        lines.append("- " + "; ".join(fields))
    if len(items) > max_items:
        lines.append(f"{len(items) - max(0, max_items)} further inventory records omitted from this summary; consult the actual inventory for them.")
    for person in people.values():
        actual = [item for item in inventory.values() if item.equipped and equipped_owner(session, item) == person.id and item.item_type == "armor" and item.armor_energy is not None and item.armor_physical is not None]
        if not actual:
            lines.append(f"{person.name}: no actual native armor profile worn; saved GM sheet armor energy +{person.d6.armor_energy}, physical +{person.d6.armor_physical}, Dexterity -{person.d6.dexterity_penalty}D. Do not add a stored prior baseline on top of worn armor.")
    for receipt in state.purchases[-max_receipts:] if max_receipts > 0 else []:
        lines.append(f"Purchase {receipt.id}: {receipt.quote.quantity} x {json.dumps(receipt.quote.name, ensure_ascii=False)}; {receipt.quote.total} credits ALREADY PAID ({receipt.quote.unit_price}/unit); acquisition {receipt.legal_basis}, source availability {receipt.quote.availability}; acquired IDs {','.join(receipt.inventory_ids)}; saved GM facts {json.dumps(receipt.reason, ensure_ascii=False)}.")
    if len(state.purchases) > max_receipts:
        lines.append(f"{len(state.purchases) - max(0, max_receipts)} earlier purchase receipts remain saved.")
    projects = sorted(state.work_projects, key=lambda project: project.status != "pending")
    for project in projects[:max(0, max_projects)]:
        item = inventory.get(project.request.item_id)
        freshness = ""
        if project.status == "pending":
            freshness = "; actual item missing" if item is None else "; actual item changed — work must be reviewed/cancelled before another attempt" if fingerprint(item) != project.quote.fingerprint else "; actual item fingerprint matches"
        lines.append(f"Equipment project {project.id}: {project.status}; {project.request.operation} {json.dumps(project.quote.item_name, ensure_ascii=False)} [{project.request.item_id}]; {project.paid_credits} parts credits ALREADY PAID ONCE; {project.quote.skill} difficulty {project.quote.difficulty}{freshness}; saved GM facts {json.dumps(project.request.reason, ensure_ascii=False)}.")
        if project.quote.new_value is not None:
            lines.append(f"  Declared profile {project.request.armor_profile or 'weapon damage'}: {project.quote.old_value} -> {project.quote.new_value}; a pending project has not granted this improvement.")
        for attempt in project.attempts[-3:]:
            result = "interrupted" if attempt.get("interrupted") else "success" if attempt.get("success") else "failed"
            lines.append(f"  Saved attempt: actor {attempt.get('actor_id')}; {attempt.get('minutes')} minutes already elapsed; {result}; {attempt.get('cp', 0)} CP and {int(bool(attempt.get('fp')))} FP already accounted for.")
        if project.status == "pending":
            minutes = (15, 60, 120)[min(len(project.attempts), 2)]
            lines.append(f"  Next standard attempt {minutes} minutes; reserved parts cover retry, no second parts payment. Actual technician, available time and native check remain required.")
        if project.cancellation_reason:
            lines.append(f"  Cancellation {json.dumps(project.cancellation_reason, ensure_ascii=False)}; no automatic refund.")
    if len(projects) > max_projects:
        lines.append(f"{len(projects) - max(0, max_projects)} additional equipment projects remain saved.")
    from dungeonforge.context.weg_gear_effect_context import build_gear_effect_context
    conditional = build_gear_effect_context(session)
    if conditional:
        lines.append(conditional)
    return "\n".join(lines)
