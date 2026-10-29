import tempfile
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from dungeonforge.api import routes
from dungeonforge.campaign.campaign_manager import CampaignManager
from dungeonforge.game.models import GameSession
from dungeonforge.game.saves import SaveManager
from dungeonforge.main import app
from dungeonforge.rules.weg_d6 import D6Roller, WEGD6Rules
from dungeonforge.rules.dice import RollResult
from dungeonforge.rules import weg_hazards as rules


def roll(total):
    return RollResult(expression="Controlled", dice_count=2, die_type=6, total=total, system="weg_d6", breakdown=f"Controlled test total {total}")


class HazardRulesTests(unittest.TestCase):
    def test_visual_falling_table_boundaries_and_explicit_fraction_convention(self):
        for meters, dice in [(3, 2), (6, 2), (6.1, 3), (12, 3), (13, 4), (18, 4), (19, 5), (30, 5), (31, 7), (50, 7), (51, 9), (100000, 9)]:
            self.assertEqual(rules.falling_dice(meters), dice)
        with self.assertRaises(ValueError): rules.falling_dice(2.9)

    def test_next_difficulty_band_uses_minimum_and_heroic_escalates(self):
        for initial, expected in [(1, 6), (5, 6), (6, 11), (10, 11), (11, 16), (15, 16), (20, 21), (30, 31)]:
            self.assertEqual(rules.harder(initial), expected)
        with self.assertRaises(ValueError): rules.harder(31)
        self.assertEqual(rules.harder(31, 36), 36)


