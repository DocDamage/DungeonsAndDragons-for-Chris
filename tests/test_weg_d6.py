import asyncio
from pathlib import Path
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
from dungeonforge.rules import get_rule_engine
from dungeonforge.rules.base import Character, Item
from dungeonforge.rules.dice import RollResult
from dungeonforge.rules.weg_d6 import D6Roller, WEGD6Rules
from dungeonforge.rules.weg_models import D6Character, D6Options, D6RoundState


def result(total):
    return RollResult(expression="3D", dice_count=3, die_type=6, total=total, system="weg_d6")


class NativeDiceTests(unittest.TestCase):
    def test_exploding_wild_die_preserves_pips_without_d20_critical(self):
        with patch("dungeonforge.rules.weg_d6.random.randint", side_effect=[4, 3, 6, 6, 2]):
            roll = D6Roller.roll("3d+2")
        self.assertEqual(roll.total, 23)
        self.assertEqual(roll.wild_rolls, [6, 6, 2])
        self.assertFalse(roll.is_crit)
        self.assertFalse(roll.is_fumble)

    def test_initial_wild_one_discards_itself_and_only_one_highest_die(self):
        with patch("dungeonforge.rules.weg_d6.random.randint", side_effect=[6, 6, 2, 1]):
            roll = D6Roller.roll("4D+1")
        self.assertEqual(roll.kept_rolls, [6, 2])
        self.assertEqual(roll.total, 9)
        self.assertEqual(roll.mishap, "penalty")

    def test_complication_keeps_other_dice_and_does_not_force_failure(self):
        with patch("dungeonforge.rules.weg_d6.random.randint", side_effect=[6, 4, 1]):
            roll = D6Roller.roll("3D+2", mishap="complication")
        self.assertEqual(roll.total, 12)
        self.assertEqual(roll.mishap, "complication")
        self.assertFalse(roll.is_fumble)

    def test_one_after_explosion_is_not_a_mishap(self):
        with patch("dungeonforge.rules.weg_d6.random.randint", side_effect=[6, 1]):
            roll = D6Roller.roll("1D")
        self.assertEqual(roll.total, 7)
        self.assertIsNone(roll.mishap)

    def test_character_point_dice_explode_and_do_not_mishap_on_one(self):
        with patch("dungeonforge.rules.weg_d6.random.randint", side_effect=[4, 6, 2, 1]):
            roll = D6Roller.roll("1D", character_points=2)
        self.assertEqual(roll.total, 13)
        self.assertEqual(roll.bonus_rolls, [6, 2, 1])
        self.assertIsNone(roll.mishap)

    def test_zero_pool_and_invalid_die_codes_are_rejected(self):
        with self.assertRaises(ValueError):
            D6Roller.roll("0D")
        for code in ("3d6", "3D+3", "-1D", "3D-1", "51D"):
            with self.subTest(code=code), self.assertRaises(ValidationError):
                D6Character(skills={"blaster": code})


