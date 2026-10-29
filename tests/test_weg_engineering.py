"""Paid craft repairs follow the 1992 tables and survive retries and saves."""
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from dungeonforge.api import routes
from dungeonforge.campaign.campaign_manager import CampaignManager
from dungeonforge.game.models import GameSession
from dungeonforge.game.saves import SaveManager
from dungeonforge.game.weg_vehicle_presets import vehicle_presets
from dungeonforge.main import app
from dungeonforge.rules import weg_engineering as engineering
from dungeonforge.rules.base import Companion, Item
from dungeonforge.rules.dice import RollResult
from dungeonforge.rules.weg_d6 import D6Roller, WEGD6Rules
from dungeonforge.rules.weg_engineering_models import D6CraftRepairRequest
from dungeonforge.rules.weg_models import D6Character
from dungeonforge.rules.weg_navigation_models import D6Journey, D6NavigationQuote, D6NavigationRequest


def controlled_roll(total):
    return RollResult(expression="4D", dice_count=4, die_type=6, total=total,
        system="weg_d6", breakdown=f"Controlled engineering total {total}")


class EngineeringRulesTests(unittest.TestCase):
    def setUp(self):
        self.craft = vehicle_presets()["yt1300"]

    def request(self, system="maneuverability", **changes):
        return D6CraftRepairRequest(craft_id=self.craft.id, system=system,
            reason="The GM confirms the damaged assembly, correct parts, and workshop.", **changes)

    def test_maneuverability_moves_and_shield_source_tables(self):
        # Printed pp.87, 89-91. Each amount is lost whole dice or lost moves.
        tables = {
            "maneuverability": ("maneuverability_lost", [(1, 10, 10), (2, 15, 15), (3, 20, 20), (5, 20, 20)]),
            "moves": ("speed_losses", [(1, 10, 10), (2, 15, 15), (3, 20, 20), (4, 30, 25)]),
            "shields": ("shields_lost", [(1, 10, 5), (2, 15, 5), (3, 20, 5), (4, 30, 10), (5, 30, 10)]),
        }
        for system, (field, rows) in tables.items():
            for lost, difficulty, percent in rows:
                with self.subTest(system=system, lost=lost):
                    setattr(self.craft, field, lost)
                    result = engineering.quote(self.craft, self.request(system))
                    self.assertEqual((result.difficulty, result.percent, result.parts_cost),
                        (difficulty, percent, 1000 * percent))

    def test_drives_and_safe_shutdown_generator_use_35_percent(self):
        self.craft.drives_disabled = self.craft.generator_shutdown = True
        for system in ("drives", "generator"):
            result = engineering.quote(self.craft, self.request(system))
            self.assertEqual((result.difficulty, result.parts_cost), (20, 35000))
        self.craft.destruction_countdown = 2
        self.craft.destruction_cause = "generator"
        with self.assertRaisesRegex(ValueError, "countdown"):
            engineering.quote(self.craft, self.request("generator"))

    def test_correct_repair_skill_for_each_craft_kind(self):
        cases = [("yt1300", "space_transports_repair"), ("xwing", "starfighter_repair"),
            ("corvette", "capital_starship_repair"), ("atst", "walker_repair"),
            ("airspeeder", "repulsorlift_repair")]
        for preset, skill in cases:
            craft = vehicle_presets()[preset]
            craft.maneuverability_lost, craft.purchase_value = 1, 10000
            self.assertEqual(engineering.quote(craft, self.request()).skill, skill)
        self.craft.kind = "vehicle"
        self.craft.maneuverability_lost = 1
        for operation, skill in [("ground_vehicle_operation", "ground_vehicle_repair"),
                ("hover_vehicle_operation", "hover_vehicle_repair")]:
            self.craft.piloting_skill = operation
            self.assertEqual(engineering.quote(self.craft, self.request()).skill, skill)

    def test_gm_can_choose_within_source_band_and_cost_rounds_up(self):
        self.craft.maneuverability_lost = 1
        result = engineering.quote(self.craft, self.request(gm_difficulty=6, asset_value=101))
        self.assertEqual((result.difficulty, result.parts_cost), (6, 11))
        for difficulty in (5, 11):
            with self.assertRaisesRegex(ValueError, "source repair band"):
                engineering.quote(self.craft, self.request(gm_difficulty=difficulty))

    def test_missing_value_damage_or_actual_reason_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "no recorded damage"):
            engineering.quote(self.craft, self.request())
        self.craft.maneuverability_lost, self.craft.purchase_value = 1, 0
        with self.assertRaisesRegex(ValueError, "actual craft/weapon value"):
            engineering.quote(self.craft, self.request())
        req = self.request(asset_value=1000).model_copy(update={"reason": "   "})
        with self.assertRaisesRegex(ValueError, "actual damage"):
            engineering.quote(self.craft, req)

    def test_hyperdrive_has_moderate_difficulty_but_requires_gm_parts_price(self):
        self.craft.hyperdrive_disabled = True
        with self.assertRaisesRegex(ValueError, "GM-approved parts cost"):
            engineering.quote(self.craft, self.request("hyperdrive"))
        result = engineering.quote(self.craft, self.request("hyperdrive", gm_cost=1234))
        self.assertEqual((result.difficulty, result.parts_cost, result.percent), (15, 1234, None))
        self.assertIn("no parts price", result.notes[0])

    def test_unlisted_systems_require_explicit_gm_difficulty_and_price(self):
        for system, field in [("controls", "controls_dead"), ("weapons", "weapons_disabled"),
                ("nav_computer", "nav_computer_disabled"), ("escape_pods", "escape_pods_disabled")]:
            setattr(self.craft, field, True)
            with self.subTest(system=system):
                with self.assertRaisesRegex(ValueError, "GM repair/installation difficulty"):
                    engineering.quote(self.craft, self.request(system, gm_cost=20))
                with self.assertRaisesRegex(ValueError, "GM-approved parts cost"):
                    engineering.quote(self.craft, self.request(system, gm_difficulty=12))
                result = engineering.quote(self.craft, self.request(system, gm_difficulty=12, gm_cost=20))
                self.assertEqual((result.difficulty, result.parts_cost, result.percent), (12, 20, None))

    def test_weapon_table_uses_recorded_damage_and_actual_weapon_value(self):
        weapon = self.craft.weapons[0]
        weapon.status, weapon.purchase_value = "disabled", 1000
        for level, difficulty, cost in [("lightly_damaged", 10, 150),
                ("heavily_damaged", 15, 250), ("severely_damaged", 30, 350)]:
            weapon.repair_damage = level
            req = self.request("weapon", weapon_id=weapon.id, assessed_damage="lightly_damaged")
            result = engineering.quote(self.craft, req)
            self.assertEqual((result.skill, result.difficulty, result.parts_cost),
                ("starship_weapon_repair", difficulty, cost))
        self.craft.scale = "capital"
        self.assertEqual(engineering.quote(self.craft, req).skill, "capital_starship_weapon_repair")
        self.craft.kind, self.craft.scale = "vehicle", "speeder"
        self.assertEqual(engineering.quote(self.craft, req).skill, "blaster_repair")

    def test_destroyed_weapon_requires_replacement_and_installation_ruling(self):
        weapon = self.craft.weapons[0]
        weapon.status, weapon.repair_damage, weapon.purchase_value = "destroyed", "destroyed", 1234
        with self.assertRaisesRegex(ValueError, "cannot be repaired"):
            engineering.quote(self.craft, self.request("weapon", weapon_id=weapon.id))
        with self.assertRaisesRegex(ValueError, "installation difficulty"):
            engineering.quote(self.craft, self.request("weapon", weapon_id=weapon.id, replacement=True))
        result = engineering.quote(self.craft, self.request("weapon", weapon_id=weapon.id,
            replacement=True, gm_difficulty=12))
        self.assertEqual((result.parts_cost, result.percent, result.difficulty), (1234, 100, 12))
        self.assertIn("not repaired", result.notes[0])
        with self.assertRaisesRegex(ValueError, "cannot be repaired"):
            engineering.repair(self.craft, self.request("weapon", weapon_id=weapon.id))
        self.assertEqual((weapon.status, weapon.repair_damage), ("destroyed", "destroyed"))

    def test_actual_mounted_weapon_required(self):
        with self.assertRaisesRegex(ValueError, "actual mounted weapon"):
            engineering.quote(self.craft, self.request("weapon", weapon_id="missing"))

    def test_per_skill_repeat_times_include_walker_and_blaster_exceptions(self):
        for skill, times in [("space_transports_repair", [15, 60, 1440, 2880, 2880]),
                ("capital_starship_weapon_repair", [15, 60, 1440, 2880, 2880]),
                ("walker_repair", [15, 360, 1440, 2880, 2880]),
                ("blaster_repair", [15, 60, 120, 120, 120])]:
            self.assertEqual([engineering.attempt_minutes(skill, count) for count in range(5)], times)

    def test_quote_readonly_and_fingerprint_tracks_only_selected_damage(self):
        self.craft.maneuverability_lost = 1
        req = self.request()
        before = self.craft.model_dump()
        result = engineering.quote(self.craft, req)
        self.assertEqual(before, self.craft.model_dump())
        self.craft.speed_losses = 2
        self.assertEqual(engineering.fingerprint(self.craft, req), result.fingerprint)
        self.craft.maneuverability_lost = 2
        self.assertNotEqual(engineering.fingerprint(self.craft, req), result.fingerprint)

    def test_success_only_restores_selected_system_and_preserves_other_damage(self):
        self.craft.damage = "severely_damaged"
        self.craft.maneuverability_lost = self.craft.speed_losses = self.craft.shields_lost = 1
        self.craft.drives_disabled = self.craft.hyperdrive_disabled = self.craft.weapons_disabled = True
        self.craft.nav_computer_disabled = self.craft.escape_pods_disabled = self.craft.hull_breached = True
        weapon = self.craft.weapons[0]
        weapon.status, weapon.repair_damage = "disabled", "heavily_damaged"
        engineering.repair(self.craft, self.request())
        self.assertEqual(self.craft.maneuverability_lost, 0)
        self.assertEqual((self.craft.speed_losses, self.craft.shields_lost), (1, 1))
        self.assertTrue(self.craft.drives_disabled and self.craft.hyperdrive_disabled and self.craft.weapons_disabled)
        self.assertTrue(self.craft.nav_computer_disabled and self.craft.escape_pods_disabled and self.craft.hull_breached)
        self.assertEqual((self.craft.damage, weapon.status, weapon.repair_damage),
            ("severely_damaged", "disabled", "heavily_damaged"))

    def test_other_weapon_damage_keeps_craft_damage_recorded(self):
        self.craft.damage, self.craft.maneuverability_lost = "lightly_damaged", 1
        self.craft.weapons[0].repair_damage = "lightly_damaged"
        engineering.repair(self.craft, self.request())
        self.assertEqual(self.craft.damage, "lightly_damaged")

    def test_generator_restoration_does_not_restore_other_systems(self):
        self.craft.damage, self.craft.destruction_cause = "severely_damaged", "generator"
        self.craft.generator_shutdown = self.craft.drives_disabled = self.craft.weapons_disabled = True
        engineering.repair(self.craft, self.request("generator"))
        self.assertFalse(self.craft.generator_shutdown)
        self.assertIsNone(self.craft.destruction_cause)
        self.assertTrue(self.craft.drives_disabled and self.craft.weapons_disabled)
        self.assertEqual(self.craft.damage, "severely_damaged")

    def test_destroyed_craft_cannot_be_quoted_or_resurrected(self):
        self.craft.damage, self.craft.maneuverability_lost = "destroyed", 1
        before = self.craft.model_dump()
        for operation in (engineering.quote, engineering.repair):
            with self.assertRaisesRegex(ValueError, "destroyed craft"):
                operation(self.craft, self.request())
            self.assertEqual(before, self.craft.model_dump())


