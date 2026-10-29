import tempfile
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from pydantic import ValidationError

from dungeonforge.api import routes, weg_template_routes as api, weg_force_routes as force_api
from dungeonforge.game.models import GameSession
from dungeonforge.game.saves import SaveManager
from dungeonforge.game.weg_vehicle_presets import vehicle_presets
from dungeonforge.rules import weg_creation as creation, weg_force as force
from dungeonforge.rules.base import Character, Item
from dungeonforge.rules.dice import RollResult
from dungeonforge.rules.weg_creation_models import D6CreationRequest
from dungeonforge.rules.weg_d6 import D6Roller, WEGD6Rules
from dungeonforge.rules.weg_force_catalog import POWERS, automatic_known_powers
from dungeonforge.rules.weg_force_models import ForceContinueRequest, ForceManageRequest, ForcePowerRequest
from dungeonforge.rules.weg_models import ATTRIBUTES, D6Character, D6Options
from dungeonforge.rules.weg_templates import (TEMPLATES, D6TemplateRequest, D6StartingPowerChoice,
    build, choose_starting_power, eligible_starting_powers, starting_craft, equipment_companions)
from dungeonforge.rules.weg_vehicle_models import D6Crew, D6VehicleAttackRequest
from dungeonforge.rules.weg_vehicles import WEGVehicleRules


def request(id="brash_pilot", **changes):
    return D6TemplateRequest(**{**dict(template_id=id, name="Tala", skill_dice=TEMPLATES[id]["suggested_skill_dice"],
        owner="Reviewed travelling companion", gm_approval="GM approves the printed template and actual gear."), **changes})


