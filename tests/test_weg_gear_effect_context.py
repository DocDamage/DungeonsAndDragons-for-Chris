import unittest

from dungeonforge.api import routes
from dungeonforge.api import weg_gear_effect_routes as api
from dungeonforge.campaign.campaign_manager import CampaignManager
from dungeonforge.context.weg_gear_effect_context import build_gear_effect_context
from dungeonforge.context.weg_equipment_context import build_equipment_context
from dungeonforge.game.models import GameSession
from dungeonforge.rules.weg_equipment import make_item
from dungeonforge.rules.weg_gear_effect_models import GearFactsRequest, GearPrepareRequest


class GearContextTests(unittest.TestCase):
    def test_actual_preparation_witness_conditions_and_source_limits_are_readonly_and_saved(self):
        session = GameSession(edition="weg_d6", character=CampaignManager.load_campaign("star_wars_d6").starter_character)
        macro, weapon = make_item("macrobinoculars"), make_item("blaster_rifle")
        weapon.equipped, weapon.equipped_by = True, session.character.id
        session.character.inventory = [macro, weapon]
        old = routes._ACTIVE_SESSION
        try:
            routes._ACTIVE_SESSION = session
            api.configure(GearFactsRequest(actor_id=session.character.id, expected_updated_at=session.updated_at,
                macro_item_id=macro.id, macro_functional=True, macro_mode="linked", linked_weapon_id=weapon.id,
                target_id="Actual tower guard", view_distance_m=200, software_confirmed=True,
                software_facts="Actual installed compatible source linkage software.", steady_rest=True,
                reason="Actual stable position, target and instruments."))
            api.prepare(GearPrepareRequest(actor_id=session.character.id, target_id="Actual tower guard",
                expected_updated_at=session.updated_at, reason="Actual complete preparation round."))
            before = session.model_dump()
            text = build_gear_effect_context(session)
            self.assertIn("actual server action-history witness verified True", text)
            self.assertIn("Next-action conditions current True", text)
            self.assertIn("native medium/long range", text)
            self.assertIn("External gear dice are not Force Point doubled", text)
            self.assertIn(text, build_equipment_context(session))
            self.assertEqual(session.model_dump(), before)
            loaded = GameSession.model_validate_json(session.model_dump_json())
            self.assertEqual(text, build_gear_effect_context(loaded))
            loaded.character.inventory[0].equipped_by = "someone_else"
            self.assertIn("actual source instrument function valid False", build_gear_effect_context(loaded))
        finally:
            routes._ACTIVE_SESSION = old

    def test_default_off_and_non_d6_add_no_conditional_claims(self):
        session = GameSession(edition="weg_d6", character=CampaignManager.load_campaign("star_wars_d6").starter_character)
        self.assertEqual(build_gear_effect_context(session), "")
        session.edition = "5e"
        self.assertEqual(build_gear_effect_context(session), "")
