import tempfile
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from dungeonforge.api import routes
from dungeonforge.campaign.campaign_manager import CampaignManager
from dungeonforge.game.models import GameSession
from dungeonforge.game.saves import SaveManager
from dungeonforge.game.weg_vehicle_presets import vehicle_presets
from dungeonforge.rules.base import Item, Companion
from dungeonforge.rules.weg_vehicle_models import D6Crew
from dungeonforge.rules.weg_d6 import D6Roller
from dungeonforge.rules.weg_navigation import ROUTES, route_hours, quote, active
from dungeonforge.rules.weg_navigation_models import D6NavigationRequest
from dungeonforge.rules.dice import RollResult
from dungeonforge.main import app
from tests.test_weg_creation import droid


def roll(total):
    return RollResult(expression="4D+1", dice_count=4, die_type=6, total=total, system="weg_d6", breakdown=f"Controlled test total {total}")


class NavigationRulesTests(unittest.TestCase):
    def req(self, **changes):
        return D6NavigationRequest(craft_id="ship", origin="Tatooine", destination="Corellia", boarding_confirmed=True, reason="GM confirms actual route and clearance.", **changes)

    def test_gazetteer_has_all_66_symmetric_pairs_and_visually_checked_values(self):
        self.assertEqual(len(ROUTES), 66)
        self.assertEqual(route_hours("Tatooine", "Corellia"), 4)
        self.assertEqual(route_hours("Coruscant", "Tatooine"), 22 * 24 + 14)
        self.assertEqual(route_hours("Dagobah", "Lianna"), 31 * 24 + 15)
        self.assertEqual(route_hours("Bespin", "Alderaan"), 8)
        self.assertIsNone(route_hours("Unknown", "Corellia"))

    def test_hyperdrive_route_frequency_hasty_and_actual_hour_adjustments(self):
        craft = vehicle_presets()["yt1300"]
        result = quote(craft, self.req(route_type="light", hasty=True, extra_hours=2, obstacles=3))
        self.assertEqual((result.hours, result.difficulty), (22, 34))  # 4h *1.25 *x2 *hasty2 +2h; (15+3)*2 -2.

    def test_missing_navigation_and_damage_modifiers(self):
        craft = vehicle_presets()["xwing"]
        craft.damage = "lightly_damaged"
        result = quote(craft, self.req())
        self.assertEqual((result.hours, result.difficulty), (13, 50))
        result = quote(craft, self.req(), has_astromech=True)
        self.assertEqual((result.hours, result.difficulty), (9, 20))

    def test_tie_no_hyperdrive_and_disabled_main_needs_actual_backup(self):
        with self.assertRaises(ValueError): quote(vehicle_presets()["tie_fighter"], self.req())
        craft = vehicle_presets()["yt1300"]
        craft.hyperdrive_disabled = True
        with self.assertRaises(ValueError): quote(craft, self.req())
        self.assertEqual(quote(craft, self.req(backup=True)).hours, 48)

    def test_actual_clearance_boarding_breach_and_known_origin_guarded(self):
        for changes in ({"clearance_units": 49}, {"boarding_confirmed": False}):
            req = self.req().model_copy(update=changes)
            with self.assertRaises(ValueError): quote(vehicle_presets()["yt1300"], req)
        craft = vehicle_presets()["yt1300"]
        craft.hull_breached = True
        with self.assertRaises(ValueError): quote(craft, self.req())
        craft.hull_breached, craft.location = False, "Sullust"
        with self.assertRaises(ValueError): quote(craft, self.req())


