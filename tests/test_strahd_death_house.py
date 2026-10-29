"""Reloaded's finite dice clock records actual source events, never fake victories."""
import asyncio
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch
from zipfile import ZipFile

from fastapi.testclient import TestClient

from dungeonforge.api import routes
from dungeonforge.campaign.strahd import build_preset
from dungeonforge.campaign import strahd_death_house as rules
from dungeonforge.context.pipeline import ContextPipeline
from dungeonforge.game.combat import CombatEncounter
from dungeonforge.game.engine import GameEngine
from dungeonforge.game.models import GameSession
from dungeonforge.game.saves import SaveManager
from dungeonforge.llm.base import LLMResponse
from dungeonforge.main import app
from dungeonforge.rules.strahd_models import DeathHouseRequest


def make_session():
    preset = build_preset()
    return GameSession(id="session_strahd", edition="5e", source_folders=["strahd"],
        character=preset.starter_character, campaign_name=preset.title, active_quests=preset.active_quests)


def event_request(session, action="start", **changes):
    return DeathHouseRequest(**{**dict(event_id=f"qa_event_{len(session.strahd_progress.death_house.events)}",
        action=action, actual_event_confirmed=True, actor_ids=[session.character.id],
        reason="GM confirms the actual source event occurred in play.", expected_updated_at=session.updated_at), **changes})


class DeathHouseSourceTests(unittest.TestCase):
    def test_actual_local_source_supports_clock_and_detailed_sacrifice_rule(self):
        archive = Path(__file__).resolve().parents[2] / "curse of straud" / "Curse_of_Strahd_Reloaded_Part_1_of_3.zip"
        if not archive.exists():
            self.skipTest("The optional user-provided local Reloaded archive is not installed.")
        with ZipFile(archive) as source:
            text = source.read(rules.SOURCE.split("!/", 1)[1]).decode("utf-8-sig")
        for fact in ("Each pip on the dice represents twenty minutes", "three six-sided dice", "Each time the players enter a new floor",
                "Perception or Investigation check to search an entire room", "short rest, tick the dice clock down by three",
                "at least one minute", "impossible for the players to take a long rest", "Feeding the mound does not free the players"):
            self.assertIn(fact.lower(), text.lower())
        normalized = text.replace("’", "'")
        for _, rooms in rules.FLOORS.values():
            for room in rooms:
                self.assertIn("### " + room, normalized)

    def test_all_nineteen_dice_states_preserve_lowest_first_and_remove_zero(self):
        for pips in range(19):
            dice = rules.dice(pips)
            self.assertEqual(sum(dice), pips)
            self.assertTrue(all(1 <= value <= 6 for value in dice))
            self.assertEqual(dice, sorted(dice))
            self.assertLessEqual(len(dice), 3)
        self.assertEqual(rules.dice(17), [5, 6, 6])
        self.assertEqual(rules.dice(12), [6, 6])
        self.assertEqual(rules.dice(1), [1])
        self.assertEqual(rules.dice(0), [])
        self.assertEqual(rules.clock_label(18), "6:00 p.m.")
        self.assertEqual(rules.clock_label(15), "7:00 p.m.")
        self.assertEqual(rules.clock_label(0), "midnight")


