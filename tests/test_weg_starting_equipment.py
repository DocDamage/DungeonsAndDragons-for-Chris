import tempfile
import unittest
from unittest.mock import patch

from dungeonforge.api import routes, weg_template_routes as template_api, weg_creation_routes as creation_api
from dungeonforge.game.models import GameSession
from dungeonforge.game.saves import SaveManager
from dungeonforge.rules import weg_creation as creation, weg_templates as templates
from dungeonforge.rules.weg_creation_models import D6CreationRequest
from dungeonforge.rules.weg_models import ATTRIBUTES, D6Character, D6Options
from dungeonforge.rules.weg_d6 import D6Roller, WEGD6Rules
from dungeonforge.rules.dice import RollResult
from dungeonforge.rules.weg_personal_equipment import armor_for_hit


def custom(**changes):
    return D6CreationRequest(**{**dict(name="Tala", occupation="Scout", attributes=dict.fromkeys(ATTRIBUTES, "3D"),
        skill_dice={"blaster": 2, "dodge": 2, "search": 1, "first_aid": 1, "space_transports": 1},
        equipment=["blaster_pistol", "heavy_blaster", "blaster_rifle", "knife", "blast_vest"], gm_approval="GM approves actual starting gear.", include_medic=False), **changes})


def stock(id):
    return templates.D6TemplateRequest(template_id=id, name="Printed " + id, owner="Actual companion",
        skill_dice=templates.TEMPLATES[id]["suggested_skill_dice"], gm_approval="Printed gear reviewed.")


