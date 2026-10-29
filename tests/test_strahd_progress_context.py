"""Narration and export retain reviewed XP without inventing progress or levels."""
import asyncio
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from dungeonforge.campaign import strahd_progress as rules
from dungeonforge.campaign.strahd import build_preset
from dungeonforge.context.pipeline import ContextPipeline
from dungeonforge.context.story_cards import StoryCardManager
from dungeonforge.game.engine import GameEngine
from dungeonforge.game.models import GameSession
from dungeonforge.game.saves import SaveManager
from dungeonforge.llm.base import LLMResponse
from dungeonforge.rules.strahd_models import StrahdArcRequest, StrahdMilestoneRequest, StrahdRegisterRequest


class StrahdProgressContextTests(unittest.TestCase):
    def setUp(self):
        preset = build_preset()
        self.session = GameSession(id="session_strahd", edition="5e", character=preset.starter_character,
            source_folders=["strahd"], campaign_name=preset.title, active_quests=preset.active_quests)
        self.session.memory.front_memory = preset.initial_memory

    def reviewed_progress(self):
        id = self.session.character.id
        rules.register(self.session, StrahdRegisterRequest(actors=[dict(actor_id=id, baseline_xp=300,
            reason="GM reviewed the actual level-two starting XP.", pc_confirmed=True)]))
        for milestone, reason in [("a_secret_stairs", "The party actually descended through the secret stairs."),
                ("a_escape_rest", "The survivors escaped and began their first long rest.")]:
            rules.award(self.session, StrahdMilestoneRequest(milestone_id=milestone, completion_confirmed=True,
                reason=reason, reviews=[dict(actor_id=id, eligible=True, reason="This actual PC participated.")]))
        rules.review_arc(self.session, StrahdArcRequest(arc="A", status="completed", reason="GM confirms the escape arc's actual completion."))

    def test_context_has_actual_xp_source_reason_and_pending_sheet_review_readonly(self):
        self.reviewed_progress()
        before = self.session.model_dump()
        summary = ContextPipeline.strahd_progress_summary(self.session)
        for fact in ("baseline 300; awarded 600; total 900 XP", "XP level 3; sheet level 2",
                "level-up sheet review pending True", "source 200 XP per eligible PC", "source 400 XP per eligible PC",
                "already awarded once", "first long rest", "actual PC participated", "A: completed", "Arc A - Escape From Death House.md"):
            self.assertIn(fact, summary)
        self.assertIn("Never fabricate a milestone award", summary)
        self.assertIn("class choices, HP, spell slots", summary)
        self.assertEqual(self.session.model_dump(), before)

    def test_legacy_empty_progress_never_infers_rewards_from_levels_or_quest_titles(self):
        self.session.character.level = 8
        summary = ContextPipeline.strahd_progress_summary(self.session)
        self.assertIn("Baseline XP and past milestone completions are unknown", summary)
        self.assertIn("No source milestone awards", summary)
        self.assertIn("quest outline is not a completion ledger", summary)
        self.assertNotIn("awarded 200 XP", summary)

    def test_context_and_chronicle_do_not_leak_into_other_campaigns_or_native_weG(self):
        for edition, source, id in (("5e", "minecraft", "session_minecraft"), ("weg_d6", "strahd", "session_strahd")):
            self.session.edition, self.session.source_folders, self.session.id = edition, [source], id
            self.assertEqual(ContextPipeline.strahd_progress_summary(self.session), "")

    def test_assemble_accepts_campaign_progress_separately_from_craft_context(self):
        self.reviewed_progress()
        summary = ContextPipeline.strahd_progress_summary(self.session)
        messages = ContextPipeline.assemble(character=self.session.character, memory=self.session.memory,
            story_card_manager=StoryCardManager(), authors_note=self.session.authors_note,
            history=[], current_input="Review our current situation", current_mode="story",
            campaign_progress_summary=summary)
        self.assertIn("total 900 XP", messages[1]["content"])
        self.assertIn("level-up sheet review pending True", messages[1]["content"])

    def test_real_story_engine_supplies_current_ledger_even_outside_recent_history(self):
        self.reviewed_progress()
        llm = SimpleNamespace(generate=AsyncMock(return_value=LLMResponse(text="Your recorded achievements remain part of the journey.")))
        library = SimpleNamespace(search=lambda *args, **kwargs: [])
        with patch("dungeonforge.library.get_library", return_value=library):
            asyncio.run(GameEngine(llm).execute_turn(self.session, "story", "Describe where we stand."))
        prompt = "\n".join(message["content"] for message in llm.generate.call_args.args[0])
        self.assertIn("total 900 XP", prompt)
        self.assertIn("level-up sheet review pending True", prompt)
        self.assertEqual(self.session.character.level, 2)
        self.assertEqual(len(self.session.strahd_progress.awards), 2)

    def test_chronicle_exports_baselines_allocations_sources_and_arc_reviews_without_instructions(self):
        self.reviewed_progress()
        before = self.session.model_dump()
        with tempfile.TemporaryDirectory() as directory:
            text = SaveManager(directory).export_markdown_chronicle(self.session)
        self.assertIn("total 900 XP", text)
        self.assertIn("XP level 3; sheet level 2", text)
        self.assertIn("source 200 XP per eligible PC", text)
        self.assertIn("awarded 400 XP; recorded total 900", text)
        self.assertIn("GM completion review: The survivors escaped", text)
        self.assertIn("Curse_of_Strahd_Reloaded_Part_1_of_3.zip", text)
        self.assertIn("No XP awarded by this status review", text)
        self.assertNotIn("Never fabricate", text)
        self.assertEqual(self.session.model_dump(), before)

    def test_save_load_preserves_pending_level_guidance_and_export(self):
        self.reviewed_progress()
        with tempfile.TemporaryDirectory() as directory:
            manager = SaveManager(directory)
            loaded = manager.load_session(manager.save_session(self.session, "reviewed"))
            self.assertEqual(loaded.strahd_progress, self.session.strahd_progress)
            self.assertEqual(ContextPipeline.strahd_progress_summary(loaded), ContextPipeline.strahd_progress_summary(self.session))
            self.assertIn("level-up sheet review pending True", manager.export_markdown_chronicle(loaded))


if __name__ == "__main__":
    unittest.main()
