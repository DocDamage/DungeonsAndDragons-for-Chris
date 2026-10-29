"""Book costs, qualification, delayed completion, and atomic saved CP spending."""
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from dungeonforge.api import routes
from dungeonforge.campaign.campaign_manager import CampaignManager
from dungeonforge.game.models import GameSession
from dungeonforge.game.saves import SaveManager
from dungeonforge.main import app
from dungeonforge.rules import weg_advancement as rules
from dungeonforge.rules.dice import RollResult
from dungeonforge.rules.weg_advancement_models import D6TrainingProject, D6TrainingRequest
from dungeonforge.rules.weg_d6 import D6Roller, WEGD6Rules
from dungeonforge.rules.weg_force_catalog import POWERS
from dungeonforge.rules.weg_models import D6Character


def master(**changes):
    values = dict(id="master", name="Jedi instructor", attributes={name: "5D" for name in rules.ATTRIBUTES},
        skills={"blaster": "8D", "first_aid": "6D", "medicine": "3D"}, skill_attributes={}, specialization_parents={},
        force_skills={"control": "8D", "sense": "8D", "alter": "8D"}, known_powers=list(POWERS))
    return rules.Trainer(**{**values, **changes})


class AdvancementRulesTests(unittest.TestCase):
    def setUp(self):
        self.state = D6Character(skills={"blaster": "4D+2"}, character_points=100, force_sensitive=True)

    def quote(self, kind="skill", key="blaster", teacher=None, **extra):
        return rules.quote(self.state, D6TrainingRequest(kind=kind, key=key, **extra), 1, teacher)

    def test_skill_cost_uses_whole_current_dice_and_carries_pips(self):
        q = self.quote(teacher=master())
        self.assertEqual((q.cp_cost, q.days, q.old_code, q.new_code), (4, 7, "4D+2", "5D"))
        self.assertEqual(self.state.skills["blaster"], "4D+2")

    def test_skill_time_bands_and_self_study_double(self):
        for old, trained, solo in [("4D", 3, 6), ("4D+1", 7, 14), ("7D", 7, 14), ("7D+1", 14, 28)]:
            with self.subTest(code=old):
                self.state.skills["blaster"] = old
                self.assertEqual(self.quote(teacher=master()).days, trained)
                self.assertEqual(self.quote().days, solo)

    def test_extra_cp_reduces_days_but_never_below_minimum(self):
        q = self.quote(teacher=master(), days_saved=6)
        self.assertEqual((q.cp_cost, q.days), (10, 1))
        with self.assertRaisesRegex(ValueError, "below 1"):
            self.quote(teacher=master(), days_saved=7)

    def test_teacher_must_match_new_rank_and_specializations_can_teach_basic(self):
        with self.assertRaisesRegex(ValueError, "instructor"):
            self.quote(teacher=master(skills={"blaster": "4D+2"}))
        q = self.quote(teacher=master(skills={"blaster_pistol": "5D"}, specialization_parents={"blaster_pistol": "blaster"}))
        self.assertEqual(q.teacher_name, "Jedi instructor")

    def test_new_skill_starts_attribute_plus_one_pip(self):
        q = self.quote(key="bargain")
        self.assertEqual((q.cp_cost, q.old_code, q.new_code), (3, "3D", "3D+1"))

    def test_custom_skill_needs_attribute_and_suitable_teacher(self):
        with self.assertRaises(ValueError):
            self.quote(key="archaeology", attribute="knowledge")
        q = self.quote(key="archaeology", attribute="knowledge", teacher=master(skills={"archaeology": "4D"}))
        self.assertEqual(q.attribute, "knowledge")

    def test_specialization_is_half_rounded_up_and_does_not_raise_parent(self):
        self.state.skills["blaster"] = "5D+2"
        q = self.quote(kind="specialization", key="blaster_pistol", parent_skill="blaster", teacher=master())
        self.assertEqual((q.cp_cost, q.new_code), (3, "6D"))
        project = D6TrainingProject(request=D6TrainingRequest(kind="specialization", key="blaster_pistol"), quote=q, started_adventure=1)
        rules.complete(self.state, project, 1, master())
        self.assertEqual(self.state.skills["blaster"], "5D+2")
        self.assertEqual(WEGD6Rules.skill_code(self.state, "blaster_pistol"), ("6D", "dexterity"))
        with self.assertRaises(ValueError):
            self.quote(kind="specialization", key="blaster", parent_skill="dodge")

    def test_medicine_requires_first_aid_starts_one_die_and_augments_prerequisite(self):
        with self.assertRaisesRegex(ValueError, "5D"):
            self.quote(kind="advanced", key="medicine", teacher=master())
        self.state.skills["first_aid"] = "5D"
        q = self.quote(kind="advanced", key="medicine", teacher=master())
        self.assertEqual((q.cp_cost, q.days, q.new_code), (2, 9, "1D"))
        project = D6TrainingProject(request=D6TrainingRequest(kind="advanced", key="medicine"), quote=q, started_adventure=1)
        rules.complete(self.state, project, 1, master())
        self.assertEqual(WEGD6Rules.pool(self.state, "medicine"), (1, 0))
        self.assertEqual(WEGD6Rules.pool(self.state, "first_aid"), (6, 0))
        self.assertEqual(rules.quote(self.state, D6TrainingRequest(kind="advanced", key="medicine"), 2).days, 18)

    def test_attribute_cost_time_no_reduction_and_species_cap_record(self):
        q = self.quote(kind="attribute", key="dexterity", teacher=master())
        self.assertEqual((q.cp_cost, q.days, q.species_maximum), (30, 70, "4D"))
        self.assertEqual(self.quote(kind="attribute", key="dexterity").days, 140)
        with self.assertRaises(ValueError):
            self.quote(kind="attribute", key="dexterity", days_saved=1)
        with self.assertRaisesRegex(ValueError, "species"):
            rules.quote(self.state, D6TrainingRequest(kind="attribute", key="dexterity"), 1, master(), "Wookiee")

    def test_attribute_success_raises_specializations_but_not_advanced_skills(self):
        self.state.skills.update(first_aid="5D", medicine="1D", medpac_use="6D")
        self.state.skill_attributes.update(first_aid="technical", medicine="technical", medpac_use="technical")
        self.state.specializations.append("medpac_use")
        self.state.specialization_parents["medpac_use"] = "first_aid"
        q = self.quote(kind="attribute", key="technical", teacher=master())
        project = D6TrainingProject(request=D6TrainingRequest(kind="attribute", key="technical"), quote=q, started_adventure=1)
        with patch("dungeonforge.rules.weg_d6.random.randint", return_value=4):
            rules.complete(self.state, project, 1, master())
        self.assertEqual(self.state.attributes["technical"], "3D+1")
        self.assertEqual(self.state.skills["first_aid"], "5D+1")
        self.assertEqual(self.state.skills["medpac_use"], "6D+1")
        self.assertEqual(self.state.skills["medicine"], "1D")

    def test_first_force_skill_requires_sensitive_student_and_three_die_teacher(self):
        with self.assertRaisesRegex(ValueError, "instructor"):
            self.quote(kind="force_skill", key="control")
        with self.assertRaisesRegex(ValueError, "3D"):
            self.quote(kind="force_skill", key="control", teacher=master(force_skills={"control": "2D+2"}))
        q = self.quote(kind="force_skill", key="control", teacher=master())
        self.assertEqual((q.cp_cost, q.days, q.new_code, q.power_slots), (20, 70, "1D", 3))
        self.state.force_sensitive = False
        with self.assertRaises(ValueError):
            self.quote(kind="force_skill", key="control", teacher=master())

    def test_initial_force_power_selections_require_skills_prerequisites_and_teacher_knowledge(self):
        with self.assertRaises(ValueError):
            self.quote(kind="force_skill", key="control", teacher=master(), powers=["emptiness"])
        q = self.quote(kind="force_skill", key="control", teacher=master(), powers=["hibernation_trance", "emptiness", "control_pain"])
        self.assertEqual(q.cp_cost, 20)
        with self.assertRaises(ValueError):
            self.quote(kind="force_skill", key="control", teacher=master(known_powers=[]), powers=["control_pain"])
        with self.assertRaises(ValueError):
            self.quote(kind="force_skill", key="control", teacher=master(), powers=["lightsaber_combat"])

    def test_taught_and_unaided_force_improvement_cost_and_minimums(self):
        self.state.force_skills["control"] = "3D+2"
        taught = self.quote(kind="force_skill", key="control", teacher=master())
        solo = self.quote(kind="force_skill", key="control")
        self.assertEqual((taught.cp_cost, taught.days, taught.new_code), (3, 7, "4D"))
        self.assertEqual((solo.cp_cost, solo.days), (6, 35))
        self.assertEqual(self.quote(kind="force_skill", key="control", days_saved=28).days, 7)
        with self.assertRaises(ValueError):
            self.quote(kind="force_skill", key="control", days_saved=29)

    def test_free_taught_power_and_independent_research_prices(self):
        self.state.force_skills["control"] = "2D"
        taught = self.quote(kind="force_skill", key="control", teacher=master(), powers=["control_pain"])
        researched = self.quote(kind="force_skill", key="control", teacher=master(known_powers=[]), powers=["control_pain"])
        solo = self.quote(kind="force_skill", key="control", powers=["control_pain"])
        self.assertEqual((taught.cp_cost, taught.days), (2, 7))
        self.assertEqual((researched.cp_cost, researched.days), (7, 14))
        self.assertEqual((solo.cp_cost, solo.days), (14, 42))

    def test_standalone_power_does_not_advance_force_rank(self):
        self.state.force_skills["control"] = "2D"
        taught = self.quote(kind="force_power", key="control_pain", teacher=master(), gm_study_days=4)
        solo = self.quote(kind="force_power", key="control_pain", gm_study_days=10)
        self.assertEqual((taught.cp_cost, taught.days), (5, 4))
        self.assertEqual((solo.cp_cost, solo.days), (10, 10))

    def test_force_master_who_is_studying_cannot_take_pupils(self):
        with self.assertRaisesRegex(ValueError, "cannot take a pupil"):
            self.quote(kind="force_skill", key="control", teacher=master(studying_with_master=True))

    def test_bundled_multiskill_power_requires_qualified_teacher_in_every_required_skill(self):
        self.state.force_skills.update(control="2D", sense="1D")
        with self.assertRaisesRegex(ValueError, "3D"):
            self.quote(kind="force_skill", key="control", teacher=master(force_skills={"control": "4D", "sense": "1D"}), powers=["lightsaber_combat"])

    def test_advancement_cannot_overflow_the_sheet_die_code_limit(self):
        self.state.skills["blaster"] = "50D+2"
        with self.assertRaisesRegex(ValueError, "50D"):
            self.quote()

    def test_move_respects_species_maximum_and_sensitivity_is_not_a_force_skill(self):
        q = self.quote(kind="move")
        self.assertEqual((q.cp_cost, q.days, q.new_code), (10, 0, "11"))
        self.state.move = 12
        with self.assertRaisesRegex(ValueError, "maximum"):
            self.quote(kind="move")
        self.state.force_sensitive = False
        q = self.quote(kind="sensitivity")
        self.assertEqual((q.cp_cost, q.days), (20, 0))


