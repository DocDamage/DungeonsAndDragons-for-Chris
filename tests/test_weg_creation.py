import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from pydantic import ValidationError
from dungeonforge.api import routes
from dungeonforge.campaign.campaign_manager import CampaignManager
from dungeonforge.game.models import GameSession
from dungeonforge.game.saves import SaveManager
from dungeonforge.main import app
from dungeonforge.rules.base import Item
from dungeonforge.rules.weg_creation import build, attributes_for, pips, SPECIES, DROIDS
from dungeonforge.rules.weg_creation_models import D6CreationRequest
from dungeonforge.rules.weg_d6 import WEGD6Rules, D6Roller
from dungeonforge.rules.weg_models import D6Character


def request(**changes):
    return D6CreationRequest(**{**dict(name="Tala", occupation="Rebel scout", species_id="human",
        attributes={key: "3D" for key in SPECIES["human"]["minimums"]},
        skill_dice={"blaster": 2, "dodge": 2, "search": 1, "first_aid": 1, "space_transports": 1},
        gm_approval="GM approves the template and equipment."), **changes})


def droid(model="r2", **changes):
    return build(request(species_id="droid", droid_model=model, owner="Rebel crew", attributes={},
        skill_dice={"search": 2, "droid_repair": 2, "computer_programming_repair": 2, "first_aid": 2, "dodge": 2}, **changes))[0]


