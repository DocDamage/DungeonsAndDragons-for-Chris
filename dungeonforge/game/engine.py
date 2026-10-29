import time
import uuid
import re
from typing import Optional, Dict, Any

from dungeonforge.game.models import GameSession
from dungeonforge.rules import get_rule_engine, Item, RuleEvaluationResult
from dungeonforge.rules.dice import DiceRoller, RollResult
from dungeonforge.context.story_cards import StoryCardManager
from dungeonforge.context.pipeline import ContextPipeline, ActionTurn
from dungeonforge.llm.base import BaseLLMClient
from dungeonforge.llm.mock import MockLLMClient
from dungeonforge.llm.api import APIClient
from dungeonforge.rules.weg_d6 import WEGD6Rules
from dungeonforge.rules.weg_models import D6RoundState


class GameEngine:
    """Core Game Engine orchestrating rules, context assembly, and LLM turns."""

    def __init__(self, llm_client: Optional[BaseLLMClient] = None):
        self.llm = llm_client or MockLLMClient()

    async def execute_turn(
        self,
        session: GameSession,
        mode: str,  # "do", "say", "story", "attack", "check", "rest"
        input_text: str,
        target_ac: Optional[int] = None,
        target_dc: Optional[int] = None,
        weapon_name: Optional[str] = None,
        ability_or_skill: Optional[str] = None,
        advantage: bool = False,
        disadvantage: bool = False
    ) -> ActionTurn:
        rule_engine = get_rule_engine(session.edition)
        native = session.edition == "weg_d6"
        in_combat = bool(session.encounter and session.encounter.active)
        if native:
            if mode not in {"say", "story", "see"}:
                from dungeonforge.game.weg_navigation import require_resolved
                require_resolved(session)
                from dungeonforge.game.weg_task_guards import require_available
                require_available(session, session.character.id)
            WEGD6Rules.require(session.character)
            from dungeonforge.game.weg_dark_side import synchronize as sync_dark_side
            sync_dark_side(session)
            if session.character.d6.corruption.control_mode == "gm" and session.character.d6.corruption.fallen_adventure is not None and mode not in {"story", "see"}:
                raise ValueError("This character is under GM control. Use Story for GM narration and the native mechanical panels for GM resolution, or authorize a redemption arc in Dark Side controls.")
            session.native_boost = None
            if session.vehicle_encounter:
                session.vehicle_encounter.boost = None
            if in_combat:
                from dungeonforge.game import weg_combat
                weg_combat.bind_party(session.encounter, session.character)
        rule_result: Optional[RuleEvaluationResult] = None

        # 1. Check if the action triggers an attack or check
        clean_input = input_text.strip()
        lower_input = clean_input.lower()

        is_attack = mode == "attack" or any(w in lower_input for w in ["attack", "strike", "shoot", "slash", "stab", "thrust"])
        is_check = mode == "check" or any(w in lower_input for w in ["check", "inspect", "search", "investigate", "sneak", "listen"])
        is_rest = mode == "rest" or "short rest" in lower_input or "long rest" in lower_input

        # Resolve weapon if attacking
        weapon = None
        if weapon_name:
            weapon = next((i for i in session.character.inventory if i.name.lower() == weapon_name.lower()), None)
        if not weapon and session.character.inventory:
            weapon = next((i for i in session.character.inventory if i.item_type == "weapon" and i.equipped and (not native or i.equipped_by in {None, session.character.id})), None)
        if native and weapon and (not weapon.equipped or weapon.equipped_by not in {None, session.character.id}):
            raise ValueError("Use the player's actual equipped weapon; assign or draw another weapon through its native controls.")

        mechanical = mode not in {"say", "story", "see"}
        if native and session.vehicle_encounter and mechanical and (is_attack or is_check or is_rest):
            raise ValueError("Use the vehicle encounter crew controls for mechanical actions, or Story/Say for narration.")
        if native and mechanical and not in_combat:
            if session.character.d6.force.attempt and (is_attack or is_check or is_rest):
                raise ValueError("Finish or cancel the current Force activation before another mechanical scene action.")
            round_state = session.character.d6.round_state
            dark_actions = round_state.dark_side_called and round_state.actions_taken < round_state.declared_actions
            if not dark_actions and (round_state.actions_taken or round_state.force_active or round_state.dark_side_called):
                WEGD6Rules.next_round(session.character.d6)
        if native:
            from dungeonforge.rules.weg_gear_effects import refresh as refresh_gear
            refresh_gear(session)
        if is_attack and mechanical:
            if native and in_combat:
                raise ValueError("Use the encounter's Attack Target controls to resolve native target resistance and wounds.")
            ac = target_ac if target_ac is not None else (10 if native else 14 if session.edition != "2e" else 5)
            rule_result = rule_engine.evaluate_attack(
                character=session.character,
                target_ac=ac,
                weapon=weapon,
                advantage=advantage,
                disadvantage=disadvantage
            )
        elif is_check and mechanical:
            dc = target_dc if target_dc is not None else (10 if native else 12)
            stat = ability_or_skill or ("dex" if "sneak" in lower_input else "wis")
            if native:
                stat = ability_or_skill or next((skill for skill in ("astrogation", "first_aid", "sneak", "search", "technical", "mechanical", "perception") if skill.replace('_', ' ') in lower_input), "perception")
                if in_combat:
                    weg_combat.validate_turn(session.encounter, weg_combat.actor(session.encounter, session.character.id))
            rule_result = rule_engine.evaluate_ability_check(
                character=session.character,
                ability=stat,
                dc_or_target=dc,
                skill_name=ability_or_skill
            )
            if native and in_combat:
                session.encounter.d6_actions_started = session.encounter.d6_turn_acted = True
        elif is_rest and mechanical:
            if native:
                from dungeonforge.rules.weg_medical import active_project
                if active_project(session, session.character.id):
                    raise ValueError("Complete or cancel the saved medical care before taking a separate rest action.")
            if not native:
                from dungeonforge.campaign.strahd_death_house import require_rest_allowed
                require_rest_allowed(session)
            if native and in_combat:
                raise ValueError("End combat before resting. Native D6 does not restore wounds through a combat rest action.")
            if "long" in lower_input:
                session.character = rule_engine.apply_long_rest(session.character)
                summary = f"Completed Long Rest. HP restored to {session.character.current_hp}/{session.character.max_hp}."
            else:
                session.character = rule_engine.apply_short_rest(session.character)
                summary = f"Completed Short Rest. HP now {session.character.current_hp}/{session.character.max_hp}."
            if native:
                from dungeonforge.game.weg_force import advance_scene
                advance_scene(session, (480 if "long" in lower_input else 1) * 12, excluded_ids={session.character.id})
                summary = f"[WEG D6 Rest] Rested {'8 hours' if 'long' in lower_input else '1 minute'}. Stun penalties cleared; wound remains {session.character.d6.wound.replace('_', ' ')}. Force and Character Points are unchanged. Natural wound healing requires 3, 14, or 30 days."
            rule_result = RuleEvaluationResult(
                action_type="rest",
                success=not native or session.character.d6.wound != "dead",
                roll_result=RollResult(expression="Rest", dice_count=0, die_type=6, system="weg_d6", breakdown="No dice required") if native else DiceRoller.roll("1d1"),
                summary=summary
            )
        if native and rule_result:
            from dungeonforge.game.weg_force import after_roll
            after_roll(session, rule_result)

        # 2. Assemble context prompt
        card_manager = StoryCardManager(session.story_cards)
        from dungeonforge.library import get_library
        source_passages = get_library().search(
            clean_input, edition=session.edition,
            campaign_folders=session.source_folders, limit=4,
        )
        messages = ContextPipeline.assemble(
            character=session.character,
            memory=session.memory,
            story_card_manager=card_manager,
            authors_note=session.authors_note,
            history=session.history,
            current_input=clean_input,
            current_mode=mode,
            rule_result=rule_result,
            source_passages=source_passages,
            rules_note=session.rules_note,
            campaign_name=session.campaign_name,
            vehicle_summary=self.vehicle_summary(session) if native else "",
            campaign_progress_summary=ContextPipeline.strahd_progress_summary(session),
        )

        # 3. Call LLM
        response = await self.llm.generate(messages)

        # 4. Apply any structured state updates from LLM
        if response.state_updates:
            self._apply_state_updates(session.character, response.state_updates)

        # 5. Auto-Card generation: check if new NPCs or artifacts were introduced
        from dungeonforge.context.auto_card import AutoCardGenerator
        auto_cards = AutoCardGenerator.extract_new_cards(response.text, session.story_cards)
        if auto_cards:
            session.story_cards.extend(auto_cards)

        # 6. Create and save the turn
        image_url = None
        if mode == "see" or lower_input.startswith("/see"):
            from dungeonforge.image.illustrator import SceneIllustrator
            image_url = SceneIllustrator.generate_image_url(
                prompt=clean_input.replace("/see", "").strip(),
                context_text=response.text
            )

        turn = ActionTurn(
            id=str(uuid.uuid4())[:8],
            mode=mode,
            player_input=clean_input,
            rule_result=rule_result,
            dm_output=response.text,
            image_url=image_url,
            timestamp=time.time(),
            source_references=[
                {key: passage[key] for key in ("source_id", "title", "section", "file_url")}
                for passage in source_passages
            ],
        )

        session.history.append(turn)
        session.undone_history.clear()
        session.updated_at = time.time()

        return turn

    @staticmethod
    def vehicle_summary(session):
        return ContextPipeline.native_travel_summary(session)

    def alter_turn(self, session: GameSession, turn_id: str, new_dm_text: str) -> Optional[ActionTurn]:
        for turn in session.history:
            if turn.id == turn_id:
                turn.dm_output = new_dm_text.strip()
                session.updated_at = time.time()
                return turn
        return None

    def undo_turn(self, session: GameSession) -> Optional[ActionTurn]:
        if session.history:
            last = session.history.pop()
            session.undone_history.append(last)
            session.updated_at = time.time()
            return last
        return None

    def redo_turn(self, session: GameSession) -> Optional[ActionTurn]:
        if session.undone_history:
            redo = session.undone_history.pop()
            session.history.append(redo)
            session.updated_at = time.time()
            return redo
        return None

    def _apply_state_updates(self, character, updates: Dict[str, Any]):
        if "hp_change" in updates and character.edition != "weg_d6":
            character.current_hp = max(0, min(character.max_hp, character.current_hp + int(updates["hp_change"])))
        if "add_items" in updates and isinstance(updates["add_items"], list):
            for it in updates["add_items"]:
                if isinstance(it, str):
                    character.inventory.append(Item(name=it))
                elif isinstance(it, dict) and "name" in it:
                    character.inventory.append(Item(**it))
        if "add_condition" in updates:
            cond = str(updates["add_condition"])
            if cond not in character.conditions:
                character.conditions.append(cond)
        if "remove_condition" in updates:
            cond = str(updates["remove_condition"])
            if cond in character.conditions:
                character.conditions.remove(cond)
        if "gold_change" in updates and character.edition != "weg_d6":
            character.gold = max(0, character.gold + int(updates["gold_change"]))
        if "credits_change" in updates and character.edition == "weg_d6" and character.d6:
            character.d6.credits = max(0, character.d6.credits + int(updates["credits_change"]))
