import unittest

from dungeonforge.campaign.campaign_manager import CampaignManager
from dungeonforge.context.weg_medical_context import build_medical_context
from dungeonforge.game.models import GameSession
from dungeonforge.rules.weg_medical_models import MedicalProject


class MedicalContextTests(unittest.TestCase):
    def setUp(self):
        self.session = GameSession(edition="weg_d6", character=CampaignManager.load_campaign("star_wars_d6").starter_character)
        self.session.character.d6.wound = "mortally_wounded"

    def test_pending_bacta_records_actual_roll_points_and_protection_without_mutation(self):
        project = MedicalProject(kind="bacta", patient_id=self.session.character.id, initial_wound="mortally_wounded",
            reason="Actual hospital care.", operator_id=self.session.character.companions[0].id,
            facility="Actual clinic tank", tank_confirmed=True, legal_basis="licensed", permission_confirmed=True,
            trained=True, skill="medicine", difficulty=5, treatment_roll={"total": 11},
            duration_roll={"total": 3}, required_rounds=51840, remaining_rounds=51828,
            elapsed_rounds=12, setup_minutes=1, character_points=1,
            medicine={"application": "operator_medicine", "item_id": "actual_dose1", "name": "Actual clinical medicine",
                "quantity": 1, "pool_dice": 3, "pool_pips": 2, "bonus_dice": 1,
                "facts": "Actual physician dose effect.", "convention": "External dose dice after Force Point doubling."})
        self.session.d6_medical.projects.append(project)
        before = self.session.model_dump()
        text = build_medical_context(self.session)
        self.assertIn("total 11 vs 5; 1 CP and 0 FP already spent", text)
        self.assertIn("1d6 -> 3 days", text)
        self.assertIn("12/51840 rounds accounted for, 51828 remaining", text)
        self.assertIn("untreated mortality: True", text)
        self.assertIn("native operator pool 3D+2, external dose +1D", text)
        self.assertIn("[actual_dose1]", text)
        self.assertIn("loading or advancing care consumes no further dose or credits", text)
        self.assertEqual(before, self.session.model_dump())
        loaded = GameSession.model_validate_json(self.session.model_dump_json())
        self.assertEqual(text, build_medical_context(loaded))
        project.status = "cancelled"
        self.assertIn("untreated mortality: False", build_medical_context(self.session))
        project.status = "active"
        project.treatment_roll["total"] = None
        project.medicine["pool_pips"] = None
        self.assertIn("untreated mortality: False", build_medical_context(self.session))
        self.assertIn("pips not recorded", build_medical_context(self.session))

    def test_ready_work_plan_preserves_actual_medicine_consumption_and_pending_roll(self):
        self.session.character.d6.wound = "wounded"
        self.session.d6_medical.projects.append(MedicalProject(kind="natural", patient_id=self.session.character.id,
            initial_wound="wounded", reason="Actual prescribed workload.", care_mode="work", status="ready",
            required_rounds=25920, elapsed_rounds=25920, remaining_rounds=0,
            medicine={"name": "Actual clinic medicine", "item_id": "dose1", "quantity": 1,
                "bonus_dice": 1, "time_factor": 0.5, "facts": "Actual dose and effect confirmed."}))
        text = build_medical_context(self.session)
        self.assertIn("Reserved from ordinary actions: False", text)
        self.assertIn("workload modifier -1D", text)
        self.assertIn("ALREADY CONSUMED ONCE", text)
        self.assertIn("No healing roll has happened yet", text)
        self.assertIn("does not consume another dose or charge credits", text)

    def test_empty_non_d6_and_summary_limits_are_explicit(self):
        self.assertEqual(build_medical_context(self.session), "")
        self.session.d6_medical.projects.append(MedicalProject(kind="natural", patient_id=self.session.character.id,
            initial_wound="mortally_wounded", reason="Actual rest.", care_mode="rest"))
        self.assertIn("1 additional saved medical procedures omitted", build_medical_context(self.session, max_projects=0))
        self.session.edition = "5e"
        self.assertEqual(build_medical_context(self.session), "")