class PrintedTemplateTests(unittest.TestCase):
    def test_all_sixteen_visually_checked_attribute_rows_and_printed_budgets(self):
        expected = {
            "alien_force_student": "2D+1 3D+1 2D 2D+1 3D 2D", "bounty_hunter": "4D 2D+2 2D+2 3D 3D+2 2D",
            "brash_pilot": "3D 2D 4D 3D 3D 3D", "curious_explorer": "2D+1 3D+2 3D 4D 2D 3D",
            "cyborged_pirate": "3D+2 2D 3D+2 3D 2D+2 3D", "cynical_scout": "2D+2 5D 2D 3D 3D 2D+1",
            "ewok_warrior": "3D+2 2D 3D+2 4D+1 1D+2 2D+2", "failed_jedi": "2D+2 3D+1 2D 3D+1 2D+2 2D",
            "gambler": "3D+2 3D 2D+1 4D 2D+2 2D+1", "kid": "3D+2 2D+2 3D 3D+2 2D+1 2D+2",
            "new_republic_bureaucrat": "2D 4D 3D 3D+2 2D+1 3D", "protocol_droid": "1D 3D 1D 1D 1D 1D",
            "smuggler": "3D+1 2D+1 3D+2 3D 3D 2D+2", "sullustan_trader": "2D+1 2D+2 4D+1 3D 2D 3D+2",
            "wookiee_first_mate": "2D+2 2D 3D 2D 5D 3D+1", "young_jedi": "2D 2D 2D 2D 2D 2D",
        }
        self.assertEqual(set(TEMPLATES), set(expected))
        for id, row in expected.items():
            with self.subTest(template=id):
                hero, _ = build(request(id))
                self.assertEqual([hero.d6.attributes[key] for key in ATTRIBUTES], row.split())
                total = sum(creation.pips(code) for code in hero.d6.attributes.values()) + 3 * len(TEMPLATES[id]["force_skills"])
                self.assertEqual(total, (8 if id == "protocol_droid" else 15 if id == "young_jedi" else 18) * 3)
                self.assertEqual(sum(hero.d6.origin.skill_dice.values()), 10 if id == "protocol_droid" else 7)
                self.assertEqual((hero.d6.character_points, hero.d6.origin.template_id), (5, id))
                self.assertIn(f"PDF p.{TEMPLATES[id]['pdf_page']}", hero.d6.origin.source)

    def test_only_printed_starting_skills_and_specialization_parents_are_available(self):
        with self.assertRaisesRegex(ValueError, "listed"):
            build(request(skill_dice={"blaster": 2, "dodge": 2, "medicine": 2, "search": 1}))
        with self.assertRaisesRegex(ValueError, "listed"):
            build(request(skill_dice={"blaster": 2, "dodge": 2, "search": 2}, specializations=[
                {"name": "a", "parent": "medicine"}, {"name": "b", "parent": "search"}, {"name": "c", "parent": "blaster"}]))
        with self.assertRaises(ValidationError):
            request(skill_dice={"blaster": True})
        with self.assertRaises(ValidationError):
            request(attributes={key: "50D" for key in ATTRIBUTES})

    def test_printed_force_policies_and_no_free_force_skills_from_sensitivity(self):
        for id in ("bounty_hunter", "curious_explorer", "protocol_droid"):
            with self.subTest(template=id), self.assertRaisesRegex(ValueError, "sensitivity"):
                build(request(id, force_sensitive=True))
        with self.assertRaisesRegex(ValueError, "sensitivity"):
            build(request("young_jedi", force_sensitive=False))
        hero, _ = build(request(force_sensitive=True))
        self.assertEqual(hero.d6.force_points, 2)
        self.assertEqual(set(hero.d6.force_skills.values()), {"0D"})
        self.assertEqual(hero.d6.advancement.power_grants, [])

    def test_stock_droid_young_jedi_and_custom_creation_keep_different_printed_budgets(self):
        protocol, _ = build(request("protocol_droid"))
        young, _ = build(request("young_jedi"))
        self.assertEqual((protocol.d6.origin.attribute_budget, protocol.d6.move), (8, 7))
        self.assertEqual((young.d6.origin.attribute_budget, young.d6.move), (15, 10))
        self.assertNotIn("languages", protocol.d6.skills)
        self.assertTrue(protocol.d6.droid.tasks)
        custom = D6CreationRequest(name="Custom", occupation="Protocol Droid", species_id="droid", droid_model="3po", owner="Owner",
            skill_dice={"search": 2, "droid_repair": 2, "dodge": 2, "languages": 2, "first_aid": 2}, gm_approval="Custom chassis.")
        created, _ = creation.build(custom)
        self.assertEqual((created.d6.origin.attribute_budget, created.d6.move, created.d6.attributes["dexterity"]), (14, 8, "2D"))
        with self.assertRaises(ValueError):
            creation.build(custom.model_copy(update={"attributes": protocol.d6.attributes}))
        with self.assertRaisesRegex(ValueError, "trusted"):
            creation.build(D6CreationRequest(name="Bad", occupation="Bad", gm_approval="Bad"), stock_template=dict(TEMPLATES["young_jedi"]))

    def test_species_bonus_template_move_and_printed_equipment_overrides(self):
        ewok, _ = build(request("ewok_warrior", skill_dice={"hide": 2, "search": 2, "sneak": 2, "glider": 1}))
        self.assertEqual(creation.pips(ewok.d6.skills["hide"]) - creation.pips(ewok.d6.attributes["perception"]), 12)
        self.assertEqual((build(request("wookiee_first_mate"))[0].d6.move, build(request("kid"))[0].d6.move), (10, 8))
        gambler, _ = build(request("gambler"))
        self.assertEqual(next(gear.damage for gear in gambler.inventory if gear.name == "Hold-out Blaster"), "3D+2")
        scout, _ = build(request("cynical_scout", survival_gear=["Water purifier"]))
        self.assertEqual(next(gear.damage for gear in scout.inventory if gear.name == "Vibroblade"), "STR+1D+2")
        self.assertIn("Water purifier", [gear.name for gear in scout.inventory])
        smuggler, _ = build(request("smuggler"))
        self.assertEqual(smuggler.d6.credits, 2000)
        self.assertIn("25000 credits owed to a crime boss", smuggler.notes)

    def test_each_birth_receives_distinct_physical_starter_items(self):
        first, _ = build(request("smuggler"))
        second, _ = build(request("smuggler"))
        first_ids = {gear.id for gear in first.inventory}
        second_ids = {gear.id for gear in second.inventory}
        self.assertEqual(len(first_ids), len(first.inventory))
        self.assertTrue(first_ids.isdisjoint(second_ids))
        self.assertTrue(first_ids.isdisjoint(gear.id for gear in TEMPLATES["smuggler"]["gear"]))
        custom = D6CreationRequest(name="Custom", occupation="Astromech", species_id="droid", droid_model="r2", owner="Owner",
            skill_dice={"search": 2, "droid_repair": 2, "dodge": 2, "languages": 2, "first_aid": 2},
            equipment=["blaster_pistol", "comlink"], gm_approval="Custom chassis equipment approved.")
        original, _ = creation.build(custom)
        later, _ = creation.build(custom)
        self.assertTrue({gear.id for gear in original.inventory}.isdisjoint(gear.id for gear in later.inventory))
        self.assertTrue({gear.id for gear in original.inventory}.isdisjoint(gear.id for gear in creation.GEAR.values()))

    def test_actual_starting_assets_and_equipment_r2_do_not_use_pc_budget(self):
        self.assertEqual(starting_craft("brash_pilot")[0].name, "X-wing")
        scout = starting_craft("cynical_scout")[0]
        self.assertEqual((scout.hull, scout.shields, scout.space_move, scout.hyperdrive_multiplier, scout.backup_hyperdrive), ("4D", "1D", 5, 2, 15))
        land = starting_craft("new_republic_bureaucrat")[0]
        self.assertEqual((land.atmosphere_move, land.hull, land.maneuverability), (120, "3D", "2D"))
        young, _ = build(request("young_jedi"))
        self.assertNotIn("Lightsaber", [gear.name for gear in young.inventory])
        r2 = equipment_companions("young_jedi", young)[0]
        self.assertEqual((r2.d6.attributes["technical"], r2.d6.skills["astrogation"], r2.d6.skills["starfighter_repair"]), ("2D", "5D", "5D"))
        self.assertEqual((r2.d6.character_points, r2.d6.force_points, r2.d6.droid.owner), (0, 0, young.name))

    def test_tyia_automatic_powers_do_not_consume_nine_earned_slots(self):
        hero, _ = build(request("alien_force_student"))
        self.assertEqual(hero.d6.origin.force_tradition, "tyia")
        self.assertEqual(set(hero.d6.force.known_powers), {"hibernation_trance", "emptiness"})
        self.assertEqual(sum(grant.remaining for grant in hero.d6.advancement.power_grants), 9)
        with self.assertRaisesRegex(ValueError, "automatic"):
            build(request("alien_force_student", powers=["hibernation_trance"]))
        failed, _ = build(request("failed_jedi"))
        self.assertEqual(failed.d6.dark_side_points, 1)
        self.assertEqual(failed.d6.corruption.events, [])
        self.assertEqual(sum(grant.remaining for grant in failed.d6.advancement.power_grants), 6)

    def test_mixed_skill_powers_use_actual_slots_with_backtracking(self):
        hero, _ = build(request("failed_jedi", powers=["lightsaber_combat", "control_pain", "accelerate_healing",
            "absorb_dissipate_energy", "life_detection", "life_sense"]))
        self.assertEqual(len(hero.d6.force.known_powers), 6)
        self.assertEqual(hero.d6.advancement.power_grants, [])
        with self.assertRaisesRegex(ValueError, "choices"):
            build(request("failed_jedi", powers=["absorb_dissipate_energy", "accelerate_healing", "control_pain", "hibernation_trance"]))

    def test_deferred_choices_require_earned_slot_trained_skills_and_existing_prerequisites(self):
        hero, _ = build(request("failed_jedi"))
        sense = next(grant for grant in hero.d6.advancement.power_grants if grant.skill == "sense")
        before_points = (hero.d6.character_points, hero.d6.force_points, dict(hero.d6.force_skills))
        self.assertNotIn("life_sense", eligible_starting_powers(hero, sense))
        with self.assertRaises(ValueError):
            choose_starting_power(hero, sense.id, "life_sense")
        for power in ("life_detection", "life_sense", "receptive_telepathy"):
            choose_starting_power(hero, sense.id, power)
        self.assertEqual(sense.remaining, 0)
        self.assertEqual((hero.d6.character_points, hero.d6.force_points, hero.d6.force_skills), before_points)
        with self.assertRaises(ValueError):
            choose_starting_power(hero, sense.id, "magnify_senses")
        control = next(grant for grant in hero.d6.advancement.power_grants if grant.skill == "control")
        choose_starting_power(hero, control.id, "control_pain")
        with self.assertRaises(ValueError):
            choose_starting_power(hero, control.id, "control_another_pain")  # Alter is actually untrained.
        self.assertEqual(control.remaining, 2)
        control.project_id = "not-this-character-origin"
        self.assertEqual(eligible_starting_powers(hero, control), [])


