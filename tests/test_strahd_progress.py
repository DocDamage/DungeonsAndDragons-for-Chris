"""Source XP is reviewed per actual PC, once, with no invented campaign progress."""
import json
from pathlib import Path
import re
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from fastapi.testclient import TestClient

from dungeonforge.api import routes
from dungeonforge.campaign.strahd import ARCHIVE, build_preset
from dungeonforge.campaign import strahd_progress as rules
from dungeonforge.game.models import GameSession
from dungeonforge.game.saves import SaveManager
from dungeonforge.main import app
from dungeonforge.rules.base import Companion
from dungeonforge.rules.strahd_models import StrahdMilestoneRequest, StrahdRegisterRequest


def make_session():
    preset = build_preset()
    preset.starter_character.companions = [Companion(id="second_pc", name="Second actual PC", level=2),
        Companion(id="npc_ireena", name="Ireena, an NPC ally", level=2)]
    return GameSession(id="session_strahd", edition="5e", character=preset.starter_character,
        source_folders=["strahd"], active_quests=preset.active_quests)


class StrahdProgressRuleTests(unittest.TestCase):
    def test_catalog_is_source_story_milestones_with_one_izek_event_and_no_monster_xp(self):
        self.assertEqual(len(rules.CATALOG), 38)
        self.assertEqual(len(rules.BY_ID), 38)
        self.assertEqual(rules.BY_ID["fg_izek"].arcs, ["F", "G"])
        self.assertEqual(rules.BY_ID["fg_izek"].variants, {"rescue_without_defeat": 750, "izek_defeated": 1500})
        self.assertFalse(any(item.id.startswith("n_") for item in rules.CATALOG))
        self.assertEqual(rules.BY_ID["u_sunrise"].xp_per_pc, 25000)

    def test_actual_scene_triggers_override_summary_shorthand(self):
        self.assertIn("first long rest", rules.BY_ID["a_escape_rest"].trigger)
        self.assertIn("first long rest", rules.BY_ID["c_vallaki_rest"].trigger)
        self.assertIn("departs the crossroads", rules.BY_ID["c_tarokka"].trigger)
        self.assertIn("returns the stolen gem", rules.BY_ID["j_gem"].trigger)
        self.assertIn("sun rises", rules.BY_ID["u_sunrise"].trigger)
        self.assertEqual(rules.BY_ID["h_tome"].xp_per_pc, 750)
        self.assertIn("blank", rules.BY_ID["h_tome"].notes[0])

    def test_2014_xp_thresholds_and_boundaries(self):
        for level, threshold in enumerate(rules.XP_THRESHOLDS, start=1):
            self.assertEqual(rules.xp_level(threshold), level)
            if threshold:
                self.assertEqual(rules.xp_level(threshold - 1), level - 1)
        self.assertEqual(rules.xp_level(1000000000), 20)
        self.assertEqual((rules.XP_THRESHOLDS[2], rules.XP_THRESHOLDS[3]), (900, 2700))

    def test_registration_does_not_infer_legacy_progress_or_xp(self):
        state = make_session()
        self.assertEqual(state.strahd_progress.accounts, [])
        self.assertEqual(state.strahd_progress.awards, [])
        self.assertEqual(state.strahd_progress.arc_reviews, [])
        req = StrahdRegisterRequest(actors=[dict(actor_id=state.character.id, baseline_xp=300,
            reason="Reviewed the actual starting level-two PC XP.", pc_confirmed=True)])
        rules.register(state, req)
        self.assertEqual(state.strahd_progress.accounts[0].baseline_xp, 300)
        self.assertEqual(state.strahd_progress.awards, [])


