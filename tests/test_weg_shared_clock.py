"""Fleet events happen at their actual round within long travel and work intervals."""
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from dungeonforge.api import routes
from dungeonforge.game.models import GameSession
from dungeonforge.game.weg_force import advance_scene
from dungeonforge.game.weg_vehicle_presets import vehicle_presets
from dungeonforge.main import app
from dungeonforge.rules.base import Character
from dungeonforge.rules.dice import RollResult
from dungeonforge.rules.weg_d6 import WEGD6Rules
from dungeonforge.rules.weg_models import D6Character
from dungeonforge.rules.weg_navigation_models import D6Journey, D6NavigationQuote, D6NavigationRequest
from dungeonforge.rules.weg_vehicle_models import D6Crew
from dungeonforge.rules.weg_vehicles import WEGVehicleRules


class SharedClockTests(unittest.TestCase):
    def setUp(self):
        self.session = GameSession(edition="weg_d6", character=Character(d6=D6Character(credits=100000)))
        craft = vehicle_presets()["yt1300"]
        craft.crew = [D6Crew(id="pilot", name="Pilot", character_id=self.session.character.id,
            stations=["pilot"], d6=self.session.character.d6)]
        craft.occupied = True
        self.session.vehicles.append(craft)
        active = patch.object(routes, "_ACTIVE_SESSION", self.session)
        active.start()
        self.addCleanup(active.stop)
        self.client = TestClient(app)
        self.addCleanup(self.client.close)
        death_dice = patch("dungeonforge.rules.weg_d6.DiceRoller.roll", return_value=RollResult(
            expression="2d6", dice_count=2, die_type=6, total=2, breakdown="Controlled mortality total 2"))
        death_dice.start()
        self.addCleanup(death_dice.stop)

    @property
    def craft(self):
        return self.session.vehicles[0]

    def countdown(self, rounds=1):
        self.craft.destruction_countdown, self.craft.destruction_cause = rounds, "structure"

    def mortal_casualty(self, craft, *args, **kwargs):
        WEGD6Rules.apply_damage(craft.crew[0].d6, 13)
        return []

    def stun_casualty(self, craft, *args, **kwargs):
        WEGD6Rules.apply_damage(craft.crew[0].d6, 0)
        return []

    def unconscious_casualty(self, craft, *args, **kwargs):
        WEGD6Rules.apply_damage(craft.crew[0].d6, 9, stun=True)
        return []

    def journey(self, rounds):
        journey = D6Journey(
            request=D6NavigationRequest(craft_id=self.craft.id, origin="Tatooine", destination="Corellia",
                boarding_confirmed=True, reason="Actual underway travel."),
            quote=D6NavigationQuote(difficulty=15, hours=rounds / 720, rounds=rounds,
                has_navigation=True, multiplier=2),
            remaining_rounds=rounds, roll={"total": 20}, travellers=[self.session.character.id])
        self.session.d6_navigation.journeys.append(journey)
        return journey

    def test_early_fleet_mortal_wound_uses_the_remaining_scene_time(self):
        self.countdown()
        with patch.object(WEGVehicleRules, "passengers", side_effect=self.mortal_casualty):
            advance_scene(self.session, 180)
        state = self.session.character.d6
        self.assertEqual((self.craft.damage, state.wound, state.mortal_rounds), ("destroyed", "dead", 3))
        self.assertEqual(state.force.elapsed_rounds, 180)

    def test_mortal_wound_at_final_boundary_has_no_early_mortality_roll(self):
        self.countdown(rounds=5)
        with patch.object(WEGVehicleRules, "passengers", side_effect=self.mortal_casualty):
            advance_scene(self.session, 5)
        self.assertEqual((self.session.character.d6.wound, self.session.character.d6.mortal_rounds),
            ("mortally_wounded", 0))
        advance_scene(self.session, 1)
        self.assertEqual(self.session.character.d6.mortal_rounds, 1)

    def test_recovery_hero_gets_new_injury_mortality_without_double_clock(self):
        self.countdown()
        with patch.object(WEGVehicleRules, "passengers", side_effect=self.mortal_casualty):
            response = self.client.post("/api/weg-d6/recover", json={"method": "rest", "minutes": 15})
        self.assertEqual(response.status_code, 200, response.text)
        state = self.session.character.d6
        self.assertEqual((state.wound, state.mortal_rounds, state.force.elapsed_rounds), ("dead", 3, 180))
        self.assertEqual(self.craft.damage, "destroyed")

    def test_recovery_new_stun_penalty_expires_during_the_remaining_time(self):
        self.countdown()
        with patch.object(WEGVehicleRules, "passengers", side_effect=self.stun_casualty):
            response = self.client.post("/api/weg-d6/recover", json={"method": "rest", "minutes": 1})
        self.assertEqual(response.status_code, 200, response.text)
        state = self.session.character.d6
        self.assertEqual((state.stun_durations, state.stun_expiries, state.stun_count), ([], [349], 1))
        self.assertEqual(state.force.elapsed_rounds, 12)
        self.assertTrue(state.can_act)

    def test_recovery_new_stun_accumulation_expires_after_thirty_minutes(self):
        self.countdown()
        with patch.object(WEGVehicleRules, "passengers", side_effect=self.stun_casualty):
            response = self.client.post("/api/weg-d6/recover", json={"method": "rest", "minutes": 31})
        self.assertEqual(response.status_code, 200, response.text)
        state = self.session.character.d6
        self.assertEqual((state.stun_durations, state.stun_expiries, state.stun_count), ([], [], 0))
        self.assertEqual(state.force.elapsed_rounds, 372)

    def test_recovery_new_unconsciousness_counts_down_and_restores_round_actions(self):
        self.countdown()
        unconscious_roll = RollResult(expression="9d6", dice_count=9, die_type=6, total=24,
            breakdown="Controlled unconscious duration 24 rounds")
        with patch.object(WEGVehicleRules, "passengers", side_effect=self.unconscious_casualty), \
                patch("dungeonforge.rules.weg_d6.DiceRoller.roll", return_value=unconscious_roll):
            response = self.client.post("/api/weg-d6/recover", json={"method": "rest", "minutes": 3})
        self.assertEqual(response.status_code, 200, response.text)
        state = self.session.character.d6
        self.assertEqual((state.unconscious_rounds, state.force.elapsed_rounds), (0, 36))
        self.assertFalse(state.round_state.blocked)
        self.assertEqual((state.round_state.declared_actions, state.round_state.actions_taken), (1, 0))
        self.assertTrue(state.can_act)

    def test_recovery_short_remainder_preserves_actual_remaining_unconsciousness(self):
        self.countdown()
        unconscious_roll = RollResult(expression="9d6", dice_count=9, die_type=6, total=24,
            breakdown="Controlled unconscious duration 24 rounds")
        with patch.object(WEGVehicleRules, "passengers", side_effect=self.unconscious_casualty), \
                patch("dungeonforge.rules.weg_d6.DiceRoller.roll", return_value=unconscious_roll):
            response = self.client.post("/api/weg-d6/recover", json={"method": "rest", "minutes": 1})
        self.assertEqual(response.status_code, 200, response.text)
        state = self.session.character.d6
        self.assertEqual((state.unconscious_rounds, state.force.elapsed_rounds), (13, 12))
        self.assertFalse(state.round_state.blocked)
        self.assertFalse(state.can_act)

    def test_recovery_does_not_count_original_unconscious_time_twice(self):
        self.countdown()
        self.session.character.d6.unconscious_rounds = 100
        with patch.object(WEGVehicleRules, "passengers", side_effect=self.unconscious_casualty):
            response = self.client.post("/api/weg-d6/recover", json={"method": "rest", "minutes": 1})
        self.assertEqual(response.status_code, 200, response.text)
        state = self.session.character.d6
        self.assertEqual((state.unconscious_rounds, state.force.elapsed_rounds), (88, 12))

    def test_arrival_before_later_craft_failure_is_recorded_before_destruction(self):
        journey = self.journey(rounds=2)
        self.countdown(rounds=5)
        with patch.object(WEGVehicleRules, "passengers", return_value=[]):
            advance_scene(self.session, 10)
        self.assertEqual((journey.status, journey.elapsed_rounds, journey.remaining_rounds), ("arrived", 2, 0))
        self.assertEqual((self.craft.location, self.craft.damage), ("Corellia", "destroyed"))
        self.assertEqual(self.session.character.d6.force.elapsed_rounds, 10)
        self.assertIn("Corellia", self.session.character.d6.species_context.visited_locations)

    def test_failure_before_arrival_records_actual_travel_up_to_the_event(self):
        journey = self.journey(rounds=8)
        self.countdown(rounds=3)
        with patch.object(WEGVehicleRules, "passengers", return_value=[]):
            advance_scene(self.session, 10)
        self.assertEqual((journey.status, journey.elapsed_rounds, journey.remaining_rounds), ("interrupted", 3, 5))
        self.assertEqual(self.session.character.d6.force.elapsed_rounds, 10)
        self.assertNotEqual(self.craft.location, "Corellia")

    def test_long_scene_uses_event_boundaries_without_a_per_round_loop(self):
        self.countdown(rounds=5)
        with patch.object(WEGVehicleRules, "passengers", return_value=[]), \
                patch.object(WEGVehicleRules, "next_round", wraps=WEGVehicleRules.next_round) as fleet_round:
            advance_scene(self.session, 1000000)
        self.assertEqual((self.craft.damage, self.session.character.d6.force.elapsed_rounds), ("destroyed", 1000000))
        self.assertLessEqual(fleet_round.call_count, 8)

    def test_pending_navigation_guard_precedes_all_clock_mutation(self):
        journey = self.journey(rounds=8)
        journey.status = "ten_point_ruling"
        self.countdown()
        before = self.session.model_dump()
        with self.assertRaisesRegex(ValueError, "Resolve the saved navigation"):
            advance_scene(self.session, 1000000)
        self.assertEqual(self.session.model_dump(), before)

    def test_paid_repair_interruption_spends_no_fp_and_applies_later_mortality(self):
        self.craft.damage, self.craft.maneuverability_lost = "lightly_damaged", 1
        response = self.client.post("/api/weg-d6/engineering/begin", json=dict(
            craft_id=self.craft.id, system="maneuverability", reason="Actual actuator and workshop.",
            expected_updated_at=self.session.updated_at))
        self.assertEqual(response.status_code, 200, response.text)
        self.countdown()
        fp = self.session.character.d6.force_points
        with patch.object(WEGVehicleRules, "passengers", side_effect=self.mortal_casualty), \
                patch.object(WEGD6Rules, "roll_skill") as skill:
            response = self.client.post("/api/weg-d6/engineering/attempt", json=dict(
                project_id=self.craft.repair_projects[0].id, force_point=True))
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual((self.session.character.d6.wound, self.session.character.d6.force_points), ("dead", fp))
        self.assertEqual(self.session.character.d6.credits, 90000)
        self.assertTrue(self.craft.repair_projects[0].attempts[-1]["interrupted"])
        skill.assert_not_called()


if __name__ == "__main__":
    unittest.main()