class TemplateRouteTests(unittest.TestCase):
    def setUp(self):
        self.session = GameSession(edition="weg_d6", character=Character(name="Existing hero", edition="weg_d6", d6=D6Character()), source_folders=[])
        active = patch.object(routes, "_ACTIVE_SESSION", self.session)
        active.start(); self.addCleanup(active.stop)

    def test_preview_readonly_stale_start_and_reviewed_start_backup(self):
        req = request("young_jedi", expected_updated_at=self.session.updated_at)
        before = self.session.model_dump()
        result = api.preview(req)
        self.assertEqual(before, self.session.model_dump())
        self.assertEqual(len(result["character"].companions), 1)
        with self.assertRaises(HTTPException) as rejected:
            api.start(req.model_copy(update={"expected_updated_at": 0}))
        self.assertEqual(rejected.exception.status_code, 400)
        self.assertEqual(before, self.session.model_dump())
        with tempfile.TemporaryDirectory() as directory:
            manager = SaveManager(directory)
            with patch.object(api, "SaveManager", return_value=manager):
                started = api.start(req)
            backup = manager.load_session(started["backup_slot"])
            self.assertEqual(backup.character.name, "Existing hero")
            self.assertEqual(started["session"].character.d6.origin.template_id, "young_jedi")
            self.assertEqual(len(started["session"].character.companions), 1)
            self.assertEqual(sum(grant.remaining for grant in started["session"].character.d6.advancement.power_grants), 9)

    def test_recruit_keeps_actual_assets_and_starting_choices_and_claims_once(self):
        result = api.recruit(request("smuggler", expected_updated_at=self.session.updated_at))
        smuggler = result["session"].character.companions[-1]
        self.assertEqual((smuggler.class_name, smuggler.d6.credits), ("Smuggler", 2000))
        self.assertEqual(self.session.vehicles[0].crew[0].character_id, smuggler.id)
        self.assertIn("Heavy Blaster Pistol", [gear.name for gear in self.session.character.inventory])
        api.recruit(request("failed_jedi", expected_updated_at=self.session.updated_at))
        person = self.session.character.companions[-1]
        grant = next(entry for entry in person.d6.advancement.power_grants if entry.skill == "control")
        choice = D6StartingPowerChoice(actor_id=person.id, grant_id=grant.id, power_id="control_pain", reason="GM records an earned starting selection.", expected_updated_at=self.session.updated_at)
        before_points = person.d6.character_points
        result = api.power_choice(choice)
        person = self.session.character.companions[-1]
        self.assertIn("control_pain", person.d6.force.known_powers)
        self.assertEqual((person.d6.character_points, person.d6.force_skills["control"]), (before_points, "1D"))
        self.assertEqual(next(entry.remaining for entry in person.d6.advancement.power_grants if entry.id == grant.id), 2)
        before = self.session.model_dump()
        with self.assertRaises(HTTPException):
            api.power_choice(choice.model_copy(update={"expected_updated_at": self.session.updated_at}))
        self.assertEqual(before, self.session.model_dump())

    def test_template_origin_deferred_slots_assets_and_r2_survive_save_load(self):
        character, craft, _ = api.prepared(request("young_jedi"))
        self.session.character, self.session.vehicles = character, craft
        with tempfile.TemporaryDirectory() as directory:
            manager = SaveManager(directory)
            restored = manager.load_session(manager.save_session(self.session, "template"))
        self.assertEqual(restored.character.d6.model_dump(), character.d6.model_dump())
        self.assertEqual(restored.character.companions[0].d6.model_dump(), character.companions[0].d6.model_dump())
        self.assertEqual(restored.character.d6.origin.template_id, "young_jedi")