class CreationRulesTests(unittest.TestCase):
    def test_human_starts_with_correct_budgets_points_and_absolute_skills(self):
        hero, _ = build(request())
        self.assertEqual((hero.d6.character_points, hero.d6.force_points, hero.d6.dark_side_points), (5, 1, 0))
        self.assertEqual(hero.d6.skills["blaster"], "5D")
        self.assertEqual(sum(pips(value) for value in hero.d6.attributes.values()), 54)
        self.assertEqual(hero.d6.origin.skill_budget, 7)
        self.assertFalse(hero.known_spells)

    def test_every_catalog_species_has_legal_suggested_attributes_and_correct_budget(self):
        for identity, spec in SPECIES.items():
            with self.subTest(species=identity):
                choices = {"melee_combat": 2, "brawling": 2, "search": 1, "first_aid": 1, "hide": 1}
                hero, _ = build(request(species_id=identity, attributes=attributes_for(spec), skill_dice=choices))
                self.assertEqual(sum(pips(value) for value in hero.d6.attributes.values()), spec["attribute_dice"] * 3)
                self.assertEqual(hero.d6.move_maximum, spec["move_maximum"])
        self.assertEqual((SPECIES["gamorrean"]["attribute_dice"], SPECIES["twilek"]["attribute_dice"]), (17, 17))

    def test_over_under_budget_out_of_range_and_unknown_species_reject(self):
        for changes in [{"attributes": {key: "4D" for key in SPECIES["human"]["minimums"]}}, {"skill_dice": {"blaster": 2}}, {"species_id": "invented"}, {"attributes": {"dexterity": "3D"}}]:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                build(request(**changes))

    def test_three_dice_and_boolean_skill_allocations_reject(self):
        with self.assertRaises(ValueError):
            build(request(skill_dice={"blaster": 3, "dodge": 2, "search": 2}))
        with self.assertRaises(ValidationError):
            request(skill_dice={"blaster": True})

    def test_specialization_package_costs_one_die_and_uses_final_basic_rating(self):
        hero, _ = build(request(skill_dice={"blaster": 2, "dodge": 2, "search": 1, "first_aid": 1}, specializations=[
            {"name": "blaster_pistol", "parent": "blaster"}, {"name": "hidden_doors", "parent": "search"}, {"name": "medpacs", "parent": "first_aid"}]))
        self.assertEqual(hero.d6.skills["blaster_pistol"], "6D")
        self.assertEqual(hero.d6.specialization_parents["blaster_pistol"], "blaster")

    def test_species_creation_bonuses_are_not_free_attribute_changes(self):
        choices = {"hide": 2, "sneak": 2, "search": 1, "glider": 1, "first_aid": 1}
        hero, _ = build(request(species_id="ewok", attributes=attributes_for(SPECIES["ewok"]), skill_dice=choices))
        self.assertEqual(pips(hero.d6.skills["hide"]) - pips(hero.d6.attributes["perception"]), 12)
        with self.assertRaisesRegex(ValueError, "Beginning Ewoks"):
            build(request(species_id="ewok", attributes=attributes_for(SPECIES["ewok"])))

    def test_initial_force_skill_costs_attribute_die_and_requires_training_story(self):
        attrs = {**request().attributes, "knowledge": "2D"}
        hero, _ = build(request(attributes=attrs, force_skills=["control"], force_background="An exiled Jedi taught me.", powers=["control_pain", "hibernation_trance", "emptiness"]))
        self.assertEqual((hero.d6.force_points, hero.d6.force_skills["control"]), (2, "1D"))
        with self.assertRaises(ValueError):
            build(request(force_skills=["control"]))
        with self.assertRaisesRegex(ValueError, "plausible"):
            build(request(attributes=attrs, force_skills=["control"]))

    def test_droid_chassis_receive_attributes_plus_one_without_npc_skills(self):
        for model, spec in DROIDS.items():
            with self.subTest(model=model):
                hero = droid(model)
                self.assertEqual([pips(value) for value in hero.d6.attributes.values()], [pips(value) + 3 for value in spec["attributes"]])
                self.assertNotIn("languages", hero.d6.skills)
                self.assertNotIn("astrogation", hero.d6.skills)
                self.assertEqual(hero.d6.origin.skill_budget, 10)
                self.assertTrue(hero.d6.droid.equipment)
        self.assertEqual(droid("k4").d6.armor_energy, "2D")

    def test_droids_need_owner_and_cannot_choose_force_or_redistribute_attributes(self):
        for changes in [{"force_sensitive": True}, {"force_skills": ["control"]}, {"owner": " "}, {"attributes": request().attributes}]:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                base = request(species_id="droid", droid_model="r2", owner="Owner", attributes={}, skill_dice={"search": 2, "droid_repair": 2, "dodge": 2, "first_aid": 2, "blaster": 2})
                build(base.model_copy(update=changes))

    def test_droid_cannot_naturally_heal_and_has_no_organic_mortal_death_roll(self):
        state = droid().d6
        state.wound = "mortally_wounded"
        with self.assertRaisesRegex(ValueError, "Droids require"):
            WEGD6Rules.recover(state, "natural", days=30)
        self.assertIsNone(WEGD6Rules.advance_mortality(state, 1000000))
        self.assertEqual(state.wound, "mortally_wounded")

    def test_destroyed_droid_is_out_of_fight_and_cannot_declare(self):
        state = droid().d6
        state.droid.destroyed = True
        self.assertFalse(state.can_act)
        self.assertTrue(state.out_of_fight)
        with self.assertRaises(ValueError):
            WEGD6Rules.declare(state)

    def test_species_roll_conditions_and_droid_sensors(self):
        state = D6Character(species_id="mon_calamari")
        state.species_context.environment = "moist"
        self.assertEqual(WEGD6Rules.pool(state, "strength"), (4, 0))
        state.species_context.environment = "dry"
        self.assertEqual(WEGD6Rules.pool(state, "blaster"), (2, 0))
        state = D6Character(species_id="sullustan")
        state.species_context.enhanced_senses = True
        self.assertEqual(WEGD6Rules.pool(state, "search"), (5, 0))
        state.species_context.familiar_destination = True
        self.assertEqual(WEGD6Rules.pool(state, "astrogation"), (4, 0))
        state = droid("9g").d6
        state.species_context.long_range_sensor = True
        state.species_context.target_distance_m = 30
        self.assertEqual(WEGD6Rules.pool(state, "search"), (6, 0))
        state.species_context.target_distance_m = 60
        self.assertEqual(WEGD6Rules.pool(state, "search"), (4, 0))

    def test_wookiee_rage_adds_only_brawling_damage_and_penalizes_other_checks(self):
        state = D6Character(species_id="wookiee")
        state.species_context.berserk = True
        self.assertEqual(WEGD6Rules.damage_pool(state, None), (5, 0))
        self.assertEqual(WEGD6Rules.pool(state, "brawling"), (3, 0))
        self.assertEqual(WEGD6Rules.pool(state, "perception"), (1, 0))
        self.assertEqual(WEGD6Rules.resistance_pool(state), (3, 0))
        self.assertEqual(WEGD6Rules.damage_pool(state, Item(name="Knife", damage="STR+1D", d6_skill="melee_combat")), (4, 0))