class StrahdProgressAPITests(unittest.TestCase):
    def setUp(self):
        self.session = make_session()
        active = patch.object(routes, "_ACTIVE_SESSION", self.session)
        active.start()
        self.addCleanup(active.stop)
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def register(self, ids=None, xp=300):
        ids = ids or [self.session.character.id, "second_pc"]
        response = self.client.post("/api/strahd/progress/register", json=dict(expected_updated_at=self.session.updated_at,
            actors=[dict(actor_id=id, baseline_xp=xp, reason="GM reviewed this actual PC's baseline XP.", pc_confirmed=True) for id in ids]))
        self.assertEqual(response.status_code, 200, response.text)

    def request(self, id="a_secret_stairs", **changes):
        present = rules.people(self.session)
        return {**dict(milestone_id=id, completion_confirmed=True, reason="GM records the actual source trigger and scene outcome.",
            expected_updated_at=self.session.updated_at,
            reviews=[dict(actor_id=account.actor_id, eligible=True, reason="This actual PC participated in the milestone.")
                for account in self.session.strahd_progress.accounts if account.actor_id in present]), **changes}

    def award(self, id="a_secret_stairs", **changes):
        return self.client.post("/api/strahd/progress/award", json=self.request(id, **changes))

    def test_state_is_readonly_and_legacy_xp_and_arcs_are_unknown(self):
        before = self.session.model_dump()
        response = self.client.get("/api/strahd/progress/state")
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()
        self.assertEqual(len(data["catalog"]), 38)
        self.assertTrue(all(actor["total_xp"] is None for actor in data["actors"]))
        self.assertTrue(all(arc["status"] == "unreviewed" for arc in data["arcs"]))
        self.assertEqual(self.session.model_dump(), before)

    def test_each_eligible_actual_pc_receives_full_source_xp_not_party_division(self):
        self.register()
        before = self.session.character.model_dump()
        response = self.award()
        self.assertEqual(response.status_code, 200, response.text)
        award = self.session.strahd_progress.awards[0]
        self.assertEqual([allocation.xp for allocation in award.allocations], [200, 200])
        self.assertEqual([allocation.total_xp for allocation in award.allocations], [500, 500])
        self.assertNotIn("npc_ireena", {allocation.actor_id for allocation in award.allocations})
        self.assertEqual(self.session.character.model_dump(), before)

    def test_quote_readonly_then_stale_or_duplicate_award_is_atomic(self):
        self.register()
        before = self.session.model_dump()
        response = self.client.post("/api/strahd/progress/quote", json=self.request())
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.session.model_dump(), before)
        response = self.award(expected_updated_at=-1)
        self.assertEqual(response.status_code, 400, response.text)
        self.assertEqual(self.session.model_dump(), before)
        self.assertEqual(self.award().status_code, 200)
        before = self.session.model_dump()
        self.assertEqual(self.award().status_code, 400)
        self.assertEqual(self.session.model_dump(), before)

    def test_concurrent_reward_reviews_cannot_overwrite_one_anothers_xp(self):
        self.register()
        requests = [self.request("a_secret_stairs"), self.request("a_escape_rest")]
        start = Barrier(2)
        actual_award = rules.award
        def delayed_award(state, request):
            time.sleep(0.03)
            return actual_award(state, request)
        def post(request):
            start.wait()
            return self.client.post("/api/strahd/progress/award", json=request)
        with patch.object(rules, "award", side_effect=delayed_award), ThreadPoolExecutor(max_workers=2) as executor:
            responses = list(executor.map(post, requests))
        self.assertEqual(sorted(response.status_code for response in responses), [200, 400])
        self.assertEqual(len(self.session.strahd_progress.awards), 1)
        retry = next(request["milestone_id"] for request, response in zip(requests, responses) if response.status_code == 400)
        self.assertEqual(self.award(retry).status_code, 200)
        self.assertEqual(len(self.session.strahd_progress.awards), 2)
        self.assertEqual([account.awarded_xp for account in self.session.strahd_progress.accounts], [600, 600])

    def test_review_revision_advances_even_when_wall_clock_is_unchanged(self):
        self.register()
        first, stale = self.request("a_secret_stairs"), self.request("a_escape_rest")
        original_revision = self.session.updated_at
        with patch("dungeonforge.api.strahd_routes.time.time", return_value=original_revision):
            self.assertEqual(self.client.post("/api/strahd/progress/award", json=first).status_code, 200)
            self.assertGreater(self.session.updated_at, original_revision)
            before = self.session.model_dump()
            self.assertEqual(self.client.post("/api/strahd/progress/award", json=stale).status_code, 400)
            self.assertEqual(self.session.model_dump(), before)

    def test_gm_completion_confirmation_and_reason_are_required(self):
        self.register()
        for changes in ({"completion_confirmed": False}, {"reason": "  "}):
            before = self.session.model_dump()
            response = self.award(**changes)
            self.assertEqual(response.status_code, 400, response.text)
            self.assertEqual(self.session.model_dump(), before)

    def test_review_every_enrolled_present_pc_once_and_cannot_insert_an_npc(self):
        self.register()
        reviews = self.request()["reviews"]
        for invalid in (reviews[:1], reviews + reviews[:1], reviews + [dict(actor_id="npc_ireena", eligible=True, reason="NPC is not an enrolled PC.")]):
            before = self.session.model_dump()
            response = self.award(reviews=invalid)
            self.assertEqual(response.status_code, 400, response.text)
            self.assertEqual(self.session.model_dump(), before)

    def test_gm_can_exclude_absent_pc_with_actual_reason(self):
        self.register()
        reviews = self.request()["reviews"]
        reviews[1].update(eligible=False, reason="This player was absent and did not participate.")
        response = self.award(reviews=reviews)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(len(self.session.strahd_progress.awards[0].allocations), 1)
        self.assertEqual(self.session.strahd_progress.accounts[1].awarded_xp, 0)

    def test_unregistered_fake_actor_and_repeated_baseline_cannot_reset_claims(self):
        self.register()
        for actors in ([dict(actor_id=self.session.character.id, baseline_xp=300, pc_confirmed=True, reason="Try resetting XP.")],
                [dict(actor_id="invented_pc", baseline_xp=300, pc_confirmed=True, reason="Not in actual party.")],
                [dict(actor_id="npc_ireena", baseline_xp=300, pc_confirmed=False, reason="NPC is not a player.")]):
            before = self.session.model_dump()
            response = self.client.post("/api/strahd/progress/register", json=dict(actors=actors, expected_updated_at=self.session.updated_at))
            self.assertEqual(response.status_code, 400, response.text)
            self.assertEqual(self.session.model_dump(), before)

    def test_baseline_must_support_actual_sheet_level_and_stale_registration_is_atomic(self):
        for xp, revision in [(0, self.session.updated_at), (300, -1)]:
            before = self.session.model_dump()
            response = self.client.post("/api/strahd/progress/register", json=dict(expected_updated_at=revision,
                actors=[dict(actor_id=self.session.character.id, baseline_xp=xp, pc_confirmed=True, reason="Reviewed actual XP.")]))
            self.assertEqual(response.status_code, 400, response.text)
            self.assertEqual(self.session.model_dump(), before)

    def test_source_bonus_requires_base_and_only_eligible_base_recipients(self):
        self.register()
        before = self.session.model_dump()
        self.assertEqual(self.award("q_redeem_abbot").status_code, 400)
        self.assertEqual(self.session.model_dump(), before)
        reviews = self.request()["reviews"]
        reviews[1].update(eligible=False, reason="Absent for the base milestone.")
        self.assertEqual(self.award("q_abbot", reviews=reviews).status_code, 200)
        before = self.session.model_dump()
        self.assertEqual(self.award("q_redeem_abbot").status_code, 400)
        self.assertEqual(self.session.model_dump(), before)
        self.assertEqual(self.award("q_redeem_abbot", reviews=reviews).status_code, 200)
        self.assertEqual(self.session.strahd_progress.accounts[0].awarded_xp, 2500)

    def test_izek_source_alternatives_cannot_be_claimed_twice_through_different_arcs(self):
        self.register()
        self.assertEqual(self.award("fg_izek").status_code, 400)
        self.assertEqual(self.award("fg_izek", variant="rescue_without_defeat").status_code, 200)
        before = self.session.model_dump()
        self.assertEqual(self.award("fg_izek", variant="izek_defeated").status_code, 400)
        self.assertEqual(self.session.model_dump(), before)
        self.assertEqual(self.session.strahd_progress.awards[0].xp_per_pc, 750)

    def test_unknown_monster_or_invented_amount_cannot_become_milestone_xp(self):
        self.register()
        before = self.session.model_dump()
        self.assertEqual(self.award("zombie_kill_50xp").status_code, 400)
        self.assertEqual(self.session.model_dump(), before)

    def test_xp_threshold_reports_pending_level_up_without_changing_sheet_or_resources(self):
        self.register()
        before_character = self.session.character.model_dump()
        self.assertEqual(self.award("a_secret_stairs").status_code, 200)
        self.assertEqual(self.award("a_escape_rest").status_code, 200)
        data = self.client.get("/api/strahd/progress/state").json()
        hero = next(actor for actor in data["actors"] if actor["id"] == self.session.character.id)
        self.assertEqual((hero["total_xp"], hero["xp_level"], hero["sheet_level"], hero["level_up_pending"]), (900, 3, 2, True))
        self.assertEqual(self.session.character.model_dump(), before_character)

    def test_arc_status_is_explicit_revisable_and_grants_no_xp_or_automatic_quests(self):
        self.register()
        before_accounts = [account.model_dump() for account in self.session.strahd_progress.accounts]
        before_quests = dict(self.session.active_quests)
        for status in ("completed", "active"):
            response = self.client.post("/api/strahd/progress/arc", json=dict(arc="A", status=status,
                reason="The GM reviews the actual unresolved scene details.", expected_updated_at=self.session.updated_at))
            self.assertEqual(response.status_code, 200, response.text)
        data = self.client.get("/api/strahd/progress/state").json()
        self.assertEqual(next(arc for arc in data["arcs"] if arc["id"] == "A")["status"], "active")
        self.assertEqual(len(self.session.strahd_progress.arc_reviews), 2)
        self.assertEqual([account.model_dump() for account in self.session.strahd_progress.accounts], before_accounts)
        self.assertEqual(self.session.active_quests, before_quests)
        self.assertEqual(self.session.strahd_progress.awards, [])

    def test_removed_pc_is_not_paid_and_new_pc_cannot_reclaim_old_event(self):
        self.register()
        self.session.character.companions = [person for person in self.session.character.companions if person.id != "second_pc"]
        self.assertEqual(self.award().status_code, 200)
        self.assertEqual(self.session.strahd_progress.accounts[1].awarded_xp, 0)
        self.session.character.companions.append(Companion(id="new_pc", name="Later PC", level=2))
        self.register(ids=["new_pc"])
        before = self.session.model_dump()
        self.assertEqual(self.award().status_code, 400)
        self.assertEqual(self.session.model_dump(), before)

    def test_wrong_campaign_and_edition_reject_before_mutation(self):
        for edition, folder in [("weg_d6", "strahd"), ("5e", "minecraft")]:
            self.session.edition, self.session.source_folders, self.session.id = edition, [folder], "session_other"
            before = self.session.model_dump()
            self.assertEqual(self.client.get("/api/strahd/progress/state").status_code, 409)
            self.assertEqual(self.session.model_dump(), before)

    def test_awards_baselines_reasons_and_arc_reviews_survive_save_load(self):
        self.register()
        self.assertEqual(self.award().status_code, 200)
        response = self.client.post("/api/strahd/progress/arc", json=dict(arc="A", status="active",
            reason="Actual dungeon scene is in progress.", expected_updated_at=self.session.updated_at))
        self.assertEqual(response.status_code, 200, response.text)
        with tempfile.TemporaryDirectory() as directory:
            manager = SaveManager(directory)
            loaded = manager.load_session(manager.save_session(self.session, "milestone"))
        self.assertEqual(loaded.strahd_progress, self.session.strahd_progress)
        routes._ACTIVE_SESSION = self.session = loaded
        self.assertEqual(self.award().status_code, 400)

    def test_legacy_save_missing_ledger_does_not_infer_completed_arcs_or_xp(self):
        self.session.character.level = 8
        self.session.active_quests = {"Completed by player notes": ["Escaped Death House"]}
        with tempfile.TemporaryDirectory() as directory:
            manager = SaveManager(directory)
            data = self.session.model_dump()
            data.pop("strahd_progress")
            (Path(directory) / "legacy.json").write_text(json.dumps(data), encoding="utf-8")
            loaded = manager.load_session("legacy")
        self.assertEqual(loaded.character.level, 8)
        self.assertEqual(loaded.strahd_progress.accounts, [])
        self.assertEqual(loaded.strahd_progress.awards, [])
        self.assertEqual(loaded.strahd_progress.arc_reviews, [])


class LocalStrahdMilestoneSourceTests(unittest.TestCase):
    def test_every_catalog_amount_is_found_in_its_actual_supplied_arc_source(self):
        path = Path(__file__).resolve().parents[2] / ARCHIVE
        if not path.exists():
            self.skipTest("User-provided Reloaded archive is not installed on this host.")
        with ZipFile(path) as archive:
            for item in rules.CATALOG:
                source_paths = [entry.split("!/", 1)[1] for entry in item.source_path.split("; ")]
                text = "\n".join(archive.read(source).decode("utf-8-sig") for source in source_paths)
                amounts = {int(value.replace(",", "")) for value in re.findall(r"\b([\d,]+)\s*XP\b", text)}
                values = set(item.variants.values()) if item.variants else {item.xp_per_pc}
                if item.id == "q_redeem_abbot":
                    self.assertIn(2000 + item.xp_per_pc, amounts)
                else:
                    self.assertTrue(values <= amounts, item.id)


if __name__ == "__main__":
    unittest.main()
