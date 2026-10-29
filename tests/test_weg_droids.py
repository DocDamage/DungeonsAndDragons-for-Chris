import tempfile
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from dungeonforge.api import routes
from dungeonforge.campaign.campaign_manager import CampaignManager
from dungeonforge.game.models import GameSession
from dungeonforge.game.saves import SaveManager
from dungeonforge.main import app
from dungeonforge.rules.base import Companion, Item
from dungeonforge.rules.weg_d6 import WEGD6Rules
from tests.test_weg_creation import droid, request


class DroidAPITests(unittest.TestCase):
    def setUp(self):
        preset = CampaignManager.load_campaign("star_wars_d6")
        self.session = GameSession(edition="weg_d6", character=preset.starter_character)
        hero = droid()
        hero.d6.character_points = 100
        self.target_id = hero.id
        self.session.character.companions.append(Companion(id=hero.id, name="R2-TEST", race=hero.race, d6=hero.d6, d6_weapon=Item(name="Brawling", damage="STR", d6_skill="brawling", damage_type="physical")))
        self.session.character.inventory.append(Item(name="Replacement Droid parts", quantity=5, item_type="parts"))
        state = self.session.character.d6
        state.skills.update(droid_programming="10D", droid_repair="10D", blaster="10D", search="10D", first_aid="10D", medicine="8D")
        active = patch.object(routes, "_ACTIVE_SESSION", self.session)
        active.start(); self.addCleanup(active.stop)
        self.client = TestClient(app); self.addCleanup(self.client.close)
        dice = patch("dungeonforge.rules.weg_d6.random.randint", return_value=4)
        dice.start(); self.addCleanup(dice.stop)

    @property
    def target(self):
        return next(item for item in self.session.character.companions if item.id == self.target_id).d6

    def post(self, operation, **changes):
        payload = dict(actor_id=self.target_id, programmer_id=self.session.character.id, operation=operation, skill="blaster", reason="GM confirms the workshop and matching software.",
            minutes=15, computer_connected=True, software_available=True, difficulty=20)
        return self.client.post("/api/weg-d6/droids/work", json={**payload, **changes})

    def test_new_skill_needs_software_connection_and_qualified_programmer_before_spending(self):
        for changes in ({"software_available": False}, {"computer_connected": False}, {"programmer_id": self.target_id}):
            before = self.session.model_dump()
            response = self.post("learn", **changes)
            self.assertEqual(response.status_code, 400, response.text)
            self.assertEqual(self.session.model_dump(), before)
        self.session.character.d6.skills["blaster"] = "4D"
        before = self.session.model_dump()
        self.assertEqual(self.post("learn").status_code, 400)
        self.assertEqual(self.session.model_dump(), before)

    def test_new_skill_is_attribute_plus_one_pip_and_pays_droid_cp_once(self):
        response = self.post("learn", credits=20)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual((self.target.skills["blaster"], self.target.character_points), ("2D+1", 98))
        self.assertEqual(self.session.character.d6.credits, 230)
        self.assertEqual(self.target.force.elapsed_rounds, 180)
        before = self.session.model_dump()
        self.assertEqual(self.post("refine").status_code, 400)
        self.assertEqual(self.session.model_dump(), before)

    def test_refining_known_skill_requires_no_external_programmer(self):
        response = self.post("refine", skill="search", programmer_id=self.target_id, computer_connected=False, software_available=False)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual((self.target.skills["search"], self.target.character_points), ("4D+1", 96))

    def test_unknown_refinement_and_13d_limit_reject_without_time_or_cost(self):
        self.target.skills["search"] = "13D"
        for operation, changes in [("refine", {"skill": "search"}), ("refine", {"skill": "blaster"}), ("cartridge", {"cartridge_rating": "13D+1"})]:
            before = self.session.model_dump()
            self.assertEqual(self.post(operation, **changes).status_code, 400)
            self.assertEqual(self.session.model_dump(), before)

    def test_failed_programming_spends_time_and_commercial_cost_not_learning_cp(self):
        self.session.character.d6.skills["droid_programming"] = "1D"
        response = self.post("learn", credits=10)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertFalse(response.json()["eval_result"]["success"])
        self.assertNotIn("blaster", self.target.skills)
        self.assertEqual((self.target.character_points, self.session.character.d6.credits), (100, 240))
        self.assertEqual(self.target.force.elapsed_rounds, 180)

    def test_successful_repair_consumes_parts_and_restores_chassis_without_mortality(self):
        self.target.wound = "mortally_wounded"
        response = self.post("repair", skill="", difficulty=30, parts_item="Replacement Droid parts")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.target.wound, "healthy")
        self.assertEqual(next(item for item in self.session.character.inventory if item.item_type == "parts").quantity, 4)
        self.assertEqual(self.target.character_points, 100)

    def test_failed_repair_retries_need_one_hour_then_two_hours(self):
        self.target.wound = "incapacitated"
        self.session.character.d6.skills["droid_repair"] = "1D"
        self.assertEqual(self.post("repair", parts_item="Replacement Droid parts").status_code, 200)
        self.assertEqual(self.target.droid.repair_attempts, 1)
        before = self.session.model_dump()
        self.assertEqual(self.post("repair", parts_item="Replacement Droid parts").status_code, 400)
        self.assertEqual(before, self.session.model_dump())
        self.assertEqual(self.post("repair", parts_item="Replacement Droid parts", minutes=60).status_code, 200)
        self.assertEqual(self.post("repair", parts_item="Replacement Droid parts", minutes=60).status_code, 400)

    def test_nearly_obliterated_salvageable_droid_can_be_repaired_but_destroyed_cannot(self):
        self.target.wound = "dead"
        self.assertEqual(self.post("repair", difficulty=31, parts_item="Replacement Droid parts").status_code, 200)
        self.assertEqual(self.target.wound, "healthy")
        self.target.droid.destroyed = True
        self.assertEqual(self.post("repair", difficulty=31, parts_item="Replacement Droid parts").status_code, 400)

    def test_memory_wipe_removes_learned_skills_and_tasks_but_keeps_hardwired(self):
        self.target.droid.hardwired_skills = {"search": "3D"}
        self.target.droid.tasks.append("Track packages")
        response = self.post("wipe", difficulty=10)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.target.skills, {"search": "3D"})
        self.assertFalse(self.target.droid.tasks)
        self.assertEqual(self.target.droid.memory_wipes, 1)
        self.assertTrue(self.target.droid.equipment)

    def test_hardwiring_adds_thirty_difficulty_and_survives_wipe(self):
        response = self.post("learn", hardwire=True)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertFalse(response.json()["eval_result"]["success"])
        self.assertNotIn("blaster", self.target.droid.hardwired_skills)
        response = self.post("learn", hardwire=True, roll_bonus=10)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.target.droid.hardwired_skills["blaster"], "2D+1")
        self.assertEqual(self.post("wipe", difficulty=10).status_code, 200)
        self.assertEqual(self.target.skills["blaster"], "2D+1")

    def test_cartridge_can_install_a_purchased_rating_without_refinement_cp(self):
        response = self.post("cartridge", cartridge_rating="6D", credits=100)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual((self.target.skills["blaster"], self.target.character_points), ("6D", 100))
        self.assertEqual(self.session.character.d6.credits, 150)

    def test_technician_points_spend_normally_and_force_expenditure_is_saved(self):
        before = self.session.character.d6.force_points
        response = self.post("task", task="Recognize Imperial uniforms", force_point=True)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.session.character.d6.force_points, before - 1)
        self.assertEqual(self.session.character.d6.rewards.expenditures[-1].source, "round_boost")
        before = self.session.model_dump()
        self.assertEqual(self.post("task", task="Another task", force_point=True, character_points=1).status_code, 400)
        self.assertEqual(self.session.model_dump(), before)

    def test_tasks_and_attachments_persist_in_work_history_and_save(self):
        response = self.post("task", task="Sort medical supplies", difficulty=10)
        self.assertEqual(response.status_code, 200, response.text)
        response = self.post("attachment", attachment="External cargo rack", parts_item="Replacement Droid parts")
        self.assertEqual(response.status_code, 200, response.text)
        with tempfile.TemporaryDirectory() as directory:
            manager = SaveManager(directory)
            loaded = manager.load_session(manager.save_session(self.session, "droid_work"))
        saved = next(item.d6.droid for item in loaded.character.companions if item.id == self.target_id)
        self.assertIn("External cargo rack", saved.equipment)
        self.assertIn("Sort medical supplies", saved.tasks)
        self.assertEqual(len(saved.work_history), 2)

    def test_specialization_and_medicine_use_their_own_cp_costs(self):
        response = self.post("learn", skill="tracking", parent_skill="search")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual((self.target.skills["tracking"], self.target.character_points), ("4D+1", 98))
        self.assertEqual(self.target.specialization_parents["tracking"], "search")
        self.target.skills["first_aid"] = "5D"
        response = self.post("learn", skill="medicine")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual((self.target.skills["medicine"], self.target.character_points), ("1D", 96))

    def test_droid_work_rejects_force_training_and_insufficient_cp_or_credits(self):
        for changes in ({"skill": "control"}, {"credits": 10000}, {"reason": " "}):
            before = self.session.model_dump()
            self.assertEqual(self.post("learn", **changes).status_code, 400)
            self.assertEqual(self.session.model_dump(), before)
        self.target.character_points = 0
        self.assertEqual(self.post("learn").status_code, 400)

    def test_native_recruit_retains_melee_weapon_and_droid_rules(self):
        payload = request(name="Grarr", species_id="wookiee", attributes={"dexterity": "3D", "knowledge": "2D", "mechanical": "3D", "perception": "2D", "strength": "5D", "technical": "3D"},
            equipment=["knife"], expected_updated_at=self.session.updated_at).model_dump()
        response = self.client.post("/api/weg-d6/creation/recruit", json=payload)
        self.assertEqual(response.status_code, 200, response.text)
        companion = self.session.character.companions[-1]
        self.assertEqual(companion.d6_weapon.d6_skill, "melee_combat")
        response = self.client.post("/api/combat/start", json={})
        self.assertEqual(response.status_code, 200, response.text)
        combatant = next(item for item in self.session.encounter.combatants if item.id == companion.id)
        self.assertEqual(combatant.weapon.d6_skill, "melee_combat")


if __name__ == "__main__":
    unittest.main()
