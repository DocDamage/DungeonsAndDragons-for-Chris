"""1992 personal catalog facts, actual equipment identity and paid work lifecycle."""
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from dungeonforge.api import routes
from dungeonforge.campaign.campaign_manager import CampaignManager
from dungeonforge.game.models import GameSession
from dungeonforge.game.saves import SaveManager
from dungeonforge.main import app
from dungeonforge.rules import weg_equipment as rules
from dungeonforge.rules.base import Item
from dungeonforge.rules.dice import RollResult
from dungeonforge.rules.weg_d6 import D6Roller


def roll(total):
    return RollResult(expression="Controlled equipment roll", dice_count=4, die_type=6,
        total=total, system="weg_d6", breakdown=f"Controlled equipment total {total}")


class EquipmentSourceTests(unittest.TestCase):
    def test_visually_checked_prices_capacities_and_restrictions_are_1992(self):
        for id, cost, capacity in [("holdout_q2", 275, 6), ("sporting_defender", 350, 50),
                ("blaster_dl18", 500, 100), ("heavy_blaster_dl44", 750, 25),
                ("blaster_carbine", 900, 100), ("blaster_rifle", 1000, 100),
                ("sporting_rifle", 900, 100), ("light_repeating_blaster", 2000, 25)]:
            item = rules.make_item(id)
            self.assertEqual((item.unit_cost, item.ammo, item.ammo_capacity), (cost, capacity, capacity))
        self.assertEqual(rules.make_item("bowcaster").power_ammo_capacity, 50)
        self.assertTrue(rules.make_item("e_web").requires_generator)
        self.assertIsNone(rules.ITEMS["lightsaber"]["cost"])
        self.assertTrue(rules.ITEMS["stormtrooper_armor"]["special_purchase"])
        self.assertIsNone(rules.ITEMS["bowcaster_power_pack"]["cost"])
        self.assertEqual(rules.ITEMS["asset_ghtroc"]["cost"], 98500)

    def test_armor_profiles_preserve_source_locations_sides_and_pips(self):
        helmet, vest = rules.make_item("blast_helmet"), rules.make_item("blast_vest")
        self.assertEqual((helmet.armor_energy, helmet.armor_physical), ("0D+1", "1D"))
        self.assertEqual((helmet.armor_locations, helmet.armor_sides), (["head"], ["front", "back"]))
        self.assertEqual((vest.armor_locations, vest.armor_sides), (["torso"], ["front"]))
        self.assertEqual(rules.make_item("vibroaxe").d6_damage_max, "7D")
        self.assertEqual(rules.make_item("vibroblade").d6_damage_max, "6D+2")

    def test_each_instantiation_has_its_own_physical_identity(self):
        first, second = rules.make_item("blaster_dl18"), rules.make_item("blaster_dl18")
        self.assertNotEqual(first.id, second.id)
        first.ammo = 0
        self.assertEqual(second.ammo, 100)


