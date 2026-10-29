"""Adventure closure must account for actual spends once, across saves and crew."""
import json
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from dungeonforge.api import routes
from dungeonforge.campaign.campaign_manager import CampaignManager
from dungeonforge.game.models import GameSession
from dungeonforge.game.saves import SaveManager
from dungeonforge.main import app
from dungeonforge.rules.weg_d6 import WEGD6Rules
from dungeonforge.rules.weg_models import D6Character
from dungeonforge.rules.weg_reward_models import AdventureActorReward
from dungeonforge.rules.weg_rewards import settle, spend
from dungeonforge.rules.weg_dark_side import gain_point, redeem


class RewardRuleTests(unittest.TestCase):
    def result(self, state, rulings, **changes):
        for item in state.rewards.expenditures:
            item.adventure = 1
        req = AdventureActorReward(actor_id="hero", reason="GM reviews the completed rescue.", reviews=[
            dict(expenditure_id=item.id, ruling=ruling, reason="Saved innocent refugees.")
            for item, ruling in zip(state.rewards.expenditures, rulings)
        ], **changes)
        return settle(state, req, 1)

    def test_normal_heroic_climax_and_unheroic_returns(self):
        for ruling, expected in [("unheroic", 0), ("heroic", 1), ("heroic_climax", 2)]:
            with self.subTest(ruling=ruling):
                state = D6Character(force_points=1)
                WEGD6Rules.declare(state, force_point=True)
                self.assertEqual(state.force_points, 0)
                self.assertEqual(self.result(state, [ruling])["force_returned"], expected)
                self.assertEqual(state.force_points, expected)

    def test_non_sensitive_overflow_is_mandatory_three_cp_per_fp(self):
        state = D6Character(force_points=4)
        spend(state, "round_boost")
        spend(state, "round_boost")
        result = self.result(state, ["heroic_climax", "heroic_climax"], character_points=6)
        self.assertEqual((state.force_points, result["force_converted"], result["conversion_cp"]), (5, 1, 3))
        self.assertEqual(state.character_points, 14)

    def test_sensitive_character_keeps_more_than_five(self):
        state = D6Character(force_points=7, force_sensitive=True)
        spend(state, "round_boost")
        result = self.result(state, ["heroic_climax"])
        self.assertEqual((state.force_points, result["conversion_cp"]), (8, 0))

    def test_zero_start_heroism_only_for_real_zero_baseline(self):
        state = D6Character(force_points=0)
        self.result(state, [], zero_point_heroism=True)
        self.assertEqual(state.force_points, 1)
        state = D6Character(force_points=1)
        spend(state, "round_boost")
        with self.assertRaisesRegex(ValueError, "beginning"):
            self.result(state, ["unheroic"], zero_point_heroism=True)

    def test_legacy_unknown_zero_start_is_not_assumed(self):
        state = D6Character(force_points=0, rewards={"baseline_known": False})
        with self.assertRaisesRegex(ValueError, "beginning"):
            self.result(state, [], zero_point_heroism=True)

    def test_consumed_requires_evil_climax_and_recorded_moral_event(self):
        state = D6Character(force_points=1, force_sensitive=True)
        state.force.dark_side_consumed = True
        spend(state, "round_boost")
        gain_point(state, "GM records cruelty at the decisive moment.", "evil_force_point")
        dark = state.corruption.events[-1]
        dark.adventure = 1
        state.rewards.expenditures[0].adventure = 1
        req = AdventureActorReward(actor_id="hero", reason="Villain adventure ended.", reviews=[dict(
            expenditure_id=state.rewards.expenditures[0].id, ruling="evil_climax", reason="Decisive evil.", corruption_event_id=dark.id)])
        result = settle(state, req, 1)
        self.assertEqual(result["force_returned"], 2)
        self.assertEqual(state.character_points, 6)  # Only the existing DSP's CP.
        self.assertEqual(len(state.corruption.events), 1)

    def test_evil_must_reference_this_adventure_without_repeating_corruption(self):
        state = D6Character(force_points=1)
        spend(state, "round_boost")
        with self.assertRaisesRegex(ValueError, "Dark Side Point first"):
            self.result(state, ["evil"])

    def test_consumed_heroic_transfer_has_no_return_and_cannot_award_cp(self):
        state = D6Character(force_points=1)
        state.force.dark_side_consumed = True
        spend(state, "transfer_force", guaranteed_heroic=True)
        self.assertTrue(state.rewards.expenditures[0].guaranteed_heroic)
        self.assertEqual(self.result(state, ["heroic"])["force_returned"], 0)
        with self.assertRaisesRegex(ValueError, "Consumed"):
            self.result(state, [], character_points=1)

    def test_transfer_return_is_reviewed_and_counter_clears(self):
        state = D6Character(force_points=2)
        spend(state, "transfer_force", guaranteed_heroic=True)
        state.force.heroic_force_returns = 1
        with self.assertRaisesRegex(ValueError, "always heroic"):
            self.result(state, ["unheroic"])
        self.result(state, ["heroic"])
        self.assertEqual((state.force_points, state.force.heroic_force_returns), (2, 0))

    def test_redemption_forfeits_all_unreviewed_points(self):
        state = D6Character(force_points=1)
        spend(state, "transfer_force", guaranteed_heroic=True)
        state.force.dark_side_consumed = True
        redeem(state)
        self.assertTrue(state.rewards.expenditures[0].forfeited)
        self.result(state, [])
        self.assertEqual(state.force_points, 0)