class NativeRulesTests(unittest.TestCase):
    def test_absolute_skills_and_untrained_attribute_fallback(self):
        state = D6Character(skills={"blaster": "4D+1"})
        self.assertEqual(WEGD6Rules.pool(state, "blaster"), (4, 1))
        self.assertEqual(WEGD6Rules.pool(state, "dodge"), (3, 0))
        self.assertEqual(WEGD6Rules.pool(state, "astrogation"), (3, 0))

    def test_force_sensitivity_does_not_grant_force_skills_or_advanced_skills(self):
        state = D6Character(force_sensitive=True)
        for skill in ("control", "sense", "alter", "medicine", "not-a-skill"):
            with self.subTest(skill=skill), self.assertRaises(ValueError):
                WEGD6Rules.skill_code(state, skill)

    def test_force_doubles_dice_and_pips_before_fixed_penalties(self):
        state = D6Character(skills={"blaster": "3D+2"}, wound="wounded", dexterity_penalty=1, force_points=1)
        WEGD6Rules.declare(state, actions=2, force_point=True)
        self.assertEqual(WEGD6Rules.pool(state, "blaster"), (3, 4))
        self.assertEqual(state.force_points, 0)

    def test_force_does_not_double_blaster_damage_or_armor(self):
        state = D6Character(armor_energy="1D", armor_physical="2D")
        state.round_state.force_active = True
        self.assertEqual(WEGD6Rules.damage_pool(state, Item(name="Blaster", damage="5D")), (5, 0))
        self.assertEqual(WEGD6Rules.damage_pool(state, Item(name="Vibroblade", damage="STR+1D")), (7, 0))
        self.assertEqual(WEGD6Rules.resistance_pool(state), (7, 0))

    def test_resistance_uses_full_strength_despite_wounds_stuns_and_actions(self):
        state = D6Character(wound="wounded", stun_durations=[2], armor_physical="1D")
        state.round_state.declared_actions = 4
        self.assertEqual(WEGD6Rules.resistance_pool(state, "physical"), (4, 0))
        with self.assertRaises(ValueError):
            WEGD6Rules.validate_action(state, "blaster")

    def test_cp_limits_and_force_conflict_leave_resources_unchanged(self):
        for cp, force in ((3, False), (1, True), (6, False)):
            state = D6Character(character_points=5)
            state.round_state.force_active = force
            with self.subTest(cp=cp, force=force), self.assertRaises(ValueError):
                WEGD6Rules.roll_skill(state, "search", 10, character_points=cp)
            self.assertEqual(state.character_points, 5)
            self.assertEqual(state.round_state.actions_taken, 0)

    def test_cp_spending_and_equality_success_are_persistent(self):
        state = D6Character(character_points=5)
        with patch("dungeonforge.rules.weg_d6.random.randint", return_value=2):
            evaluation = WEGD6Rules.roll_skill(state, "search", 8, character_points=1)
        self.assertTrue(evaluation.success)
        self.assertEqual(state.character_points, 4)
        self.assertEqual(state.round_state.actions_taken, 1)

    def test_native_damage_table_boundaries(self):
        for margin, expected in ((-1, "unharmed"), (0, "stunned"), (3, "stunned"), (4, "wounded"), (8, "wounded"), (9, "incapacitated"), (12, "incapacitated"), (13, "mortally_wounded"), (15, "mortally_wounded"), (16, "dead")):
            with self.subTest(margin=margin):
                self.assertEqual(WEGD6Rules.apply_damage(D6Character(), margin), expected)

    def test_1992_second_wound_incapacitates_without_revised_wounded_twice(self):
        state = D6Character()
        WEGD6Rules.apply_damage(state, 4)
        WEGD6Rules.apply_damage(state, 4)
        self.assertEqual(state.wound, "incapacitated")
        WEGD6Rules.apply_damage(state, 4)
        self.assertEqual(state.wound, "mortally_wounded")
        state.mortal_rounds = 3
        WEGD6Rules.apply_damage(state, 4)
        self.assertEqual(state.mortal_rounds, 3)
        WEGD6Rules.apply_damage(state, 9)
        self.assertEqual(state.wound, "dead")

    def test_stuns_expire_after_next_round_but_accumulate_for_unconsciousness(self):
        state = D6Character()
        WEGD6Rules.apply_damage(state, 0)
        WEGD6Rules.next_round(state)
        self.assertEqual(state.stun_durations, [1])
        WEGD6Rules.next_round(state)
        self.assertEqual(state.stun_durations, [])
        self.assertEqual(state.stun_count, 1)
        WEGD6Rules.apply_damage(state, 0)
        with patch("dungeonforge.rules.dice.random.randint", return_value=3):
            self.assertEqual(WEGD6Rules.apply_damage(state, 0), "unconscious")
        self.assertEqual(state.unconscious_rounds, 72)

    def test_stun_weapon_does_not_kill_even_on_large_margin(self):
        state = D6Character()
        with patch("dungeonforge.rules.dice.random.randint", return_value=2):
            self.assertEqual(WEGD6Rules.apply_damage(state, 16, stun=True), "unconscious")
        self.assertEqual(state.wound, "healthy")
        self.assertEqual(state.unconscious_rounds, 32)

    def test_normal_dodge_can_replace_base_even_when_lower(self):
        for full, use_roll, expected in ((False, True, 4), (False, False, 10), (True, True, 14)):
            target = D6Character()
            target.round_state.defense_skill = "dodge"
            target.round_state.defense_total = 4
            target.round_state.full_defense = full
            target.round_state.use_defense_roll = use_roll
            with self.subTest(full=full, use_roll=use_roll), patch.object(D6Roller, "values", side_effect=[result(1)]):
                evaluation = WEGD6Rules.resolve_attack(D6Character(), target, Item(name="Blaster", damage="4D"))
            self.assertEqual(evaluation.target_value, expected)

    def test_full_defense_requires_only_one_action_and_consumes_it(self):
        state = D6Character()
        state.round_state.declared_actions = 2
        with self.assertRaises(ValueError):
            WEGD6Rules.defense(state, full=True)
        state.round_state.declared_actions = 1
        with patch.object(D6Roller, "values", return_value=result(10)):
            WEGD6Rules.defense(state, full=True)
        with self.assertRaises(ValueError):
            WEGD6Rules.roll_skill(state, "blaster", 10)

    def test_damage_roll_is_resisted_and_never_becomes_hp_damage(self):
        target = D6Character()
        with patch.object(D6Roller, "values", side_effect=[result(10), result(18), result(10)]):
            evaluation = WEGD6Rules.resolve_attack(D6Character(), target, Item(name="Blaster", damage="4D"))
        self.assertTrue(evaluation.success)
        self.assertIsNone(evaluation.damage_dealt)
        self.assertEqual(evaluation.wound_result, "wounded")
        self.assertEqual(target.wound, "wounded")

    def test_short_and_long_rest_do_not_heal_wounds_or_restore_points(self):
        character = Character(edition="weg_d6", d6=D6Character(wound="wounded", force_points=0, character_points=1))
        WEGD6Rules().apply_short_rest(character)
        WEGD6Rules().apply_long_rest(character)
        self.assertEqual((character.d6.wound, character.d6.force_points, character.d6.character_points), ("wounded", 0, 1))

    def test_natural_healing_requires_days_and_uses_native_strength_table(self):
        state = D6Character(wound="wounded")
        with self.assertRaises(ValueError):
            WEGD6Rules.recover(state, "natural", days=1)
        with patch.object(D6Roller, "roll", return_value=result(7)):
            WEGD6Rules.recover(state, "natural", days=3)
        self.assertEqual(state.wound, "healthy")

    def test_medpac_difficulty_increases_after_failed_attempt(self):
        state = D6Character(wound="wounded")
        healer = D6Character(skills={"first_aid": "5D"})
        with patch.object(D6Roller, "values", return_value=result(9)):
            _, first = WEGD6Rules.recover(state, "medpac", healer=healer)
            _, second = WEGD6Rules.recover(state, "medpac", healer=healer)
        self.assertIn("vs 10", first)
        self.assertIn("vs 15", second)
        self.assertEqual(state.medpacs_used, 2)