class EquipmentAPITests(unittest.TestCase):
    def setUp(self):
        preset = CampaignManager.load_campaign("star_wars_d6")
        self.session = GameSession(edition="weg_d6", character=preset.starter_character)
        self.session.character.d6.credits = 100000
        self.session.character.d6.skills.update(armor_repair="6D", blaster_repair="6D")
        active = patch.object(routes, "_ACTIVE_SESSION", self.session)
        active.start()
        self.addCleanup(active.stop)
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def post(self, endpoint, **changes):
        return self.client.post(f"/api/weg-d6/equipment/{endpoint}", json={
            "reason": "GM confirms the actual seller, stock, facilities and equipment procedure.",
            "expected_updated_at": self.session.updated_at, **changes})

    def buy(self, catalog_id, quantity=1, **changes):
        response = self.post("purchase", catalog_id=catalog_id, quantity=quantity,
            availability_confirmed=True, legal_basis="authorized", permit_confirmed=True,
            special_acquisition_confirmed=True, **changes)
        self.assertEqual(response.status_code, 200, response.text)
        ids = self.session.d6_equipment.purchases[-1].inventory_ids
        return [item for item in self.session.character.inventory if item.id in ids]

    def loadout(self, weapon=None, armor=None, **changes):
        return self.post("loadout", weapon_id=weapon.id if weapon else None,
            armor_ids=[item.id for item in (armor or [])], **changes)

    def begin_work(self, item, **changes):
        response = self.post("work-begin", item_id=item.id, **changes)
        self.assertEqual(response.status_code, 200, response.text)
        return self.session.d6_equipment.work_projects[-1]

    def test_catalog_and_quote_are_readonly_then_stale_purchase_rejects_atomically(self):
        before = self.session.model_dump()
        self.assertEqual(self.client.get("/api/weg-d6/equipment/catalog").status_code, 200)
        response = self.post("quote", catalog_id="medpac", quantity=2, availability_confirmed=True)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["quote"]["total"], 200)
        self.assertEqual(self.session.model_dump(), before)
        stale = self.post("purchase", catalog_id="medpac", quantity=2,
            availability_confirmed=True, expected_updated_at=self.session.updated_at - 1)
        self.assertEqual(stale.status_code, 400)
        self.assertEqual(self.session.model_dump(), before)

    def test_purchase_charges_once_and_makes_distinct_persistent_weapon_records(self):
        weapons = self.buy("blaster_dl18", quantity=2)
        self.assertEqual(self.session.character.d6.credits, 99000)
        self.assertEqual(len({item.id for item in weapons}), 2)
        weapons[0].ammo = 3
        self.assertEqual(weapons[1].ammo, 100)
        with tempfile.TemporaryDirectory() as folder:
            manager = SaveManager(folder)
            loaded = manager.load_session(manager.save_session(self.session, "equipment_identity"))
        actual = {item.id: item for item in loaded.character.inventory}
        self.assertEqual((actual[weapons[0].id].ammo, actual[weapons[1].id].ammo), (3, 100))
        self.assertEqual(loaded.d6_equipment.purchases[-1].inventory_ids, [item.id for item in weapons])

    def test_actual_availability_license_and_exceptional_source_facts_required(self):
        cases = [dict(catalog_id="medpac"),
            dict(catalog_id="blaster_rifle", availability_confirmed=True),
            dict(catalog_id="blaster_rifle", availability_confirmed=True, legal_basis="authorized"),
            dict(catalog_id="stormtrooper_armor", availability_confirmed=True,
                legal_basis="authorized", permit_confirmed=True),
            dict(catalog_id="lightsaber", availability_confirmed=True, legal_basis="black_market",
                special_acquisition_confirmed=True)]
        for payload in cases:
            with self.subTest(payload=payload):
                before = self.session.model_dump()
                self.assertEqual(self.post("purchase", **payload).status_code, 400)
                self.assertEqual(self.session.model_dump(), before)
        self.buy("lightsaber", unit_price=4000)
        self.assertEqual(self.session.d6_equipment.purchases[-1].quote.total, 4000)

    def test_asset_reference_does_not_create_fictional_personal_inventory(self):
        before = self.session.model_dump()
        response = self.post("purchase", catalog_id="asset_yt1300",
            availability_confirmed=True, legal_basis="authorized", permit_confirmed=True)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.session.model_dump(), before)

    def test_bowcaster_seller_restriction_and_unlisted_supply_prices(self):
        before = self.session.model_dump()
        self.assertEqual(self.post("purchase", catalog_id="bowcaster", availability_confirmed=True,
            legal_basis="licensed", permit_confirmed=True).status_code, 400)
        self.assertEqual(self.session.model_dump(), before)
        self.session.character.d6.species_id = "wookiee"
        self.buy("bowcaster")
        before = self.session.model_dump()
        self.assertEqual(self.post("purchase", catalog_id="bowcaster_power_pack",
            availability_confirmed=True).status_code, 400)
        self.assertEqual(self.session.model_dump(), before)
        self.buy("bowcaster_power_pack", unit_price=30)

    def test_actual_loadout_accepts_helmet_vest_and_rejects_overlap_atomically(self):
        helmet, vest, suit = self.buy("blast_helmet")[0], self.buy("blast_vest")[0], self.buy("bounty_hunter_armor")[0]
        self.assertEqual(self.loadout(armor=[helmet, vest], use_legacy_armor=False).status_code, 200)
        before = self.session.model_dump()
        response = self.loadout(armor=[suit, helmet], use_legacy_armor=False)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.session.model_dump(), before)

    def test_loadout_preserves_explicit_gm_baseline_without_stacking(self):
        initial = self.session.character.d6.armor_energy, self.session.character.d6.armor_physical, self.session.character.d6.dexterity_penalty
        helmet = self.buy("blast_helmet")[0]
        self.assertEqual(self.loadout(armor=[helmet], use_legacy_armor=False).status_code, 200)
        self.assertEqual(self.session.character.d6.armor_energy, "0D+1")
        self.assertEqual(self.loadout(use_legacy_armor=False).status_code, 200)
        self.assertEqual((self.session.character.d6.armor_energy, self.session.character.d6.armor_physical), ("0D", "0D"))
        self.assertEqual(self.loadout(use_legacy_armor=True).status_code, 200)
        actual = self.session.character.d6
        self.assertEqual((actual.armor_energy, actual.armor_physical, actual.dexterity_penalty), initial)

    def test_companion_weapon_is_actual_item_and_cannot_be_double_assigned(self):
        weapon = self.buy("blaster_dl18")[0]
        companion = self.session.character.companions[0]
        self.assertEqual(self.loadout(weapon=weapon, actor_id=companion.id, use_legacy_armor=True).status_code, 200)
        self.assertEqual(self.session.character.companions[0].d6_weapon.id, weapon.id)
        before = self.session.model_dump()
        self.assertEqual(self.loadout(weapon=weapon).status_code, 400)
        self.assertEqual(self.session.model_dump(), before)
        self.assertEqual(self.loadout(actor_id=companion.id, use_legacy_armor=True).status_code, 200)
        self.assertEqual(self.session.character.companions[0].d6_weapon.d6_skill, "brawling")

    def test_standard_reload_consumes_actual_compatible_pack_and_one_scene_round(self):
        weapon = self.buy("blaster_dl18")[0]
        packs = self.buy("standard_blaster_power_pack", quantity=2)[0]
        self.assertEqual(self.loadout(weapon=weapon).status_code, 200)
        weapon = rules.inventory_item(self.session, weapon.id)
        weapon.ammo = 0
        response = self.post("reload", item_id=weapon.id)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(rules.inventory_item(self.session, weapon.id).ammo, 100)
        self.assertEqual(rules.inventory_item(self.session, packs.id).quantity, 1)
        self.assertEqual(self.session.character.d6.force.elapsed_rounds, 1)
        self.assertEqual(self.session.character.companions[0].d6.force.elapsed_rounds, 1)
        before = self.session.model_dump()
        self.assertEqual(self.post("reload", item_id=weapon.id).status_code, 400)
        self.assertEqual(self.session.model_dump(), before)

    def test_wrong_reload_supply_rejects_before_time_or_consumption(self):
        weapon = self.buy("holdout_q2")[0]
        self.buy("standard_blaster_power_pack")
        self.assertEqual(self.loadout(weapon=weapon).status_code, 200)
        rules.inventory_item(self.session, weapon.id).ammo = 0
        before = self.session.model_dump()
        self.assertEqual(self.post("reload", item_id=weapon.id).status_code, 400)
        self.assertEqual(self.session.model_dump(), before)

    def test_bowcaster_failed_strength_uses_action_but_preserves_both_supplies(self):
        self.session.character.d6.species_id = "wookiee"
        weapon = self.buy("bowcaster")[0]
        quarrels = self.buy("bowcaster_quarrels", unit_price=12)[0]
        power = self.buy("bowcaster_power_pack", unit_price=30)[0]
        self.assertEqual(self.loadout(weapon=weapon).status_code, 200)
        actual = rules.inventory_item(self.session, weapon.id)
        actual.ammo, actual.power_ammo = 0, 0
        with patch.object(D6Roller, "values", return_value=roll(1)):
            response = self.post("reload", item_id=weapon.id, primary=True, power=True)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertFalse(response.json()["eval_result"]["success"])
        self.assertEqual(rules.inventory_item(self.session, quarrels.id).quantity, 1)
        self.assertEqual(rules.inventory_item(self.session, power.id).quantity, 1)
        self.assertEqual(self.session.character.d6.round_state.actions_taken, 1)
        with patch.object(D6Roller, "values", return_value=roll(20)):
            response = self.post("reload", item_id=weapon.id, primary=True, power=True)
        self.assertEqual(response.status_code, 200, response.text)
        actual = rules.inventory_item(self.session, weapon.id)
        self.assertEqual((actual.ammo, actual.power_ammo), (6, 50))
        self.assertNotIn(quarrels.id, [item.id for item in self.session.character.inventory])
        self.assertNotIn(power.id, [item.id for item in self.session.character.inventory])

    def test_bowcaster_two_feed_validation_is_atomic_before_strength_roll(self):
        self.session.character.d6.species_id = "wookiee"
        weapon = self.buy("bowcaster")[0]
        self.buy("bowcaster_quarrels", unit_price=12)
        self.assertEqual(self.loadout(weapon=weapon).status_code, 200)
        actual = rules.inventory_item(self.session, weapon.id)
        actual.ammo, actual.power_ammo = 0, 0
        before = self.session.model_dump()
        with patch.object(D6Roller, "values") as dice:
            response = self.post("reload", item_id=weapon.id, primary=True, power=True)
        self.assertEqual(response.status_code, 400)
        dice.assert_not_called()
        self.assertEqual(self.session.model_dump(), before)

    def test_repair_parts_paid_once_and_failed_retry_uses_source_schedule(self):
        weapon = self.buy("blaster_dl18")[0]
        weapon.weapon_damage_state = "lightly_damaged"
        project = self.begin_work(weapon)
        self.assertEqual((project.quote.parts_cost, project.quote.difficulty), (75, 10))
        paid_balance = self.session.character.d6.credits
        for total in (1, 20):
            with patch.object(D6Roller, "values", return_value=roll(total)):
                response = self.post("work-attempt", project_id=project.id)
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(self.session.character.d6.credits, paid_balance)
        actual = rules.inventory_item(self.session, weapon.id)
        saved = self.session.d6_equipment.work_projects[-1]
        self.assertEqual(actual.weapon_damage_state, "intact")
        self.assertEqual(saved.status, "completed")
        self.assertEqual([attempt["minutes"] for attempt in saved.attempts], [15, 60])
        self.assertEqual(self.session.character.d6.force.elapsed_rounds, 900)

    def test_work_fingerprint_change_rejects_without_time_and_cancel_has_no_refund(self):
        weapon = self.buy("blaster_dl18")[0]
        weapon.weapon_damage_state = "lightly_damaged"
        project = self.begin_work(weapon)
        rules.inventory_item(self.session, weapon.id).weapon_damage_state = "heavily_damaged"
        before = self.session.model_dump()
        with patch.object(D6Roller, "values") as dice:
            response = self.post("work-attempt", project_id=project.id)
        self.assertEqual(response.status_code, 400)
        dice.assert_not_called()
        self.assertEqual(self.session.model_dump(), before)
        wallet = self.session.character.d6.credits
        self.assertEqual(self.post("work-cancel", project_id=project.id).status_code, 200)
        self.assertEqual(self.session.character.d6.credits, wallet)

    def test_blaster_improvements_are_from_original_and_capped_at_five_pips(self):
        weapon = self.buy("blaster_dl18")[0]
        for target, expected in ((1, "4D+1"), (2, "4D+2"), (5, "5D+2")):
            actual = rules.inventory_item(self.session, weapon.id)
            project = self.begin_work(actual, operation="improve", target_pips=target)
            with patch.object(D6Roller, "values", return_value=roll(50)):
                response = self.post("work-attempt", project_id=project.id)
            self.assertEqual(response.status_code, 200, response.text)
            actual = rules.inventory_item(self.session, weapon.id)
            self.assertEqual((actual.damage, actual.original_damage), (expected, "4D"))
        before = self.session.model_dump()
        self.assertEqual(self.post("work-begin", item_id=weapon.id, operation="improve", target_pips=6).status_code, 422)
        self.assertEqual(self.session.model_dump(), before)

    def test_armor_improvement_preserves_other_profile_and_actual_coverage(self):
        vest = self.buy("blast_vest")[0]
        project = self.begin_work(vest, operation="improve", armor_profile="physical", target_pips=5)
        with patch.object(D6Roller, "values", return_value=roll(50)):
            response = self.post("work-attempt", project_id=project.id)
        self.assertEqual(response.status_code, 200, response.text)
        actual = rules.inventory_item(self.session, vest.id)
        self.assertEqual((actual.armor_physical, actual.original_armor_physical, actual.armor_energy), ("2D+2", "1D", "0D+1"))
        self.assertEqual((actual.armor_locations, actual.armor_sides), (["torso"], ["front"]))

    def test_destroyed_gear_and_unlisted_melee_procedures_cannot_be_repaired(self):
        blaster, knife = self.buy("blaster_dl18")[0], self.buy("knife")[0]
        blaster.weapon_damage_state = "destroyed"
        knife.weapon_damage_state = "heavily_damaged"
        for item in (blaster, knife):
            before = self.session.model_dump()
            self.assertEqual(self.post("work-begin", item_id=item.id).status_code, 400)
            self.assertEqual(self.session.model_dump(), before)

    def test_saved_paid_work_and_unknown_legacy_ammunition_are_not_refilled(self):
        legacy = Item(name="Old GM blaster", item_type="weapon", damage="4D", d6_skill="blaster")
        self.session.character.inventory.append(legacy)
        weapon = self.buy("blaster_dl18")[0]
        weapon.weapon_damage_state = "heavily_damaged"
        project = self.begin_work(weapon)
        with tempfile.TemporaryDirectory() as folder:
            manager = SaveManager(folder)
            loaded = manager.load_session(manager.save_session(self.session, "paid_personal_work"))
        self.assertEqual(loaded.d6_equipment.work_projects[-1].id, project.id)
        self.assertEqual(loaded.d6_equipment.work_projects[-1].paid_credits, 125)
        old = next(item for item in loaded.character.inventory if item.id == legacy.id)
        self.assertIsNone(old.ammo)
        self.assertIsNone(old.ammo_capacity)


if __name__ == "__main__":
    unittest.main()
