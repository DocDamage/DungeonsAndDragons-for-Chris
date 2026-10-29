"""Visual-source 1992 p.67 organic care and shared-scene lifecycle edges."""
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from dungeonforge.api import routes
from dungeonforge.campaign.campaign_manager import CampaignManager
from dungeonforge.game.models import GameSession
from dungeonforge.game.saves import SaveManager
from dungeonforge.game.weg_force import advance_scene
from dungeonforge.game.weg_task_guards import require_available
from dungeonforge.main import app
from dungeonforge.rules.dice import RollResult
from dungeonforge.rules.weg_d6 import D6Roller
from dungeonforge.rules import weg_medical as rules
from dungeonforge.rules.weg_equipment import make_item


def roll(total):
    return RollResult(expression="Controlled medical roll", dice_count=3, die_type=6, total=total,
        system="weg_d6", breakdown=f"Controlled total {total}")


class MedicalTests(unittest.TestCase):
    def setUp(self):
        preset = CampaignManager.load_campaign("star_wars_d6")
        self.session = GameSession(edition="weg_d6", character=preset.starter_character)
        self.patient_id = self.session.character.id
        self.doctor_id = self.session.character.companions[0].id
        self.session.character.d6.wound = "wounded"
        self.session.character.companions[0].d6.skills.update(first_aid="5D", medicine="3D")
        active = patch.object(routes, "_ACTIVE_SESSION", self.session)
        active.start()
        self.addCleanup(active.stop)
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    @property
    def patient(self):
        return self.session.character.d6

    @property
    def doctor(self):
        return self.session.character.companions[0].d6

    def post(self, endpoint, **changes):
        return self.client.post(f"/api/weg-d6/medical/{endpoint}", json={"patient_id": self.patient_id,
            "reason": "Actual GM medical facts, facility and care workload.", "expected_updated_at": self.session.updated_at, **changes})

    def bacta(self, total=5, duration=2, **changes):
        with patch.object(D6Roller, "values", return_value=roll(total)), patch("dungeonforge.api.weg_medical_routes.DiceRoller.roll", return_value=roll(duration)):
            return self.post("bacta-start", operator_id=self.doctor_id, facility="Actual Alliance clinic tank7",
                tank_confirmed=True, permission_confirmed=True, setup_minutes=1, **changes)

    def natural(self, **changes):
        response = self.post("natural-start", **changes)
        self.assertEqual(response.status_code, 200, response.text)
        return self.session.d6_medical.projects[-1]

    def test_catalog_is_readonly_and_correctly_reports_dice_not_ocr_fixed_times(self):
        before = self.session.model_dump()
        data = self.client.get("/api/weg-d6/medical/catalog").json()
        self.assertEqual([(entry["duration_dice"], entry["unit"]) for entry in data["bacta"]], [("1d6", "hours"), ("4d6", "hours"), ("1d6", "days")])
        self.assertEqual([entry["days"] for entry in data["natural"]], [3, 14, 30])
        self.assertEqual(self.session.model_dump(), before)

    def test_actual_tank_permission_and_current_revision_are_required_atomically(self):
        for changes in ({"tank_confirmed": False}, {"permission_confirmed": False}, {"facility": " "}, {"expected_updated_at": self.session.updated_at - 1}):
            before = self.session.model_dump()
            response = self.post("bacta-start", operator_id=self.doctor_id, setup_minutes=1,
                **({"facility": "Actual tank", "tank_confirmed": True, "permission_confirmed": True} | changes))
            self.assertEqual(response.status_code, 400, response.text)
            self.assertEqual(self.session.model_dump(), before)

    def test_successful_trained_bacta_saves_actual_roll_duration_and_shared_setup_time(self):
        credits = self.patient.credits
        response = self.bacta(duration=3, character_points=1)
        self.assertEqual(response.status_code, 200, response.text)
        project = self.session.d6_medical.projects[-1]
        self.assertEqual((project.skill, project.difficulty, project.required_rounds, project.remaining_rounds), ("medicine", 5, 2160, 2148))
        self.assertEqual(self.patient.wound, "wounded")
        self.assertEqual((self.patient.force.elapsed_rounds, self.doctor.force.elapsed_rounds), (12, 12))
        self.assertEqual(self.doctor.character_points, 4)
        self.assertEqual(self.patient.credits, credits)
        self.assertEqual(project.facility, "Actual Alliance clinic tank7")
        self.assertEqual(rules.protected_actor_ids(self.session), {self.patient_id})

    def test_incapacitated_and_mortal_treatment_use_plain_source_dice_and_full_healing(self):
        for wound, expression, scale in (("incapacitated", "4d6", 720), ("mortally_wounded", "1d6", 17280)):
            with self.subTest(wound=wound):
                self.session.d6_medical.projects.clear()
                self.patient.wound = wound
                with patch.object(D6Roller, "values", return_value=roll(5)), patch("dungeonforge.api.weg_medical_routes.DiceRoller.roll", return_value=roll(4)) as ordinary:
                    response = self.post("bacta-start", operator_id=self.doctor_id, setup_minutes=1,
                        facility="Actual working hospital tank", tank_confirmed=True, permission_confirmed=True)
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(ordinary.call_args.args, (expression,))
                project = self.session.d6_medical.projects[-1]
                self.assertEqual(project.required_rounds, 4 * scale)
                response = self.post("advance", rounds=project.remaining_rounds)
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual((self.patient.wound, self.session.d6_medical.projects[-1].status), ("healthy", "completed"))

    def test_untrained_heroic_failure_increases_two_wound_levels_and_consumes_real_time(self):
        self.doctor.skills.pop("medicine")
        response = self.bacta(total=30)
        self.assertEqual(response.status_code, 200, response.text)
        project = self.session.d6_medical.projects[-1]
        self.assertEqual((project.skill, project.difficulty, project.trained), ("first_aid", 31, False))
        self.assertEqual((self.patient.wound, project.status, self.doctor.force.elapsed_rounds), ("mortally_wounded", "failed", 12))
        self.assertEqual(rules.protected_actor_ids(self.session), set())

    def test_untrained_incapacitated_failure_kills_but_trained_failure_does_not_invent_wound_damage(self):
        self.patient.wound = "incapacitated"
        self.doctor.skills.pop("medicine")
        self.assertEqual(self.bacta(total=20).status_code, 200)
        self.assertEqual(self.patient.wound, "dead")
        self.patient.wound = "wounded"
        self.doctor.skills["medicine"] = "3D"
        self.assertEqual(self.bacta(total=1).status_code, 200)
        self.assertEqual(self.patient.wound, "wounded")
        self.assertEqual(self.session.d6_medical.projects[-1].status, "failed")

    def test_source_band_and_cp_force_mix_fail_before_clinical_time(self):
        for changes in ({"difficulty": 6}, {"character_points": 1, "force_point": True}):
            before = self.session.model_dump()
            self.assertEqual(self.bacta(**changes).status_code, 400)
            self.assertEqual(self.session.model_dump(), before)

    def test_saved_bacta_patient_is_reserved_and_completed_duration_does_not_refill_wallet(self):
        self.assertEqual(self.bacta().status_code, 200)
        with self.assertRaisesRegex(ValueError, "medical|care|treatment"):
            require_available(self.session, self.patient_id)
        with tempfile.TemporaryDirectory() as directory:
            manager = SaveManager(directory)
            loaded = manager.load_session(manager.save_session(self.session, "medical_pending"))
        self.assertEqual(loaded.d6_medical.projects, self.session.d6_medical.projects)
        self.assertEqual(rules.protected_actor_ids(loaded), {self.patient_id})
        require_available(loaded, self.doctor_id)

    def test_clock_crossing_new_wound_interrupts_instead_of_instant_heal(self):
        self.assertEqual(self.bacta(duration=1).status_code, 200)
        remaining = self.session.d6_medical.projects[-1].remaining_rounds
        def actual_injury(session, rounds):
            session.character.d6.wound = "incapacitated"
        with patch("dungeonforge.game.weg_vehicle_combat.advance_fleet_time", side_effect=actual_injury):
            response = self.post("advance", rounds=remaining)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.patient.wound, "incapacitated")
        self.assertEqual(self.session.d6_medical.projects[-1].status, "interrupted")

    def test_clock_crossing_new_stun_also_requires_reassessment(self):
        self.assertEqual(self.bacta(duration=1).status_code, 200)
        def actual_stun(session, rounds):
            state = session.character.d6
            state.stun_count = 1
            state.stun_durations, state.stun_expiries = [2], [360]
        with patch("dungeonforge.game.weg_vehicle_combat.advance_fleet_time", side_effect=actual_stun):
            response = self.post("advance", rounds=self.session.d6_medical.projects[-1].remaining_rounds)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual((self.patient.wound, self.patient.stun_count), ("wounded", 1))
        self.assertEqual(self.session.d6_medical.projects[-1].status, "interrupted")

    def test_cancelled_bacta_does_not_permanently_stabilize_mortal_patient(self):
        self.patient.wound = "mortally_wounded"
        self.assertEqual(self.bacta(duration=1).status_code, 200)
        project = self.session.d6_medical.projects[-1]
        self.assertEqual(self.post("cancel", project_id=project.id).status_code, 200)
        self.assertEqual(rules.protected_actor_ids(self.session), set())
        with patch("dungeonforge.rules.weg_d6.DiceRoller.roll", return_value=roll(2)):
            advance_scene(self.session, 4)
        self.assertEqual(self.patient.wound, "dead")

    def test_natural_rest_does_not_roll_early_then_uses_full_actual_strength(self):
        self.patient.attributes["strength"] = "3D+2"
        project = self.natural()
        self.assertEqual(project.required_rounds, 3 * rules.DAY)
        before = self.session.model_dump()
        self.assertEqual(self.post("natural-resolve", project_id=project.id).status_code, 400)
        self.assertEqual(self.session.model_dump(), before)
        self.assertEqual(self.post("advance", rounds=project.remaining_rounds).status_code, 200)
        self.assertEqual(self.session.d6_medical.projects[-1].status, "ready")
        with patch.object(D6Roller, "values", return_value=roll(7)) as rolling:
            response = self.post("natural-resolve", project_id=project.id)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(rolling.call_args.args[:2], (3, 2))
        self.assertEqual(rolling.call_args.kwargs, {"mishap": "penalty"})
        self.assertEqual(self.patient.wound, "healthy")

    def test_work_care_may_act_and_rolls_one_fewer_die_after_actual_period(self):
        project = self.natural(mode="work")
        require_available(self.session, self.patient_id)
        self.assertEqual(self.post("advance", rounds=project.required_rounds).status_code, 200)
        with patch.object(D6Roller, "values", return_value=roll(5)) as rolling:
            response = self.post("natural-resolve", project_id=project.id)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(rolling.call_args.args[:2], (2, 0))
        self.assertEqual(self.patient.wound, "wounded")

    def test_ready_natural_roll_does_not_instantly_erase_a_new_unrelated_stun(self):
        project = self.natural()
        self.assertEqual(self.post("advance", rounds=project.remaining_rounds).status_code, 200)
        self.patient.stun_count, self.patient.unconscious_rounds = 1, 12
        self.patient.stun_durations, self.patient.stun_expiries = [2], [360]
        with patch.object(D6Roller, "values", return_value=roll(7)):
            response = self.post("natural-resolve", project_id=project.id)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.patient.wound, "healthy")
        self.assertEqual((self.patient.stun_count, self.patient.unconscious_rounds, self.patient.stun_durations), (1, 12, [2]))

    def test_double_easy_period_and_real_medicine_stack_but_doses_are_consumed_once(self):
        medicine = make_item("medicine", unit_cost=350)
        medicine.quantity = 2
        self.session.character.inventory.append(medicine)
        project = self.natural(mode="easy", medicine_item_id=medicine.id, medicine_confirmed=True,
            medicine_bonus_dice=1, medicine_time_factor=0.5, medicine_facts="Actual clinic medicine, verified dosage and half-time regimen.")
        self.assertEqual(project.required_rounds, 3 * rules.DAY)
        self.assertEqual(next(item for item in self.session.character.inventory if item.id == medicine.id).quantity, 1)
        self.assertEqual(self.post("advance", rounds=project.remaining_rounds).status_code, 200)
        with patch.object(D6Roller, "values", return_value=roll(7)) as rolling:
            self.assertEqual(self.post("natural-resolve", project_id=project.id).status_code, 200)
        self.assertEqual(rolling.call_args.args[:2], (5, 0))
        self.assertEqual(next(item for item in self.session.character.inventory if item.id == medicine.id).quantity, 1)

    def test_fake_medicine_and_unconfirmed_exceptional_effects_are_atomic(self):
        for changes in ({"medicine_bonus_dice": 1}, {"medicine_item_id": "missing", "medicine_bonus_dice": 1, "medicine_confirmed": True}):
            before = self.session.model_dump()
            response = self.post("natural-start", **changes)
            self.assertEqual(response.status_code, 400, response.text)
            self.assertEqual(self.session.model_dump(), before)
        medicine = make_item("medicine")
        self.session.character.inventory.append(medicine)
        before = self.session.model_dump()
        response = self.post("natural-start", medicine_item_id=medicine.id, medicine_confirmed=True,
            medicine_bonus_dice=2, medicine_time_factor=0.25, medicine_facts="Actual exceptional hospital medicine.")
        self.assertEqual(response.status_code, 400, response.text)
        self.assertEqual(self.session.model_dump(), before)

    def test_multiple_care_clocks_share_actual_scene_once_and_rest_clears_exhaustion(self):
        first = self.natural()
        self.doctor.wound = "wounded"
        second = self.natural(patient_id=self.doctor_id, mode="easy")
        self.patient.hazards.exhausted = self.patient.hazards.fatigued = True
        self.patient.hazards.exertion_rounds = 10
        self.assertEqual(self.post("advance", rounds=100).status_code, 200)
        self.assertEqual((self.patient.force.elapsed_rounds, self.doctor.force.elapsed_rounds), (100, 100))
        self.assertEqual([project.elapsed_rounds for project in self.session.d6_medical.projects], [100, 100])
        self.assertEqual([project.remaining_rounds for project in self.session.d6_medical.projects], [first.required_rounds - 100, second.required_rounds - 100])
        self.assertFalse(self.patient.hazards.exhausted)

    def test_natural_mortal_plan_never_suppresses_untreated_death_checks(self):
        self.patient.wound = "mortally_wounded"
        self.natural()
        self.assertEqual(rules.protected_actor_ids(self.session), set())
        with patch("dungeonforge.rules.weg_d6.DiceRoller.roll", return_value=roll(2)):
            response = self.post("advance", rounds=4)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual((self.patient.wound, self.session.d6_medical.projects[-1].status), ("dead", "interrupted"))

    def test_healthy_and_droid_patients_cannot_create_healing_or_refund_medicine(self):
        self.patient.wound = "healthy"
        self.assertEqual(self.post("natural-start").status_code, 400)
        self.patient.wound = "wounded"
        self.session.character.race = "Droid"
        self.assertEqual(self.post("natural-start").status_code, 400)

    def test_legacy_recovery_cannot_bypass_work_care_period(self):
        self.natural(mode="work")
        before = self.session.model_dump()
        response = self.client.post("/api/weg-d6/recover", json={"method": "natural", "days": 3})
        self.assertGreaterEqual(response.status_code, 400)
        self.assertEqual(self.session.model_dump(), before)

    def test_actual_doctor_dose_adds_after_force_doubling_and_is_not_consumed_again(self):
        self.doctor.skills["medicine"] = "3D+2"
        self.doctor.force_points = 2
        medicine = make_item("medicine")
        medicine.quantity = 2
        self.session.character.inventory.append(medicine)
        with patch.object(D6Roller, "values", return_value=roll(15)) as rolling, patch("dungeonforge.api.weg_medical_routes.DiceRoller.roll", return_value=roll(1)):
            response = self.post("bacta-start", operator_id=self.doctor_id, setup_minutes=1,
                facility="Actual clinic tank", tank_confirmed=True, permission_confirmed=True, force_point=True,
                medicine_item_id=medicine.id, medicine_quantity=1, medicine_confirmed=True,
                medicine_bonus_dice=1, medicine_facts="Actual clinical dose increases trained Medicine by1D.")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(rolling.call_args.args[:3], (7, 4, 0))  # Native6D+4, external1D, not doubled.
        project = self.session.d6_medical.projects[-1]
        self.assertEqual((project.medicine["pool_dice"], project.medicine["pool_pips"], project.medicine["item_id"]), (6, 4, medicine.id))
        self.assertEqual(self.doctor.force_points, 1)
        self.assertEqual(next(item for item in self.session.character.inventory if item.id == medicine.id).quantity, 1)
        with tempfile.TemporaryDirectory() as directory:
            manager = SaveManager(directory)
            loaded = manager.load_session(manager.save_session(self.session, "doctor_actual_dose"))
        self.assertEqual(loaded.d6_medical.projects[-1].medicine, project.medicine)
        self.assertEqual(self.post("advance", rounds=project.remaining_rounds).status_code, 200)
        self.assertEqual(next(item for item in self.session.character.inventory if item.id == medicine.id).quantity, 1)

    def test_failed_actual_doctor_dose_is_used_once_and_another_plain_attempt_has_no_bonus(self):
        medicine = make_item("medicine")
        medicine.quantity = 2
        self.session.character.inventory.append(medicine)
        response = self.bacta(total=1, medicine_item_id=medicine.id, medicine_confirmed=True,
            medicine_bonus_dice=2, medicine_facts="GM confirms this actual medicine effect, not an automatic source bonus.")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.session.d6_medical.projects[-1].status, "failed")
        self.assertEqual(next(item for item in self.session.character.inventory if item.id == medicine.id).quantity, 1)
        self.assertEqual(self.bacta().status_code, 200)
        self.assertEqual(self.session.d6_medical.projects[-1].medicine, {})
        self.assertEqual(next(item for item in self.session.character.inventory if item.id == medicine.id).quantity, 1)

    def test_doctor_bonus_needs_actual_trained_medicine_dose_and_effect_facts_atomically(self):
        medicine = make_item("medicine")
        self.session.character.inventory.append(medicine)
        for changes in ({"medicine_item_id": "missing", "medicine_facts": "Actual dose effect."},
                {"medicine_item_id": medicine.id, "medicine_facts": ""},
                {"medicine_item_id": medicine.id, "medicine_quantity": 2, "medicine_facts": "Actual dose effect."},
                {"medicine_facts": "Actual dose effect."}):
            before = self.session.model_dump()
            response = self.bacta(medicine_confirmed=True, medicine_bonus_dice=1, **changes)
            self.assertEqual(response.status_code, 400, response.text)
            self.assertEqual(self.session.model_dump(), before)
        self.doctor.skills.pop("medicine")
        before = self.session.model_dump()
        response = self.bacta(medicine_item_id=medicine.id, medicine_confirmed=True,
            medicine_bonus_dice=1, medicine_facts="An actual dose cannot grant untrained Medicine.")
        self.assertEqual(response.status_code, 400, response.text)
        self.assertEqual(self.session.model_dump(), before)

    def test_actual_external_doctor_dose_can_restore_pool_depleted_by_fatigue(self):
        self.doctor.skills["medicine"] = "1D"
        self.doctor.hazards.fatigued = True
        medicine = make_item("medicine")
        self.session.character.inventory.append(medicine)
        with patch.object(D6Roller, "values", return_value=roll(5)) as rolling, patch("dungeonforge.api.weg_medical_routes.DiceRoller.roll", return_value=roll(1)):
            response = self.post("bacta-start", operator_id=self.doctor_id, setup_minutes=1,
                facility="Actual clinic tank", tank_confirmed=True, permission_confirmed=True,
                medicine_item_id=medicine.id, medicine_confirmed=True, medicine_bonus_dice=1,
                medicine_facts="Actual external Medicine dose restores one usable die afterfatigue.")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(rolling.call_args.args[:2], (1, 0))