class TemplateRuntimeTests(unittest.TestCase):
    def test_tyia_minimum_time_easy_emptiness_and_alter_band_after_all_modifiers(self):
        hero, _ = build(request("alien_force_student", powers=["telekinesis"]))
        state = hero.d6
        self.assertTrue(all(force.preparation_rounds(state, power) >= 12 for power in POWERS.values()))
        self.assertEqual(force.preparation_rounds(D6Character(), POWERS["telekinesis"]), 1)
        self.assertEqual(force.difficulty(state, ForcePowerRequest(power_id="emptiness"), None, "control")[0], 10)
        self.assertEqual(force.difficulty(D6Character(), ForcePowerRequest(power_id="emptiness"), None, "control")[0], 15)
        req = ForcePowerRequest(power_id="telekinesis", mass_kg=1, proximity="line_of_sight")
        self.assertEqual(force.difficulty(D6Character(), req, None, "alter")[0], 7)
        self.assertEqual(force.difficulty(state, req, None, "alter")[0], 11)
        heroic = req.model_copy(update={"base_difficulties": {"alter": 40}, "proximity": "touching"})
        with self.assertRaisesRegex(ValueError, "Heroic"):
            force.difficulty(state, heroic, None, "alter")
        heroic.tyia_alter_difficulty = 70
        self.assertEqual(force.difficulty(state, heroic, None, "alter")[0], 70)

    def test_tyia_immediate_injury_windows_are_not_bypassed(self):
        hero, _ = build(request("alien_force_student", powers=["control_pain", "reduce_injury", "remain_conscious"]))
        for power_id in ("reduce_injury", "remain_conscious"):
            with self.subTest(power=power_id), self.assertRaisesRegex(ValueError, "one-minute"):
                force.validate_request(hero.d6, ForcePowerRequest(power_id=power_id), None)
        novice = D6Character(force_sensitive=True)
        novice.origin.force_tradition = "tyia"
        self.assertEqual(automatic_known_powers(novice), [])
        novice.force_skills["control"] = "1D"
        self.assertEqual(set(automatic_known_powers(novice)), {"hibernation_trance", "emptiness"})

    def test_tyia_preparation_preserves_fp_until_the_actual_skill_roll(self):
        hero, _ = build(request("alien_force_student"))
        session = GameSession(edition="weg_d6", character=hero, source_folders=[])
        with patch.object(routes, "_ACTIVE_SESSION", session):
            before = session.model_dump()
            with self.assertRaises(HTTPException):
                force_api.begin(ForcePowerRequest(power_id="emptiness", force_point=True))
            self.assertEqual(before, session.model_dump())
            force_api.begin(ForcePowerRequest(power_id="emptiness"))
            self.assertEqual(session.character.d6.force.attempt.preparation_remaining, 11)
            with self.assertRaises(HTTPException):
                force_api.continue_power(ForceContinueRequest(force_point=True))
            self.assertEqual(session.character.d6.force_points, 2)
            for _ in range(11):
                force_api.manage(ForceManageRequest(action="advance", rounds=1))
                if session.character.d6.force.attempt.preparation_remaining:
                    force_api.continue_power(ForceContinueRequest())
            controlled = RollResult(expression="2D", dice_count=2, die_type=6, total=20, system="weg_d6", breakdown="Controlled source preparation check")
            with patch.object(D6Roller, "values", return_value=controlled) as dice:
                result = force_api.continue_power(ForceContinueRequest(force_point=True))
            self.assertEqual(dice.call_args.args[0], 2)
            self.assertEqual(session.character.d6.force_points, 1)
            self.assertEqual(result["eval_result"].target_value, 10)
            self.assertEqual(session.character.d6.force.effects[-1].power_id, "emptiness")

    def test_protocol_life_preservation_prevents_sentient_and_unspecified_harm_before_roll(self):
        hero, _ = build(request("protocol_droid"))
        before = hero.d6.model_dump()
        with patch.object(D6Roller, "values") as dice:
            with self.assertRaisesRegex(ValueError, "life-preservation"):
                WEGD6Rules.resolve_attack(hero.d6, D6Character(), Item(name="Blaster", damage="4D", d6_skill="blaster"), D6Options(character_points=1))
            with self.assertRaisesRegex(ValueError, "nonsentient"):
                WEGD6Rules().evaluate_attack(hero, 1)
            dice.assert_not_called()
        self.assertEqual(before, hero.d6.model_dump())
        craft = vehicle_presets()["xwing"]
        crew = D6Crew(id="protocol", name="Protocol", character_id=hero.id, d6=hero.d6, stations=["pilot", "gunner"])
        craft.crew = [crew]
        target = vehicle_presets()["tie_fighter"]
        target.crew = [D6Crew(id="pilot", name="Actual sentient pilot", d6=D6Character(), stations=["pilot"])]
        req = D6VehicleAttackRequest(actor_id=crew.id, target_id=target.id, weapon_id=craft.weapons[0].id)
        with self.assertRaisesRegex(ValueError, "life-preservation"):
            WEGVehicleRules.attack(craft, crew, target, craft.weapons[0], req, "space")


if __name__ == "__main__":
    unittest.main()
