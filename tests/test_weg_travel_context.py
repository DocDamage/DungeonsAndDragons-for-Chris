import json
from pathlib import Path
import tempfile
import unittest

from dungeonforge.context.pipeline import ContextPipeline
from dungeonforge.context.story_cards import StoryCardManager
from dungeonforge.game.models import GameSession
from dungeonforge.game.saves import SaveManager
from dungeonforge.game.weg_vehicle_presets import vehicle_presets
from dungeonforge.rules.base import Character, Item
from dungeonforge.rules.weg_engineering_models import D6CraftRepairProject, D6CraftRepairQuote, D6CraftRepairRequest
from dungeonforge.rules.weg_models import D6Character
from dungeonforge.rules.weg_navigation_models import D6Journey, D6NavigationQuote, D6NavigationRequest
from dungeonforge.rules.weg_vehicle_models import D6VehicleEncounter


class TravelContextTests(unittest.TestCase):
    def setUp(self):
        self.craft = vehicle_presets()["yt1300"]
        self.craft.id, self.craft.location = "test_ship", "Tatooine"
        self.craft.damage, self.craft.maneuverability_lost = "heavily_damaged", 1
        self.craft.hull_breached = self.craft.nav_computer_disabled = self.craft.escape_pods_disabled = True
        self.craft.weapons[0].purchase_value = 1200
        self.craft.weapons[0].status, self.craft.weapons[0].repair_damage = "destroyed", "destroyed"
        self.session = GameSession(
            id="travel_context_test", edition="weg_d6", title="Unfinished flight", campaign_name="Rebel flight",
            character=Character(id="hero", name="Pilot", edition="weg_d6", d6=D6Character(credits=9000, vacuum_unconscious=True),
                                inventory=[Item(name="Sealed suit", quantity=1, sealed_survival_suit=True), Item(name="Filter mask")]),
            vehicles=[self.craft], source_folders=[], updated_at=1234567890,
        )
        req = D6CraftRepairRequest(craft_id=self.craft.id, system="maneuverability", reason="Actual actuator parts in a repair bay.")
        self.project = D6CraftRepairProject(
            id="repair_saved", request=req,
            quote=D6CraftRepairQuote(craft_id=self.craft.id, key="maneuverability", skill="space_transports_repair", difficulty=10,
                                    parts_cost=10000, percent=10, fingerprint="recorded-damage"),
            paid_credits=10000, parts_source="credits",
            attempts=[{"actor_id": "hero", "minutes": 15, "success": False, "cp": 1, "fp": False,
                       "roll": {"total": 4, "breakdown": "saved failed repair roll"}}],
        )
        self.craft.repair_projects.append(self.project)
        self.journey = D6Journey(
            id="journey_saved", request=D6NavigationRequest(craft_id=self.craft.id, origin="Tatooine", destination="Corellia",
                                                          reason="GM confirms actual boarding and route."),
            quote=D6NavigationQuote(difficulty=15, hours=8, rounds=5760, has_navigation=True, multiplier=2),
            status="emergency", remaining_rounds=5000, elapsed_rounds=760, roll={"total": 10}, miss=5, mishap=11,
            travellers=["hero"], emergency_round=2,
            crew_exposure={"hero": {"protected": False, "phase": "unconscious", "suit_round": 1, "breath_round": 2,
                                     "suit_name": None},
                           "actor_round:hero": {"protected": True, "phase": "action_tracker", "last_action_round": 2}},
            resolution=["Collision ruptured the hull; rescue remains unresolved."],
            auxiliary_rolls=[{"expression": "2d6", "total": 11, "breakdown": "plain mishap: 5 + 6"}],
        )
        self.session.d6_navigation.journeys.append(self.journey)

    def chronicle(self):
        with tempfile.TemporaryDirectory() as directory:
            return SaveManager(directory).export_markdown_chronicle(self.session)

    def test_context_contains_actual_state_and_blocks_fabricated_travel_or_repairs(self):
        before = self.session.model_dump()
        summary = ContextPipeline.native_travel_summary(self.session)
        messages = ContextPipeline.assemble(
            character=self.session.character, memory=self.session.memory, story_card_manager=StoryCardManager(),
            authors_note=self.session.authors_note, history=[], current_input="Describe the situation", current_mode="story",
            vehicle_summary=summary,
        )
        prompt = messages[1]["content"]
        for fact in ("Last recorded realspace location: Tatooine", "main hyperdrive x2", "backup hyperdrive x12",
                     "nav computer installed True", "nav computer disabled True", "escape pods disabled True", "hull breached True",
                     "repair damage destroyed", "purchase value 1200 credits", "status emergency", "remaining 5000 rounds",
                     "roll 10 vs 15", "paid once 10000 credits", "next standard attempt 60 minutes", "saved failed repair roll",
                     "Actual sealed survival suits in inventory: Sealed suit x1", "vacuum unconscious True", "Emergency action tracker actor_round:hero"):
            self.assertIn(fact, prompt)
        self.assertIn("A route destination is an intention until the saved journey status is arrived", prompt)
        self.assertIn("Never fabricate arrival, hull repair", prompt)
        self.assertIn("cancellation gives no automatic refund", prompt)
        self.assertEqual(self.session.model_dump(), before)

    def test_each_pending_navigation_ruling_keeps_saved_roll_location_and_damage(self):
        pending = {
            "ten_point_ruling": "saved miss of exactly ten without rerolling",
            "awaiting_location": "actual dropout location; the intended destination is not established",
            "close_call_pending": "select the actual damaged system",
            "exposure_pending": "identify the actually exposed crew",
            "emergency": "ordinary time advancement is blocked",
        }
        for status, instruction in pending.items():
            with self.subTest(status=status):
                self.journey.status = status
                before = self.session.model_dump()
                text = ContextPipeline.native_travel_summary(self.session)
                self.assertIn(f"status {status}", text)
                self.assertIn(instruction, text)
                self.assertEqual(self.session.model_dump(), before)

    def test_export_records_failed_paid_work_emergency_and_actual_equipment(self):
        before = self.session.model_dump()
        text = self.chronicle()
        for fact in ("**Craft:** Stock YT-1300 Transport", "heavily damaged", "hull breached True", "parts value 10000 credits",
                     "paid once 10000 credits", "Repair attempt 1: failed", "roll 4 vs 10; CP 1; FP False",
                     "Tatooine → Corellia", "status emergency", "Vacuum emergency round: 2", "'phase': 'unconscious'",
                     "Crew exposure Pilot [hero]", "Collision ruptured the hull", "Saved plain mishap roll: 2d6 = 11"):
            self.assertIn(fact, text)
        self.assertNotIn("Never fabricate", text)
        self.assertNotIn("status arrived", text)
        self.assertEqual(self.session.model_dump(), before)

    def test_project_statuses_do_not_erase_other_damage_or_refund_cancelled_work(self):
        for status in ("completed", "cancelled"):
            with self.subTest(status=status):
                self.project.status = status
                text = self.chronicle()
                self.assertIn(f"status {status}", text)
                self.assertIn("paid once 10000 credits", text)
                self.assertIn("hull breached True", text)
                self.assertIn("repair damage destroyed", text)
                self.assertNotIn("Pending repair: reserved materials", text)
                self.assertEqual(self.session.character.d6.credits, 9000)
        self.assertIn("Cancelled repair: no automatic refund", text)

    def test_live_encounter_copy_is_exported_once_and_does_not_hide_other_fleet(self):
        live = self.craft.model_copy(deep=True)
        live.generator_shutdown, live.destruction_countdown, live.destruction_cause = True, 2, "generator"
        other = vehicle_presets()["tie_fighter"]
        other.id = "other_ship"
        self.session.vehicles.append(other)
        self.session.vehicle_encounter = D6VehicleEncounter(craft=[live], round=3)
        text = self.chronicle()
        self.assertEqual(text.count("**Craft:** Stock YT-1300 Transport"), 1)
        self.assertIn("COMBAT, ROUND 3", text)
        self.assertIn("generator shutdown True", text)
        self.assertIn("destruction countdown 2 (cause generator)", text)
        self.assertIn("**Craft:** TIE/ln Fighter", text)
        self.assertFalse(self.craft.generator_shutdown)

    def test_save_load_preserves_pending_emergency_paid_project_and_export(self):
        with tempfile.TemporaryDirectory() as directory:
            manager = SaveManager(directory)
            loaded = manager.load_session(manager.save_session(self.session, "pending"))
            self.assertEqual(loaded.d6_navigation.model_dump(), self.session.d6_navigation.model_dump())
            self.assertEqual(loaded.vehicles[0].model_dump(), self.craft.model_dump())
            self.assertEqual(loaded.character.d6.vacuum_unconscious, True)
            self.assertEqual(loaded.character.d6.credits, 9000)
            self.assertEqual(ContextPipeline.native_travel_summary(loaded), ContextPipeline.native_travel_summary(self.session))
            exported = manager.export_markdown_chronicle(loaded)
            self.assertIn("status emergency", exported)
            self.assertIn("paid once 10000 credits", exported)

    def test_legacy_migration_fills_only_missing_stock_equipment_and_preserves_explicit_values(self):
        data = self.session.model_dump()
        missing = data["vehicles"][0]
        for field in ("hyperdrive_multiplier", "backup_hyperdrive", "nav_computer", "purchase_value"):
            missing.pop(field)
        explicit = self.craft.model_dump()
        explicit.update(hyperdrive_multiplier=None, backup_hyperdrive=None, nav_computer=False, purchase_value=0)
        data["vehicle_encounter"] = D6VehicleEncounter(craft=[]).model_dump()
        data["vehicle_encounter"]["craft"].append(explicit)
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "legacy.json").write_text(json.dumps(data), encoding="utf-8")
            loaded = SaveManager(directory).load_session("legacy")
        self.assertEqual((loaded.vehicles[0].hyperdrive_multiplier, loaded.vehicles[0].backup_hyperdrive,
                          loaded.vehicles[0].nav_computer, loaded.vehicles[0].purchase_value), (2, 12, True, 100000))
        encounter = loaded.vehicle_encounter.craft[0]
        self.assertEqual((encounter.hyperdrive_multiplier, encounter.backup_hyperdrive, encounter.nav_computer, encounter.purchase_value),
                         (None, None, False, 0))
        self.assertTrue(loaded.vehicles[0].hull_breached)
        self.assertEqual(loaded.d6_navigation.model_dump(), self.session.d6_navigation.model_dump())
        self.assertEqual(loaded.vehicles[0].repair_projects[0].model_dump(), self.project.model_dump())


if __name__ == "__main__":
    unittest.main()
