"""Independent regressions for source timing and shared hazard lifecycle edges."""
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from dungeonforge.api import routes
from dungeonforge.campaign.campaign_manager import CampaignManager
from dungeonforge.game.models import GameSession
from dungeonforge.main import app
from dungeonforge.rules.dice import RollResult
from dungeonforge.rules.weg_d6 import D6Roller
from dungeonforge.rules.weg_force_models import ForceAttempt
from dungeonforge.rules.weg_hazard_models import D6Drowning


def controlled(total):
    return RollResult(expression="Controlled edge roll", dice_count=2, die_type=6,
        total=total, system="weg_d6", breakdown=f"Controlled total {total}")


class HazardLifecycleEdgeTests(unittest.TestCase):
    def setUp(self):
        preset = CampaignManager.load_campaign("star_wars_d6")
        self.session = GameSession(edition="weg_d6", character=preset.starter_character)
        active = patch.object(routes, "_ACTIVE_SESSION", self.session)
        active.start()
        self.addCleanup(active.stop)
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    @property
    def hero(self):
        return self.session.character

    @property
    def companion(self):
        return self.session.character.companions[0]

    def post(self, endpoint, **changes):
        return self.client.post(f"/api/weg-d6/hazards/{endpoint}", json={
            "actor_id": self.hero.id,
            "reason": "GM records this actual shared-round environmental event.",
            **changes,
        })

    def swim(self, actor_id=None, total=1, **changes):
        with patch.object(D6Roller, "values", return_value=controlled(total)):
            response = self.post("swim", actor_id=actor_id or self.hero.id,
                difficulty=10, **changes)
        self.assertEqual(response.status_code, 200, response.text)
        return response

    def next_round(self, totals=None):
        with patch("dungeonforge.api.weg_hazard_routes.DiceRoller.roll",
                side_effect=[controlled(total) for total in (totals or [12])]) as dice:
            response = self.post("drowning-next")
        self.assertEqual(response.status_code, 200, response.text)
        return dice.call_count

    def reserve_exclusive_task(self):
        response = self.client.post("/api/weg-d6/tasks/begin", json={
            "actor_id": self.hero.id, "label": "Exclusive sensor analysis",
            "reason": "The GM declares actual uninterrupted work at the sensor station.",
            "exclusive": True, "expected_updated_at": self.session.updated_at,
            "steps": [{"skill": "search", "difficulty": 10, "rounds": 12,
                "mode": "normal", "reason": "Analyze the actual sensor record."}],
        })
        self.assertEqual(response.status_code, 200, response.text)
        return self.session.d6_tasks.projects[-1]

    def test_initial_failure_records_round_zero_without_early_death_roll(self):
        with patch("dungeonforge.api.weg_hazard_routes.DiceRoller.roll") as death_dice:
            self.swim()
        death_dice.assert_not_called()
        drowning = self.hero.d6.hazards.drowning
        self.assertEqual((drowning.round, drowning.attempted_round, drowning.declared_round), (0, 0, 0))
        self.assertEqual(self.hero.d6.force.elapsed_rounds, 1)
        self.assertEqual(self.companion.d6.force.elapsed_rounds, 1)
        self.assertEqual(self.next_round([2]), 1)
        self.assertEqual(self.hero.d6.hazards.drowning.round, 1)
        self.assertNotEqual(self.hero.d6.wound, "dead")

    def test_late_join_has_its_own_elapsed_drowning_clock_in_shared_scene(self):
        self.swim()
        self.next_round([12])
        self.assertEqual(self.post("drowning-action", action="pass").status_code, 200)
        before_time = self.hero.d6.force.elapsed_rounds
        self.swim(actor_id=self.companion.id)
        self.assertEqual(self.hero.d6.force.elapsed_rounds, before_time)
        self.assertEqual(self.companion.d6.force.elapsed_rounds, before_time)
        self.assertEqual(self.hero.d6.hazards.drowning.round, 1)
        self.assertEqual(self.companion.d6.hazards.drowning.round, 0)
        self.assertEqual(self.next_round([2, 2]), 2)
        self.assertEqual(self.hero.d6.hazards.drowning.round, 2)
        self.assertEqual(self.companion.d6.hazards.drowning.round, 1)
        self.assertEqual(self.hero.d6.force.elapsed_rounds, before_time + 1)
        self.assertEqual(self.companion.d6.force.elapsed_rounds, before_time + 1)
        self.assertNotEqual(self.hero.d6.wound, "dead")
        self.assertNotEqual(self.companion.d6.wound, "dead")

    def test_successful_joining_swimmer_cannot_reroll_same_shared_round(self):
        self.swim()
        self.swim(actor_id=self.companion.id, total=20)
        self.assertIsNone(self.companion.d6.hazards.drowning)
        before = self.session.model_dump()
        with patch.object(D6Roller, "values") as dice:
            response = self.post("swim", actor_id=self.companion.id, difficulty=10)
        self.assertEqual(response.status_code, 400)
        dice.assert_not_called()
        self.assertEqual(self.session.model_dump(), before)
        self.next_round([12])
        self.swim(actor_id=self.companion.id, total=20)
        self.assertEqual(self.companion.d6.hazards.swim_round, self.session.d6_hazard_round)

    def test_waking_drowning_character_must_resolve_current_opportunity(self):
        self.swim()
        self.hero.d6.unconscious_rounds = 1
        self.assertFalse(self.hero.d6.can_act)
        self.next_round([12])
        self.assertTrue(self.hero.d6.can_act)
        self.assertEqual(self.hero.d6.hazards.drowning.round, 1)
        before = self.session.model_dump()
        with patch("dungeonforge.api.weg_hazard_routes.DiceRoller.roll") as dice:
            response = self.post("drowning-next")
        self.assertEqual(response.status_code, 400)
        dice.assert_not_called()
        self.assertEqual(self.session.model_dump(), before)
        self.assertEqual(self.post("drowning-action", action="pass").status_code, 200)
        self.next_round([12])

    def test_gm_rescue_is_an_actual_fact_and_preserves_pending_activation(self):
        self.swim()
        self.hero.d6.force.attempt = ForceAttempt(power_id="magnify_senses",
            source_id=self.hero.id, skills=["sense"], preparation_remaining=3)
        self.hero.d6.wound = "incapacitated"
        before_time = self.hero.d6.force.elapsed_rounds
        points = self.hero.d6.character_points, self.hero.d6.force_points
        with patch.object(D6Roller, "values") as dice:
            response = self.post("drowning-action", action="rescued")
        self.assertEqual(response.status_code, 200, response.text)
        dice.assert_not_called()
        self.assertIsNone(self.hero.d6.hazards.drowning)
        self.assertEqual(self.hero.d6.wound, "incapacitated")
        self.assertEqual(self.hero.d6.force.attempt.power_id, "magnify_senses")
        self.assertEqual(self.hero.d6.force.attempt.preparation_remaining, 3)
        self.assertEqual(self.hero.d6.force.elapsed_rounds, before_time)
        self.assertEqual((self.hero.d6.character_points, self.hero.d6.force_points), points)

    def test_gm_breathing_protection_does_not_consume_a_rescue_or_wound(self):
        self.swim()
        before_time = self.hero.d6.force.elapsed_rounds
        self.swim(actor_id=self.companion.id, breathing_risk=False)
        self.assertIsNone(self.companion.d6.hazards.drowning)
        self.assertEqual(self.companion.d6.wound, "healthy")
        self.assertEqual(self.hero.d6.force.elapsed_rounds, before_time)
        self.assertEqual(self.companion.d6.force.elapsed_rounds, before_time)
        self.assertEqual(self.hero.d6.hazards.drowning.round, 0)

    def test_recovery_credits_only_selected_actor_and_preserves_other_fatigue(self):
        for person in (self.hero, self.companion):
            person.d6.hazards.fatigued = True
            person.d6.hazards.fatigue_failures = 1
            person.d6.hazards.exertion_rounds = 120
        response = self.post("rest", rounds=120)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertFalse(self.hero.d6.hazards.fatigued)
        self.assertTrue(self.companion.d6.hazards.fatigued)
        self.assertEqual(self.companion.d6.hazards.rest_rounds, 0)
        self.assertEqual(self.hero.d6.force.elapsed_rounds, 120)
        self.assertEqual(self.companion.d6.force.elapsed_rounds, 120)

    def test_stopping_willpower_retains_all_exertion_and_requires_double_rest(self):
        hazard = self.hero.d6.hazards
        hazard.fatigued = hazard.willpower_driven = True
        hazard.fatigue_failures = 1
        hazard.exertion_rounds = 120
        before_time = self.hero.d6.force.elapsed_rounds
        self.assertEqual(self.post("stop-pushing").status_code, 200)
        self.assertEqual(self.hero.d6.force.elapsed_rounds, before_time)
        self.assertTrue(self.hero.d6.hazards.exhausted)
        self.assertFalse(self.hero.d6.hazards.willpower_driven)
        self.assertEqual(self.post("rest", rounds=239).status_code, 200)
        self.assertTrue(self.hero.d6.hazards.exhausted)
        self.assertEqual(self.post("rest", rounds=1).status_code, 200)
        self.assertFalse(self.hero.d6.hazards.exhausted)
        self.assertEqual(self.hero.d6.hazards.exertion_rounds, 0)

    def test_reserved_exclusive_worker_cannot_exert_swim_or_claim_rest(self):
        self.reserve_exclusive_task()
        before = self.session.model_dump()
        with patch.object(D6Roller, "values") as dice:
            for endpoint in ("exert", "swim", "rest"):
                response = self.post(endpoint, rounds=12, difficulty=10)
                self.assertEqual(response.status_code, 400, response.text)
                self.assertEqual(self.session.model_dump(), before)
            dice.assert_not_called()

    def test_actual_gm_fall_preserves_reserved_exclusive_project(self):
        project = self.reserve_exclusive_task()
        clock = self.hero.d6.force.elapsed_rounds
        with patch.object(D6Roller, "values", side_effect=[controlled(1), controlled(20)]):
            response = self.post("fall", meters=3)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.hero.d6.wound, "healthy")
        self.assertEqual(self.session.d6_tasks.projects[-1].id, project.id)
        self.assertEqual(self.session.d6_tasks.projects[-1].status, "pending")
        self.assertEqual(self.hero.d6.force.elapsed_rounds, clock)

    def test_actual_gm_rescue_is_allowed_for_reserved_worker(self):
        project = self.reserve_exclusive_task()
        self.hero.d6.hazards.drowning = D6Drowning(initial_difficulty=10, rescue_difficulty=11)
        clock = self.hero.d6.force.elapsed_rounds
        with patch.object(D6Roller, "values") as dice:
            response = self.post("drowning-action", action="rescued")
        self.assertEqual(response.status_code, 200, response.text)
        dice.assert_not_called()
        self.assertIsNone(self.hero.d6.hazards.drowning)
        self.assertEqual(self.session.d6_tasks.projects[-1].id, project.id)
        self.assertEqual(self.session.d6_tasks.projects[-1].status, "pending")
        self.assertEqual(self.hero.d6.force.elapsed_rounds, clock)

    def test_gamorrean_companion_retry_precedes_fatigue_injury_and_no_extra_action(self):
        self.companion.d6.species_id = "gamorrean"
        before_cp = self.companion.d6.character_points
        with patch.object(D6Roller, "values", side_effect=[controlled(1), controlled(20)]):
            response = self.post("exert", actor_id=self.companion.id, rounds=12, difficulty=10,
                character_points=1, gamorrean_retry=True, retry_character_points=1,
                failure_damage_margin=16)
        self.assertEqual(response.status_code, 200, response.text)
        state = self.companion.d6
        self.assertEqual(state.hazards.fatigue_failures, 0)
        self.assertFalse(state.hazards.fatigued)
        self.assertEqual(state.wound, "healthy")
        self.assertEqual(state.round_state.actions_taken, 1)
        self.assertEqual(state.character_points, before_cp - 2)
        self.assertEqual(len(state.hazards.history[-1]["details"]["rolls"]), 2)
        self.assertTrue(state.hazards.history[-1]["details"]["gamorrean_retry"])
        self.assertEqual(self.hero.d6.force.elapsed_rounds, 12)
        self.assertEqual(state.force.elapsed_rounds, 12)

    def test_gamorrean_retry_rejects_force_point_mix_and_aggregate_overdraft_atomically(self):
        self.hero.d6.species_id = "gamorrean"
        self.hero.d6.skills["willpower"] = "5D"
        for changes in ({"force_point": True, "retry_character_points": 1},
                {"character_points": 2, "retry_character_points": 2,
                    "push_with_willpower": True, "willpower_character_points": 2}):
            before = self.session.model_dump()
            with patch.object(D6Roller, "values") as dice:
                response = self.post("exert", rounds=12, difficulty=10,
                    gamorrean_retry=True, **changes)
            self.assertEqual(response.status_code, 400, response.text)
            dice.assert_not_called()
            self.assertEqual(self.session.model_dump(), before)

    def test_heroic_swimming_requires_actual_harder_gm_rescue_difficulty(self):
        before = self.session.model_dump()
        with patch.object(D6Roller, "values") as dice:
            response = self.post("swim", difficulty=31)
        self.assertEqual(response.status_code, 400, response.text)
        dice.assert_not_called()
        self.assertEqual(self.session.model_dump(), before)
        with patch.object(D6Roller, "values", return_value=controlled(1)):
            response = self.post("swim", difficulty=31, rescue_difficulty=45)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.hero.d6.hazards.drowning.rescue_difficulty, 45)

    def test_heroic_willpower_push_requires_explicit_harder_gm_difficulty(self):
        self.hero.d6.skills.update(stamina="5D", willpower="5D")
        before = self.session.model_dump()
        with patch.object(D6Roller, "values") as dice:
            response = self.post("exert", rounds=12, difficulty=31, push_with_willpower=True)
        self.assertEqual(response.status_code, 400, response.text)
        dice.assert_not_called()
        self.assertEqual(self.session.model_dump(), before)
        with patch.object(D6Roller, "values", side_effect=[controlled(1), controlled(45)]):
            response = self.post("exert", rounds=12, difficulty=31,
                push_with_willpower=True, willpower_difficulty=45)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(self.hero.d6.hazards.willpower_driven)
        self.assertIn("difficulty 45", response.json()["eval_result"]["summary"])

    def test_next_band_override_cannot_skip_printed_difficulty_level(self):
        self.hero.d6.skills["willpower"] = "5D"
        for endpoint, changes in (("swim", {"rescue_difficulty": 16}),
                ("exert", {"rounds": 12, "push_with_willpower": True, "willpower_difficulty": 16})):
            before = self.session.model_dump()
            with patch.object(D6Roller, "values") as dice:
                response = self.post(endpoint, difficulty=10, **changes)
            self.assertEqual(response.status_code, 400, response.text)
            dice.assert_not_called()
            self.assertEqual(self.session.model_dump(), before)

    def test_willpower_worsens_only_actual_gm_failure_injury_one_level(self):
        initial = self.hero.d6.model_copy(deep=True)
        initial.skills.update(stamina="5D", willpower="5D")
        for margin, expected in ((0, "wounded"), (4, "incapacitated"),
                (9, "mortally_wounded"), (13, "dead"), (16, "dead")):
            with self.subTest(margin=margin):
                self.hero.d6 = initial.model_copy(deep=True)
                with patch.object(D6Roller, "values", side_effect=[controlled(1), controlled(20)]):
                    response = self.post("exert", rounds=12, difficulty=10,
                        push_with_willpower=True, failure_damage_margin=margin)
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(self.hero.d6.wound, expected)
                saved = self.hero.d6.hazards.history[-1]["details"]
                self.assertEqual(saved["environmental_damage_margin"], margin)
                self.assertTrue(saved["willpower_worsened_injury"])
                if margin == 0:
                    self.assertEqual(self.hero.d6.stun_count, 0)
                    self.assertEqual(self.hero.d6.stun_durations, [])
                    self.assertEqual(self.hero.d6.stun_expiries, [])

    def test_worsened_stun_preserves_only_preexisting_stuns_and_unconsciousness(self):
        self.hero.d6.skills.update(stamina="6D", willpower="6D")
        self.hero.d6.stun_count = 1
        self.hero.d6.stun_durations = [50]
        self.hero.d6.stun_expiries = [100]
        with patch.object(D6Roller, "values", side_effect=[controlled(1), controlled(20)]):
            response = self.post("exert", rounds=12, difficulty=10,
                push_with_willpower=True, failure_damage_margin=0)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.hero.d6.wound, "wounded")
        self.assertEqual(self.hero.d6.stun_count, 1)
        self.assertEqual(self.hero.d6.stun_durations, [38])
        self.assertEqual(self.hero.d6.stun_expiries, [88])
        self.assertEqual(self.hero.d6.unconscious_rounds, 0)

    def test_worsened_stun_does_not_leave_its_replaced_new_unconscious_timer(self):
        self.hero.d6.skills.update(stamina="6D", willpower="6D")
        self.hero.d6.attributes["strength"] = "1D"
        with patch.object(D6Roller, "values", side_effect=[controlled(1), controlled(20)]), \
                patch("dungeonforge.rules.weg_d6.DiceRoller.roll", return_value=controlled(2)):
            response = self.post("exert", rounds=12, difficulty=10,
                push_with_willpower=True, failure_damage_margin=0)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.hero.d6.wound, "wounded")
        self.assertEqual(self.hero.d6.unconscious_rounds, 0)
        self.assertEqual(self.hero.d6.stun_count, 0)
        self.assertEqual(self.hero.d6.stun_durations, [])
        self.assertEqual(self.hero.d6.stun_expiries, [])


if __name__ == "__main__":
    unittest.main()