class HazardAPITests(unittest.TestCase):
    def setUp(self):
        preset = CampaignManager.load_campaign("star_wars_d6")
        self.session = GameSession(edition="weg_d6", character=preset.starter_character)
        active = patch.object(routes, "_ACTIVE_SESSION", self.session)
        active.start(); self.addCleanup(active.stop)
        self.client = TestClient(app); self.addCleanup(self.client.close)

    @property
    def state(self):
        return self.session.character.d6

    def post(self, endpoint, **changes):
        return self.client.post(f"/api/weg-d6/hazards/{endpoint}", json={"actor_id": self.session.character.id, "reason": "GM records the actual environmental conditions.", **changes})

    def swim_fail(self, **changes):
        with patch.object(D6Roller, "values", return_value=roll(1)):
            response = self.post("swim", difficulty=10, **changes)
        self.assertEqual(response.status_code, 200, response.text)

    def next_drowning(self, total=12):
        with patch("dungeonforge.api.weg_hazard_routes.DiceRoller.roll", return_value=roll(total)):
            response = self.post("drowning-next")
        self.assertEqual(response.status_code, 200, response.text)
        return response

    def test_actual_fall_uses_source_damage_physical_armor_and_free_full_strength(self):
        self.state.wound = "wounded"
        self.state.stun_durations = [2]
        self.state.round_state.declared_actions = 4
        with patch.object(D6Roller, "values", side_effect=[roll(14), roll(5)]) as dice:
            response = self.post("fall", meters=7, resistance_character_points=1)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(dice.call_args_list[0].args[:2], (3, 0))
        self.assertEqual(dice.call_args_list[1].args[:2], (4, 0))
        self.assertEqual((self.state.wound, self.state.character_points), ("incapacitated", 4))
        self.assertEqual(self.state.hazards.history[-1]["details"]["damage"]["total"], 14)

    def test_nonstandard_and_short_falls_need_gm_code_and_invalid_requests_are_atomic(self):
        for payload in ({"meters": 2.9}, {"meters": 10, "standard_gravity": False}, {"meters": 10, "damage_code": "d20"}):
            before = self.session.model_dump()
            self.assertEqual(self.post("fall", **payload).status_code, 400)
            self.assertEqual(self.session.model_dump(), before)
        with patch.object(D6Roller, "values", side_effect=[roll(2), roll(20)]):
            self.assertEqual(self.post("fall", meters=2, damage_code="1D", standard_gravity=False).status_code, 200)
        self.assertEqual(self.state.wound, "healthy")

    def test_fatigue_is_one_die_not_stacked_and_third_failure_needs_double_exertion_rest(self):
        baseline = WEGD6Rules.pool(self.state, "stamina", free=True)
        for index in range(3):
            with patch.object(D6Roller, "values", return_value=roll(1)):
                response = self.post("exert", rounds=120, difficulty=10)
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(self.state.hazards.fatigue_failures, index + 1)
            self.assertEqual(WEGD6Rules.pool(self.state, "stamina", free=True), baseline)
            self.assertEqual(WEGD6Rules.pool(self.state, "stamina")[0], baseline[0] - 1)
        self.assertTrue(self.state.hazards.exhausted)
        self.assertFalse(self.state.can_act)
        before = self.session.model_dump()
        self.assertEqual(self.post("exert", rounds=1).status_code, 400)
        self.assertEqual(self.session.model_dump(), before)
        self.assertEqual(self.post("rest", rounds=719).status_code, 200)
        self.assertTrue(self.state.hazards.exhausted)
        self.assertEqual(self.post("rest", rounds=1).status_code, 200)
        self.assertFalse(self.state.hazards.fatigued)
        self.assertTrue(self.state.can_act)
        self.assertEqual(self.state.force.elapsed_rounds, 1080)

    def test_regular_native_rest_clears_fatigue_only_after_actual_required_rest(self):
        with patch.object(D6Roller, "values", return_value=roll(1)):
            self.assertEqual(self.post("exert", rounds=240, difficulty=10).status_code, 200)
        self.assertEqual(self.client.post("/api/weg-d6/recover", json={"method": "rest", "minutes": 1}).status_code, 200)
        self.assertTrue(self.state.hazards.fatigued)
        self.assertEqual(self.client.post("/api/weg-d6/recover", json={"method": "rest", "minutes": 19}).status_code, 200)
        self.assertFalse(self.state.hazards.fatigued)

    def test_willpower_push_declares_both_actions_pays_once_fp_and_uses_harder_band(self):
        self.state.skills["willpower"] = "5D"
        with patch.object(D6Roller, "values", side_effect=[roll(1), roll(20)]):
            response = self.post("exert", rounds=120, difficulty=10, push_with_willpower=True, force_point=True)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.state.force_points, 1)
        self.assertTrue(self.state.hazards.willpower_driven)
        self.assertEqual(len(self.state.hazards.history[-1]["details"]["rolls"]), 2)
        with patch.object(D6Roller, "values", return_value=roll(1)):
            response = self.post("exert", rounds=120, difficulty=10)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["eval_result"]["target_value"], 11)
        self.assertTrue(self.state.hazards.exhausted)
        self.assertEqual(rules.rest_required(self.state), 480)

    def test_unrollable_followup_and_point_mix_reject_before_time_or_first_roll(self):
        for payload in ({"push_with_willpower": True}, {"force_point": True, "character_points": 1}):
            before = self.session.model_dump()
            with patch.object(D6Roller, "values") as dice:
                response = self.post("exert", rounds=120, **payload)
                self.assertEqual(response.status_code, 400, response.text)
                dice.assert_not_called()
            self.assertEqual(self.session.model_dump(), before)

    def test_failed_swimming_begins_persistent_emergency_and_blocks_time_check_and_fleet(self):
        self.swim_fail()
        self.assertEqual((self.state.hazards.drowning.round, self.state.hazards.drowning.rescue_difficulty), (0, 11))
        before = self.session.model_dump()
        requests = [("/api/weg-d6/recover", {"method": "rest"}), ("/api/weg-d6/check", {"skill": "search", "difficulty": 10}), ("/api/weg-d6/vehicles/add", {"preset": "yt1300"})]
        for path, payload in requests:
            self.assertIn(self.client.post(path, json=payload).status_code, {400, 409})
            self.assertEqual(self.session.model_dump(), before)

    def test_drowning_uses_plain_two_dice_death_strict_less_and_once_per_round_rescue(self):
        self.swim_fail()
        self.next_drowning(2)
        self.assertNotEqual(self.state.wound, "dead")
        with patch.object(D6Roller, "values", return_value=roll(1)):
            self.assertEqual(self.post("drowning-action", action="swim").status_code, 200)
        before = self.session.model_dump()
        self.assertEqual(self.post("drowning-action", action="swim").status_code, 400)
        self.assertEqual(self.session.model_dump(), before)
        self.next_drowning(2)
        self.assertNotEqual(self.state.wound, "dead")
        self.assertEqual(self.post("drowning-action", action="pass").status_code, 200)
        response = self.next_drowning(2)
        self.assertEqual(self.state.wound, "dead")
        self.assertIn("drowned and died", response.json()["eval_result"]["summary"])

    def test_other_actions_penalized_self_rescue_exempt_and_same_round_fp_cannot_repeat(self):
        self.state.skills.update(search="6D", swimming="5D")
        self.swim_fail()
        self.next_drowning()
        with patch.object(D6Roller, "values", return_value=roll(20)) as dice:
            self.assertEqual(self.post("drowning-action", action="other", skill="search", actions=2, force_point=True).status_code, 200)
            self.assertEqual(dice.call_args.args[0], 8)  # 6D*2 -3D drowning -1D MAP.
        before = self.session.model_dump()
        self.assertEqual(self.post("drowning-action", action="swim", force_point=True).status_code, 400)
        self.assertEqual(self.post("drowning-action", action="swim", character_points=1).status_code, 400)
        self.assertEqual(self.session.model_dump(), before)
        with patch.object(D6Roller, "values", return_value=roll(20)) as dice:
            self.assertEqual(self.post("drowning-action", action="swim").status_code, 200)
            self.assertEqual(dice.call_args.args[0], 9)  # 5D*2 -1D MAP, no drowning penalty.
        self.assertIsNone(self.state.hazards.drowning)

    def test_multiple_swimmers_share_one_scene_round_then_all_must_resolve(self):
        self.swim_fail()
        clock = self.state.force.elapsed_rounds
        helper = self.session.character.companions[0]
        self.swim_fail(actor_id=helper.id)
        self.assertEqual(self.state.force.elapsed_rounds, clock)
        self.assertEqual(len(rules.drowning_people(self.session)), 2)
        self.next_drowning()
        self.assertEqual(self.state.force.elapsed_rounds, clock + 1)
        self.assertEqual(self.post("drowning-action", action="pass").status_code, 200)
        self.assertEqual(self.post("drowning-next").status_code, 400)
        self.assertEqual(self.post("drowning-action", actor_id=helper.id, action="pass").status_code, 200)
        self.next_drowning()

    def test_gm_confirmed_breathing_protection_prevents_drowning_and_rescue_preserves_wounds(self):
        self.swim_fail(breathing_risk=False)
        self.assertIsNone(self.state.hazards.drowning)
        self.swim_fail()
        self.state.wound = "incapacitated"
        self.assertEqual(self.post("drowning-action", action="rescued").status_code, 200)
        self.assertEqual(self.state.wound, "incapacitated")
        self.assertIsNone(self.state.hazards.drowning)

    def test_save_load_retains_actual_emergency_fatigue_rolls_and_round_budget(self):
        self.state.hazards.fatigued = True
        self.state.hazards.exertion_rounds = 100
        self.swim_fail()
        self.next_drowning()
        self.assertEqual(self.post("drowning-action", action="pass").status_code, 200)
        with tempfile.TemporaryDirectory() as directory:
            manager = SaveManager(directory)
            loaded = manager.load_session(manager.save_session(self.session, "hazard"))
        self.assertEqual(loaded.character.d6.hazards, self.state.hazards)
        self.assertEqual(loaded.d6_hazard_round, self.session.d6_hazard_round)


if __name__ == "__main__": unittest.main()
