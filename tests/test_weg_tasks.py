"""Original 1992 Command charts and declared, exclusive scene-task procedures."""
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from dungeonforge.api import routes
from dungeonforge.game.models import GameSession
from dungeonforge.game.saves import SaveManager
from dungeonforge.game.weg_force import advance_scene
from dungeonforge.main import app
from dungeonforge.rules import weg_tasks as rules
from dungeonforge.rules.base import Character, Companion
from dungeonforge.rules.dice import RollResult
from dungeonforge.rules.weg_d6 import D6Roller
from dungeonforge.rules.weg_models import D6Character
from dungeonforge.rules.weg_force_models import ForceEffect
from dungeonforge.rules.weg_navigation_models import D6Journey, D6NavigationQuote, D6NavigationRequest
from dungeonforge.rules.weg_tasks_models import D6TaskRequest


def roll(total):
    return RollResult(expression="4D", dice_count=4, die_type=6, total=total,
        system="weg_d6", breakdown=f"Controlled task total {total}")


def session():
    hero = Character(id="commander", name="Commander", d6=D6Character(
        skills={"command": "5D", "space_transports_repair": "6D"}, force_points=2, character_points=5))
    hero.companions = [Companion(id=id, name=id, d6=D6Character(skills={"space_transports_repair": code}))
        for id, code in [("worker1", "2D+2"), ("worker2", "4D+1"), ("worker3", "5D")]]
    return GameSession(edition="weg_d6", character=hero)


def request(state, **changes):
    return {**dict(actor_id="commander", label="Align the power couplings", reason="GM declares the actual apparatus and procedure.",
        exclusive=True, steps=[dict(skill="space_transports_repair", difficulty=10, rounds=12,
            mode="normal", reason="Align this coupling with the actual tools.")], expected_updated_at=state.updated_at), **changes}