class DeathHouseAPITests(unittest.TestCase):
    def setUp(self):
        self.session = make_session()
        active = patch.object(routes, "_ACTIVE_SESSION", self.session)
        active.start()
        self.addCleanup(active.stop)
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def request(self, action="start", **changes):
        return event_request(self.session, action, **changes).model_dump()

    def post(self, action="start", **changes):
        response = self.client.post("/api/strahd/progress/death-house/event", json=self.request(action, **changes))
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def rejected(self, payload):
        before = self.session.model_dump()
        response = self.client.post("/api/strahd/progress/death-house/event", json=payload)
        self.assertIn(response.status_code, {400, 409, 422}, response.text)
        self.assertEqual(self.session.model_dump(), before)
        return response

    def test_legacy_state_readonly_unstarted_unknown_no_floor_or_reward_inference(self):
        self.session.character.level = 8
        before = self.session.model_dump()
        response = self.client.get("/api/strahd/progress/death-house/state")
        self.assertEqual(response.status_code, 200)
        clock = response.json()["clock"]
        self.assertEqual(clock["status"], "unstarted")
        self.assertIsNone(clock["remaining_minutes"])
        self.assertEqual(clock["visited_floors"], [])
        self.assertIn("unknown", clock["clock_label"])
        self.assertEqual(self.session.model_dump(), before)

    def test_quote_readonly_begin_stale_and_start_never_resets(self):
        payload = self.request()
        before = self.session.model_dump()
        response = self.client.post("/api/strahd/progress/death-house/quote", json=payload)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["clock"]["dice"], [6, 6, 6])
        self.assertEqual(self.session.model_dump(), before)
        self.session.updated_at += 1
        self.rejected(payload)
        self.post()
        self.assertEqual(self.session.strahd_progress.death_house.visited_floors, ["first"])
        self.rejected(self.request())

    def test_duplicate_event_id_rejected_without_second_charge(self):
        self.post()
        payload = self.request("room_search", floor="first", room="Main Hall", skill="perception")
        response = self.client.post("/api/strahd/progress/death-house/event", json=payload)
        self.assertEqual(response.status_code, 200)
        payload["expected_updated_at"] = self.session.updated_at
        self.rejected(payload)
        self.assertEqual(self.session.strahd_progress.death_house.remaining_pips, 17)

    def test_actual_actors_confirmation_reason_and_relevant_fields_required_atomic(self):
        for changes in (dict(actual_event_confirmed=False), dict(reason="   "), dict(actor_ids=["invented_pc"]),
                dict(actor_ids=[self.session.character.id] * 2), dict(floor="first"), dict(skill="perception"),
                dict(room="Main Hall"), dict(early_trigger="mound_attacked")):
            self.rejected(self.request(**changes))
        self.assertEqual(self.session.strahd_progress.death_house.events, [])

    def test_first_entry_unique_floor_but_repeated_actual_room_checks_cost_each_time(self):
        self.post()
        self.post("new_floor", floor="second")
        self.rejected(self.request("new_floor", floor="second"))
        self.rejected(self.request("room_search", floor="third", room="Bathroom", skill="perception"))
        self.rejected(self.request("room_search", floor="second", room="Bathroom", skill="perception"))
        self.rejected(self.request("room_search", floor="second", room="Library", skill=None))
        self.post("room_search", floor="second", room="Library", skill="perception")
        self.post("room_search", floor="second", room="Library", skill="investigation")
        clock = self.session.strahd_progress.death_house
        self.assertEqual(clock.remaining_pips, 15)
        self.assertEqual(clock.events[-1].chimes, ["7:00 p.m."])
        self.assertEqual(clock.events[-1].actors[0].name, self.session.character.name)
        self.assertEqual([event.skill for event in clock.events[-2:]], ["perception", "investigation"])

    def test_completed_rest_three_pips_and_main_house_haunting_without_recovery(self):
        self.post()
        self.session.character.current_hp = 1
        self.session.character.spell_slots["1"].current = 0
        self.post("short_rest", floor="first")
        clock = self.session.strahd_progress.death_house
        self.assertEqual(clock.remaining_pips, 15)
        self.assertEqual(clock.events[-1].requested_pips, 3)
        self.assertEqual(clock.events[-1].chimes, ["7:00 p.m."])
        self.assertTrue(any("hauntings" in reminder for reminder in clock.events[-1].reminders))
        self.assertEqual(self.session.character.current_hp, 1)
        self.assertEqual(self.session.character.spell_slots["1"].current, 0)

    def test_midnight_single_saved_trigger_no_enemy_damage_or_xp_and_no_more_exploration(self):
        before_character = self.session.character.model_dump()
        self.post()
        for _ in range(6):
            self.post("short_rest", floor="first")
        clock = self.session.strahd_progress.death_house
        self.assertEqual((clock.status, clock.remaining_pips), ("hunting", 0))
        self.assertEqual(clock.events[-1].chimes, ["midnight"])
        self.assertIn("At least one minute", " ".join(clock.events[-1].reminders))
        self.assertEqual([chime for event in clock.events for chime in event.chimes], ["7:00 p.m.", "8:00 p.m.", "9:00 p.m.", "10:00 p.m.", "11:00 p.m.", "midnight"])
        self.assertIsNone(self.session.encounter)
        self.assertEqual(self.session.character.model_dump(), before_character)
        self.assertEqual(self.session.strahd_progress.awards, [])
        self.rejected(self.request("short_rest", floor="first"))
        self.rejected(self.request("escaped"))

    def test_rest_near_midnight_clamps_pips_and_records_interruption_without_recovery(self):
        self.post()
        for _ in range(5):
            self.post("short_rest", floor="first")
        self.post("room_search", floor="first", room="Main Hall", skill="investigation")
        self.assertEqual(self.session.strahd_progress.death_house.remaining_pips, 2)
        self.post("short_rest", floor="first")
        event = self.session.strahd_progress.death_house.events[-1]
        self.assertEqual((event.pips_before, event.pips_after, event.requested_pips), (2, 0, 3))
        self.assertIn("whether this attempted rest completes", " ".join(event.reminders))

    def test_early_awake_needs_actual_source_cause_then_destruction_and_actual_escape(self):
        self.post()
        self.rejected(self.request("awakens_early"))
        self.post("awakens_early", early_trigger="tendrils_damaged")
        self.assertEqual(self.session.strahd_progress.death_house.status, "awakened_early")
        self.assertEqual(self.session.strahd_progress.death_house.remaining_pips, 18)
        self.rejected(self.request("new_floor", floor="second"))
        self.rejected(self.request("escaped"))
        self.post("mound_destroyed")
        self.assertEqual(self.session.strahd_progress.death_house.status, "escaping")
        self.post("escaped")
        self.assertEqual(self.session.strahd_progress.death_house.status, "escaped")
        self.assertEqual(self.session.strahd_progress.awards, [])
        self.assertEqual(self.session.strahd_progress.arc_reviews, [])
        self.assertEqual(self.session.character.companions, [])
        self.rejected(self.request("mound_destroyed"))

    def test_no_sacrifice_terminal_or_unstarted_fake_victory(self):
        self.rejected(self.request("mound_destroyed"))
        self.rejected(self.request("escaped"))
        payload = self.request()
        payload["action"] = "appeased"
        self.rejected(payload)

    def test_save_load_retains_exact_actor_evidence_clock_and_pending_pursuit(self):
        self.post()
        self.post("awakens_early", early_trigger="mound_attacked", reason="Varis actually attacked the sleeping mound; GM reviewed surprise.")
        with tempfile.TemporaryDirectory() as directory:
            manager = SaveManager(directory)
            manager.save_session(self.session, "isolated_clock")
            loaded = manager.load_session("isolated_clock")
        self.assertEqual(loaded.strahd_progress, self.session.strahd_progress)
        self.assertEqual(loaded.strahd_progress.death_house.status, "awakened_early")
        self.assertIn("sleeping mound", loaded.strahd_progress.death_house.events[-1].reason)

    def test_wrong_campaign_and_active_combat_cannot_mutate(self):
        self.session.encounter = CombatEncounter(active=True)
        self.rejected(self.request())
        self.session.encounter = None
        self.session.source_folders = ["minecraft"]
        self.session.id = "session_minecraft"
        self.rejected(self.request())

    def test_rest_action_api_cannot_skip_source_time_or_restore_hp_while_trapped(self):
        self.post()
        self.session.character.current_hp = 1
        for text in ("I take a short rest", "I take a long rest"):
            before = self.session.model_dump()
            response = self.client.post("/api/action", json={"mode": "rest", "text": text})
            self.assertEqual(response.status_code, 400, response.text)
            self.assertIn("three pips", response.json()["detail"])
            self.assertEqual(self.session.model_dump(), before)

    def test_older_progress_ledger_missing_clock_loads_unstarted_without_inferring_escape(self):
        data = self.session.model_dump()
        data["strahd_progress"].pop("death_house")
        data["active_quests"] = {"Old player notes": ["Escaped Death House"]}
        restored = GameSession.model_validate(data)
        self.assertEqual(restored.active_quests, data["active_quests"])
        self.assertEqual(restored.strahd_progress.death_house.status, "unstarted")
        self.assertEqual(restored.strahd_progress.death_house.events, [])

    def test_post_escape_rest_reward_cannot_contradict_explicit_unresolved_house_clock(self):
        response = self.client.post("/api/strahd/progress/register", json={"actors": [{"actor_id": self.session.character.id,
            "baseline_xp": 300, "pc_confirmed": True, "reason": "GM reviews actual starting PC XP."}], "expected_updated_at": self.session.updated_at})
        self.assertEqual(response.status_code, 200, response.text)
        self.post()
        def review():
            return {"milestone_id": "a_escape_rest", "completion_confirmed": True,
                "reason": "GM confirms the first actual long rest after exit.", "expected_updated_at": self.session.updated_at,
                "reviews": [{"actor_id": self.session.character.id, "eligible": True, "reason": "Actual PC participated."}]}
        for status in ("exploring", "escaping"):
            self.assertEqual(self.session.strahd_progress.death_house.status, status)
            before = self.session.model_dump()
            response = self.client.post("/api/strahd/progress/award", json=review())
            self.assertEqual(response.status_code, 400, response.text)
            self.assertIn("still records the party inside", response.json()["detail"])
            self.assertEqual(self.session.model_dump(), before)
            if status == "exploring":
                self.post("mound_destroyed")
        self.post("escaped")
        self.assertEqual(self.session.strahd_progress.awards, [])
        response = self.client.post("/api/strahd/progress/award", json=review())
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.session.strahd_progress.accounts[0].awarded_xp, 400)
        self.assertEqual(self.session.character.level, 2)


class DeathHouseIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.session = make_session()

    def test_generic_rest_guard_atomic_inside_and_released_only_by_actual_exit(self):
        rules.apply(self.session, event_request(self.session))
        self.session.character.current_hp = 1
        llm = SimpleNamespace(generate=AsyncMock(return_value=LLMResponse(text="Rest completed outside the house.")))
        engine = GameEngine(llm)
        for text in ("I take a long rest", "I take a short rest"):
            before = self.session.model_dump()
            with self.assertRaisesRegex(ValueError, "Death House is unresolved"):
                asyncio.run(engine.execute_turn(self.session, "rest", text))
            self.assertEqual(self.session.model_dump(), before)
        llm.generate.assert_not_awaited()
        rules.apply(self.session, event_request(self.session, "mound_destroyed"))
        with self.assertRaises(ValueError):
            rules.require_rest_allowed(self.session)
        rules.apply(self.session, event_request(self.session, "escaped"))
        with patch("dungeonforge.library.get_library", return_value=SimpleNamespace(search=lambda *args, **kwargs: [])):
            asyncio.run(engine.execute_turn(self.session, "rest", "I take a long rest"))
        self.assertEqual(self.session.character.current_hp, self.session.character.max_hp)
        self.assertEqual(self.session.strahd_progress.awards, [])

    def test_legacy_and_other_campaign_rest_untouched(self):
        rules.require_rest_allowed(self.session)
        rules.apply(self.session, event_request(self.session))
        self.session.id, self.session.source_folders = "session_minecraft", ["minecraft"]
        rules.require_rest_allowed(self.session)
        self.session.id, self.session.source_folders, self.session.edition = "session_strahd", ["strahd"], "weg_d6"
        rules.require_rest_allowed(self.session)

    def test_context_and_chronicle_carry_saved_facts_and_source_without_invented_outcomes(self):
        rules.apply(self.session, event_request(self.session))
        rules.apply(self.session, event_request(self.session, "new_floor", floor="second", reason="Actual staircase climbed; library not yet searched."))
        before = self.session.model_dump()
        summary = ContextPipeline.strahd_progress_summary(self.session)
        for fact in ("Death House reviewed state: exploring", "dice [5, 6, 6]", "6:20", "Actual staircase climbed", "library not yet searched", "room n/a", "source: curse of straud", "Do not infer"):
            self.assertIn(fact, summary)
        self.assertNotIn("Death House reviewed state: escaped", summary)
        self.assertEqual(self.session.model_dump(), before)
        with tempfile.TemporaryDirectory() as directory:
            chronicle = SaveManager(directory).export_markdown_chronicle(self.session)
        self.assertIn("Actual staircase climbed", chronicle)
        self.assertIn("pips 18 → 17", chronicle)
        self.assertIn("Arc A - Escape From Death House.md", chronicle)
        self.assertNotIn("Use the saved GM clock as authority", chronicle)


if __name__ == "__main__":
    unittest.main()