class NativeAPITests(unittest.TestCase):
    def setUp(self):
        preset = CampaignManager.load_campaign("star_wars_d6")
        self.session = GameSession(id="session_star_wars_d6", edition="weg_d6", character=preset.starter_character, campaign_name=preset.title, source_folders=["star_wars"])
        session_patch = patch.object(routes, "_ACTIVE_SESSION", self.session)
        session_patch.start()
        self.addCleanup(session_patch.stop)
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def start(self):
        with patch("dungeonforge.rules.weg_d6.random.randint", return_value=3):
            response = self.client.post("/api/combat/start", json={})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["encounter"]

    def test_native_registration_campaign_and_legacy_alias(self):
        self.assertIsInstance(get_rule_engine("weg_d6"), WEGD6Rules)
        self.assertIsInstance(get_rule_engine("d6"), WEGD6Rules)
        with self.assertRaises(ValueError):
            get_rule_engine("invented")
        self.assertEqual(CampaignManager.load_campaign("star_wars_2e").edition, "weg_d6")
        self.assertIsNotNone(self.session.character.d6)

    def test_invalid_resource_request_does_not_spend_a_force_point(self):
        response = self.client.post("/api/weg-d6/check", json={"skill": "search", "force_point": True, "character_points": 1})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.session.character.d6.force_points, 2)
        self.assertEqual(self.session.character.d6.character_points, 5)

    def test_successful_scene_checks_reset_actions_and_use_absolute_pools(self):
        for _ in range(2):
            with patch("dungeonforge.rules.weg_d6.random.randint", return_value=3):
                response = self.client.post("/api/weg-d6/check", json={"skill": "astrogation", "difficulty": 13})
            self.assertEqual(response.status_code, 200, response.text)
            self.assertTrue(response.json()["eval_result"]["success"])
            self.assertEqual(response.json()["eval_result"]["roll_result"]["expression"], "4D+1")

    def test_native_combat_uses_wounds_and_prevents_second_attack_in_same_pass(self):
        encounter = self.start()
        enemy = next(c for c in encounter["combatants"] if not c["is_player"])
        self.assertEqual(encounter["system"], "weg_d6")
        with patch("dungeonforge.rules.weg_d6.random.randint", return_value=3):
            response = self.client.post("/api/combat/attack", json={"target_id": enemy["id"]})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["eval_result"]["wound_result"], "wounded")
        target = next(c for c in response.json()["encounter"]["combatants"] if c["id"] == enemy["id"])
        self.assertEqual(target["current_hp"], enemy["current_hp"])
        self.assertEqual(self.client.post("/api/combat/attack", json={"target_id": enemy["id"]}).status_code, 400)
        self.assertEqual(self.client.post("/api/weg-d6/declare", json={"actions": 2}).status_code, 400)

    def test_enemy_attack_updates_character_and_encounter_wound_together(self):
        self.start()
        for _ in range(4):
            current = self.session.encounter.active_combatant
            if not current.is_player:
                break
            self.client.post("/api/combat/next")
        with patch("dungeonforge.rules.weg_d6.random.randint", return_value=3):
            response = self.client.post("/api/combat/attack", json={"attacker_id": current.id, "target_id": self.session.character.id, "d6_options": {"difficulty": 1}})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["session"]["character"]["d6"]["wound"], "wounded")

    def test_declared_multiple_actions_are_resolved_in_separate_passes(self):
        self.start()
        response = self.client.post("/api/weg-d6/declare", json={"actions": 2})
        self.assertEqual(response.status_code, 200)
        first_round = self.session.encounter.round
        self.client.post("/api/combat/next")
        for _ in range(5):
            if self.session.encounter.active_combatant.id == self.session.character.id:
                break
            self.client.post("/api/combat/next")
        self.assertEqual(self.session.encounter.active_combatant.id, self.session.character.id)
        self.assertEqual(self.session.encounter.round, first_round)
        self.assertEqual(self.session.character.d6.round_state.actions_taken, 1)

    def test_medpac_consumes_inventory_and_companion_can_treat_incapacitated_player(self):
        self.session.character.d6.wound = "incapacitated"
        with patch("dungeonforge.rules.weg_d6.random.randint", return_value=4):
            response = self.client.post("/api/weg-d6/recover", json={"method": "medpac", "healer_id": "rebel_medic"})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.session.character.d6.wound, "wounded")
        self.assertEqual(next(i.quantity for i in self.session.character.inventory if i.name == "Medpac"), 1)

    def test_native_character_cannot_use_spell_slots_or_d20_stat_rolls(self):
        self.assertEqual(self.client.post("/api/character/roll-stats").status_code, 409)
        self.assertEqual(self.client.post("/api/character/cast-spell", json={"spell_name": "Cure Wounds", "slot_level": 0}).status_code, 409)
        self.assertEqual(self.client.post("/api/session/edition", params={"edition": "2e"}).status_code, 409)

    def test_dnd_enemies_are_rejected_without_replacing_the_session(self):
        response = self.client.post("/api/combat/start", json={"enemies": [{"name": "D20 foe", "hp": 100, "ac": 18}]})
        self.assertEqual(response.status_code, 400)
        self.assertIsNone(self.session.encounter)

    def test_native_save_restores_round_resources_and_wounds(self):
        self.start()
        self.client.post("/api/weg-d6/declare", json={"actions": 2, "force_point": True})
        with tempfile.TemporaryDirectory() as directory:
            manager = SaveManager(directory)
            saved = manager.save_session(self.session, "native")
            loaded = manager.load_session(saved)
        self.assertEqual(loaded.edition, "weg_d6")
        self.assertEqual(loaded.character.d6.force_points, 1)
        self.assertTrue(loaded.character.d6.round_state.force_active)
        self.assertEqual(loaded.encounter.system, "weg_d6")

    def test_character_points_can_be_added_after_a_failed_check_without_rerolling(self):
        with patch("dungeonforge.rules.weg_d6.random.randint", return_value=2):
            first = self.client.post("/api/weg-d6/check", json={"skill": "astrogation", "difficulty": 15})
        self.assertFalse(first.json()["eval_result"]["success"])
        wild = first.json()["eval_result"]["roll_result"]["wild_rolls"]
        with patch("dungeonforge.rules.weg_d6.random.randint", side_effect=[6, 2]):
            boosted = self.client.post("/api/weg-d6/boost", json={"points": 1})
        self.assertEqual(boosted.status_code, 200, boosted.text)
        self.assertTrue(boosted.json()["eval_result"]["success"])
        self.assertEqual(boosted.json()["eval_result"]["roll_result"]["wild_rolls"], wild)
        self.assertEqual(self.session.character.d6.character_points, 4)
        self.assertEqual(len(self.session.history), 1)

    def test_post_roll_boost_cannot_exceed_limit_or_follow_force_use(self):
        self.client.post("/api/weg-d6/check", json={"skill": "search", "force_point": True})
        self.assertEqual(self.client.post("/api/weg-d6/boost", json={"points": 1}).status_code, 400)
        self.client.post("/api/weg-d6/check", json={"skill": "search"})
        self.assertEqual(self.client.post("/api/weg-d6/boost", json={"points": 3}).status_code, 400)
        self.assertEqual(self.session.character.d6.character_points, 5)

    def test_another_roll_closes_the_character_point_window(self):
        self.client.post("/api/weg-d6/check", json={"skill": "search"})
        self.client.post("/api/weg-d6/pool", json={"code": "3D"})
        self.assertEqual(self.client.post("/api/weg-d6/boost", json={"points": 1}).status_code, 400)

    def test_defense_can_be_boosted_before_action_phase(self):
        self.start()
        self.client.post("/api/weg-d6/declare", json={"actions": 2})
        defended = self.client.post("/api/weg-d6/defend", json={"skill": "dodge"})
        old = defended.json()["eval_result"]["roll_result"]["total"]
        with patch("dungeonforge.rules.weg_d6.random.randint", return_value=3):
            response = self.client.post("/api/weg-d6/boost", json={"points": 1})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.session.character.d6.round_state.defense_total, old + 3)

    def test_mortal_wound_cannot_be_ignored_by_skipping_to_long_rest(self):
        self.session.character.d6.wound = "mortally_wounded"
        with patch("dungeonforge.rules.dice.random.randint", return_value=1):
            response = self.client.post("/api/weg-d6/recover", json={"method": "rest", "minutes": 1440})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertFalse(response.json()["eval_result"]["success"])
        self.assertEqual(self.session.character.d6.wound, "dead")

    def test_failed_treatment_of_stuns_is_not_reported_as_success(self):
        state = self.session.character.d6
        state.stun_count = 1
        state.stun_durations = [2]
        state.stun_expiries = [360]
        with patch("dungeonforge.rules.weg_d6.random.randint", return_value=1):
            response = self.client.post("/api/weg-d6/recover", json={"method": "medpac", "healer_id": "rebel_medic"})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertFalse(response.json()["eval_result"]["success"])
        self.assertEqual(self.session.character.d6.stun_count, 1)

    def test_native_chronicle_uses_wounds_and_attributes_instead_of_character_level(self):
        with tempfile.TemporaryDirectory() as directory:
            text = SaveManager(directory).export_markdown_chronicle(self.session)
        self.assertIn("WEG Star Wars D6", text)
        self.assertIn("Dexterity 3D+2", text)
        self.assertNotIn("Lvl", text)

    def test_combat_rolls_survive_ending_encounter_in_chronicle(self):
        self.start()
        target = next(c for c in self.session.encounter.combatants if not c.is_player)
        with patch("dungeonforge.rules.weg_d6.random.randint", return_value=3):
            response = self.client.post("/api/combat/attack", json={"target_id": target.id, "d6_options": {"difficulty": 1}})
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()["eval_result"]
        self.assertIsNotNone(result["damage_roll"])
        self.assertEqual(self.session.history[-1].rule_result.roll_result.system, "weg_d6")
        self.client.post("/api/combat/end")
        with tempfile.TemporaryDirectory() as directory:
            chronicle = SaveManager(directory).export_markdown_chronicle(self.session)
        self.assertIn(result["summary"], chronicle)


if __name__ == "__main__":
    unittest.main()