class NavigationAPITests(unittest.TestCase):
    def setUp(self):
        preset = CampaignManager.load_campaign("star_wars_d6")
        self.session = GameSession(edition="weg_d6", character=preset.starter_character)
        session_patch = patch.object(routes, "_ACTIVE_SESSION", self.session)
        session_patch.start(); self.addCleanup(session_patch.stop)
        self.client = TestClient(app); self.addCleanup(self.client.close)
        self.client.post("/api/weg-d6/vehicles/add", json={"preset": "yt1300"})
        self.craft_id = self.session.vehicles[0].id

    def request(self, **changes):
        return {**dict(craft_id=self.craft_id, origin="Tatooine", destination="Corellia", boarding_confirmed=True,
            reason="The GM confirms actual boarding and clearance.", expected_updated_at=self.session.updated_at), **changes}

    def plot(self, total=20, **changes):
        with patch.object(D6Roller, "values", return_value=roll(total)):
            response = self.client.post("/api/weg-d6/navigation/plot", json=self.request(**changes))
        self.assertEqual(response.status_code, 200, response.text)
        return self.session.d6_navigation.journeys[-1]

    def resolve(self, action, **changes):
        return self.client.post("/api/weg-d6/navigation/resolve", json=dict(journey_id=active(self.session).id, action=action, reason="GM records the actual result.", **changes))

    def mishap(self, value):
        with patch("dungeonforge.game.weg_navigation.plain", side_effect=[value, 2, 4]):
            return self.plot(total=10)

    def test_quote_readonly_and_success_clocks_all_characters_then_arrives_once(self):
        before = self.session.model_dump()
        response = self.client.post("/api/weg-d6/navigation/quote", json=self.request())
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(before, self.session.model_dump())
        journey = self.plot()
        self.assertEqual(journey.remaining_rounds, 8 * 720)
        start_time = self.session.character.d6.force.elapsed_rounds
        response = self.client.post("/api/weg-d6/navigation/advance", json={"rounds": 8 * 720})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.session.character.d6.force.elapsed_rounds, start_time + 8 * 720)
        self.assertEqual(self.session.vehicles[0].location, "Corellia")
        self.assertIsNone(active(self.session))
        self.assertIn("Corellia", self.session.character.d6.species_context.visited_locations)
        self.assertEqual(self.client.post("/api/weg-d6/navigation/advance", json={"rounds": 1}).status_code, 400)

    def test_rest_and_droid_work_time_share_the_journey_clock(self):
        unit = droid()
        self.session.character.companions.append(Companion(id=unit.id, name="R2 Nav", race="Droid", d6=unit.d6))
        self.plot()
        response = self.client.post("/api/weg-d6/recover", json={"method": "rest", "minutes": 60})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(active(self.session).remaining_rounds, 7 * 720)
        response = self.client.post("/api/weg-d6/droids/work", json={"actor_id": unit.id, "operation": "refine", "skill": "search", "minutes": 15, "reason": "Droid processes its installed skill during the journey."})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(active(self.session).remaining_rounds, 7 * 720 - 180)

    def test_personal_combat_round_advances_existing_journey_once(self):
        self.plot()
        response = self.client.post("/api/combat/start", json={"enemies": []})
        self.assertEqual(response.status_code, 200, response.text)
        encounter = self.session.encounter
        before = active(self.session).remaining_rounds
        first_round = encounter.round
        for _ in range(len(encounter.combatants) + 1):
            response = self.client.post("/api/combat/next")
            self.assertEqual(response.status_code, 200, response.text)
            if encounter.round > first_round:
                break
        self.assertEqual(active(self.session).remaining_rounds, before - 1)

    def test_stale_plot_and_unassigned_astrogator_are_atomic(self):
        for changes in ({"expected_updated_at": -1}, {"actor_id": "missing"}):
            before = self.session.model_dump()
            response = self.client.post("/api/weg-d6/navigation/plot", json=self.request(**changes))
            self.assertEqual(response.status_code, 400, response.text)
            self.assertEqual(self.session.model_dump(), before)

    def test_explicit_boarding_reboards_previously_evacuated_assigned_crew(self):
        for crew in self.session.vehicles[0].crew:
            crew.evacuated = True
        self.plot()
        self.assertFalse(any(crew.evacuated for crew in self.session.vehicles[0].crew if crew.character_id))

    def test_r2_route_memory_is_exact_symmetric_limited_and_used_for_navigation(self):
        unit = droid()
        self.session.character.companions.append(Companion(id=unit.id, name="R2 Nav", race="Droid", d6=unit.d6))
        craft = self.session.vehicles[0]
        craft.nav_computer = False
        craft.crew.append(D6Crew(id="r2-navigation-station", name="R2 Nav", character_id=unit.id, d6=unit.d6, stations=["engineer"]))
        response = self.client.post("/api/weg-d6/navigation/quote", json=self.request(astromech_id=unit.id))
        self.assertEqual(response.json()["quote"]["difficulty"], 45)
        payload = dict(actor_id=unit.id, origin="Corellia", destination="Tatooine", reason="Actual downloaded route in the R2's memory.")
        self.assertEqual(self.client.post("/api/weg-d6/navigation/route-memory", json=payload).status_code, 200)
        response = self.client.post("/api/weg-d6/navigation/quote", json=self.request(astromech_id=unit.id))
        self.assertEqual(response.json()["quote"]["difficulty"], 15)
        self.assertEqual(self.client.post("/api/weg-d6/navigation/route-memory", json={**payload, "origin": "Tatooine", "destination": "Corellia"}).status_code, 400)
        for index in range(9):
            self.assertEqual(self.client.post("/api/weg-d6/navigation/route-memory", json={**payload, "destination": f"Actual system {index}"}).status_code, 200)
        before = self.session.model_dump()
        self.assertEqual(self.client.post("/api/weg-d6/navigation/route-memory", json={**payload, "destination": "Eleventh jump"}).status_code, 400)
        self.assertEqual(self.session.model_dump(), before)

    def test_sullustan_bonus_uses_actual_current_destination_not_stale_scene_toggle(self):
        state = self.session.character.d6
        state.species_id = "sullustan"
        state.species_context.familiar_destination = True
        pools = []
        for visited, places in [(False, []), (True, []), (False, ["CORELLIA"])]:
            self.session.character.d6.species_context.visited_locations = places
            with patch.object(D6Roller, "values", return_value=roll(20)) as dice:
                response = self.client.post("/api/weg-d6/navigation/plot", json=self.request(destination_visited=visited))
                self.assertEqual(response.status_code, 200, response.text)
            pools.append(dice.call_args.args[0])
            self.session.d6_navigation.journeys[-1].status = "aborted"
        self.assertEqual(pools[1:], [pools[0] + 1, pools[0] + 1])
        self.assertTrue(self.session.character.d6.species_context.familiar_destination)

    def test_large_failure_cannot_enter_and_exact_ten_waits_for_gm_without_reroll(self):
        journey = self.plot(total=4)
        self.assertEqual(journey.status, "aborted")
        journey = self.plot(total=5)
        self.assertEqual(journey.status, "ten_point_ruling")
        before = self.session.model_dump()
        self.assertEqual(self.client.post("/api/weg-d6/recover", json={"method": "rest", "minutes": 60}).status_code, 400)
        self.assertEqual(self.session.model_dump(), before)
        self.assertEqual(self.resolve("abort").status_code, 200)
        self.assertEqual(self.session.d6_navigation.journeys[-1].roll["total"], 5)

    def test_main_damage_dropout_and_actual_location_before_new_route(self):
        self.mishap(2)
        self.assertTrue(self.session.vehicles[0].hyperdrive_disabled)
        self.assertEqual(active(self.session).status, "awaiting_location")
        self.assertEqual(self.resolve("location", location="Outer Rim dropout").status_code, 200)
        self.assertEqual(self.session.vehicles[0].location, "Outer Rim dropout")
        self.assertIsNone(active(self.session))

    def test_radiation_mynocks_and_close_call_effects(self):
        journey = self.mishap(3)
        self.assertEqual(journey.remaining_rounds, 10 * 720)
        journey.status = "aborted"
        journey = self.mishap(9)
        self.assertEqual(journey.remaining_rounds, (8 + 48) * 720)
        journey.status = "aborted"
        self.mishap(10)
        self.assertEqual(self.resolve("close_call", system="nav_computer").status_code, 200)
        self.assertTrue(self.session.vehicles[0].nav_computer_disabled)
        self.assertEqual(active(self.session).status, "travelling")

    def test_fleet_edit_and_new_course_blocked_while_underway(self):
        self.plot()
        before = self.session.model_dump()
        self.assertEqual(self.client.post("/api/weg-d6/vehicles/add", json={"preset": "xwing"}).status_code, 409)
        self.assertEqual(self.client.post("/api/weg-d6/navigation/plot", json=self.request()).status_code, 400)
        self.assertEqual(self.session.model_dump(), before)

    def test_saved_pending_mishap_retains_roll_crew_and_remaining_time(self):
        self.mishap(7)
        with tempfile.TemporaryDirectory() as directory:
            manager = SaveManager(directory)
            loaded = manager.load_session(manager.save_session(self.session, "trip"))
        self.assertEqual(loaded.d6_navigation, self.session.d6_navigation)
        self.assertEqual(loaded.vehicles[0].hyperdrive_multiplier, 2)

    def test_collision_exposure_and_suits_close_emergency_without_repairing_wreck(self):
        self.mishap(11)
        self.assertEqual(self.resolve("exposure", actor_ids=[self.session.character.id]).status_code, 200)
        self.session.character.inventory.append(Item(name="Sealed suit", quantity=1, sealed_survival_suit=True))
        request = dict(journey_id=active(self.session).id, actor_id=self.session.character.id, method="suit", suit_name="Sealed suit", reason="Put on the actual suit.")
        with patch.object(D6Roller, "values", return_value=roll(20)):
            response = self.client.post("/api/weg-d6/navigation/crew-emergency", json=request)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIsNone(active(self.session))
        self.assertTrue(self.session.vehicles[0].hull_breached)
        self.assertEqual(self.session.character.d6.survival_suit, "Sealed suit")

    def test_failed_suit_requires_breathing_next_round_and_cannot_spend_two_fp(self):
        self.mishap(12)
        self.resolve("exposure", actor_ids=[self.session.character.id])
        self.session.character.inventory.append(Item(name="Suit", sealed_survival_suit=True))
        req = dict(journey_id=active(self.session).id, actor_id=self.session.character.id, method="suit", suit_name="Suit", reason="Actual emergency action.")
        with patch.object(D6Roller, "values", return_value=roll(1)):
            self.assertEqual(self.client.post("/api/weg-d6/navigation/crew-emergency", json=req).status_code, 200)
        self.assertEqual(self.resolve("next_round").status_code, 200)
        with patch.object(D6Roller, "values", return_value=roll(20)):
            response = self.client.post("/api/weg-d6/navigation/crew-emergency", json={**req, "method": "breathe", "actions": 2, "force_point": True})
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(self.client.post("/api/weg-d6/navigation/crew-emergency", json={**req, "force_point": True}).status_code, 400)
            self.assertEqual(self.client.post("/api/weg-d6/navigation/crew-emergency", json=req).status_code, 200)
        self.assertEqual(self.session.character.d6.force_points, 1)

    def test_unconscious_exposed_crew_cannot_sleep_away_vacuum(self):
        self.mishap(11)
        self.resolve("exposure", actor_ids=[self.session.character.id])
        self.session.character.inventory.append(Item(name="Suit", sealed_survival_suit=True))
        req = dict(journey_id=active(self.session).id, actor_id=self.session.character.id, suit_name="Suit", reason="Actual emergency action.")
        with patch.object(D6Roller, "values", return_value=roll(1)):
            self.client.post("/api/weg-d6/navigation/crew-emergency", json={**req, "method": "suit"})
            self.resolve("next_round")
            self.client.post("/api/weg-d6/navigation/crew-emergency", json={**req, "method": "breathe"})
        self.assertTrue(self.session.character.d6.vacuum_unconscious)
        self.assertFalse(self.session.character.d6.can_act)
        self.assertEqual(self.client.post("/api/weg-d6/recover", json={"method": "rest", "minutes": 60}).status_code, 400)

    def test_no_suit_initial_opportunity_can_pass_then_requires_breathing(self):
        self.mishap(11)
        self.resolve("exposure", actor_ids=[self.session.character.id])
        req = dict(journey_id=active(self.session).id, actor_id=self.session.character.id, method="wait", reason="No sealed suit is within reach.")
        before_cp = self.session.character.d6.character_points
        with patch.object(D6Roller, "values") as dice:
            response = self.client.post("/api/weg-d6/navigation/crew-emergency", json=req)
            self.assertEqual(response.status_code, 200, response.text)
            dice.assert_not_called()
        self.assertEqual(self.session.character.d6.character_points, before_cp)
        self.assertEqual(self.resolve("next_round").status_code, 200)
        self.assertEqual(self.resolve("next_round").status_code, 400)
        before = self.session.model_dump()
        self.assertEqual(self.client.post("/api/weg-d6/navigation/crew-emergency", json=req).status_code, 400)
        self.assertEqual(self.session.model_dump(), before)

    def test_force_roll_cannot_reset_actions_inside_unresolved_navigation(self):
        self.session.character.d6.force.known_powers = ["control_pain"]
        self.session.character.d6.force_skills["control"] = "5D"
        self.mishap(11)
        self.resolve("exposure", actor_ids=[self.session.character.id])
        before = self.session.model_dump()
        with patch.object(D6Roller, "values") as dice:
            response = self.client.post("/api/weg-d6/force/begin", json={"power_id": "control_pain", "force_point": True})
            self.assertEqual(response.status_code, 400, response.text)
            self.assertIn("navigation", response.json()["detail"])
            dice.assert_not_called()
        self.assertEqual(self.session.model_dump(), before)
        self.assertEqual(self.client.post("/api/combat/start", json={"enemies": []}).status_code, 409)
        before = self.session.model_dump()
        self.assertEqual(self.client.post("/api/weg-d6/check", json={"skill": "stamina", "difficulty": 10, "force_point": True}).status_code, 400)
        self.assertEqual(self.session.model_dump(), before)

    def test_already_unconscious_exposed_crew_can_advance_and_be_rescued(self):
        self.mishap(11)
        target = self.session.character
        target.d6.unconscious_rounds = 12
        helper = target.companions[0]
        target.inventory.append(Item(name="Sealed suit", quantity=1, sealed_survival_suit=True))
        self.resolve("exposure", actor_ids=[target.id])
        self.assertEqual(active(self.session).crew_exposure[target.id]["phase"], "unconscious")
        self.assertEqual(self.resolve("next_round").status_code, 200)
        with patch.object(D6Roller, "values", return_value=roll(20)):
            response = self.client.post("/api/weg-d6/navigation/crew-emergency", json=dict(journey_id=active(self.session).id, actor_id=target.id, rescuer_id=helper.id, method="rescue", suit_name="Sealed suit", reason="Conscious protected crewmate fits the real suit."))
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIsNone(active(self.session))
        self.assertTrue(self.session.vehicles[0].hull_breached)

    def test_worn_sealed_suit_remains_protection_but_breath_mask_does_not(self):
        self.mishap(11)
        self.session.character.inventory.append(Item(name="Worn vacuum suit", sealed_survival_suit=True))
        self.session.character.d6.survival_suit = "Worn vacuum suit"
        self.assertEqual(self.resolve("exposure", actor_ids=[self.session.character.id]).status_code, 200)
        self.assertIsNone(active(self.session))
        self.assertEqual(self.session.d6_navigation.journeys[-1].crew_exposure[self.session.character.id]["suit_name"], "Worn vacuum suit")

    def test_legacy_stock_metadata_fills_missing_only_preserves_explicit_custom_values(self):
        with tempfile.TemporaryDirectory() as directory:
            manager = SaveManager(directory)
            slot = manager.save_session(self.session, "legacy-trip")
            path = Path(directory) / f"{slot}.json"
            data = json.loads(path.read_text())
            for field in ("hyperdrive_multiplier", "backup_hyperdrive", "nav_computer", "purchase_value"):
                data["vehicles"][0].pop(field)
            path.write_text(json.dumps(data))
            loaded = manager.load_session(slot)
            self.assertEqual((loaded.vehicles[0].hyperdrive_multiplier, loaded.vehicles[0].backup_hyperdrive, loaded.vehicles[0].nav_computer), (2, 12, True))
            data["vehicles"][0]["hyperdrive_multiplier"] = None
            data["vehicles"][0]["purchase_value"] = 1234
            path.write_text(json.dumps(data))
            loaded = manager.load_session(slot)
            self.assertIsNone(loaded.vehicles[0].hyperdrive_multiplier)
            self.assertEqual(loaded.vehicles[0].purchase_value, 1234)

    def test_gamorrean_breathing_retry_resolves_before_passout_without_another_action(self):
        self.session.character.d6.species_id = "gamorrean"
        self.mishap(11)
        self.resolve("exposure", actor_ids=[self.session.character.id])
        request = dict(journey_id=active(self.session).id, actor_id=self.session.character.id, method="wait", reason="The suit is out of reach.")
        self.assertEqual(self.client.post("/api/weg-d6/navigation/crew-emergency", json=request).status_code, 200)
        self.assertEqual(self.resolve("next_round").status_code, 200)
        request.update(method="breathe", gamorrean_retry=True, character_points=1, retry_character_points=1)
        with patch.object(D6Roller, "values", side_effect=[roll(1), roll(20)]) as dice:
            response = self.client.post("/api/weg-d6/navigation/crew-emergency", json=request)
        self.assertEqual(response.status_code, 200, response.text)
        state = self.session.character.d6
        self.assertEqual((state.character_points, state.round_state.actions_taken, dice.call_count), (3, 1, 2))
        self.assertFalse(state.vacuum_unconscious)
        self.assertTrue(response.json()["eval_result"]["state_changes"]["gamorrean_retry"])
        before = self.session.model_dump()
        self.assertEqual(self.client.post("/api/weg-d6/navigation/crew-emergency", json=request).status_code, 400)
        self.assertEqual(self.session.model_dump(), before)


if __name__ == "__main__": unittest.main()
