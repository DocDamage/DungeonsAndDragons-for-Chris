"""1992 corruption uses a plain die, reviewed adventures and explicit tolls."""
import asyncio
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from pydantic import ValidationError

from dungeonforge.api import routes
from dungeonforge.campaign.campaign_manager import CampaignManager
from dungeonforge.game.engine import GameEngine
from dungeonforge.game.models import GameSession
from dungeonforge.game.saves import SaveManager
from dungeonforge.main import app
from dungeonforge.rules import weg_dark_side as dark
from dungeonforge.rules.base import Item
from dungeonforge.rules.weg_dark_models import AtonementRequest, DarkCallRequest, DarkDemand
from dungeonforge.rules.weg_d6 import WEGD6Rules
from dungeonforge.rules.weg_force_catalog import POWERS
from dungeonforge.rules.weg_force_models import ForceEffect
from dungeonforge.rules.weg_models import D6Character


class DarkSideRulesTests(unittest.TestCase):
    def setUp(self):
        self.state = D6Character(force_sensitive=True, force_skills={"control": "4D"}, character_points=12, force_points=3)

    def test_plain_six_never_explodes_and_first_point_cannot_cause_fall(self):
        with patch("dungeonforge.rules.weg_dark_side.random.randint", return_value=6) as dice:
            event = dark.gain_point(self.state, "Evil", "test")
        self.assertEqual(dice.call_count, 1)
        self.assertEqual(event.fall_die, 6)
        self.assertFalse(event.fell)
        self.state.dark_side_points = 0
        with patch("dungeonforge.rules.weg_dark_side.random.randint", return_value=1):
            self.assertFalse(dark.gain_point(self.state, "Evil", "test").fell)

    def test_strict_less_than_and_guaranteed_fall_at_seven_retains_resources(self):
        self.state.dark_side_points = 5
        with patch("dungeonforge.rules.weg_dark_side.random.randint", return_value=6):
            self.assertFalse(dark.gain_point(self.state, "Evil", "test").fell)
            self.assertTrue(dark.gain_point(self.state, "Evil", "test").fell)
        self.assertTrue(self.state.force.dark_side_consumed)
        self.assertEqual((self.state.character_points, self.state.force_points), (12, 3))
        self.assertEqual(self.state.corruption.control_mode, "gm")

    def test_already_consumed_gets_one_cp_per_new_dsp_without_retesting_fall(self):
        self.state.force.dark_side_consumed = True
        with patch("dungeonforge.rules.weg_dark_side.random.randint") as dice:
            event = dark.gain_point(self.state, "Evil", "test")
        dice.assert_not_called()
        self.assertEqual(event.cp_awarded, 1)
        self.assertEqual(self.state.character_points, 13)

    def test_fall_drops_forbidden_emptiness_effects_but_no_other_learned_power(self):
        self.state.force.known_powers = ["control_pain"]
        self.state.force.effects = [ForceEffect(power_id="emptiness_bonus", source_id="hero"), ForceEffect(power_id="control_pain", source_id="hero")]
        self.state.dark_side_points = 1
        with patch("dungeonforge.rules.weg_dark_side.random.randint", return_value=1):
            dark.gain_point(self.state, "Evil", "test")
        self.assertEqual([effect.power_id for effect in self.state.force.effects], ["control_pain"])
        self.assertEqual(self.state.force.known_powers, ["control_pain"])

    def test_new_point_interrupts_atonement_and_preserves_failed_cycle(self):
        self.state.dark_side_points = 1
        dark.atone(self.state, AtonementRequest(action="begin", reason="Follow the code"), 1)
        with patch("dungeonforge.rules.weg_dark_side.random.randint", return_value=4):
            dark.gain_point(self.state, "Accepted temptation", "temptation")
        self.assertIsNone(self.state.corruption.atonement)
        self.assertEqual(self.state.corruption.atonement_history[0].status, "failed")

    def test_call_bands_follow_sensitivity_harm_and_fallen_escalation(self):
        self.assertEqual(dark.call_level(self.state, True, 1), 1)
        self.assertEqual(dark.call_level(self.state, False, 1), 3)
        self.state.force_sensitive = False
        self.assertEqual(dark.call_level(self.state, True, 1), 2)
        self.assertEqual(dark.call_level(self.state, False, 1), 4)
        self.state.force.dark_side_consumed = True
        self.state.corruption.calls_adventure, self.state.corruption.calls = 1, 2
        self.assertEqual(dark.call_level(self.state, True, 1), 3)
        self.assertEqual(dark.call_level(self.state, False, 1), 5)
        self.assertEqual(dark.call_level(self.state, True, 2), 1)

    def test_beyond_heroic_requires_gm_rule_instead_of_invented_band(self):
        self.state.force.dark_side_consumed = True
        self.state.corruption.calls_adventure, self.state.corruption.calls = 1, 5
        with self.assertRaisesRegex(ValueError, "exceeds Heroic"):
            dark.call_level(self.state, True, 1)

    def test_drain_preserves_pips_and_does_not_lower_absolute_learned_skills(self):
        self.state.attributes["dexterity"] = "3D+2"
        self.state.skills["blaster"] = "5D"
        with patch("dungeonforge.rules.weg_dark_side.random.randint", return_value=4):
            self.state.corruption.pending_demand = DarkDemand(cp_loss=4, roll=dark.plain_die("Demand"))
        dark.settle_demand(self.state, "attribute", "dexterity")
        self.assertEqual(self.state.attributes["dexterity"], "2D+2")
        self.assertEqual(self.state.skills["blaster"], "5D")

    def test_drain_to_no_whole_die_is_fatal_and_serializable(self):
        self.state.attributes["strength"] = "1D+2"
        with patch("dungeonforge.rules.weg_dark_side.random.randint", return_value=4):
            self.state.corruption.pending_demand = DarkDemand(cp_loss=4, roll=dark.plain_die("Demand"))
        dark.settle_demand(self.state, "attribute", "strength")
        self.assertEqual(self.state.attributes["strength"], "0D+2")
        self.assertEqual(self.state.wound, "dead")
        self.assertFalse(self.state.can_act)
        loaded = D6Character.model_validate_json(self.state.model_dump_json())
        self.assertTrue(loaded.corruption.dead)
        with self.assertRaises(ValidationError):
            D6Character(attributes={**self.state.attributes}, wound="healthy")

    def test_call_counts_reset_without_adventure_sync_in_pure_rules(self):
        self.state.corruption.calls_adventure, self.state.corruption.calls = 1, 4
        with patch("dungeonforge.rules.weg_dark_side.random.randint", return_value=4):
            dark.call(self.state, DarkCallRequest(intention="Attack foe"), 2)
        self.assertEqual(self.state.corruption.calls, 1)


