import unittest

from dungeonforge.campaign.campaign_manager import CampaignManager
from dungeonforge.context.weg_equipment_context import build_equipment_context
from dungeonforge.game.models import GameSession
from dungeonforge.rules import weg_equipment as equipment
from dungeonforge.rules.base import Item
from dungeonforge.rules.weg_equipment_models import EquipmentPurchaseRecord, EquipmentPurchaseRequest, EquipmentWorkProject, EquipmentWorkRequest


class EquipmentContextTests(unittest.TestCase):
    def setUp(self):
        character = CampaignManager.load_campaign("star_wars_d6").starter_character
        self.session = GameSession(edition="weg_d6", character=character)
        self.session.character.inventory = []

    def test_actual_ammo_damage_profile_and_owner_survive_serialization_without_mutation(self):
        weapon = equipment.make_item("bowcaster")
        weapon.equipped = True
        weapon.equipped_by = self.session.character.id
        weapon.ammo, weapon.power_ammo = 2, 7
        weapon.weapon_damage_state = "heavily_damaged"
        armor = equipment.make_item("blast_helmet")
        armor.equipped, armor.equipped_by = True, self.session.character.id
        armor.armor_damage_state = "lightly_damaged"
        self.session.character.inventory = [weapon, armor]
        before = self.session.model_dump()
        text = build_equipment_context(self.session)
        self.assertIn("ammunition 2/6", text)
        self.assertIn("separate power 7/50", text)
        self.assertIn("weapon condition heavily_damaged", text)
        self.assertIn("armor condition lightly_damaged", text)
        self.assertIn("coverage head; sides front,back", text)
        self.assertIn(f"equipped by {self.session.character.name}", text)
        self.assertEqual(before, self.session.model_dump())
        loaded = GameSession.model_validate_json(self.session.model_dump_json())
        self.assertEqual(text, build_equipment_context(loaded))

    def test_paid_purchase_and_pending_retry_do_not_grant_future_improvement_or_charge_twice(self):
        item = equipment.make_item("blaster_dl18")
        self.session.character.inventory = [item]
        purchase = EquipmentPurchaseRequest(catalog_id="blaster_dl18", reason="Actual licensed seller.", availability_confirmed=True, legal_basis="licensed", permit_confirmed=True)
        self.session.d6_equipment.purchases.append(EquipmentPurchaseRecord(actor_id=self.session.character.id,
            quote=equipment.quote_purchase(purchase, self.session.character), inventory_ids=[item.id], legal_basis="licensed", reason=purchase.reason))
        req = EquipmentWorkRequest(item_id=item.id, operation="improve", target_pips=1, reason="Actual suitable parts and bench.")
        project = EquipmentWorkProject(request=req, quote=equipment.quote_work(item, req), paid_credits=75,
            attempts=[{"actor_id": self.session.character.id, "minutes": 15, "success": False, "cp": 1, "fp": False}])
        self.session.d6_equipment.work_projects.append(project)
        text = build_equipment_context(self.session)
        self.assertIn("500 credits ALREADY PAID", text)
        self.assertIn("75 parts credits ALREADY PAID ONCE", text)
        self.assertIn("pending project has not granted this improvement", text)
        self.assertIn("Next standard attempt 60 minutes", text)
        self.assertIn("15 minutes already elapsed; failed; 1 CP", text)
        self.assertIn("actual item fingerprint matches", text)
        item.weapon_damage_state = "lightly_damaged"
        self.assertIn("actual item changed", build_equipment_context(self.session))

    def test_legacy_unknown_ammo_is_not_enriched_and_limits_preserve_omission_counts(self):
        self.session.character.inventory = [Item(name="Legacy GM blaster", item_type="weapon", damage="4D", equipped=True)]
        text = build_equipment_context(self.session)
        self.assertIn("ammunition not recorded; do not assume a full supply", text)
        self.assertIn("no actual native armor profile worn", text)
        self.assertIn("1 further inventory records omitted", build_equipment_context(self.session, max_items=0))
        self.session.edition = "5e"
        self.assertEqual(build_equipment_context(self.session), "")