class RewardAPITests(unittest.TestCase):
    def setUp(self):
        preset = CampaignManager.load_campaign("star_wars_d6")
        self.session = GameSession(edition="weg_d6", character=preset.starter_character)
        active = patch.object(routes, "_ACTIVE_SESSION", self.session)
        active.start()
        self.addCleanup(active.stop)
        dice = patch("dungeonforge.rules.weg_d6.random.randint", return_value=4)
        dice.start()
        self.addCleanup(dice.stop)
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def post(self, endpoint, payload):
        return self.client.post(f"/api/weg-d6/advancement/{endpoint}", json=payload)

    def request(self, ruling="heroic", cp=0):
        view = self.client.get("/api/weg-d6/advancement/state").json()
        return dict(adventure=view["campaign"]["adventure"], expected_updated_at=self.session.updated_at, next_label="Next Rebel mission", actors=[dict(
            actor_id=person["id"], character_points=cp, reason="Completed the rescue.", reviews=[dict(
                expenditure_id=item["id"], ruling="heroic" if item["guaranteed_heroic"] else ruling, reason="Protected the refugees.")
                for item in person["d6"]["rewards"]["expenditures"] if item["adventure"] == view["campaign"]["adventure"] and item["ruling"] is None and not item["forfeited"]]
        ) for person in view["actors"]])

    def check(self):
        response = self.client.post("/api/weg-d6/check", json={"skill": "search", "difficulty": 10, "force_point": True})
        self.assertEqual(response.status_code, 200, response.text)

    def test_quote_readonly_finish_once_and_prevents_replay(self):
        before_fp = self.session.character.d6.force_points
        self.check()
        req = self.request("heroic_climax", cp=5)
        before = self.session.model_dump()
        preview = self.post("reward-quote", req)
        self.assertEqual(preview.status_code, 200, preview.text)
        self.assertEqual(self.session.model_dump(), before)
        finished = self.post("finish-adventure", req)
        self.assertEqual(finished.status_code, 200, finished.text)
        self.assertEqual(self.session.character.d6.force_points, before_fp + 1)
        self.assertEqual(self.session.d6_advancement.adventure, 2)
        after = self.session.model_dump()
        self.assertEqual(self.post("finish-adventure", req).status_code, 400)
        self.assertEqual(self.session.model_dump(), after)

    def test_missing_duplicate_and_foreign_reviews_reject_atomically(self):
        self.check()
        for mode in ("missing", "duplicate", "foreign", "missing_actor", "duplicate_actor"):
            with self.subTest(mode=mode):
                req = self.request()
                if mode == "missing": req["actors"][0]["reviews"] = []
                if mode == "duplicate": req["actors"][0]["reviews"] *= 2
                if mode == "foreign": req["actors"][0]["reviews"][0]["expenditure_id"] = "unknown"
                if mode == "missing_actor": req["actors"].pop()
                if mode == "duplicate_actor": req["actors"].append(req["actors"][0])
                before = self.session.model_dump()
                self.assertEqual(self.post("finish-adventure", req).status_code, 400)
                self.assertEqual(self.session.model_dump(), before)

    def test_later_member_failure_cannot_partially_award_first(self):
        req = self.request(cp=3)
        req["actors"][-1]["reason"] = " "
        before = self.session.model_dump()
        self.assertEqual(self.post("finish-adventure", req).status_code, 400)
        self.assertEqual(self.session.model_dump(), before)

    def test_new_spend_invalidates_old_preview(self):
        self.check()
        req = self.request()
        self.assertEqual(self.post("reward-quote", req).status_code, 200)
        self.check()
        before = self.session.model_dump()
        self.assertEqual(self.post("finish-adventure", req).status_code, 400)
        self.assertEqual(self.session.model_dump(), before)

    def test_old_boundary_cannot_discard_unreviewed_spends(self):
        self.check()
        self.assertEqual(self.post("adventure", {"label": "Cannot skip review"}).status_code, 400)
        self.assertEqual(self.session.d6_advancement.adventure, 1)

    def test_combat_must_end_before_adventure_rewards(self):
        response = self.client.post("/api/combat/start", json={})
        self.assertEqual(response.status_code, 200, response.text)
        before = self.session.model_dump()
        self.assertEqual(self.post("finish-adventure", self.request()).status_code, 400)
        self.assertEqual(self.session.model_dump(), before)

    def test_legacy_transfer_ids_are_stable_and_claimed_once_after_load(self):
        self.session.character.d6.force.heroic_force_returns = 2
        first = self.request()
        second = self.request()
        self.assertEqual(first, second)
        self.assertEqual(self.post("finish-adventure", first).status_code, 200)
        self.assertEqual(self.session.character.d6.force.heroic_force_returns, 0)
        self.assertFalse(self.request()["actors"][0]["reviews"])

    def test_save_load_keeps_pending_and_final_rewards_and_chronicle(self):
        self.check()
        with tempfile.TemporaryDirectory() as directory:
            manager = SaveManager(directory)
            slot = manager.save_session(self.session, "pending")
            loaded = manager.load_session(slot)
            self.assertEqual(loaded.character.d6.rewards, self.session.character.d6.rewards)
            self.assertEqual(self.post("finish-adventure", self.request()).status_code, 200)
            slot = manager.save_session(self.session, "finished")
            loaded = manager.load_session(slot)
            self.assertEqual(loaded.d6_advancement.rewards, self.session.d6_advancement.rewards)
            text = manager.export_markdown_chronicle(loaded)
            self.assertIn("Adventure rewards 1", text)
            self.assertIn("heroic", text)

    def test_legacy_load_does_not_guess_zero_start_eligibility(self):
        self.session.character.d6.force_points = 0
        with tempfile.TemporaryDirectory() as directory:
            manager = SaveManager(directory)
            data = self.session.model_dump()
            del data["character"]["d6"]["rewards"]
            with open(f"{directory}/legacy.json", "w", encoding="utf-8") as file:
                json.dump(data, file)
            loaded = manager.load_session("legacy")
        self.assertFalse(loaded.character.d6.rewards.baseline_known)
        self.assertIsNone(loaded.character.d6.rewards.starting_force_points)

    def test_sheet_edit_cannot_forge_or_clear_expenditures(self):
        self.check()
        original = self.session.character.d6.rewards.model_dump()
        char = self.session.character.model_dump()
        char["d6"]["rewards"]["expenditures"] = []
        response = self.client.post("/api/character", json=char)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.session.character.d6.rewards.model_dump(), original)

    def test_crew_and_personal_declarations_survive_end_encounter(self):
        for vehicle in (False, True):
            with self.subTest(vehicle=vehicle):
                if vehicle:
                    response = self.client.post("/api/weg-d6/vehicles/add", json={"preset": "xwing"})
                    self.assertEqual(response.status_code, 200, response.text)
                    response = self.client.post("/api/weg-d6/vehicles/start", json={"vehicle_id": self.session.vehicles[0].id, "enemies": ["tie_fighter"]})
                    self.assertEqual(response.status_code, 200, response.text)
                    declaration, end = "/api/weg-d6/vehicles/declare", "/api/weg-d6/vehicles/end"
                else:
                    self.assertEqual(self.client.post("/api/combat/start", json={}).status_code, 200)
                    declaration, end = "/api/weg-d6/declare", "/api/combat/end"
                response = self.client.post(declaration, json={"actor_id": self.session.character.id, "actions": 1, "force_point": True})
                self.assertEqual(response.status_code, 200, response.text)
                response = self.client.post(end)
                self.assertEqual(response.status_code, 200, response.text)
        req = self.request()
        self.assertEqual(len(req["actors"][0]["reviews"]), 2)
        self.assertEqual(self.post("finish-adventure", req).status_code, 200)
        self.assertEqual(self.session.character.d6.force_points, 2)

    def test_dark_side_call_records_granted_point_without_deducting_stored_fp(self):
        self.session.character.d6.attributes["perception"] = "6D"
        before = self.session.character.d6.force_points
        response = self.client.post("/api/weg-d6/dark-side/call", json={"actions": 2, "intention": "Defeat the Imperial patrol", "harmful": True})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.session.character.d6.force_points, before)
        uses = self.session.character.d6.rewards.expenditures
        self.assertEqual([item.source for item in uses], ["dark_side_call"])
        req = self.request("unheroic")
        self.assertEqual(self.post("finish-adventure", req).status_code, 200)
        self.assertEqual(self.session.character.d6.force_points, before)

    def test_changed_session_invalidates_preview_even_without_new_spend(self):
        req = self.request()
        self.assertEqual(self.post("reward-quote", req).status_code, 200)
        self.session.updated_at += 1
        self.assertEqual(self.post("finish-adventure", req).status_code, 400)

    def test_closed_adventure_enables_atonement_review_and_resets_call_count(self):
        state = self.session.character.d6
        state.dark_side_points = 1
        response = self.client.post("/api/weg-d6/dark-side/atonement", json={"action": "begin", "reason": "Follow the Jedi code"})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.post("finish-adventure", self.request()).status_code, 200)
        response = self.client.post("/api/weg-d6/dark-side/atonement", json={"action": "approve", "adventure": 1, "reason": "The GM approves the completed adventure."})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.session.character.d6.corruption.atonement.consecutive, 1)
        self.assertEqual(self.session.character.d6.corruption.calls_adventure, 2)

    def test_point_overflow_rejects_entire_party_without_losing_review(self):
        self.check()
        self.session.character.companions[-1].d6.character_points = 1_000_000
        req = self.request(cp=1)
        before = self.session.model_dump()
        self.assertEqual(self.post("finish-adventure", req).status_code, 400)
        self.assertEqual(self.session.model_dump(), before)


if __name__ == "__main__":
    unittest.main()
