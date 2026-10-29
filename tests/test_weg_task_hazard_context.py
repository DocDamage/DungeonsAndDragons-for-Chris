import json
from pathlib import Path
import tempfile
import unittest

from dungeonforge.context.pipeline import ContextPipeline
from dungeonforge.context.story_cards import StoryCardManager
from dungeonforge.game.models import GameSession
from dungeonforge.game.saves import SaveManager
from dungeonforge.rules.base import Character, Companion
from dungeonforge.rules.weg_hazard_models import D6Drowning, D6HazardState
from dungeonforge.rules.weg_models import D6Character, D6RoundState
from dungeonforge.rules.weg_tasks_models import D6TaskProject, D6TaskQuote, D6TaskRequest, D6TaskStep, D6TaskStepQuote


class TaskHazardContextTests(unittest.TestCase):
    def setUp(self):
        hazards = D6HazardState(
            fatigued=True, exhausted=True, fatigue_failures=3, exertion_rounds=120, rest_rounds=40, swim_round=7,
            drowning=D6Drowning(round=2, initial_difficulty=10, rescue_difficulty=11, attempted_round=2, declared_round=2),
            history=[
                {"operation": "Drowning round", "round": 2, "dead": False, "reason": "The current pulls the swimmer under.",
                 "roll": {"expression": "2d6", "total": 8, "breakdown": "plain death check 3+5=8"}},
                {"operation": "Drowning action", "success": False, "reason": "Actual failed self-rescue.",
                 "summary": "The Swimming self-rescue failed; drowning continues.", "roll": {"total": 3, "breakdown": "saved swimming roll"},
                 "details": {"self_rescue": False}},
            ],
        )
        hero = Character(id="hero", name="Ariadne", edition="weg_d6", d6=D6Character(
            skills={"search": "4D"}, character_points=3, hazards=hazards,
            round_state=D6RoundState(declared_actions=2, actions_taken=1)))
        hero.companions = [
            Companion(id="tech", name="Blaise", d6=D6Character(skills={"search": "4D"},
                      hazards=D6HazardState(fatigued=True, willpower_driven=True, exertion_rounds=60))),
            Companion(id="leader", name="Cara", d6=D6Character(skills={"command": "6D"}, force_points=0)),
        ]
        self.session = GameSession(id="task_hazard_context", edition="weg_d6", character=hero,
                                   campaign_name="Rebel work", title="Unfinished crossing", source_folders=[], d6_hazard_round=7)
        step = D6TaskStep(skill="search", difficulty=15, rounds=12, reason="Search the actual terminal indexes.")
        req = D6TaskRequest(actor_id="hero", label="Locate the evacuation manifest", reason="The actual linked terminals are available.",
            exclusive=True, steps=[step], participant_ids=["tech", "hero"], commander_id="leader", contact_confirmed=True,
            target_visible=True, same_range=True, participant_limit=2, command_force_point=True)
        quote = D6TaskQuote(steps=[D6TaskStepQuote(skill="search", mode="normal", difficulty=15, base_rounds=12,
            preparation_rounds=0, work_rounds=12, total_rounds=12)], combined=True, average_skill=4,
            command_band="easy", command_difficulty=10, declared_count=2, table_count=2)
        self.project = D6TaskProject(id="task_pending", label=req.label, reason=req.reason, request=req, quote=quote,
            work_rounds=5, elapsed_rounds=5, actor_clocks={"hero": 15, "tech": 15, "leader": 15},
            command={"actor_id": "leader", "name": "Cara", "difficulty": 10, "band": "easy", "success": True,
                "declared_count": 2, "table_count": 2, "coordinated_count": 2, "coordinated_ids": ["tech", "hero"],
                "average_skill": 4, "bonus_dice": 1, "cp": 0, "fp": True, "participates": False,
                "roll": {"total": 12, "breakdown": "saved Command roll 12"}},
            declarations=[{"actor_id": "tech", "name": "Blaise", "role": "worker", "declared_actions": 1,
                           "exclusive": True, "skills": {"search": "4D"}},
                          {"actor_id": "leader", "name": "Cara", "role": "commander", "declared_actions": 1,
                           "skill_code": "6D", "cp": 0, "fp": True}],
            work_log=[{"step": 0, "rounds": 5, "reason": "Five focused rounds, with no other actions."}])
        self.session.d6_tasks.projects.append(self.project)

    def export(self):
        with tempfile.TemporaryDirectory() as directory:
            return SaveManager(directory).export_markdown_chronicle(self.session)

    def test_native_prompt_has_actual_rest_debt_push_and_drowning_actions(self):
        before = self.session.model_dump()
        summary = ContextPipeline.native_travel_summary(self.session)
        messages = ContextPipeline.assemble(character=self.session.character, memory=self.session.memory,
            story_card_manager=StoryCardManager(), authors_note=self.session.authors_note, history=[],
            current_input="Describe our unfinished work", current_mode="story", vehicle_summary=summary)
        text = messages[1]["content"]
        for fact in ("Environmental hazards: fatigued True; exhausted True; Willpower-driven False", "fatigue failures 3",
                     "exertion 120 rounds; actual rest 40 rounds", "rest threshold 240 rounds; remaining rest debt 200 rounds",
                     "drowning active True, round 2", "self-rescue attempted round 2", "actions declared round 2; current actions 1/2",
                     "Saved shared hazard round: 7", "Hazards — Blaise", "Willpower-driven True", "rest threshold 120 rounds",
                     "Narration cannot erase exhaustion or rest debt", "ordinary time and narration do not"):
            self.assertIn(fact, text)
        self.assertEqual(before, self.session.model_dump())

    def test_tasks_without_craft_show_exclusive_priority_stages_and_once_paid_command(self):
        before = self.session.model_dump()
        text = ContextPipeline.native_travel_summary(self.session)
        for fact in ("status pending; combined group", "current focused work 5 rounds", "total recorded work 5 rounds",
                     "paid points 0 CP / 1 FP", "Declared worker priority: Blaise, Ariadne", "exclusive work True",
                     "Pending exclusive task actors: Blaise, Ariadne, Cara", "still needs 7 focused rounds",
                     "Required task stage 1: search; difficulty 15; mode normal", "Saved Command result: Cara; roll 12 vs 10",
                     "coordinated 2/2; workers Blaise, Ariadne; bonus +1D; paid once 0 CP / 1 FP", "saved Command roll 12",
                     "Recorded focused work: stage 1; 5 rounds", "Saved exclusive worker clock checkpoints: Ariadne: 15"):
            self.assertIn(fact, text)
        self.assertNotIn("NATIVE WEG CRAFT", text)
        self.assertIn("Generic task success does not install equipment, repair craft, grant training", text)
        self.assertEqual(before, self.session.model_dump())

    def test_export_retains_task_and_hazard_rolls_without_narration_guidance(self):
        before = self.session.model_dump()
        text = self.export()
        for fact in ("Locate the evacuation manifest; status pending", "paid once 0 CP / 1 FP", "saved Command roll 12",
                     "Saved drowning death check — Ariadne: round 2; plain 2d6 total 8; died False",
                     "plain death check 3+5=8", "Saved hazard action — Ariadne: Drowning action; success False; roll 3",
                     "The Swimming self-rescue failed", "saved swimming roll", "Saved hazard consequences — Ariadne: {'self_rescue': False}",
                     "remaining rest debt 200 rounds"):
            self.assertIn(fact, text)
        self.assertNotIn("Living drowning actors need", text)
        self.assertNotIn("Narration cannot", text)
        self.assertEqual(before, self.session.model_dump())

    def test_terminal_task_states_and_actual_stage_results_stay_distinct(self):
        for status in ("completed", "failed", "interrupted", "cancelled"):
            with self.subTest(status=status):
                self.project.status = status
                self.project.results = [] if status in {"interrupted", "cancelled"} else [{
                    "step": 0, "skill": "search", "success": status == "completed", "mode": "normal", "difficulty": 15,
                    "rounds": 12, "actor_ids": ["tech", "hero"], "pool_dice": 5, "pool_pips": 0,
                    "cp": 0, "fp": False, "roll": {"total": 18 if status == "completed" else 4, "breakdown": "saved group stage roll"}}]
                text = self.export()
                self.assertIn(f"status {status}; combined group", text)
                self.assertIn("paid points 0 CP / 1 FP", text)
                self.assertNotIn("Pending exclusive task actors", text)
                if self.project.results:
                    outcome = "success" if status == "completed" else "failed"
                    self.assertIn(f"Saved task result: stage 1; search; {outcome}", text)
                    self.assertIn("pool 5D+0", text)
                    self.assertIn("saved group stage roll", text)
                self.assertTrue(self.session.character.d6.hazards.exhausted)
                self.assertIsNotNone(self.session.character.d6.hazards.drowning)

    def test_required_preparation_and_saved_fractional_rushing_ruling_are_exported(self):
        self.project.request.steps = [D6TaskStep(skill="search", difficulty=10, rounds=6, mode="prepared", reason="Prepare the indexes."),
            D6TaskStep(skill="search", difficulty=12, rounds=5, mode="rushed", reason="Search the reduced index.", rush_rounding="up", rounding_reason="GM permits whole-round rounding up.")]
        self.project.quote.steps = [D6TaskStepQuote(skill="search", difficulty=10, mode="prepared", base_rounds=6,
            preparation_rounds=6, work_rounds=6, total_rounds=12), D6TaskStepQuote(skill="search", difficulty=12, mode="rushed",
            base_rounds=5, preparation_rounds=0, work_rounds=3, total_rounds=3)]
        self.project.request.participant_ids = []
        self.project.request.commander_id = None
        self.project.request.command_force_point = False
        self.project.quote.combined = False
        self.project.command = None
        self.project.declarations = []
        text = self.export()
        self.assertIn("current required stage 1/2", text)
        self.assertIn("mode prepared; base 6, preparation 6, work 6, total 12 rounds", text)
        self.assertIn("Required task stage 2: search; difficulty 12; mode rushed", text)
        self.assertIn("Saved rushing rounding: up; GM permits whole-round rounding up.", text)
        self.assertIn("paid points 0 CP / 0 FP", text)

    def test_recorded_drowning_death_stays_dead_and_is_not_a_pending_rescue(self):
        state = self.session.character.d6
        state.wound = "dead"
        state.hazards.drowning.round = 4
        state.hazards.history.append({"operation": "Drowning round", "round": 4, "dead": True,
            "roll": {"expression": "2d6", "total": 2}, "reason": "The actual death check failed."})
        text = self.export()
        self.assertIn("drowning active False, round 4", text)
        self.assertIn("round 4; plain 2d6 total 2; died True", text)
        self.assertEqual(state.wound, "dead")
        self.assertIsNotNone(state.hazards.drowning)

    def test_save_load_preserves_all_pending_task_hazard_and_point_records(self):
        with tempfile.TemporaryDirectory() as directory:
            manager = SaveManager(directory)
            loaded = manager.load_session(manager.save_session(self.session, "task_hazard"))
            self.assertEqual(loaded.d6_tasks.model_dump(), self.session.d6_tasks.model_dump())
            self.assertEqual(loaded.d6_hazard_round, 7)
            for before, after in zip([self.session.character, *self.session.character.companions], [loaded.character, *loaded.character.companions]):
                self.assertEqual(before.d6.hazards.model_dump(), after.d6.hazards.model_dump())
                self.assertEqual((before.d6.character_points, before.d6.force_points), (after.d6.character_points, after.d6.force_points))
            self.assertEqual(ContextPipeline.native_travel_summary(loaded), ContextPipeline.native_travel_summary(self.session))

    def test_legacy_saves_gain_empty_task_and_hazard_defaults(self):
        data = self.session.model_dump()
        data.pop("d6_tasks")
        data.pop("d6_hazard_round")
        for person in [data["character"], *data["character"]["companions"]]:
            person["d6"].pop("hazards")
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "legacy.json").write_text(json.dumps(data), encoding="utf-8")
            loaded = SaveManager(directory).load_session("legacy")
        self.assertEqual(loaded.d6_tasks.projects, [])
        self.assertEqual(loaded.d6_hazard_round, 0)
        self.assertEqual(loaded.character.d6.hazards, D6HazardState())
        self.assertEqual(loaded.character.d6.character_points, 3)
        self.assertEqual(loaded.character.companions[-1].d6.force_points, 0)


if __name__ == "__main__":
    unittest.main()