class DarkSideAPITests(unittest.TestCase):
    def setUp(self):
        preset = CampaignManager.load_campaign("star_wars_d6")
        self.session = GameSession(edition="weg_d6", character=preset.starter_character)
        state = self.session.character.d6
        state.character_points, state.force_points = 12, 3
        state.force_skills = {"control": "4D", "sense": "4D", "alter": "4D"}
        state.force.known_powers = list(POWERS)
        active = patch.object(routes, "_ACTIVE_SESSION", self.session)
        active.start()
        self.addCleanup(active.stop)
        dice = patch("dungeonforge.rules.weg_d6.random.randint", return_value=4)
        dice.start()
        self.addCleanup(dice.stop)
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def post(self, endpoint, **payload):
        response = self.client.post(f"/api/weg-d6/dark-side/{endpoint}", json=payload)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def award(self, **extra):
        return self.post("award", cause="evil_act", player_warned=True, reason="Knowingly harmed an innocent", **extra)

    def boundary(self):
        response = self.client.post("/api/weg-d6/advancement/adventure", json={"label": "Next completed adventure"})
        self.assertEqual(response.status_code, 200, response.text)

    def fall(self, points=2):
        self.session.character.d6.dark_side_points = points
        self.session.character.d6.force.dark_side_consumed = True
        self.client.get("/api/weg-d6/dark-side/state")

    def light_jedi(self):
        response = self.client.post("/api/weg-d6/advancement/instructor", json={"name": "Light Jedi", "force_skills": {"control": "3D+2"}})
        self.assertEqual(response.status_code, 200, response.text)
        return self.session.d6_advancement.instructors[0].id

    def test_ordinary_award_requires_warning_and_is_atomic_on_rejection(self):
        before = self.session.model_dump()
        response = self.client.post("/api/weg-d6/dark-side/award", json={"reason": "An evil choice"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(before, self.session.model_dump())
        result = self.award()
        self.assertEqual(self.session.character.d6.dark_side_points, 1)
        event = result["eval_result"]["state_changes"]["corruption_events"][0]
        self.assertEqual(event["fall_die"], 4)
        self.assertEqual(len(self.session.character.d6.corruption.events), 1)

    def test_sensitive_evil_inaction_and_non_sensitive_force_point_distinction(self):
        state = self.session.character.d6
        state.force_skills = dict.fromkeys(["control", "sense", "alter"], "0D")
        state.force.known_powers = []
        state.force_sensitive = False
        self.assertEqual(self.client.post("/api/weg-d6/dark-side/award", json={"cause": "evil_act", "player_warned": True, "reason": "Evil"}).status_code, 400)
        self.assertEqual(self.client.post("/api/weg-d6/dark-side/award", json={"cause": "inaction", "player_warned": True, "reason": "Stood by"}).status_code, 400)
        before_fp = state.force_points
        self.post("award", cause="evil_force_point", player_warned=True, reason="Evil while using an already spent FP")
        self.assertEqual(self.session.character.d6.dark_side_points, 1)
        self.assertEqual(self.session.character.d6.force_points, before_fp)

    def test_fall_keeps_points_sets_gm_control_and_disables_ordinary_adventure_cp(self):
        self.award()
        with patch("dungeonforge.rules.weg_dark_side.random.randint", return_value=1):
            self.award()
        state = self.session.character.d6
        self.assertTrue(state.force.dark_side_consumed)
        self.assertEqual((state.character_points, state.force_points), (12, 3))
        self.assertEqual(state.corruption.fallen_adventure, 1)
        self.assertEqual(self.client.post("/api/weg-d6/advancement/award", json={"points": 5, "reason": "Adventure reward"}).status_code, 400)
        self.award()
        self.assertEqual(self.session.character.d6.character_points, 13)

    def test_native_harmful_power_auto_award_rolls_once_even_after_cp_boost(self):
        state = self.session.character.d6
        state.force_skills["alter"] = "2D"
        target = self.session.character.companions[0]
        response = self.client.post("/api/weg-d6/force/begin", json={"power_id": "injure_kill", "target_id": target.id, "proximity": "touching", "resistance_total": 10})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertFalse(response.json()["eval_result"]["success"])
        boosted = self.client.post("/api/weg-d6/force/boost", json={"points": 1})
        self.assertEqual(boosted.status_code, 200, boosted.text)
        self.assertTrue(boosted.json()["eval_result"]["success"])
        self.assertEqual(self.session.character.d6.dark_side_points, 1)
        self.assertEqual(len(self.session.character.d6.corruption.events), 1)
        self.assertEqual(boosted.json()["eval_result"]["state_changes"]["corruption_events"][0]["fall_die"], 4)

    def test_taught_dark_side_student_awards_and_checks_npc_teacher(self):
        self.light_jedi()
        teacher = self.session.d6_advancement.instructors[0]
        teacher.dark_side_points = 1
        self.session.character.d6.dark_side_points = 1
        self.session.character.d6.force_skills["control"] = "1D"
        self.session.character.d6.character_points = 20
        response = self.client.post("/api/weg-d6/advancement/start", json={"kind": "force_skill", "key": "control", "teacher_id": teacher.id})
        self.assertEqual(response.status_code, 200, response.text)
        with patch("dungeonforge.rules.weg_dark_side.random.randint", return_value=1):
            response = self.client.post("/api/weg-d6/advancement/study", json={"days": 1})
        self.assertEqual(response.status_code, 200, response.text)
        teacher = self.session.d6_advancement.instructors[0]
        self.assertTrue(teacher.dark_side_consumed)
        self.assertEqual(len(teacher.corruption.events), 1)
        self.assertIn("corruption_events", response.json()["eval_result"]["state_changes"])

    def test_call_consumes_one_action_dsp_and_immediate_fp_without_storing_it(self):
        response = self.post("call", intention="Strike the enemy")
        self.assertTrue(response["eval_result"]["success"])
        state = self.session.character.d6
        self.assertEqual((state.dark_side_points, state.force_points), (1, 3))
        self.assertTrue(state.round_state.dark_side_active)
        self.assertEqual(state.round_state.actions_taken, 1)
        self.assertEqual(WEGD6Rules.pool(state, "blaster"), (9, 4))
        self.assertEqual(WEGD6Rules.damage_pool(state, Item(name="Blaster", damage="5D")), (5, 0))

    def test_additional_fp_stacks_only_personal_dice_and_never_equipment(self):
        self.post("call", intention="Strike the enemy", force_point=True)
        state = self.session.character.d6
        self.assertEqual(state.force_points, 2)
        self.assertEqual(WEGD6Rules.pool(state, "blaster"), (19, 8))
        self.assertEqual(WEGD6Rules.damage_pool(state, Item(name="Vibroaxe", damage="STR+2D")), (14, 0))
        self.assertEqual(WEGD6Rules.damage_pool(state, Item(name="Blaster", damage="5D")), (5, 0))

    def test_remaining_scene_check_uses_call_boost_and_rejects_cp_then_clears_next_round(self):
        self.post("call", intention="Strike the enemy")
        self.assertEqual(self.client.post("/api/weg-d6/check", json={"skill": "blaster", "character_points": 1}).status_code, 400)
        response = self.client.post("/api/weg-d6/check", json={"skill": "blaster"})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["eval_result"]["roll_result"]["dice_count"], 9)
        self.assertEqual(self.client.post("/api/weg-d6/boost", json={"points": 1}).status_code, 400)
        response = self.client.post("/api/weg-d6/check", json={"skill": "blaster", "character_points": 1})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertFalse(self.session.character.d6.round_state.dark_side_called)

    def test_scene_force_power_uses_the_calls_remaining_action_and_boost(self):
        self.post("call", intention="Harm foe")
        response = self.client.post("/api/weg-d6/force/begin", json={"power_id": "control_pain", "keep_up": True})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["eval_result"]["roll_result"]["dice_count"], 7)
        self.assertEqual(self.session.character.d6.round_state.actions_taken, 2)

    def test_existing_normal_fp_declaration_is_not_spent_again_by_call(self):
        WEGD6Rules.declare(self.session.character.d6, 2, True)
        self.post("call", intention="Harm foe")
        self.assertEqual(self.session.character.d6.force_points, 2)
        self.assertEqual(WEGD6Rules.force_factor(self.session.character.d6), 4)

    def test_failure_still_awards_dsp_and_prevents_cp_for_that_round(self):
        response = self.post("call", intention="Avoid harm", harmful=False)
        self.assertFalse(response["eval_result"]["success"])
        self.assertEqual(response["eval_result"]["target_value"], 20)
        state = self.session.character.d6
        self.assertEqual(state.dark_side_points, 1)
        self.assertIsNone(state.corruption.pending_demand)
        self.assertFalse(state.round_state.dark_side_active)
        self.assertEqual(self.client.post("/api/weg-d6/check", json={"skill": "search", "character_points": 1}).status_code, 400)

    def test_non_sensitive_can_call_perception_and_belief_can_forbid_it(self):
        state = self.session.character.d6
        state.force_skills = dict.fromkeys(["control", "sense", "alter"], "0D")
        state.force.known_powers = []
        state.force_sensitive = False
        self.post("belief", refuses_force=True)
        before = self.session.model_dump()
        self.assertEqual(self.client.post("/api/weg-d6/dark-side/call", json={"intention": "Attack"}).status_code, 400)
        self.assertEqual(before, self.session.model_dump())
        self.post("belief", refuses_force=False)
        result = self.post("call", intention="Attack", force_point=True)
        self.assertEqual(result["eval_result"]["target_value"], 15)
        self.assertTrue(result["eval_result"]["success"])

    def test_call_failure_for_consumed_creates_saved_demand_and_blocks_actions(self):
        self.fall()
        self.post("call", intention="Harm foe")
        second = self.post("call", intention="Harm foe again")
        self.assertFalse(second["eval_result"]["success"])
        state = self.session.character.d6
        self.assertEqual(state.corruption.calls, 2)
        self.assertEqual(state.corruption.pending_demand.cp_loss, 4)
        self.assertEqual(state.character_points, 14)
        self.assertEqual(self.client.post("/api/weg-d6/check", json={"skill": "blaster"}).status_code, 400)
        self.assertEqual(self.client.post("/api/weg-d6/advancement/start", json={"kind": "skill", "key": "blaster"}).status_code, 400)
        self.post("pay-demand", method="character_points")
        self.assertEqual(self.session.character.d6.character_points, 10)
        self.assertIsNone(self.session.character.d6.corruption.pending_demand)
        self.assertFalse(self.session.character.d6.round_state.character_points_spent)

    def test_demand_loss_may_kill_and_survives_save_load(self):
        self.fall()
        self.post("call", intention="Harm foe", harmful=False)
        self.session.character.d6.force_skills["sense"] = "1D"
        self.post("pay-demand", method="force_skill", key="sense")
        state = self.session.character.d6
        self.assertEqual(state.wound, "dead")
        with tempfile.TemporaryDirectory() as directory:
            manager = SaveManager(directory)
            loaded = manager.load_session(manager.save_session(self.session, "dark-death"))
        self.assertTrue(loaded.character.d6.corruption.dead)
        self.assertEqual(loaded.character.d6.force_skills["sense"], "0D")

    def test_unpaid_demand_survives_rest_and_reload_and_can_be_paid_only_once(self):
        self.fall()
        self.post("call", intention="Avoid harm", harmful=False)
        self.client.post("/api/weg-d6/recover", json={"method": "rest", "minutes": 1})
        self.assertEqual(self.session.character.d6.corruption.pending_demand.cp_loss, 4)
        with tempfile.TemporaryDirectory() as directory:
            manager = SaveManager(directory)
            loaded = manager.load_session(manager.save_session(self.session, "unpaid-demand"))
        with patch.object(routes, "_ACTIVE_SESSION", loaded):
            response = self.client.post("/api/weg-d6/check", json={"skill": "search"})
            self.assertEqual(response.status_code, 400)
            self.assertEqual(self.client.post("/api/weg-d6/dark-side/pay-demand", json={"method": "character_points"}).status_code, 200)
            points = loaded.character.d6.character_points
            self.assertEqual(self.client.post("/api/weg-d6/dark-side/pay-demand", json={"method": "character_points"}).status_code, 400)
            self.assertEqual(loaded.character.d6.character_points, points)

    def test_invalid_call_difficulty_rolls_nothing_and_spends_nothing(self):
        before = self.session.model_dump()
        with patch("dungeonforge.rules.weg_dark_side.random.randint") as dice:
            response = self.client.post("/api/weg-d6/dark-side/call", json={"intention": "Harm foe", "difficulty": 1, "force_point": True})
        self.assertEqual(response.status_code, 400)
        dice.assert_not_called()
        self.assertEqual(before, self.session.model_dump())

    def test_call_during_combat_declarations_allows_later_actions_but_not_after_defense(self):
        self.client.post("/api/combat/start", json={})
        self.post("call", intention="Harm foe")
        self.assertFalse(self.session.encounter.d6_actions_started)
        self.assertEqual(self.session.character.d6.round_state.actions_taken, 1)
        self.assertEqual(self.client.post("/api/weg-d6/defend", json={"skill": "dodge", "character_points": 1}).status_code, 400)
        self.client.post("/api/combat/end")
        self.client.post("/api/combat/start", json={})
        self.client.post("/api/weg-d6/declare", json={"actions": 2})
        self.client.post("/api/weg-d6/defend", json={"skill": "dodge"})
        self.assertEqual(self.client.post("/api/weg-d6/dark-side/call", json={"intention": "Harm foe"}).status_code, 400)

    def test_crew_call_uses_declaration_and_imperial_crews_refuse_force(self):
        self.client.post("/api/weg-d6/vehicles/add", json={"preset": "yt1300"})
        self.client.post("/api/weg-d6/vehicles/start", json={"vehicle_id": self.session.vehicles[0].id, "enemies": ["tie_fighter"]})
        self.post("call", intention="Destroy the pursuing fighter")
        self.assertTrue(self.session.character.d6.round_state.dark_side_active)
        self.assertFalse(self.session.vehicle_encounter.actions_started)
        enemy = next(craft for craft in self.session.vehicle_encounter.craft if not craft.is_player).crew[0]
        self.assertTrue(enemy.d6.corruption.refuses_force)
        self.assertEqual(self.client.post("/api/weg-d6/dark-side/call", json={"actor_id": enemy.id, "intention": "Attack Rebels"}).status_code, 400)

    def test_atonement_needs_two_completed_and_explicitly_reviewed_adventures(self):
        self.award()
        self.post("atonement", action="begin", reason="Follow Jedi code")
        self.assertEqual(self.client.post("/api/weg-d6/dark-side/atonement", json={"action": "approve", "reason": "Good conduct"}).status_code, 400)
        self.client.post("/api/weg-d6/force/manage", json={"action": "advance", "rounds": 10000})
        self.assertEqual(self.session.character.d6.corruption.atonement.consecutive, 0)
        self.boundary()
        self.post("atonement", action="approve", adventure=1, reason="Protected innocents and opposed evil")
        self.assertEqual(self.session.character.d6.dark_side_points, 1)
        self.boundary()
        self.assertEqual(self.session.character.d6.dark_side_points, 1)
        self.post("atonement", action="approve", adventure=2, reason="Continued to follow Jedi code")
        self.assertEqual(self.session.character.d6.dark_side_points, 0)
        self.assertEqual(self.session.character.d6.character_points, 12)
        self.assertEqual(self.session.character.d6.force_points, 3)
        self.assertIsNone(self.session.character.d6.corruption.atonement)
        self.assertEqual(self.client.post("/api/weg-d6/dark-side/atonement", json={"action": "approve", "reason": "Again"}).status_code, 400)

    def test_rejection_restarts_two_adventure_count_and_no_review_can_be_repeated(self):
        self.award()
        self.post("atonement", action="begin", reason="Follow the code")
        self.boundary()
        self.post("atonement", action="approve", reason="Good conduct")
        self.assertEqual(self.client.post("/api/weg-d6/dark-side/atonement", json={"action": "approve", "adventure": 1, "reason": "Duplicate"}).status_code, 400)
        self.boundary()
        self.post("atonement", action="reject", reason="Repeated warnings and selfish choices")
        self.assertEqual(self.session.character.d6.corruption.atonement.consecutive, 0)
        self.boundary()
        self.post("atonement", action="approve", reason="Renewed commitment")
        self.assertEqual(self.session.character.d6.dark_side_points, 1)
        self.boundary()
        self.post("atonement", action="approve", reason="Consistent commitment")
        self.assertEqual(self.session.character.d6.dark_side_points, 0)

    def test_temptation_requires_active_atonement_and_needs_no_repeat_warning(self):
        self.assertEqual(self.client.post("/api/weg-d6/dark-side/award", json={"cause": "temptation", "reason": "Chose evil"}).status_code, 400)
        self.award()
        self.post("atonement", action="begin", reason="Follow code")
        self.post("award", cause="temptation", reason="Chose the evil temptation")
        self.assertIsNone(self.session.character.d6.corruption.atonement)
        self.assertEqual(self.session.character.d6.dark_side_points, 2)

    def test_fallen_character_cannot_use_ordinary_atonement(self):
        self.fall()
        self.assertEqual(self.client.post("/api/weg-d6/dark-side/atonement", json={"action": "begin", "reason": "Atone"}).status_code, 400)

    def test_moment_of_doubt_uses_whole_control_dice_plus_one_plain_die(self):
        jedi = self.light_jedi()
        self.fall(10)
        self.post("redemption", action="allow_arc", reason="Agreed player redemption story")
        result = self.post("redemption", action="moment_of_doubt", light_jedi_id=jedi, confrontation_key="first-confrontation", reason="Jedi affirmed the Light is stronger")
        self.assertEqual(result["eval_result"]["state_changes"]["doubt_reduction"], 7)
        self.assertEqual(self.session.character.d6.dark_side_points, 3)
        before = self.session.model_dump()
        self.assertEqual(self.client.post("/api/weg-d6/dark-side/redemption", json={"action": "moment_of_doubt", "light_jedi_id": jedi, "confrontation_key": "first-confrontation", "reason": "Repeat"}).status_code, 400)
        self.assertEqual(before, self.session.model_dump())
        self.post("redemption", action="moment_of_doubt", light_jedi_id=jedi, confrontation_key="second-confrontation", reason="A later actual confrontation")
        state = self.session.character.d6
        self.assertFalse(state.force.dark_side_consumed)
        self.assertEqual((state.dark_side_points, state.character_points, state.force_points), (0, 0, 0))
        self.assertEqual(state.corruption.control_mode, "player")
        self.assertEqual(state.force_skills["control"], "4D")

    def test_expired_arc_is_permanent_npc_even_after_heroic_redemption(self):
        jedi = self.light_jedi()
        self.fall(8)
        self.post("redemption", action="allow_arc", adventures=1, reason="One-adventure deadline")
        self.boundary()
        self.assertTrue(self.session.character.d6.corruption.npc_permanent)
        self.post("redemption", action="heroic_sacrifice", light_jedi_id=jedi, reason="Risked certain death saving children")
        state = self.session.character.d6
        self.assertFalse(state.force.dark_side_consumed)
        self.assertEqual(state.corruption.control_mode, "gm")
        self.assertEqual((state.character_points, state.force_points), (0, 0))

    def test_heroic_sacrifice_can_redeem_at_death_in_a_light_jedis_presence(self):
        jedi = self.light_jedi()
        self.fall(8)
        self.post("redemption", action="heroic_sacrifice", light_jedi_id=jedi, died=True, reason="Saved an innocent at the cost of his life")
        self.assertEqual(self.session.character.d6.wound, "dead")
        self.assertFalse(self.session.character.d6.force.dark_side_consumed)
        self.assertEqual(self.session.character.d6.dark_side_points, 0)

    def test_redemption_forfeits_suspended_cp_and_unclaimed_old_fp_returns(self):
        from dungeonforge.rules import weg_advancement
        from dungeonforge.rules.weg_advancement_models import D6TrainingProject, D6TrainingRequest
        request = D6TrainingRequest(kind="attribute", key="dexterity")
        quote = weg_advancement.quote(self.session.character.d6, request, 1)
        course = D6TrainingProject(request=request, quote=quote, started_adventure=1, finished_adventure=1, status="suspended")
        self.session.character.d6.advancement.history.append(course)
        self.session.character.d6.force.heroic_force_returns = 2
        jedi = self.light_jedi()
        self.fall(8)
        self.post("redemption", action="heroic_sacrifice", light_jedi_id=jedi, reason="Risked death to save innocents")
        self.assertEqual(self.session.character.d6.force.heroic_force_returns, 0)
        self.assertEqual(self.session.character.d6.advancement.history[-1].status, "forfeited")
        self.boundary()
        response = self.client.post("/api/weg-d6/advancement/release-suspended", json={"project_id": course.id})
        self.assertEqual(response.status_code, 400)

    def test_unconscious_light_jedi_cannot_cause_moment_of_doubt(self):
        jedi = self.session.character.companions[0]
        jedi.d6.force_sensitive = True
        jedi.d6.force_skills["control"] = "3D"
        jedi.d6.wound = "incapacitated"
        self.fall(8)
        before = self.session.model_dump()
        response = self.client.post("/api/weg-d6/dark-side/redemption", json={"action": "moment_of_doubt", "light_jedi_id": jedi.id, "confrontation_key": "chamber", "reason": "Spoke about the Light"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(before, self.session.model_dump())

    def test_chronicle_includes_corruption_and_pending_atonement(self):
        self.award()
        self.post("atonement", action="begin", reason="Follow code and prevent evil")
        with tempfile.TemporaryDirectory() as directory:
            text = SaveManager(directory).export_markdown_chronicle(self.session)
        self.assertIn("Corruption — Corran Horn", text)
        self.assertIn("plain die 4", text)
        self.assertIn("0/2 approved adventures", text)

    def test_sheet_edit_cannot_bypass_corruption_but_explicit_correction_is_logged(self):
        char = self.session.character.model_dump()
        char["d6"]["dark_side_points"] = 2
        self.assertEqual(self.client.post("/api/character", json=char).status_code, 422)
        self.post("correction", points=2, consumed=False, reason="Import legacy adventure history")
        self.assertEqual(self.session.character.d6.dark_side_points, 2)
        self.assertIsNone(self.session.character.d6.corruption.events[-1].fall_die)
        self.assertIn("legacy/GM correction", self.session.history[-1].rule_result.summary)

    def test_save_restores_pending_demand_and_atonement_review_progress(self):
        self.award()
        self.post("atonement", action="begin", reason="Follow code")
        self.boundary()
        self.post("atonement", action="approve", reason="Good conduct")
        with tempfile.TemporaryDirectory() as directory:
            manager = SaveManager(directory)
            loaded = manager.load_session(manager.save_session(self.session, "atonement"))
        with patch.object(routes, "_ACTIVE_SESSION", loaded):
            self.client.post("/api/weg-d6/advancement/adventure", json={"label": "Next"})
            response = self.client.post("/api/weg-d6/dark-side/atonement", json={"action": "approve", "reason": "Good conduct continued"})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(loaded.character.d6.dark_side_points, 0)
        self.assertEqual(len(loaded.character.d6.corruption.atonement_history[0].reviews), 2)

    def test_old_saves_have_no_retrospective_corruption_rolls_and_gm_narrative_guard(self):
        data = self.session.model_dump()
        data["character"]["d6"].pop("corruption")
        loaded = GameSession.model_validate(data)
        self.assertFalse(loaded.character.d6.corruption.events)
        self.fall()
        with self.assertRaisesRegex(ValueError, "GM control"):
            asyncio.run(GameEngine().execute_turn(self.session, "do", "walk across the room"))


if __name__ == "__main__":
    unittest.main()