class TaskRulesTests(unittest.TestCase):
    def setUp(self):
        self.session = session()

    def req(self, **changes):
        return D6TaskRequest(**request(self.session, **changes))

    def group(self, **changes):
        return self.req(**{**dict(actor_id="worker1", participant_ids=["worker1", "worker2", "worker3"],
            commander_id="commander", contact_confirmed=True, target_visible=True, same_range=True,
            participant_limit=3), **changes})

    def test_1992_command_chart_corners_and_bonus_rows(self):
        self.assertEqual((len(rules.COMMAND), len(rules.COMMAND[0])), (15, 8))
        self.assertEqual(rules.COMMAND[0], (2, 2, 1, 1, 1, 0, 0, 0))
        self.assertEqual(rules.COMMAND[6], (4, 4, 4, 3, 3, 3, 2, 2))
        self.assertEqual(rules.COMMAND[-1], (5,) * 8)
        self.assertEqual([rules.bonus(count) for count in rules.COUNTS], list(range(1, 16)))
        self.assertEqual((rules.bonus(1), rules.bonus(3), rules.bonus(85)), (0, 1, 8))

    def test_printed_tirog_example_full_and_partial_command_results(self):
        # Forty 5D troops, GM difficulty 18: printed pp.69-70.
        for total, expected in [(18, 40), (17, 25), (16, 25), (15, 15), (11, 15), (10, 4), (6, 4), (5, 0)]:
            self.assertEqual(rules.commanded(40, 5, 18, total), expected)

    def test_same_band_failure_moves_to_first_band_row_and_at_least_one_row(self):
        self.assertEqual(rules.commanded(60, 5, 20, 17), 25)
        self.assertEqual(rules.commanded(25, 5, 20, 17), 15)
        self.assertEqual(rules.commanded(2, 1, 15, 12), 0)
        self.assertEqual(rules.commanded(85, 5, 20, 20), 60)

    def test_actual_worker_codes_floor_pips_then_average_and_floor_people(self):
        result = rules.quote(self.session, self.group())
        self.assertEqual((result.average_skill, result.declared_count, result.table_count), (3, 3, 2))
        self.assertEqual((result.command_band, result.command_difficulty), ("easy", 10))
        self.assertEqual(result.participants[0]["skills"], {"space_transports_repair": "2D+2"})

    def test_quote_readonly_and_source_defaults_no_later_one_bonus_per_three_rule(self):
        before = self.session.model_dump()
        result = rules.quote(self.session, self.group())
        self.assertEqual(self.session.model_dump(), before)
        self.assertEqual(result.table_count, 2)
        self.assertIn("1992", result.source)

    def test_gm_command_difficulty_must_stay_within_actual_source_band(self):
        self.assertEqual(rules.quote(self.session, self.group(command_difficulty=6)).command_difficulty, 6)
        with self.assertRaisesRegex(ValueError, "source Command row"):
            rules.quote(self.session, self.group(command_difficulty=15))

    def test_contact_visibility_shared_range_and_hands_on_limit_are_required(self):
        for changes in ({"contact_confirmed": False}, {"target_visible": False}, {"same_range": False},
                {"participant_limit": 2}, {"participant_limit": None}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                rules.quote(self.session, self.group(**changes))

    def test_unknown_duplicate_and_unrepresented_actual_workers_are_rejected(self):
        for changes in ({"participant_ids": ["worker1", "fictional"]},
                {"participant_ids": ["worker1", "worker1"]}, {"actor_id": "commander"}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                rules.quote(self.session, self.group(**changes))

    def test_commander_participation_must_match_worker_declaration(self):
        with self.assertRaisesRegex(ValueError, "exactly when"):
            rules.quote(self.session, self.group(commander_participates=True))
        with self.assertRaisesRegex(ValueError, "exactly when"):
            rules.quote(self.session, self.group(actor_id="commander", participant_ids=["commander", "worker1"]))

    def test_preparation_equal_time_plus_one_die_and_rushing_halves_time(self):
        prepared = self.req(steps=[dict(skill="space_transports_repair", difficulty=10, rounds=24,
            mode="prepared", reason="Exclusive preparation and work.")])
        q = rules.quote(self.session, prepared).steps[0]
        self.assertEqual((q.preparation_rounds, q.work_rounds, q.total_rounds), (24, 24, 48))
        rushed = prepared.model_copy(deep=True)
        rushed.steps[0].mode = "rushed"
        q = rules.quote(self.session, rushed).steps[0]
        self.assertEqual((q.preparation_rounds, q.work_rounds, q.total_rounds), (0, 12, 12))

    def test_one_round_cannot_rush_and_exclusive_concentration_is_required(self):
        req = self.req(steps=[dict(skill="search", difficulty=10, rounds=1, mode="rushed", reason="Actual work.")])
        with self.assertRaisesRegex(ValueError, "two rounds"):
            rules.quote(self.session, req)
        with self.assertRaisesRegex(ValueError, "exclusive concentration"):
            rules.quote(self.session, self.req(exclusive=False))

    def test_preparation_and_combination_bans_include_specializations(self):
        state = self.session.character.d6
        state.skills["dueling"] = "5D"
        state.specializations.append("dueling")
        state.specialization_parents["dueling"] = "lightsaber"
        req = self.req(steps=[dict(skill="dueling", difficulty=10, rounds=1, mode="prepared", reason="Actual training target.")])
        with self.assertRaisesRegex(ValueError, "cannot receive"):
            rules.quote(self.session, req)
        req = self.group(steps=[dict(skill="astrogation", difficulty=10, rounds=1, reason="Actual route.")])
        with self.assertRaisesRegex(ValueError, "cannot be combined"):
            rules.quote(self.session, req)
        # Astrogation is in the combination ban, but is absent from the preparation ban.
        req = self.req(steps=[dict(skill="astrogation", difficulty=10, rounds=1, mode="prepared", reason="Actual calculation.")])
        self.assertEqual(rules.quote(self.session, req).steps[0].total_rounds, 2)

    def test_odd_rushing_requires_explicit_gm_rounding_without_invented_default(self):
        req = self.req(steps=[dict(skill="search", difficulty=10, rounds=3, mode="rushed", reason="Actual search.")])
        with self.assertRaisesRegex(ValueError, "fractional"):
            rules.quote(self.session, req)
        req.steps[0].rush_rounding, req.steps[0].rounding_reason = "up", "The GM resolves odd rounds and dice upward."
        self.assertEqual(rules.quote(self.session, req).steps[0].total_rounds, 2)

    def test_participating_long_task_commander_cannot_claim_exclusive_personal_points(self):
        for points in ({"command_character_points": 1}, {"command_force_point": True}):
            req = self.group(actor_id="commander", participant_ids=["commander", "worker1"], commander_participates=True, **points)
            with self.assertRaisesRegex(ValueError, "only one action"):
                rules.quote(self.session, req)

    def test_maintaining_another_power_breaks_exclusive_concentration(self):
        self.session.character.d6.force.effects.append(ForceEffect(power_id="control_pain", source_id="commander",
            skills=["control"], maintained=True))
        with self.assertRaisesRegex(ValueError, "maintain another power"):
            rules.quote(self.session, self.req())


class TaskAPITests(unittest.TestCase):
    def setUp(self):
        self.session = session()
        active = patch.object(routes, "_ACTIVE_SESSION", self.session)
        active.start()
        self.addCleanup(active.stop)
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    @property
    def project(self):
        return self.session.d6_tasks.projects[-1]

    def begin(self, total=20, **changes):
        with patch.object(D6Roller, "values", return_value=roll(total)):
            response = self.client.post("/api/weg-d6/tasks/begin", json=request(self.session, **changes))
        self.assertEqual(response.status_code, 200, response.text)
        return self.project

    def advance(self, rounds=1000000):
        return self.client.post("/api/weg-d6/tasks/advance", json=dict(project_id=self.project.id,
            rounds=rounds, reason="Actual exclusive work during this scene interval."))

    def resolve(self, total=20, **changes):
        with patch.object(D6Roller, "values", return_value=roll(total)) as dice:
            response = self.client.post("/api/weg-d6/tasks/resolve", json=dict(project_id=self.project.id, **changes))
        return response, dice

    def group(self, **changes):
        return {**dict(actor_id="worker1", participant_ids=["worker1", "worker2", "worker3"], commander_id="commander",
            contact_confirmed=True, target_visible=True, same_range=True, participant_limit=3), **changes}

    def test_quote_readonly_stale_begin_atomic_and_actual_participants_saved(self):
        before = self.session.model_dump()
        response = self.client.post("/api/weg-d6/tasks/quote", json=request(self.session, **self.group()))
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.session.model_dump(), before)
        response = self.client.post("/api/weg-d6/tasks/begin", json=request(self.session, expected_updated_at=-1))
        self.assertEqual(response.status_code, 400, response.text)
        self.assertEqual(self.session.model_dump(), before)
        self.begin(**self.group())
        self.assertEqual(self.project.command["coordinated_ids"], ["worker1", "worker2"])
        self.assertEqual(self.project.quote.participants[0]["skills"]["space_transports_repair"], "2D+2")

    def test_prepared_work_has_one_shared_clock_and_cannot_resolve_early_or_twice(self):
        self.begin(steps=[dict(skill="space_transports_repair", difficulty=10, rounds=2, mode="prepared", reason="Actual focused work.")])
        before = self.session.model_dump()
        response, dice = self.resolve()
        self.assertEqual(response.status_code, 400, response.text)
        self.assertEqual(self.session.model_dump(), before)
        dice.assert_not_called()
        self.assertEqual(self.advance().status_code, 200)
        self.assertEqual((self.project.work_rounds, self.project.elapsed_rounds), (4, 4))
        for person in [self.session.character, *self.session.character.companions]:
            self.assertEqual(person.d6.force.elapsed_rounds, 4)
        response, dice = self.resolve()
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(dice.call_args.args, (7, 0, 0))
        self.assertEqual(self.project.status, "completed")
        before = self.session.model_dump()
        self.assertEqual(self.resolve()[0].status_code, 400)
        self.assertEqual(self.session.model_dump(), before)

    def test_rushed_task_halves_actual_pool_and_time(self):
        self.begin(steps=[dict(skill="space_transports_repair", difficulty=10, rounds=12, mode="rushed", reason="Actual hurried repair check.")])
        self.assertEqual(self.advance().status_code, 200)
        response, dice = self.resolve()
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(dice.call_args.args, (3, 0, 0))
        self.assertEqual((self.project.elapsed_rounds, self.session.character.d6.force.elapsed_rounds), (6, 6))

    def test_required_multi_roll_stages_and_fp_cover_only_one_actual_stage(self):
        self.begin(steps=[dict(skill="space_transports_repair", difficulty=10, rounds=2, reason="Align the cells."),
            dict(skill="space_transports_repair", difficulty=10, rounds=3, reason="Connect the replacement chamber.")])
        self.advance()
        response, dice = self.resolve(force_point=True)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(dice.call_args.args, (12, 0, 0))
        self.assertEqual((self.project.current_step, self.project.work_rounds, self.project.status), (1, 0, "pending"))
        self.advance()
        response, dice = self.resolve()
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(dice.call_args.args, (6, 0, 0))
        self.assertEqual((self.project.status, len(self.project.results), self.project.elapsed_rounds), ("completed", 2, 5))
        self.assertEqual(self.session.character.d6.force_points, 1)
        self.assertEqual(len(self.session.character.d6.rewards.expenditures), 1)

    def test_failure_spends_actual_cp_once_and_cannot_reroll_required_stage(self):
        self.begin()
        self.advance()
        response, _ = self.resolve(total=1, character_points=2)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual((self.project.status, self.session.character.d6.character_points), ("failed", 3))
        before = self.session.model_dump()
        self.assertEqual(self.resolve()[0].status_code, 400)
        self.assertEqual(self.session.model_dump(), before)

    def test_command_cp_cost_and_partial_group_benefit_are_saved_once(self):
        self.begin(**self.group(command_character_points=2))
        self.assertEqual((self.project.command["cp"], self.session.character.d6.character_points), (2, 3))
        self.assertEqual(self.project.command["bonus_dice"], 1)
        self.advance()
        response, dice = self.resolve()
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(dice.call_args.args, (4,))  # average of actual first 2 workers: (2+4)//2 +1D.
        self.assertEqual(self.session.character.d6.character_points, 3)
        self.assertEqual(self.project.results[-1]["actor_ids"], ["worker1", "worker2"])

    def test_participating_commander_both_actions_receive_source_penalty(self):
        self.begin(**self.group(actor_id="commander", participant_ids=["commander", "worker2"], commander_participates=True))
        self.assertEqual(self.project.command["roll"]["total"], 20)
        self.advance()
        response, dice = self.resolve()
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(dice.call_args.args, (5,))  # (6D-1D + 4D)//2 +1D.
        self.assertEqual(self.session.character.d6.round_state.actions_taken, 2)
        self.assertEqual(self.session.character.companions[1].d6.round_state.actions_taken, 1)

    def test_group_cannot_spend_someone_elses_points_on_aggregate(self):
        self.begin(**self.group())
        self.advance()
        for changes in ({"character_points": 1}, {"force_point": True}):
            before = self.session.model_dump()
            response, dice = self.resolve(**changes)
            self.assertEqual(response.status_code, 400, response.text)
            self.assertEqual(self.session.model_dump(), before)
            dice.assert_not_called()

    def test_one_round_command_fp_applies_only_to_that_commanders_own_contribution(self):
        self.begin(**self.group(actor_id="commander", participant_ids=["commander", "worker2"], commander_participates=True,
            command_force_point=True, steps=[dict(skill="space_transports_repair", difficulty=10, rounds=1, reason="Actual single-round work.")]))
        self.assertEqual(self.session.character.d6.force_points, 1)
        self.advance()
        response, dice = self.resolve()
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(dice.call_args.args, (8,))  # Only commander: (6D*2-1D + worker 4D)//2 +1D.
        self.assertEqual(self.session.character.d6.force_points, 1)
        self.assertEqual(self.session.character.companions[1].d6.force_points, 1)

    def test_zero_workers_coordinated_never_get_a_free_combined_roll(self):
        self.begin(total=1, **self.group())
        self.assertEqual(self.project.command["coordinated_count"], 0)
        self.advance()
        response, dice = self.resolve()
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.project.status, "failed")
        dice.assert_not_called()

    def test_invalid_personal_points_are_atomic_after_completed_work(self):
        self.begin()
        self.advance()
        for changes in ({"character_points": 1, "force_point": True}, {"character_points": 3}):
            before = self.session.model_dump()
            response, dice = self.resolve(**changes)
            self.assertEqual(response.status_code, 400, response.text)
            self.assertEqual(self.session.model_dump(), before)
            dice.assert_not_called()
        self.session.character.d6.force_points = 0
        before = self.session.model_dump()
        response, dice = self.resolve(force_point=True)
        self.assertEqual(response.status_code, 400, response.text)
        self.assertEqual(self.session.model_dump(), before)
        dice.assert_not_called()

    def test_incapacitated_actual_actor_cannot_spend_points_or_advance_task(self):
        self.begin()
        self.session.character.d6.wound = "incapacitated"
        before = self.session.model_dump()
        self.assertEqual(self.advance().status_code, 400)
        response, dice = self.resolve(force_point=True)
        self.assertEqual(response.status_code, 400, response.text)
        self.assertEqual(self.session.model_dump(), before)
        dice.assert_not_called()

    def test_external_scene_time_invalidates_exclusive_work_without_new_spend(self):
        self.begin()
        advance_scene(self.session, 1)
        before_rounds = self.session.character.d6.force.elapsed_rounds
        response, dice = self.resolve(force_point=True)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.project.status, "interrupted")
        self.assertEqual((self.session.character.d6.force.elapsed_rounds, self.session.character.d6.force_points), (before_rounds, 2))
        self.assertNotIn("commander", rules.busy_actor_ids(self.session))
        dice.assert_not_called()

    def test_cancel_preserves_actual_command_fp_expenditure(self):
        self.begin(**self.group(command_force_point=True))
        response = self.client.post("/api/weg-d6/tasks/cancel", json=dict(project_id=self.project.id,
            reason="Workshop access was withdrawn."))
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual((self.project.status, self.session.character.d6.force_points), ("cancelled", 1))
        self.assertEqual(len(self.session.character.d6.rewards.expenditures), 1)

    def test_pending_task_prevents_second_exclusive_commitment_and_cancel_releases_it(self):
        self.begin()
        self.assertIn("commander", rules.busy_actor_ids(self.session))
        before = self.session.model_dump()
        response = self.client.post("/api/weg-d6/tasks/begin", json=request(self.session))
        self.assertEqual(response.status_code, 400, response.text)
        self.assertEqual(self.session.model_dump(), before)
        response = self.client.post("/api/weg-d6/tasks/cancel", json=dict(project_id=self.project.id,
            reason="The apparatus is no longer available."))
        self.assertEqual(response.status_code, 200, response.text)
        self.assertNotIn("commander", rules.busy_actor_ids(self.session))

    def test_saved_command_paid_costs_and_partial_work_survive_reload(self):
        self.begin(**self.group(command_force_point=True))
        self.assertEqual(self.advance(rounds=3).status_code, 200)
        with tempfile.TemporaryDirectory() as directory:
            manager = SaveManager(directory)
            loaded = manager.load_session(manager.save_session(self.session, "task"))
        self.assertEqual(loaded.d6_tasks, self.session.d6_tasks)
        routes._ACTIVE_SESSION = self.session = loaded
        self.assertEqual((self.project.work_rounds, self.session.character.d6.force_points), (3, 1))
        self.advance()
        self.assertEqual(self.resolve()[0].status_code, 200)
        self.assertEqual(self.session.character.d6.force_points, 1)

    def test_pending_navigation_blocks_task_mutations_and_points_atomically(self):
        self.begin()
        journey = D6Journey(request=D6NavigationRequest(craft_id="actual-ship", origin="A", destination="B", reason="Actual route."),
            quote=D6NavigationQuote(difficulty=15, hours=1, rounds=720, has_navigation=True, multiplier=1),
            status="ten_point_ruling", remaining_rounds=720, roll={"total": 5})
        self.session.d6_navigation.journeys.append(journey)
        before = self.session.model_dump()
        self.assertEqual(self.advance().status_code, 400)
        self.assertEqual(self.resolve(force_point=True)[0].status_code, 400)
        self.assertEqual(self.session.model_dump(), before)


if __name__ == "__main__":
    unittest.main()
