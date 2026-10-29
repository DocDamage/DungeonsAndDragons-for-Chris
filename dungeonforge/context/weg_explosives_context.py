"""Read-only source evidence for current and archived native grenade encounters."""
from dungeonforge.rules.weg_explosives import DIRECTIONS, SOURCE


def point(value):
    return f"({value.x:g}, {value.y:g})m"


def native_explosives_summary(session, *, guidance=True):
    if session.edition != "weg_d6":
        return ""
    encounters = {}
    current = session.encounter
    for encounter in [*getattr(session, "d6_combat_history", [])[-5:], *([current] if current else [])]:
        state = encounter.d6_explosives
        if encounter.system != "weg_d6" or not (state.grenades or state.positions or state.intents):
            continue
        encounters.pop(encounter.id, None)
        encounters[encounter.id] = encounter
    if not encounters:
        return ""
    lines = ["### NATIVE WEG GRENADES AND EXPLOSIONS", f"Source: {SOURCE}"]
    for encounter in encounters.values():
        state = encounter.d6_explosives
        names = {actor.id: actor.name for actor in encounter.combatants}
        name = lambda id: names.get(id, id)
        label = "current" if current and current.id == encounter.id else "archived"
        live = [grenade for grenade in state.grenades if grenade.status == "armed"]
        lines.append(f"Grenade encounter {encounter.id}: {label}; active {encounter.active}; saved round {encounter.round}; round-end reaction pause {getattr(encounter, 'd6_round_closing', False)}; actual live fuses {len(live)}.")
        if state.positions:
            lines.append(f"GM position review round {state.position_round}: {state.position_reason} Exhaustive occupants confirmed {state.all_scene_actors_confirmed}; same-plane unobstructed confirmed {state.same_plane_unobstructed_confirmed}; independent per-target damage rolls confirmed {state.independent_damage_rolls_confirmed}; fractional blast meters round {state.distance_rounding}.")
            for id, saved in state.positions.items():
                lines.append(f"Actual blast position — {name(id)} [{id}]: {point(saved.point)}; exposure side {saved.side}; armor hit location {saved.hit_location or 'not recorded'}; resistance CP requested per blast {saved.resistance_character_points} (spent points appear only in actual results).")
        for grenade in state.grenades:
            lines.append(f"Saved grenade {grenade.id}: {grenade.name}; actual physical item {grenade.item_id}; catalog {grenade.catalog_id}; status {grenade.status}; position {point(grenade.position)}; holder {name(grenade.holder_id) if grenade.holder_id else 'none'}; created round {grenade.created_round}; trigger {grenade.trigger}; actual timer {grenade.timer_seconds if grenade.timer_seconds is not None else 'none'} seconds; original due end of round {grenade.due_round}; resolved round {grenade.resolved_round if grenade.resolved_round is not None else 'not resolved'}. {grenade.reason}")
            lines.append(f"Saved blast conventions: fractional distance round {grenade.distance_rounding}; independent per-target damage/free Strength; timer checkpoints ceil(seconds/5), under five seconds end of throwing round; rethrow never resets original fuse. Fuses due at the shared boundary resolve in saved throw order, one blast/immediate-reaction checkpoint before the next, with no extra elapsed round. Position ruling: {grenade.position_reason}. Source: {grenade.source}")
            for index, saved in enumerate(grenade.throws, 1):
                lines.append(f"Saved {'toss-away' if saved.rethrow else 'initial throw'} {index} — {saved.name}: round {saved.round}; actual origin {point(saved.origin)}; intended point {point(saved.target)}; actual distance {saved.distance:g}m; range {saved.range_band}; roll {saved.roll.total} vs {saved.difficulty}; success {saved.success}; actual landing {point(saved.landing)}; paid {saved.character_points} CP; FP active from round declaration {saved.force_point_active}. {saved.roll.breakdown} Reason: {saved.reason}")
                if saved.scatter_direction:
                    lines.append(f"Saved plain grenade scatter: direction {saved.scatter_direction.total} ({DIRECTIONS.get(saved.scatter_direction.total, 'unrecognized saved direction')}); {saved.scatter_direction.expression} total {saved.scatter_direction.total}; distance {saved.scatter_distance.expression if saved.scatter_distance else 'not recorded'} total {saved.scatter_distance.total if saved.scatter_distance else 'not recorded'} meters; no Wild Die added.")
                if saved.positions:
                    lines.append("Actual complete positions at this throw: " + "; ".join(f"{name(id)} [{id}] {point(position.point)}" for id, position in saved.positions.items()) + ".")
            for victim in grenade.victims:
                line = f"Saved blast result — {victim.name} [{victim.actor_id}]: actual position {point(victim.point)}; actual distance {victim.distance:g}m; GM blast distance {victim.blast_distance}m; affected {victim.affected}; source damage {victim.damage_code or 'outside blast'}; wound {victim.before} → {victim.after}; actual resistance CP spent {victim.character_points}; armor location {victim.hit_location or 'not recorded'}, side {victim.side}."
                if victim.damage_roll:
                    line += f" Actual damage roll {victim.damage_roll.expression} = {victim.damage_roll.total}: {victim.damage_roll.breakdown}."
                if victim.resistance_roll:
                    line += f" Actual free full-Strength resistance {victim.resistance_roll.expression} = {victim.resistance_roll.total}: {victim.resistance_roll.breakdown}; margin {victim.margin}; injury {victim.injury}."
                if victim.armor_damage:
                    line += f" Actual armor consequence: {victim.armor_damage}."
                if victim.point_note:
                    line += " " + victim.point_note
                lines.append(line)
        for intent in state.intents:
            lines.append(f"Saved pre-landing toss-away intent — {name(intent.actor_id)} [{intent.actor_id}]: declared round {intent.declared_round}; actual grenade {intent.grenade_id or 'not approached'}; current stage {intent.stage}; actual paid stages {len(intent.actions)}/3. {intent.reason}")
            for action in intent.actions:
                lines.append(f"Actual toss-away action: {action.get('operation')}; round {action.get('round')}; from {action.get('from', 'not a movement step')}; to {action.get('to', 'not a movement step')}; reason {action.get('reason', '')}.")
    if guidance:
        lines.append("Only native grenade actions and the actual combat round clock can move the saved grenade, spend its single physical charge or resolve its blast. Narration cannot invent positions or victims, grant a free escape/Dodge benefit, reset or freeze a fuse, compress move/grab/throw into one action, reroll saved scatter/damage, erase injury, or end combat/rest through a live timer. Resolve immediate injury reactions before finishing the saved round-end pause. Obstructed or unregistered blast geometry and mines/scaled weapons require separate actual GM procedures.")
    return "\n".join(lines)