class EngineeringAPITests(unittest.TestCase):
    def setUp(self):
        preset = CampaignManager.load_campaign("star_wars_d6")
        self.session = GameSession(edition="weg_d6", character=preset.starter_character)
        self.session.character.d6.credits = 100000
        self.session.character.companions.append(Companion(id="technician", name="Ship technician",
            d6=D6Character(skills={"space_transports_repair": "6D"}, character_points=4, force_points=2)))
        craft = vehicle_presets()["yt1300"]
        craft.damage, craft.maneuverability_lost = "lightly_damaged", 1
        self.session.vehicles.append(craft)
        active = patch.object(routes, "_ACTIVE_SESSION", self.session)
        active.start()
        self.addCleanup(active.stop)
        dice = patch("dungeonforge.rules.weg_d6.random.randint", return_value=4)
        dice.start()
        self.addCleanup(dice.stop)
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    @property
    def craft(self):
        return self.session.vehicles[0]

    @property
    def project(self):
        return self.craft.repair_projects[-1]

    def request(self, **changes):
        return {**dict(craft_id=self.craft.id, system="maneuverability",
            reason="GM confirms the failed maneuver actuator, parts and workshop.",
            expected_updated_at=self.session.updated_at), **changes}

    def begin(self, **changes):
        response = self.client.post("/api/weg-d6/engineering/begin", json=self.request(**changes))
        self.assertEqual(response.status_code, 200, response.text)
        return self.project

    def attempt(self, total=30, **changes):
        with patch.object(D6Roller, "values", return_value=controlled_roll(total)) as dice:
            response = self.client.post("/api/weg-d6/engineering/attempt", json={
                "project_id": self.project.id, **changes})
        return response, dice

    def test_quote_is_readonly_and_begin_reserves_parts_once(self):
        before = self.session.model_dump()
        response = self.client.post("/api/weg-d6/engineering/quote", json=self.request())
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.session.model_dump(), before)
        project = self.begin()
        self.assertEqual((project.paid_credits, project.parts_source, self.session.character.d6.credits),
            (10000, "credits", 90000))
        self.assertEqual(project.quote.parts_cost, 10000)
        before = self.session.model_dump()
        response = self.client.post("/api/weg-d6/engineering/begin", json=self.request())
        self.assertEqual(response.status_code, 400, response.text)
        self.assertEqual(self.session.model_dump(), before)

    def test_stale_begin_and_unaffordable_parts_are_atomic(self):
        before = self.session.model_dump()
        response = self.client.post("/api/weg-d6/engineering/begin", json=self.request(expected_updated_at=-1))
        self.assertEqual(response.status_code, 400, response.text)
        self.assertEqual(before, self.session.model_dump())
        self.session.character.d6.credits = 9999
        before = self.session.model_dump()
        response = self.client.post("/api/weg-d6/engineering/begin", json=self.request())
        self.assertEqual(response.status_code, 400, response.text)
        self.assertEqual(before, self.session.model_dump())

    def test_inventory_parts_consumed_once_across_failed_retry(self):
        self.session.character.inventory.append(Item(name="Maneuver actuator kit", quantity=2))
        self.begin(parts_item="Maneuver actuator kit")
        self.assertEqual(self.project.paid_credits, 0)
        for total in (1, 30):
            response, _ = self.attempt(total)
            self.assertEqual(response.status_code, 200, response.text)
        kit = next(item for item in self.session.character.inventory if item.name == "Maneuver actuator kit")
        self.assertEqual((kit.quantity, self.session.character.d6.credits), (1, 100000))
        self.assertEqual(self.project.status, "completed")

    def test_missing_inventory_parts_do_not_charge_or_create_project(self):
        before = self.session.model_dump()
        response = self.client.post("/api/weg-d6/engineering/begin", json=self.request(parts_item="Absent kit"))
        self.assertEqual(response.status_code, 400, response.text)
        self.assertEqual(before, self.session.model_dump())

    def test_pending_navigation_rulings_block_begin_and_attempt_without_mutation(self):
        journey = D6Journey(
            request=D6NavigationRequest(craft_id=self.craft.id, origin="Tatooine", destination="Corellia",
                boarding_confirmed=True, reason="The saved route is awaiting its actual result."),
            quote=D6NavigationQuote(difficulty=15, hours=8, rounds=5760, has_navigation=True, multiplier=2),
            status="ten_point_ruling", remaining_rounds=5760, roll={"total": 5})
        self.session.d6_navigation.journeys.append(journey)
        for status in ("ten_point_ruling", "awaiting_location", "close_call_pending", "exposure_pending", "emergency"):
            journey.status = status
            before = self.session.model_dump()
            response = self.client.post("/api/weg-d6/engineering/begin", json=self.request())
            self.assertEqual(response.status_code, 400, response.text)
            self.assertIn("Resolve the saved navigation", response.text)
            self.assertEqual(before, self.session.model_dump())
        journey.status = "aborted"
        self.begin()
        for status in ("ten_point_ruling", "awaiting_location", "close_call_pending", "exposure_pending", "emergency"):
            self.session.d6_navigation.journeys[-1].status = status
            before = self.session.model_dump()
            response, dice = self.attempt(actor_id="technician", force_point=True)
            self.assertEqual(response.status_code, 400, response.text)
            self.assertIn("Resolve the saved navigation", response.text)
            self.assertEqual(before, self.session.model_dump())
            dice.assert_not_called()

    def test_failure_retains_damage_parts_and_source_retry_times(self):
        self.begin()
        for expected in (15, 60, 1440, 2880, 2880):
            response, _ = self.attempt(total=1)
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(self.project.attempts[-1]["minutes"], expected)
            self.assertEqual(self.craft.maneuverability_lost, 1)
            self.assertEqual(self.session.character.d6.credits, 90000)
        self.assertEqual(self.project.status, "pending")

    def test_walker_and_vehicle_weapon_use_their_distinct_retry_times(self):
        walker = vehicle_presets()["atst"]
        walker.maneuverability_lost, walker.purchase_value = 1, 1000
        self.session.vehicles[0] = walker
        self.begin()
        for expected in (15, 360):
            response, _ = self.attempt(total=1)
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(self.project.attempts[-1]["minutes"], expected)
        self.session.vehicles[0] = vehicle_presets()["airspeeder"]
        weapon = self.craft.weapons[0]
        weapon.status, weapon.purchase_value = "disabled", 1000
        self.begin(system="weapon", weapon_id=weapon.id)
        for expected in (15, 60, 120, 120):
            response, _ = self.attempt(total=1)
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(self.project.attempts[-1]["minutes"], expected)

    def test_custom_time_requires_reason_and_advances_entire_party(self):
        self.begin()
        before = self.session.model_dump()
        response, dice = self.attempt(minutes=5)
        self.assertEqual(response.status_code, 400, response.text)
        self.assertEqual(before, self.session.model_dump())
        dice.assert_not_called()
        start = {person.id: person.d6.force.elapsed_rounds for person in
            [self.session.character, *self.session.character.companions] if person.d6}
        response, _ = self.attempt(minutes=5, timing_reason="The GM confirms a preassembled swap-in actuator.")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.project.attempts[-1]["minutes"], 5)
        for person in [self.session.character, *self.session.character.companions]:
            if person.d6:
                self.assertEqual(person.d6.force.elapsed_rounds, start[person.id] + 60)

    def test_actual_technician_skill_cp_and_force_points_are_used(self):
        self.begin()
        hero_before = (self.session.character.d6.character_points, self.session.character.d6.force_points)
        response, dice = self.attempt(total=1, actor_id="technician", character_points=2)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(dice.call_args.args, (6, 0, 2, "penalty"))
        tech = self.session.character.companions[-1]
        self.assertEqual((tech.d6.character_points, tech.d6.force_points), (2, 2))
        response, dice = self.attempt(total=1, actor_id="technician", force_point=True)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(dice.call_args.args, (12, 0, 0, "penalty"))
        tech = self.session.character.companions[-1]
        self.assertEqual((tech.d6.character_points, tech.d6.force_points), (2, 1))
        self.assertEqual((self.session.character.d6.character_points, self.session.character.d6.force_points), hero_before)
        self.assertEqual(self.project.attempts[-1]["actor_id"], "technician")
        self.assertEqual(len(tech.d6.rewards.expenditures), 1)

    def test_invalid_actor_or_point_spends_are_rejected_before_time_or_roll(self):
        self.begin()
        for changes in ({"actor_id": "stranger"}, {"character_points": 1, "force_point": True},
                {"character_points": 3}):
            before = self.session.model_dump()
            response, dice = self.attempt(**changes)
            self.assertIn(response.status_code, (400, 422), response.text)
            self.assertEqual(before, self.session.model_dump())
            dice.assert_not_called()
        self.session.character.companions[-1].d6.force_points = 0
        before = self.session.model_dump()
        response, dice = self.attempt(actor_id="technician", force_point=True)
        self.assertEqual(response.status_code, 400, response.text)
        self.assertEqual(before, self.session.model_dump())
        dice.assert_not_called()

    def test_incapacitated_technician_cannot_attempt(self):
        self.begin()
        self.session.character.companions[-1].d6.wound = "incapacitated"
        before = self.session.model_dump()
        response, dice = self.attempt(actor_id="technician")
        self.assertEqual(response.status_code, 400, response.text)
        self.assertEqual(before, self.session.model_dump())
        dice.assert_not_called()

    def test_new_selected_damage_invalidates_paid_project_without_refund_or_time(self):
        self.begin()
        self.craft.maneuverability_lost = 2
        before = self.session.model_dump()
        response, dice = self.attempt()
        self.assertEqual(response.status_code, 400, response.text)
        self.assertIn("damage changed", response.text)
        self.assertEqual(before, self.session.model_dump())
        dice.assert_not_called()

    def test_other_system_damage_does_not_invalidate_or_get_repaired(self):
        self.begin()
        self.craft.speed_losses = 2
        response, _ = self.attempt()
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual((self.craft.maneuverability_lost, self.craft.speed_losses, self.craft.damage),
            (0, 2, "lightly_damaged"))
        self.assertEqual(self.project.status, "completed")
        before = self.session.model_dump()
        response, dice = self.attempt()
        self.assertEqual(response.status_code, 400, response.text)
        self.assertEqual(before, self.session.model_dump())
        dice.assert_not_called()

    def test_destruction_before_or_during_attempt_cannot_resurrect_craft(self):
        self.begin()
        self.craft.damage = "destroyed"
        before = self.session.model_dump()
        response, dice = self.attempt()
        self.assertEqual(response.status_code, 400, response.text)
        self.assertEqual(before, self.session.model_dump())
        dice.assert_not_called()
        self.craft.damage = "severely_damaged"
        self.craft.destruction_countdown, self.craft.destruction_cause = 1, "structure"
        with patch.object(WEGD6Rules, "roll_skill") as skill_roll:
            response, _ = self.attempt(force_point=True)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.craft.damage, "destroyed")
        self.assertTrue(self.project.attempts[-1]["interrupted"])
        self.assertEqual(self.project.status, "pending")
        self.assertEqual(self.session.character.d6.force_points, 2)
        skill_roll.assert_not_called()

    def test_destroyed_weapon_replacement_pays_full_value_and_only_replaces_that_mount(self):
        weapon = self.craft.weapons[0]
        weapon.status, weapon.repair_damage, weapon.purchase_value = "destroyed", "destroyed", 1234
        self.begin(system="weapon", weapon_id=weapon.id, replacement=True, gm_difficulty=12)
        self.assertEqual(self.session.character.d6.credits, 98766)
        response, _ = self.attempt()
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual((self.craft.weapons[0].status, self.craft.weapons[0].repair_damage), ("operational", "intact"))
        self.assertEqual((self.craft.maneuverability_lost, self.craft.damage), (1, "lightly_damaged"))

    def test_weapon_damage_fingerprint_invalidates_prior_repair_assessment(self):
        weapon = self.craft.weapons[0]
        weapon.status, weapon.repair_damage, weapon.purchase_value = "disabled", "lightly_damaged", 1000
        self.begin(system="weapon", weapon_id=weapon.id)
        self.craft.weapons[0].repair_damage = "heavily_damaged"
        before = self.session.model_dump()
        response, dice = self.attempt()
        self.assertEqual(response.status_code, 400, response.text)
        self.assertEqual(before, self.session.model_dump())
        dice.assert_not_called()

    def test_cancel_keeps_payment_and_allows_new_quote(self):
        self.begin()
        response = self.client.post("/api/weg-d6/engineering/cancel", json={
            "project_id": self.project.id, "reason": "The actual damage changed before installation."})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual((self.project.status, self.session.character.d6.credits), ("cancelled", 90000))
        before = self.session.model_dump()
        response = self.client.post("/api/weg-d6/engineering/cancel", json={"project_id": self.project.id, "reason": "Again"})
        self.assertEqual(response.status_code, 400, response.text)
        self.assertEqual(before, self.session.model_dump())
        self.assertEqual(self.client.post("/api/weg-d6/engineering/quote", json=self.request()).status_code, 200)

    def test_saved_failed_paid_project_retains_roll_damage_time_and_no_second_charge(self):
        self.begin()
        response, _ = self.attempt(total=1, actor_id="technician", character_points=1)
        self.assertEqual(response.status_code, 200, response.text)
        project_dump = self.project.model_dump()
        with tempfile.TemporaryDirectory() as directory:
            manager = SaveManager(directory)
            loaded = manager.load_session(manager.save_session(self.session, "engineering"))
        self.assertEqual(loaded.vehicles[0].repair_projects[0].model_dump(), project_dump)
        self.assertEqual((loaded.character.d6.credits, loaded.vehicles[0].maneuverability_lost), (90000, 1))
        routes._ACTIVE_SESSION = self.session = loaded
        response, _ = self.attempt(actor_id="technician")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual((self.project.status, self.project.attempts[-1]["minutes"], self.session.character.d6.credits),
            ("completed", 60, 90000))


if __name__ == "__main__":
    unittest.main()
