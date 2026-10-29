import os
import json
import time
from typing import List, Dict, Any, Optional
from dungeonforge.game.models import GameSession


class SaveManager:
    """Manages multi-slot adventure persistence and markdown chronicle export."""

    def __init__(self, saves_dir: Optional[str] = None):
        if not saves_dir:
            saves_dir = os.path.join(os.path.dirname(__file__), "..", "..", "saves")
        self.saves_dir = os.path.abspath(saves_dir)
        os.makedirs(self.saves_dir, exist_ok=True)

    def list_saves(self) -> List[Dict[str, Any]]:
        saves = []
        if not os.path.exists(self.saves_dir):
            return saves

        for fname in os.listdir(self.saves_dir):
            if fname.endswith(".json"):
                slot_id = fname[:-5]
                filepath = os.path.join(self.saves_dir, fname)
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    saves.append({
                        "slot_id": slot_id,
                        "title": data.get("title", slot_id),
                        "campaign_name": data.get("campaign_name", "Custom"),
                        "edition": data.get("edition", "5e"),
                        "character_name": data.get("character", {}).get("name", "Unknown"),
                        "turns_count": len(data.get("history", [])),
                        "saved_at": data.get("updated_at", os.path.getmtime(filepath))
                    })
                except Exception:
                    continue

        saves.sort(key=lambda s: s["saved_at"], reverse=True)
        return saves

    def save_session(self, session: GameSession, slot_name: Optional[str] = None) -> str:
        slot_id = slot_name or f"{session.id}_{int(time.time())}"
        slot_id = "".join(c if c.isalnum() or c in "-_" else "_" for c in slot_id)
        filepath = os.path.join(self.saves_dir, f"{slot_id}.json")

        session.updated_at = time.time()
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(session.model_dump(), f, indent=2)

        return slot_id

    def load_session(self, slot_id: str) -> Optional[GameSession]:
        filepath = os.path.join(self.saves_dir, f"{slot_id}.json")
        if not os.path.exists(filepath):
            return None

        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)

        def migrate_rewards(value):
            if isinstance(value, dict):
                if "attributes" in value and "force_skills" in value and "force_points" in value:
                    value.setdefault("rewards", {"baseline_known": False})
                for nested in value.values():
                    migrate_rewards(nested)
            elif isinstance(value, list):
                for nested in value:
                    migrate_rewards(nested)

        migrate_rewards(data)
        # Known stock craft in pre-navigation saves gain only missing source metadata.
        from dungeonforge.game.weg_vehicle_presets import vehicle_presets
        stock = {craft.name: craft for craft in vehicle_presets().values()}
        craft_records = [*data.get("vehicles", []), *(data.get("vehicle_encounter") or {}).get("craft", [])]
        for record in craft_records:
            preset = stock.get(record.get("name"))
            if preset:
                for field in ("hyperdrive_multiplier", "backup_hyperdrive", "nav_computer", "purchase_value"):
                    record.setdefault(field, getattr(preset, field))

        if "source_folders" not in data:
            from dungeonforge.campaign.campaign_manager import CampaignManager
            try:
                preset = CampaignManager.load_campaign(data.get("id", "").removeprefix("session_"))
                data.update(source_folders=[preset.source_folder], source_rule_system=preset.source_rule_system, rules_note=preset.rules_note)
            except ValueError:
                data["source_folders"] = []

        if data.get("id") == "session_star_wars_2e" and data.get("edition") == "2e" and not data.get("character", {}).get("d6"):
            data["source_rule_system"] = "AD&D 2e (legacy Star Wars adaptation)"
            data["rules_note"] = "This saved character uses the legacy AD&D adaptation. Start the Star Wars D6 campaign for a native WEG character; existing saves are not silently converted."

        return GameSession(**data)

    def delete_save(self, slot_id: str) -> bool:
        filepath = os.path.join(self.saves_dir, f"{slot_id}.json")
        if os.path.exists(filepath):
            os.remove(filepath)
            return True
        return False

    def export_markdown_chronicle(self, session: GameSession) -> str:
        lines = []
        lines.append(f"# 📖 {session.campaign_name}: {session.title}")
        if session.edition == "weg_d6" and session.character.d6:
            state = session.character.d6
            lines.append(f"**Rules:** WEG Star Wars D6 (1992) | **Hero:** {session.character.name} ({session.character.race}, {session.character.class_name})")
            lines.append(f"**Wound:** {state.wound.replace('_', ' ')} | **Character Points:** {state.character_points} | **Force Points:** {state.force_points} | **Credits:** {state.credits}")
            lines.append("**Attributes:** " + ", ".join(f"{name.title()} {code}" for name, code in state.attributes.items()))
            lines.append(f"**Advancement window:** {session.d6_advancement.adventure} — {session.d6_advancement.label}")
            for record in session.d6_advancement.rewards:
                lines.append(f"**Adventure rewards {record.adventure} — {record.label}:**")
                for award in record.actors:
                    lines.append(f"- {award['actor_id']}: {award['force_returned']} FP returned, {award['zero_point_award']} zero-start FP, {award['character_points_awarded']} adventure CP, {award['conversion_cp']} excess-conversion CP. {award['reason']}")
                    for use in award['reviews']:
                        lines.append(f"  - {use['source']}: {use['ruling']} → {use['returned']} FP. {use['reason']}")
            from dungeonforge.rules.weg_force_catalog import POWERS
            for person in [session.character, *session.character.companions]:
                if not person.d6:
                    continue
                native = person.d6
                lines.append(f"**Origin — {person.name}:** {native.origin.method}; species {native.species_id or person.race}; {native.origin.attribute_budget}D attributes / {native.origin.skill_budget}D skills. {native.origin.gm_approval}")
                lines.append(f"**Species conditions — {person.name}:** {native.species_context.model_dump()}")
                if native.origin.custom_species:
                    from dungeonforge.rules.weg_custom_species import summary as species_summary
                    lines.append(f"**GM-defined species — {person.name}:** {species_summary(native.origin.custom_species)}")
                if native.droid:
                    lines.append(f"**Droid — {person.name}:** {native.droid.model}; owner {native.droid.owner}; memory wipes {native.droid.memory_wipes}; hardwired {native.droid.hardwired_skills}; equipment {'; '.join(native.droid.equipment)}")
                    for work in native.droid.work_history:
                        lines.append(f"- Droid work: {work['operation']}, {'completed' if work['success'] else 'failed'}, {work['minutes']} minutes, {work['cp_spent']} CP, {work['credits']} credits. {work['reason']}")
                lines.append(f"**Corruption — {person.name}:** {native.dark_side_points} DSP; consumed {native.force.dark_side_consumed}; control {native.corruption.control_mode}; permanent NPC {native.corruption.npc_permanent}; redemption deadline {native.corruption.redemption_deadline}")
                if native.corruption.atonement:
                    cycle = native.corruption.atonement
                    lines.append(f"**Atonement:** {cycle.consecutive}/2 approved adventures; next review {cycle.next_review}; intention {cycle.intention}")
                if native.corruption.pending_demand:
                    lines.append(f"**Unpaid Dark Side demand:** lose {native.corruption.pending_demand.cp_loss} CP or 1D from an attribute/Force skill")
                for event in native.corruption.events:
                    lines.append(f"**Corruption event:** adventure {event.adventure}; {event.source}; DSP {event.before} → {event.after}; plain die {event.fall_die}; fell {event.fell}; {event.reason}")
                lines.append(f"**Move — {person.name}:** {native.move} meters")
                if native.advancement.project:
                    project = native.advancement.project
                    lines.append(f"**Training — {person.name}:** {project.quote.key} {project.quote.old_code} → {project.quote.new_code}; {project.quote.cp_cost} CP paid; {project.days_completed}/{project.quote.days} intensive days; instructor {project.quote.teacher_name or 'self-study'}")
                for course in native.advancement.history:
                    lines.append(f"**Training record — {person.name}:** {course.quote.key}; {course.status}; {course.quote.cp_cost} CP; {course.days_completed}/{course.quote.days} days")
                if native.advancement.power_grants:
                    lines.append("**Included power choices:** " + "; ".join(f"{grant.skill}: {grant.remaining} remaining, instructor {grant.teacher_id}" for grant in native.advancement.power_grants if grant.remaining))
                lines.append(f"**Force — {person.name}:** " + ", ".join(f"{skill.title()} {code}" for skill, code in native.force_skills.items()) + "; learned: " + (", ".join(POWERS[id].name if id in POWERS else id for id in native.force.known_powers) or "none"))
                if native.force.effects:
                    lines.append("**Ongoing Force effects:** " + "; ".join(f"{effect.power_id} (target {effect.target_id}, {'recipient' if effect.recipient else 'caster'}, ready in {effect.ready_in_rounds}, remaining rounds {effect.rounds_remaining})" for effect in native.force.effects))
                if native.force.attempt:
                    attempt = native.force.attempt
                    lines.append(f"**Force activation:** {attempt.power_id}; preparation remaining {attempt.preparation_remaining}; skills resolved {len(attempt.rolls)}/{len(attempt.skills)}; failed {attempt.failed}")
                if native.force.permanent_injuries:
                    lines.append("**Permanent injuries:** " + "; ".join(native.force.permanent_injuries))
                if native.force.heroic_force_returns:
                    lines.append(f"**Heroic Force Points owed at adventure end:** {native.force.heroic_force_returns}")
                unreviewed = [item for item in native.rewards.expenditures if item.ruling is None and not item.forfeited]
                if unreviewed:
                    lines.append(f"**Pending Force Point reviews — {person.name}:** " + "; ".join(f"{item.source} (adventure {item.adventure or session.d6_advancement.adventure})" for item in unreviewed))
            from dungeonforge.context.pipeline import ContextPipeline
            native_scene = ContextPipeline.native_travel_summary(session, guidance=False)
            if native_scene:
                lines.append(native_scene)
        else:
            lines.append(f"**Edition:** {session.edition.upper()} | **Hero:** {session.character.name} (Lvl {session.character.level} {session.character.race} {session.character.class_name})")
            from dungeonforge.context.pipeline import ContextPipeline
            strahd_progress = ContextPipeline.strahd_progress_summary(session, guidance=False)
            if strahd_progress:
                lines.append(strahd_progress)
        lines.append(f"**Chronicle Date:** {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(session.updated_at))}\n")
        lines.append("---\n")

        for idx, turn in enumerate(session.history, 1):
            lines.append(f"### Chapter {idx}")
            if turn.mode == "do":
                lines.append(f"> **You** {turn.player_input}\n")
            elif turn.mode == "say":
                lines.append(f'> **You say,** "{turn.player_input}"\n')
            elif turn.mode == "attack":
                lines.append(f"> ⚔️ **Attack:** {turn.player_input}\n")
            elif turn.mode == "check":
                lines.append(f"> 🎲 **Check:** {turn.player_input}\n")
            else:
                lines.append(f"> {turn.player_input}\n")

            if turn.rule_result:
                lines.append(f"*[{turn.rule_result.summary}]*\n")

            if not turn.rule_result or turn.dm_output != turn.rule_result.summary:
                lines.append(f"{turn.dm_output}\n")
            lines.append("---\n")

        return "\n".join(lines)