class AdvancementAPITests(unittest.TestCase):
    def setUp(self):
        preset = CampaignManager.load_campaign("star_wars_d6")
        self.session = GameSession(edition="weg_d6", character=preset.starter_character)
        self.session.character.d6.character_points = 200
        self.session.character.d6.armor_physical = "0D"
        active = patch.object(routes, "_ACTIVE_SESSION", self.session)
        active.start()
        self.addCleanup(active.stop)
        dice = patch("dungeonforge.rules.weg_d6.random.randint", return_value=4)
        dice.start()
        self.addCleanup(dice.stop)
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def post(self, endpoint, **payload):
        response = self.client.post(f"/api/weg-d6/advancement/{endpoint}", json=payload)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def teacher(self, **changes):
        record = dict(name="Master instructor", skills={"blaster": "8D", "first_aid": "6D", "medicine": "2D"},
            attributes={name: "6D" for name in rules.ATTRIBUTES}, force_skills={"control": "8D", "sense": "8D", "alter": "8D"}, known_powers=list(POWERS))
        self.post("instructor", **{**record, **changes})
        return self.session.d6_advancement.instructors[-1].id

    def test_quote_is_readonly_and_invalid_spending_is_atomic(self):
        before = self.session.model_dump()
        q = self.post("quote", kind="skill", key="blaster")["quote"]
        self.assertEqual(q["cp_cost"], 5)
        self.assertEqual(before, self.session.model_dump())
        self.session.character.d6.character_points = 1
        before = self.session.model_dump()
        response = self.client.post("/api/weg-d6/advancement/start", json={"kind": "skill", "key": "blaster"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(before, self.session.model_dump())

    def test_paid_course_delays_rank_until_full_study_and_preserves_on_save(self):
        teacher = self.teacher()
        self.post("start", kind="skill", key="blaster", teacher_id=teacher)
        self.assertEqual(self.session.character.d6.character_points, 195)
        self.assertEqual(self.session.character.d6.skills["blaster"], "5D+2")
        self.post("study", days=3)
        self.assertEqual(self.session.character.d6.skills["blaster"], "5D+2")
        with tempfile.TemporaryDirectory() as directory:
            manager = SaveManager(directory)
            loaded = manager.load_session(manager.save_session(self.session, "training"))
        self.assertEqual(loaded.character.d6.advancement.project.days_completed, 3)
        self.assertEqual(loaded.d6_advancement.instructors[0].id, teacher)
        self.post("study", days=4)
        self.assertEqual(self.session.character.d6.skills["blaster"], "6D")
        self.assertIsNone(self.session.character.d6.advancement.project)
        self.assertEqual(self.session.character.d6.character_points, 195)

    def test_skill_one_pip_limit_renews_only_after_explicit_boundary(self):
        teacher = self.teacher()
        self.post("start", kind="skill", key="blaster", teacher_id=teacher, days_saved=6)
        self.post("study", days=1)
        self.assertEqual(self.client.post("/api/weg-d6/advancement/start", json={"kind": "skill", "key": "blaster", "teacher_id": teacher}).status_code, 400)
        points = self.session.character.d6.character_points
        self.post("adventure", label="After the rescue")
        self.assertEqual(self.session.character.d6.character_points, points)
        self.post("start", kind="skill", key="blaster", teacher_id=teacher)

    def test_ordinary_rest_passes_time_but_never_completes_study(self):
        self.post("start", kind="skill", key="search")
        self.client.post("/api/weg-d6/recover", json={"method": "rest", "minutes": 1440})
        self.assertEqual(self.session.character.d6.advancement.project.days_completed, 0)
        self.assertEqual(self.session.character.d6.skills["search"], "4D")

    def test_attribute_failure_suspends_points_then_releases_once_after_next_adventure(self):
        self.post("start", kind="attribute", key="dexterity")
        student_roll = RollResult(expression="3D+2", dice_count=3, die_type=6, total=25, system="weg_d6")
        maximum_roll = RollResult(expression="4D", dice_count=4, die_type=6, total=10, system="weg_d6")
        with patch.object(D6Roller, "roll", side_effect=[student_roll, maximum_roll]):
            self.post("study", days=140)
        state = self.session.character.d6
        self.assertEqual(state.attributes["dexterity"], "3D+2")
        self.assertEqual(state.character_points, 170)
        project = state.advancement.history[-1]
        self.assertEqual(project.status, "suspended")
        self.assertEqual(self.client.post("/api/weg-d6/advancement/release-suspended", json={"project_id": project.id}).status_code, 400)
        self.post("adventure", label="Return to the Rebel base")
        self.post("release-suspended", project_id=project.id)
        self.assertEqual(self.session.character.d6.character_points, 200)
        self.assertEqual(self.client.post("/api/weg-d6/advancement/release-suspended", json={"project_id": project.id}).status_code, 400)

    def test_initial_force_training_grants_only_selected_powers_at_completion(self):
        teacher = self.teacher()
        self.post("start", kind="force_skill", key="control", teacher_id=teacher, powers=["control_pain", "hibernation_trance", "emptiness"], days_saved=69)
        self.assertEqual(self.session.character.d6.force_skills["control"], "0D")
        self.assertFalse(self.session.character.d6.force.known_powers)
        self.assertEqual(self.session.character.d6.character_points, 111)
        self.post("study", days=1)
        self.assertEqual(self.session.character.d6.force_skills["control"], "1D")
        self.assertEqual(set(self.session.character.d6.force.known_powers), {"control_pain", "hibernation_trance", "emptiness"})
        response = self.client.post("/api/weg-d6/force/begin", json={"power_id": "control_pain", "base_difficulties": {"control": 1}})
        self.assertEqual(response.status_code, 200, response.text)

    def test_deferred_included_power_choice_is_bound_to_course_instructor_and_prerequisites(self):
        teacher = self.teacher()
        self.post("start", kind="force_skill", key="control", teacher_id=teacher, days_saved=69)
        self.post("study", days=1)
        grant = self.session.character.d6.advancement.power_grants[0]
        self.assertEqual(grant.remaining, 3)
        self.assertEqual(self.client.post("/api/weg-d6/advancement/claim-power", json={"grant_id": grant.id, "power_id": "emptiness"}).status_code, 400)
        points = self.session.character.d6.character_points
        self.post("claim-power", grant_id=grant.id, power_id="hibernation_trance")
        self.post("claim-power", grant_id=grant.id, power_id="emptiness")
        self.assertEqual(self.session.character.d6.character_points, points)
        self.assertEqual(self.session.character.d6.advancement.power_grants[0].remaining, 1)

    def test_force_pupil_capacity_and_studying_master_restriction(self):
        teacher = self.teacher()
        self.post("start", kind="force_skill", key="control", teacher_id=teacher)
        companion = self.session.character.companions[0]
        companion.d6.force_sensitive = True
        companion.d6.character_points = 30
        response = self.client.post("/api/weg-d6/advancement/start", json={"actor_id": companion.id, "kind": "force_skill", "key": "sense", "teacher_id": teacher})
        self.assertEqual(response.status_code, 400)
        # A pupil cannot teach, even if a GM recorded adequate Force ranks.
        self.session.character.d6.force_skills["sense"] = "4D"
        response = self.client.post("/api/weg-d6/advancement/start", json={"actor_id": companion.id, "kind": "force_skill", "key": "sense", "teacher_id": self.session.character.id})
        self.assertEqual(response.status_code, 400)

    def test_teaching_dark_side_student_awards_teacher_once_per_course(self):
        teacher = self.teacher()
        self.session.character.d6.dark_side_points = 1
        self.post("start", kind="force_skill", key="control", teacher_id=teacher)
        self.post("study", days=1)
        self.post("study", days=1)
        self.assertEqual(self.session.d6_advancement.instructors[0].dark_side_points, 1)
        self.assertEqual(self.session.character.d6.dark_side_points, 1)

    def test_parallel_study_advances_scene_time_once(self):
        teacher = self.teacher(full_time=True)
        companion = self.session.character.companions[0]
        companion.d6.force_sensitive = True
        companion.d6.character_points = 100
        self.post("start", kind="force_skill", key="control", teacher_id=teacher)
        self.post("start", actor_id=companion.id, kind="force_skill", key="sense", teacher_id=teacher)
        self.post("study", actor_ids=[self.session.character.id, companion.id], days=2)
        self.assertEqual(self.session.character.d6.force.elapsed_rounds, 34560)
        self.assertEqual(self.session.character.companions[0].d6.force.elapsed_rounds, 34560)
        self.assertEqual(self.session.character.companions[0].d6.advancement.project.days_completed, 2)

    def test_instructor_becoming_unqualified_rejects_without_spending_or_time(self):
        teacher = self.teacher()
        self.post("start", kind="force_skill", key="control", teacher_id=teacher)
        self.session.d6_advancement.instructors[0].force_skills["control"] = "2D"
        before = self.session.model_dump()
        response = self.client.post("/api/weg-d6/advancement/study", json={"days": 1})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(before, self.session.model_dump())

    def test_sensitivity_and_move_immediate_purchases_have_native_costs(self):
        self.session.character.d6.force_sensitive = False
        points = self.session.character.d6.force_points
        self.post("start", kind="sensitivity")
        self.assertTrue(self.session.character.d6.force_sensitive)
        self.assertEqual(self.session.character.d6.character_points, 180)
        self.assertEqual(self.session.character.d6.force_points, points + 1)
        self.assertFalse(self.session.character.d6.force.known_powers)
        self.post("start", kind="move")
        self.assertEqual(self.session.character.d6.move, 11)
        self.assertEqual(self.session.character.d6.character_points, 170)
        char = self.session.character.model_dump()
        char["d6"]["force_sensitive"] = False
        self.assertEqual(self.client.post("/api/character", json=char).status_code, 422)

    def test_awards_are_explicit_and_recorded_without_resetting_skill_eligibility(self):
        self.post("award", points=7, reason="Protected the refugees")
        self.assertEqual(self.session.character.d6.character_points, 207)
        self.assertEqual(self.session.d6_advancement.adventure, 1)
        self.assertIn("Protected the refugees", self.session.history[-1].rule_result.summary)

    def test_training_forbidden_in_combat_and_cancel_never_refunds(self):
        self.client.post("/api/combat/start", json={})
        before = self.session.model_dump()
        self.assertEqual(self.client.post("/api/weg-d6/advancement/start", json={"kind": "skill", "key": "blaster"}).status_code, 400)
        self.assertEqual(before, self.session.model_dump())
        self.client.post("/api/combat/end")
        self.post("start", kind="skill", key="blaster")
        self.post("cancel")
        self.assertEqual(self.session.character.d6.character_points, 195)
        self.assertEqual(self.session.character.d6.skills["blaster"], "5D+2")

    def test_old_saves_load_default_training_state_and_gm_edits_preserve_project(self):
        self.post("start", kind="skill", key="blaster")
        before = self.session.character.d6.advancement.model_dump()
        char = self.session.character.model_dump()
        char["d6"].pop("advancement")
        response = self.client.post("/api/character", json=char)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.session.character.d6.advancement.model_dump(), before)
        char["d6"]["skills"]["blaster"] = "9D"
        self.assertEqual(self.client.post("/api/character", json=char).status_code, 422)
        data = self.session.model_dump()
        data.pop("d6_advancement")
        data["character"]["d6"].pop("advancement")
        loaded = GameSession.model_validate(data)
        self.assertEqual(loaded.d6_advancement.adventure, 1)
        self.assertIsNone(loaded.character.d6.advancement.project)

    def test_repeated_start_excess_days_and_duplicate_students_are_atomic(self):
        self.post("start", kind="skill", key="blaster")
        for endpoint, body in [("start", {"kind": "skill", "key": "dodge"}), ("study", {"days": 15}), ("study", {"actor_ids": [self.session.character.id, self.session.character.id], "days": 1})]:
            before = self.session.model_dump()
            response = self.client.post(f"/api/weg-d6/advancement/{endpoint}", json=body)
            self.assertEqual(response.status_code, 400)
            self.assertEqual(before, self.session.model_dump())

    def test_instructor_must_still_know_a_promised_free_bundled_power(self):
        teacher = self.teacher()
        self.session.character.d6.force_skills["control"] = "2D"
        self.post("start", kind="force_skill", key="control", teacher_id=teacher, powers=["control_pain"])
        self.session.d6_advancement.instructors[0].known_powers = []
        before = self.session.model_dump()
        response = self.client.post("/api/weg-d6/advancement/study", json={"days": 7})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(before, self.session.model_dump())

    def test_standalone_power_price_cannot_survive_loss_of_teacher_knowledge(self):
        teacher = self.teacher()
        self.session.character.d6.force_skills["control"] = "2D"
        self.post("start", kind="force_power", key="control_pain", teacher_id=teacher, gm_study_days=3)
        self.session.d6_advancement.instructors[0].known_powers = []
        before = self.session.model_dump()
        self.assertEqual(self.client.post("/api/weg-d6/advancement/study", json={"days": 3}).status_code, 400)
        self.assertEqual(before, self.session.model_dump())

    def test_live_party_teacher_receives_dark_side_point_and_keeps_real_ratings(self):
        teacher = self.session.character.companions[0]
        teacher.d6.force_sensitive = True
        teacher.d6.force_skills["control"] = "3D"
        teacher.d6.force.known_powers = ["control_pain"]
        self.session.character.d6.dark_side_points = 1
        self.post("start", kind="force_skill", key="control", teacher_id=teacher.id, powers=["control_pain"])
        self.post("study", days=1)
        self.assertEqual(self.session.character.companions[0].d6.dark_side_points, 1)
        self.assertEqual(self.session.character.companions[0].d6.force_skills["control"], "3D")

    def test_loaded_force_course_completes_without_charging_again(self):
        teacher = self.teacher()
        self.post("start", kind="force_skill", key="control", teacher_id=teacher, days_saved=68, powers=["control_pain"])
        self.post("study", days=1)
        with tempfile.TemporaryDirectory() as directory:
            manager = SaveManager(directory)
            loaded = manager.load_session(manager.save_session(self.session, "force-study"))
        points = loaded.character.d6.character_points
        with patch.object(routes, "_ACTIVE_SESSION", loaded):
            response = self.client.post("/api/weg-d6/advancement/study", json={"days": 1})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(loaded.character.d6.force_skills["control"], "1D")
        self.assertIn("control_pain", loaded.character.d6.force.known_powers)
        self.assertEqual(loaded.character.d6.character_points, points)
        self.assertEqual(loaded.character.d6.advancement.power_grants[0].remaining, 2)

    def test_chronicle_records_paid_study_and_uses_no_unearned_rank(self):
        self.post("start", kind="skill", key="blaster")
        self.post("study", days=2)
        with tempfile.TemporaryDirectory() as directory:
            text = SaveManager(directory).export_markdown_chronicle(self.session)
        self.assertIn("5 CP paid; 2/14 intensive days", text)
        self.assertIn("Advancement window", text)
        self.assertEqual(self.session.character.d6.skills["blaster"], "5D+2")


if __name__ == "__main__":
    unittest.main()