class StartingEquipmentTests(unittest.TestCase):
    def test_fresh_custom_weapons_have_source_ammo_ranges_and_actual_owner(self):
        hero, _ = creation.build(custom())
        pistol, heavy, rifle = hero.inventory[:3]
        self.assertEqual((pistol.catalog_id, pistol.ammo, pistol.ammo_capacity, pistol.d6_ranges), ("blaster_dl18", 100, 100, (3, 10, 30, 120)))
        self.assertEqual((heavy.ammo, rifle.ammo, heavy.reload_catalog_id), (25, 100, "standard_blaster_power_pack"))
        self.assertTrue(pistol.equipped)
        self.assertFalse(heavy.equipped)
        self.assertTrue(all(gear.equipped_by == hero.id for gear in hero.inventory))
        self.assertEqual((hero.d6.credits, hero.d6.character_points), (250, 5))

    def test_printed_overrides_remain_authoritative_with_finite_source_feeds(self):
        gambler, _ = templates.build(stock("gambler"))
        holdout = next(gear for gear in gambler.inventory if gear.item_type == "weapon")
        self.assertEqual((holdout.name, holdout.damage, holdout.original_damage, holdout.ammo, holdout.reload_catalog_id),
            ("Hold-out Blaster", "3D+2", "3D+2", 6, "q2_power_pack"))
        bureaucrat, _ = templates.build(stock("new_republic_bureaucrat"))
        sporting = next(gear for gear in bureaucrat.inventory if gear.item_type == "weapon")
        self.assertEqual((sporting.damage, sporting.original_damage, sporting.ammo), ("3D+2", "3D+2", 50))
        scout, _ = templates.build(stock("cynical_scout"))
        blade = next(gear for gear in scout.inventory if gear.name == "Vibroblade")
        self.assertEqual((blade.damage, blade.original_damage, blade.d6_difficulty), ("STR+1D+2", "STR+1D+2", 15))
        self.assertEqual((gambler.d6.credits, bureaucrat.d6.credits), (1000, 4000))

    def test_bowcaster_has_both_actual_limited_feeds_and_new_attack_consumes_each(self):
        hero, _ = templates.build(stock("wookiee_first_mate"))
        weapon = hero.inventory[0]
        self.assertEqual((weapon.ammo, weapon.ammo_capacity, weapon.power_ammo, weapon.power_ammo_capacity), (6, 6, 50, 50))
        self.assertEqual((weapon.reload_catalog_id, weapon.power_reload_catalog_id), ("bowcaster_quarrels", "bowcaster_power_pack"))
        roll = RollResult(expression="3D", dice_count=3, die_type=6, total=9, system="weg_d6", breakdown="Controlled miss consumes actual ammunition")
        with patch.object(D6Roller, "values", return_value=roll):
            WEGD6Rules.resolve_attack(hero.d6, D6Character(), weapon, D6Options(difficulty=100, distance_m=5))
        self.assertEqual((weapon.ammo, weapon.power_ammo), (5, 49))
        weapon.power_ammo = 0
        before = hero.d6.model_dump()
        with patch.object(D6Roller, "values") as dice, self.assertRaisesRegex(ValueError, "out of ammunition or power"):
            WEGD6Rules.resolve_attack(hero.d6, D6Character(), weapon, D6Options(character_points=1))
        dice.assert_not_called()
        self.assertEqual(before, hero.d6.model_dump())

    def test_starter_pistol_miss_consumes_actual_pack_once(self):
        hero, _ = creation.build(custom())
        weapon = hero.inventory[0]
        roll = RollResult(expression="5D", dice_count=5, die_type=6, total=15, system="weg_d6", breakdown="Controlled miss")
        with patch.object(D6Roller, "values", return_value=roll):
            WEGD6Rules.resolve_attack(hero.d6, D6Character(), weapon, D6Options(difficulty=100))
        self.assertEqual(weapon.ammo, 99)

    def test_location_armor_is_equipped_only_on_its_printed_coverage(self):
        hero, _ = creation.build(custom())
        vest = next(gear for gear in hero.inventory if gear.item_type == "armor")
        self.assertEqual((vest.armor_locations, vest.armor_sides), (["torso"], ["front"]))
        self.assertIsNone(armor_for_hit([vest], "energy", "torso", "back"))
        self.assertIsNone(armor_for_hit([vest], "energy", "head", "front"))
        hunter, _ = templates.build(stock("bounty_hunter"))
        protective = next(gear for gear in hunter.inventory if gear.name == "Protective vest")
        self.assertEqual((protective.armor_energy, protective.armor_physical, protective.armor_locations, protective.armor_sides), ("0D+2", "0D+2", ["torso"], ["front", "back"]))
        pirate, _ = templates.build(stock("cyborged_pirate"))
        arm = next(gear for gear in pirate.inventory if gear.name == "Cybernetic left arm")
        self.assertEqual((arm.armor_locations, arm.armor_energy), (["left_arm"], "1D"))
        self.assertIsNone(armor_for_hit([arm], "physical", "right_arm"))
        self.assertTrue(all(gear.equipped and gear.equipped_by == owner.id for owner, gear in [(hero, vest), (hunter, protective), (pirate, arm)]))

    def test_unlisted_statistics_are_not_invented_and_new_ids_never_mutate_prototypes(self):
        explorer, _ = templates.build(stock("curious_explorer"))
        powder = next(gear for gear in explorer.inventory if gear.name == "Black Powder Pistol")
        self.assertEqual((powder.damage, powder.ammo, powder.d6_ranges), ("3D", None, None))
        first, _ = templates.build(stock("bounty_hunter"))
        second, _ = templates.build(stock("bounty_hunter"))
        self.assertTrue({gear.id for gear in first.inventory}.isdisjoint(gear.id for gear in second.inventory))
        self.assertTrue(all(gear.ammo is None for gear in templates.TEMPLATES["bounty_hunter"]["gear"]))
        self.assertIsNone(creation.GEAR["blaster_pistol"].ammo)

    def test_internal_k4_rifle_keeps_printed_ranges_and_actual_owner(self):
        hero, _ = creation.build(custom(species_id="droid", droid_model="k4", owner="Owner", attributes={}, equipment=[],
            skill_dice={"blaster": 2, "dodge": 2, "search": 2, "first_aid": 2, "droid_repair": 2}))
        rifle = hero.inventory[0]
        self.assertEqual((rifle.name, rifle.damage, rifle.d6_ranges, rifle.ammo, rifle.equipped_by), ("Internal Blaster Rifle", "5D", (5, 30, 100, 200), 100, hero.id))

    def test_recruit_and_save_load_keep_actual_loadout_and_depleted_ammunition(self):
        hero, _ = creation.build(custom())
        session = GameSession(edition="weg_d6", character=hero, source_folders=[])
        with patch.object(routes, "_ACTIVE_SESSION", session):
            req = stock("wookiee_first_mate").model_copy(update={"expected_updated_at": session.updated_at})
            session = template_api.recruit(req)["session"]
            companion = session.character.companions[-1]
            weapon = next(gear for gear in session.character.inventory if gear.id == companion.d6_weapon.id)
            self.assertTrue(weapon.equipped)
            self.assertEqual(weapon.equipped_by, companion.id)
            weapon.ammo, weapon.power_ammo = 1, 2
            session.character.inventory[0].ammo = None  # Existing unknown legacy metadata must remain unknown.
            with tempfile.TemporaryDirectory() as directory:
                manager = SaveManager(directory)
                restored = manager.load_session(manager.save_session(session, "actual_starter_gear"))
            saved = next(gear for gear in restored.character.inventory if gear.id == weapon.id)
            self.assertEqual((saved.ammo, saved.power_ammo, saved.equipped_by, saved.equipped), (1, 2, companion.id, True))
            self.assertIsNone(restored.character.inventory[0].ammo)

    def test_custom_recruit_preserves_its_new_companion_owner_and_armor(self):
        hero, _ = creation.build(custom())
        session = GameSession(edition="weg_d6", character=hero, source_folders=[])
        with patch.object(routes, "_ACTIVE_SESSION", session):
            result = creation_api.recruit(custom(name="Recruit", expected_updated_at=session.updated_at))
        person = result["session"].character.companions[-1]
        owned = [gear for gear in result["session"].character.inventory if gear.equipped_by == person.id]
        self.assertTrue(any(gear.equipped and gear.item_type == "armor" for gear in owned))
        self.assertTrue(any(gear.equipped and gear.id == person.d6_weapon.id for gear in owned))


if __name__ == "__main__":
    unittest.main()