class CreationAPITests(unittest.TestCase):
    def setUp(self):
        preset = CampaignManager.load_campaign("star_wars_d6")
        self.session = GameSession(edition="weg_d6", character=preset.starter_character)
        active = patch.object(routes, "_ACTIVE_SESSION", self.session)
        active.start(); self.addCleanup(active.stop)
        self.client = TestClient(app); self.addCleanup(self.client.close)
        dice = patch("dungeonforge.rules.weg_d6.random.randint", return_value=4)
        dice.start(); self.addCleanup(dice.stop)

    def test_preview_readonly_and_start_saves_complete_previous_adventure(self):
        payload = request(expected_updated_at=self.session.updated_at).model_dump()
        before = self.session.model_dump()
        response = self.client.post("/api/weg-d6/creation/preview", json=payload)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(before, self.session.model_dump())
        with tempfile.TemporaryDirectory() as directory:
            manager = SaveManager(directory)
            with patch("dungeonforge.api.weg_creation_routes.SaveManager", return_value=manager):
                response = self.client.post("/api/weg-d6/creation/start", json=payload)
            self.assertEqual(response.status_code, 200, response.text)
            restored = manager.load_session(response.json()["backup_slot"])
            self.assertEqual(restored.character.name, self.session.character.name)
            self.assertEqual(len(restored.history), len(self.session.history))
        self.assertEqual(routes._ACTIVE_SESSION.character.name, "Tala")
        self.assertEqual(routes._ACTIVE_SESSION.d6_advancement.adventure, 1)
        self.assertEqual(self.client.post("/api/weg-d6/creation/start", json=payload).status_code, 400)

    def test_bad_creation_and_stale_start_do_not_mutate_existing_session(self):
        before = self.session.model_dump()
        response = self.client.post("/api/weg-d6/creation/start", json=request(expected_updated_at=0).model_dump())
        self.assertEqual(response.status_code, 400)
        self.assertEqual(before, self.session.model_dump())

    def test_species_rage_requires_danger_and_calm_requires_controlled_enemies(self):
        self.session.character.race = "Wookiee"
        self.session.character.d6.species_id = "wookiee"
        context = self.session.character.d6.species_context.model_dump()
        context["berserk"] = True
        payload = {"context": context, "reason": "Life-debt companion is under fire."}
        self.assertEqual(self.client.post("/api/weg-d6/creation/species-context", json=payload).status_code, 400)
        response = self.client.post("/api/weg-d6/creation/species-context", json={**payload, "deadly_danger": True})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.client.post("/api/weg-d6/creation/calm", json={}).status_code, 400)
        self.session.character.d6.attributes["perception"] = "6D"
        response = self.client.post("/api/weg-d6/creation/calm", json={"enemies_controlled": True})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertFalse(self.session.character.d6.species_context.berserk)

    def test_legal_wookiee_perception_can_calm_with_fp_or_actual_coordination(self):
        state = self.session.character.d6
        state.species_id = "wookiee"
        state.species_context.berserk = True
        state.attributes["perception"] = "2D+1"
        before = self.session.model_dump()
        self.assertEqual(self.client.post("/api/weg-d6/creation/calm", json={"enemies_controlled": True}).status_code, 400)
        self.assertEqual(self.session.model_dump(), before)
        with patch("dungeonforge.rules.weg_d6.random.randint", return_value=5):
            response = self.client.post("/api/weg-d6/creation/calm", json={"enemies_controlled": True, "force_point": True, "difficulty": 11})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertFalse(self.session.character.d6.species_context.berserk)
        self.assertEqual(self.session.character.d6.force_points, 1)
        self.assertEqual(self.session.character.d6.rewards.expenditures[-1].source, "round_boost")

    def test_gamorrean_stamina_retry_once_without_extra_action(self):
        self.session.character.d6.species_id = "gamorrean"
        response = self.client.post("/api/weg-d6/check", json={"skill": "stamina", "difficulty": 100})
        self.assertEqual(response.status_code, 200, response.text)
        actions = self.session.character.d6.round_state.actions_taken
        response = self.client.post("/api/weg-d6/creation/stamina-retry", json={})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.session.character.d6.round_state.actions_taken, actions)
        self.assertEqual(self.client.post("/api/weg-d6/creation/stamina-retry", json={}).status_code, 400)

    def test_origin_context_and_droid_identity_survive_save(self):
        self.session.character = droid("9g")
        self.session.character.d6.species_context.moving_target_sensor = True
        with tempfile.TemporaryDirectory() as directory:
            manager = SaveManager(directory)
            restored = manager.load_session(manager.save_session(self.session, "droid"))
        self.assertEqual(restored.character.d6, self.session.character.d6)


if __name__ == "__main__":
    unittest.main()
