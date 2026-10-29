import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from pydantic import ValidationError

from dungeonforge.api import routes
from dungeonforge.campaign.campaign_manager import CampaignManager
from dungeonforge.game.models import GameSession
from dungeonforge.game.saves import SaveManager
from dungeonforge.game import weg_vehicle_combat as combat
from dungeonforge.game.weg_vehicle_presets import vehicle_presets
from dungeonforge.main import app
from dungeonforge.rules.weg_d6 import D6Roller, WEGD6Rules
from dungeonforge.rules.weg_models import D6Character
from dungeonforge.rules.weg_vehicle_models import D6Crew, D6Vehicle, D6VehicleAttackRequest, D6VehicleMoveRequest
from dungeonforge.rules.weg_vehicles import WEGVehicleRules as Rules, TO_HIT, TO_DODGE, DAMAGE_CAP, RESIST_CAP, cap_for, capped


def pilot(**kwargs):
    return D6Crew(id="pilot", name="Pilot", stations=["pilot", "gunner", "shields", "engineer"], d6=D6Character(**kwargs))


def ship(preset="xwing", **kwargs):
    craft = vehicle_presets()[preset]
    craft.crew = [pilot(**kwargs)]
    return craft


class VehicleRulesTests(unittest.TestCase):
    def test_invalid_equipment_ranges_duplicate_stations_and_missing_pilot_are_rejected(self):
        craft = ship()
        invalid = craft.model_dump()
        invalid["weapons"][0]["space_ranges"] = [1, 12, 3, 25]
        with self.assertRaises(ValidationError):
            D6Vehicle.model_validate(invalid)
        invalid = craft.model_dump()
        invalid["crew"][0]["stations"] = ["gunner"]
        with self.assertRaises(ValidationError):
            D6Vehicle.model_validate(invalid)
    def test_1992_scale_charts_include_impossible_pairs_and_weapon_scale(self):
        self.assertEqual(cap_for(TO_HIT, "starfighter", "speeder"), 4)
        self.assertIsNone(cap_for(TO_HIT, "capital", "character"))
        self.assertEqual(cap_for(TO_DODGE, "walker", "speeder"), 2)
        self.assertIsNone(cap_for(TO_DODGE, "walker", "character"))
        self.assertIsNone(cap_for(DAMAGE_CAP, "starfighter", "death_star"))
        self.assertEqual(cap_for(DAMAGE_CAP, "speeder", "walker"), 3)
        self.assertEqual(cap_for(RESIST_CAP, "starfighter", "speeder"), 3)
        self.assertIsNone(cap_for(RESIST_CAP, "capital", "character"))

    def test_caps_apply_to_wild_and_cp_explosions_without_capping_pips(self):
        with patch("dungeonforge.rules.weg_d6.random.randint", side_effect=[5, 6, 6, 2, 6, 5]):
            raw = D6Roller.roll("2D+2", character_points=1)
        roll = capped(raw, 3)
        self.assertEqual(raw.wild_rolls, [6, 6, 2])
        self.assertEqual(roll.total, 19)  # 3 + (3+3+2) + (3+3) + 2 pips
        self.assertEqual(raw.total, 32)
        self.assertEqual(roll.raw_rolls, raw.raw_rolls)

    def test_force_doubles_only_crew_skill_not_fire_control_maneuver_hull_or_damage(self):
        craft = ship(skills={"starfighter_piloting": "4D+1", "starship_gunnery": "4D+2"}, force_points=1)
        craft.weapons[0].fire_control = "2D+1"
        crew = craft.crew[0]
        WEGD6Rules.declare(crew.d6, actions=2, force_point=True)
        dice, extra = Rules.validate_crew(crew, "starship_gunnery", equipment=Rules.equipment(craft, craft.weapons[0].fire_control))
        self.assertEqual((dice, extra), (9, 5))  # 8D+4 −1D +2D+1
        self.assertEqual(Rules.equipment(craft, craft.weapons[0].damage), (6, 0))
        with patch("dungeonforge.rules.weg_d6.random.randint", return_value=3):
            result = Rules.dodge(craft, crew)
            hull = Rules.hull_roll(craft)
        self.assertEqual(result.roll_result.expression, "10D+2")  # 8D+2 −1D +3D
        self.assertEqual(hull.expression, "4D")

    def test_normal_vehicle_dodge_uses_higher_base_unlike_character_normal_dodge(self):
        attacker, target = ship(), ship()
        with patch("dungeonforge.rules.weg_d6.random.randint", return_value=2):
            Rules.dodge(target, target.crew[0])
            req = D6VehicleAttackRequest(actor_id="pilot", target_id=target.id, weapon_id="laser", distance=20, passenger_damage=False)
            result = Rules.attack(attacker, attacker.crew[0], target, attacker.weapons[0], req, "space")
        self.assertEqual(result.target_value, 20)

    def test_full_dodge_adds_base_and_is_only_skill_action(self):
        craft = ship()
        with patch("dungeonforge.rules.weg_d6.random.randint", return_value=3):
            Rules.dodge(craft, craft.crew[0], full=True)
        with self.assertRaises(ValueError):
            Rules.crew_roll(craft.crew[0], "starship_gunnery")
        self.assertTrue(craft.full_dodge)
        attacker = ship()
        with patch("dungeonforge.rules.weg_d6.random.randint", return_value=3):
            result = Rules.attack(attacker, attacker.crew[0], craft, attacker.weapons[0], D6VehicleAttackRequest(actor_id="pilot", target_id=craft.id, weapon_id="laser", distance=3, passenger_damage=False), "space")
        self.assertEqual(result.target_value, 28)  # 10 base + 6D dodge total 18

    def test_dodge_is_recapped_for_each_incoming_weapon_without_reroll(self):
        craft = ship("atst")
        with patch("dungeonforge.rules.weg_d6.random.randint", return_value=5):
            Rules.dodge(craft, craft.crew[0])
        raw = craft.dodge_roll
        self.assertEqual(capped(raw, cap_for(TO_DODGE, "walker", "speeder")).total, 8)
        self.assertEqual(capped(raw, cap_for(TO_DODGE, "walker", "walker")).total, 20)
        self.assertEqual(raw.total, 20)

    def test_shield_arcs_have_difficulty_and_allocation_budget(self):
        craft = ship("ywing", skills={"starship_shields": "5D"})
        with self.assertRaises(ValueError):
            Rules.shields(craft, craft.crew[0], {"front": "2D"})
        self.assertEqual(craft.crew[0].d6.round_state.actions_taken, 0)
        with patch("dungeonforge.rules.weg_d6.random.randint", return_value=4):
            result = Rules.shields(craft, craft.crew[0], {"front": "1D", "back": "0D+2"})
        self.assertTrue(result.success)
        self.assertEqual(result.target_value, 15)
        with patch("dungeonforge.rules.weg_d6.random.randint", return_value=3):
            self.assertEqual(Rules.hull_roll(craft, "front").expression, "5D")
            self.assertEqual(Rules.hull_roll(craft, "left").expression, "4D")
            self.assertEqual(Rules.hull_roll(craft, "front", "ion").expression, "4D")
            self.assertEqual(Rules.hull_roll(craft, "front", "missile").expression, "4D")

    def test_particles_offline_reduce_starship_hull_but_not_vehicle_body(self):
        craft, vehicle = ship(), ship("atst")
        craft.particle_shields = vehicle.particle_shields = False
        with patch("dungeonforge.rules.weg_d6.random.randint", return_value=3):
            self.assertEqual(Rules.hull_roll(craft).expression, "2D")
            self.assertEqual(Rules.hull_roll(vehicle).expression, "3D")

    def test_weapon_arcs_range_operator_ammo_and_character_points_are_validated_first(self):
        attacker, target = ship(), ship()
        req = D6VehicleAttackRequest(actor_id="pilot", target_id=target.id, weapon_id="laser", fire_arc="back", character_points=1)
        with self.assertRaises(ValueError):
            Rules.attack(attacker, attacker.crew[0], target, attacker.weapons[0], req, "space")
        self.assertEqual(attacker.crew[0].d6.character_points, 5)
        self.assertEqual(attacker.crew[0].d6.round_state.actions_taken, 0)
        req.fire_arc = "front"
        req.distance = 26
        with self.assertRaises(ValueError):
            Rules.attack(attacker, attacker.crew[0], target, attacker.weapons[0], req, "space")

    def test_physical_launch_lowers_own_particle_shields_and_spends_ammo_on_miss(self):
        attacker, target = ship(), ship()
        target.declared_moves = 1
        req = D6VehicleAttackRequest(actor_id="pilot", target_id=target.id, weapon_id="torpedo", difficulty=100, passenger_damage=False)
        with patch("dungeonforge.rules.weg_d6.random.randint", return_value=3):
            result = Rules.attack(attacker, attacker.crew[0], target, attacker.weapons[1], req, "space")
        self.assertFalse(result.success)
        self.assertEqual(result.target_value, 120)
        self.assertEqual(attacker.weapons[1].ammo, 5)
        self.assertFalse(attacker.particle_shields)

    def test_ywing_turret_requires_separate_gunner_and_evacuated_crew_cannot_operate(self):
        craft, target = ship("ywing"), ship()
        self.assertFalse(craft.weapons[1].pilot_operated)
        req = D6VehicleAttackRequest(actor_id="pilot", target_id=target.id, weapon_id="ion")
        with self.assertRaises(ValueError):
            Rules.attack(craft, craft.crew[0], target, craft.weapons[1], req, "space")
        craft.crew[0].evacuated = True
        with self.assertRaises(ValueError):
            Rules.dodge(craft, craft.crew[0])
        enemy = combat.make_enemy("ywing")
        self.assertEqual(len(enemy.crew), 2)
        self.assertEqual(enemy.weapons[1].operator_id, enemy.crew[1].id)

    def test_vehicle_and_starship_damage_subtables_are_distinct(self):
        vehicle, craft = ship("atst"), ship()
        with patch("dungeonforge.rules.weg_vehicles.random.randint", return_value=3):
            Rules.damage(vehicle, 4, exposed=False)
            Rules.damage(craft, 4, exposed=False)
        self.assertEqual(vehicle.maneuverability_lost, 1)
        self.assertEqual(sum(w.status == "destroyed" for w in craft.weapons), 1)

    def test_damage_margin_boundaries_and_repeated_damage_progression(self):
        for margin, expected in [(-1, "intact"), (0, "intact"), (3, "intact"), (4, "lightly_damaged"), (8, "lightly_damaged"), (9, "heavily_damaged"), (12, "heavily_damaged"), (13, "severely_damaged"), (15, "severely_damaged"), (16, "destroyed")]:
            with self.subTest(margin=margin), patch("dungeonforge.rules.weg_vehicles.random.randint", return_value=1):
                craft = ship()
                Rules.damage(craft, margin, exposed=False)
                self.assertEqual(craft.damage, expected)
        craft = ship()
        with patch("dungeonforge.rules.weg_vehicles.random.randint", return_value=1):
            Rules.damage(craft, 4, exposed=False)
            Rules.damage(craft, 4, exposed=False)
            self.assertEqual(craft.damage, "lightly_damaged")
            Rules.damage(craft, 9, exposed=False)
            Rules.damage(craft, 4, exposed=False)
            self.assertEqual(craft.damage, "severely_damaged")
            Rules.damage(craft, 4, exposed=False)
            self.assertEqual(craft.damage, "destroyed")

    def test_ion_damage_boundaries_bypass_structural_damage_and_freeze_controls(self):
        for margin, count in [(0, 1), (5, 1), (6, 2), (10, 2), (11, 3), (15, 3), (16, 4), (20, 4)]:
            with self.subTest(margin=margin):
                craft = ship()
                Rules.damage(craft, margin, ion=True)
                self.assertEqual(len(craft.ion_durations), count)
                self.assertEqual(craft.damage, "intact")
        craft = ship()
        Rules.damage(craft, 21, ion=True)
        self.assertTrue(craft.controls_dead)
        craft = ship("tie_fighter")
        Rules.damage(craft, 6, ion=True)
        self.assertEqual(craft.frozen_rounds, 3)
        with self.assertRaises(ValueError):
            Rules.operational(craft)
        Rules.next_round(craft)
        self.assertEqual(len(craft.ion_durations), 2)
        Rules.next_round(craft)
        self.assertEqual(len(craft.ion_durations), 0)
        self.assertEqual(craft.frozen_rounds, 1)
        Rules.next_round(craft)
        self.assertEqual(craft.frozen_rounds, 0)

    def test_shield_loss_persists_ion_reduces_active_arcs_and_no_shields_ionizes(self):
        craft = ship("ywing")
        craft.shield_allocation = {"front": "1D+2"}
        Rules.damage(craft, 0, exposed=False)
        self.assertEqual(craft.shields_lost, 1)
        self.assertEqual(craft.shield_allocation, {"front": "0D+2"})
        Rules.damage(craft, 0, ion=True)
        self.assertEqual(craft.shield_allocation, {})
        Rules.damage(craft, 0, exposed=False)
        self.assertEqual(len(craft.ion_durations), 2)
        Rules.next_round(craft)
        self.assertEqual(craft.shields_lost, 1)

    def test_passenger_damage_is_character_scale_and_exposure_is_a_gm_choice(self):
        craft = ship()
        with patch("dungeonforge.rules.weg_d6.random.randint", return_value=3):
            outcomes = Rules.passengers(craft, "heavily_damaged")
        self.assertEqual(outcomes[0]["damage_roll"]["expression"], "3D")
        self.assertEqual(outcomes[0]["outcome"], "stunned")
        self.assertEqual(Rules.passengers(craft, "destroyed", exposed=False), [])

    def test_generator_and_structural_countdowns_destroy_after_their_rounds(self):
        craft = ship()
        with patch("dungeonforge.rules.weg_vehicles.random.randint", return_value=2):
            Rules.damage(craft, 13, exposed=False)
        self.assertEqual(craft.destruction_countdown, 3)
        Rules.next_round(craft)
        Rules.next_round(craft)
        self.assertEqual(craft.damage, "severely_damaged")
        with patch("dungeonforge.rules.weg_d6.random.randint", return_value=3):
            Rules.next_round(craft)
        self.assertEqual(craft.damage, "destroyed")

    def test_half_speed_is_free_without_roll_and_full_speed_spends_action(self):
        craft = ship()
        craft.declared_moves, craft.half_speed = 1, True
        req = D6VehicleMoveRequest(actor_id="pilot", terrain_difficulty=15)
        result = Rules.move(craft, craft.crew[0], req, "space")
        self.assertTrue(result.state_changes["free_move"])
        self.assertEqual(craft.crew[0].d6.round_state.actions_taken, 0)
        self.assertEqual(craft.distance_moved, 4)
        with self.assertRaises(ValueError):
            Rules.move(craft, craft.crew[0], req, "space")

    def test_half_speed_difficult_terrain_reduces_three_bands_but_costs_action(self):
        craft = ship()
        craft.declared_moves, craft.half_speed = 1, True
        with patch("dungeonforge.rules.weg_d6.random.randint", return_value=3):
            result = Rules.move(craft, craft.crew[0], D6VehicleMoveRequest(actor_id="pilot", terrain_difficulty=30), "space")
        self.assertEqual(result.target_value, 10)
        self.assertFalse(result.state_changes["free_move"])
        self.assertEqual(craft.crew[0].d6.round_state.actions_taken, 1)

    def test_maneuver_difficulty_is_included_in_movement_failure(self):
        craft = ship()
        craft.declared_moves = 1
        with patch("dungeonforge.rules.weg_d6.random.randint", return_value=2):
            result = Rules.move(craft, craft.crew[0], D6VehicleMoveRequest(actor_id="pilot", terrain_difficulty=10, maneuver_modifier=5), "space")
        self.assertFalse(result.success)
        self.assertEqual(craft.crew[0].control_penalty, 1)  # 12 vs 15

    def test_bad_movement_uses_declared_speed_collision_damage(self):
        craft = ship()
        craft.declared_moves = 2
        with patch("dungeonforge.rules.weg_d6.random.randint", return_value=2):
            result = Rules.move(craft, craft.crew[0], D6VehicleMoveRequest(actor_id="pilot", terrain_difficulty=25, passenger_damage=False), "space")
        self.assertIn("collision", result.state_changes)
        self.assertEqual(result.state_changes["collision"]["damage_roll"]["expression"], "1D")  # 4D −3D minor collision

    def test_full_dodge_allows_free_half_move_but_not_a_piloting_roll(self):
        craft = ship()
        craft.declared_moves, craft.half_speed = 1, True
        with patch("dungeonforge.rules.weg_d6.random.randint", return_value=3):
            Rules.dodge(craft, craft.crew[0], full=True)
        result = Rules.move(craft, craft.crew[0], D6VehicleMoveRequest(actor_id="pilot"), "space")
        self.assertTrue(result.success)

    def test_frozen_controls_preserve_speed_and_skipped_piloting_crashes(self):
        craft = ship("tie_fighter")
        craft.declared_moves = 2
        Rules.damage(craft, 6, ion=True)
        self.assertEqual(craft.forced_moves, 2)
        with patch("dungeonforge.rules.weg_d6.random.randint", return_value=3):
            Rules.next_round(craft)
        self.assertEqual(craft.declared_moves, 2)
        self.assertTrue(any("automatic crash" in line for line in craft.damage_log))

    def test_ramming_applies_speed_damage_to_both_craft(self):
        attacker, target = ship(), ship()
        attacker.declared_moves = 2
        req = D6VehicleMoveRequest(actor_id="pilot", terrain_difficulty=1, ram_target_id=target.id, passenger_damage=False)
        with patch("dungeonforge.rules.weg_d6.random.randint", return_value=3):
            result = Rules.move(attacker, attacker.crew[0], req, "space", target)
        self.assertTrue(result.success)
        hits = result.state_changes["ram_collisions"]
        self.assertEqual(hits[0]["damage_roll"]["expression"], "1D")  # 4D speed −3D attacker
        self.assertEqual(hits[1]["damage_roll"]["expression"], "4D")

    def test_airborne_powerplant_loss_causes_fall_even_at_half_speed(self):
        craft = ship("airspeeder")
        craft.airborne, craft.altitude, craft.half_speed = True, 10, True
        with patch("dungeonforge.rules.weg_vehicles.random.randint", return_value=1):
            detail, _ = Rules.damage(craft, 13, exposed=False)
        self.assertIn("crash", detail)
        self.assertFalse(craft.airborne)
        self.assertTrue(craft.drives_disabled)
        self.assertEqual(Rules.falling_dice(10), 3)

    def test_head_on_collision_adds_three_dice_after_movement_failure_modifier(self):
        craft = ship()
        craft.declared_moves = 2
        req = D6VehicleMoveRequest(actor_id="pilot", terrain_difficulty=25, passenger_damage=False, collision_angle="head_on")
        with patch("dungeonforge.rules.weg_d6.random.randint", return_value=2):
            result = Rules.move(craft, craft.crew[0], req, "space")
        self.assertEqual(result.state_changes["collision"]["damage_roll"]["expression"], "4D")  # 4D speed −3D minor +3D head on

    def test_destroyed_emplacement_damages_its_gunner_even_when_other_crew_are_sheltered(self):
        craft = ship("ghtroc")
        gunner = D6Crew(id="gunner", name="Gunner", stations=["gunner"], d6=D6Character())
        craft.crew.append(gunner)
        craft.weapons[0].operator_id = gunner.id
        with patch("dungeonforge.rules.weg_vehicles.random.randint", return_value=3):
            _, injured = Rules.damage(craft, 4, exposed=False)
        self.assertEqual([result["crew_id"] for result in injured], ["gunner"])
        self.assertEqual(injured[0]["damage_roll"]["expression"], "1D")

    def test_different_scale_mounted_weapon_uses_weapon_scale_not_platform(self):
        attacker, target = ship("corvette"), ship("atst")
        req = D6VehicleAttackRequest(actor_id="pilot", target_id=target.id, weapon_id="turbolaser", distance=100, difficulty=100, passenger_damage=False)
        with patch("dungeonforge.rules.weg_d6.random.randint", return_value=5):
            result = Rules.attack(attacker, attacker.crew[0], target, attacker.weapons[0], req, "atmosphere")
        self.assertEqual(result.roll_result.total, 30)  # 6D, cap5, not capital→walker cap2
        self.assertIn("starfighter → walker, cap 5", result.summary)


class VehicleAPITests(unittest.TestCase):
    def setUp(self):
        preset = CampaignManager.load_campaign("star_wars_d6")
        self.session = GameSession(edition="weg_d6", character=preset.starter_character, source_folders=["star_wars"])
        active = patch.object(routes, "_ACTIVE_SESSION", self.session)
        active.start()
        self.addCleanup(active.stop)
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def post(self, endpoint, data=None):
        response = self.client.post("/api/weg-d6/vehicles/" + endpoint, json=data or {})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def start(self, preset="xwing", enemies=None, environment="space"):
        self.post("add", {"preset": preset})
        craft = self.session.vehicles[-1]
        self.post("start", {"vehicle_id": craft.id, "enemies": enemies or ["tie_fighter"], "environment": environment})
        encounter = self.session.vehicle_encounter
        self.post(f"initiative?winner_first={'true' if encounter.initiative_winner else 'false'}")
        return self.session.vehicle_encounter

    def test_legacy_saves_default_to_empty_fleet_and_catalog_is_native(self):
        self.assertEqual(self.session.vehicles, [])
        self.assertIsNone(self.session.vehicle_encounter)
        response = self.client.get("/api/weg-d6/vehicles/catalog")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(any(craft["id"] == "atst" for craft in response.json()["presets"]))

    def test_surface_vehicles_reject_space_without_mutating_fleet(self):
        self.post("add", {"preset": "airspeeder"})
        response = self.client.post("/api/weg-d6/vehicles/start", json={"vehicle_id": self.session.vehicles[0].id})
        self.assertEqual(response.status_code, 400)
        self.assertIsNone(self.session.vehicle_encounter)

    def test_crew_actions_resources_and_invalid_request_atomicity(self):
        self.start()
        actor = self.session.character.id
        self.post("declare", {"actor_id": actor, "actions": 2, "force_point": True, "moves": 1})
        self.assertEqual(self.session.character.d6.force_points, 1)
        encounter = self.session.vehicle_encounter
        enemy = next(c for c in encounter.craft if not c.is_player)
        before = encounter.model_dump()
        invalid = self.client.post("/api/weg-d6/vehicles/attack", json={"actor_id": actor, "target_id": enemy.id, "weapon_id": "laser", "character_points": 1})
        self.assertEqual(invalid.status_code, 400)
        self.assertEqual(self.session.vehicle_encounter.model_dump(), before)
        with patch("dungeonforge.rules.weg_d6.random.randint", return_value=3):
            data = self.post("attack", {"actor_id": actor, "target_id": enemy.id, "weapon_id": "laser", "difficulty": 1, "passenger_damage": False})
        self.assertEqual(data["eval_result"]["roll_result"]["expression"], "8D+2")  # Mechanical 3D+1 *2 −1D +3D
        self.assertEqual(data["eval_result"]["damage_roll"]["expression"], "6D")
        self.assertEqual(self.session.history[-1].mode, "attack")
        second = self.client.post("/api/weg-d6/vehicles/attack", json={"actor_id": actor, "target_id": enemy.id, "weapon_id": "laser"})
        self.assertIn(second.status_code, (400, 409))

    def test_dedicated_gunner_uses_own_actions_and_default_attribute(self):
        self.start("ghtroc")
        encounter = self.session.vehicle_encounter
        party = next(c for c in encounter.craft if c.is_player)
        self.assertEqual(party.weapons[0].operator_id, "rebel_medic")
        wrong = self.client.post("/api/weg-d6/vehicles/attack", json={"actor_id": self.session.character.id, "target_id": encounter.craft[1].id, "weapon_id": "laser"})
        self.assertEqual(wrong.status_code, 400)
        self.post("next")
        self.assertEqual(self.session.vehicle_encounter.actor_order[self.session.vehicle_encounter.current_turn_index], "rebel_medic")
        with patch("dungeonforge.rules.weg_d6.random.randint", return_value=3):
            data = self.post("attack", {"actor_id": "rebel_medic", "target_id": encounter.craft[1].id, "weapon_id": "laser", "difficulty": 1, "passenger_damage": False})
        self.assertEqual(data["eval_result"]["roll_result"]["expression"], "3D+3")  # Mechanical2D+1 + 1D+2 fire control
        self.assertEqual(self.session.character.d6.round_state.actions_taken, 1)  # skipped pilot action
        self.assertEqual(self.session.character.companions[0].d6.round_state.actions_taken, 1)

    def test_character_combat_scene_checks_recovery_and_edit_cannot_bypass_crew_round(self):
        self.start()
        self.assertEqual(self.client.post("/api/combat/start", json={}).status_code, 409)
        self.assertEqual(self.client.post("/api/weg-d6/check", json={"skill": "astrogation"}).status_code, 409)
        self.assertEqual(self.client.post("/api/weg-d6/recover", json={"method": "rest"}).status_code, 409)
        self.assertEqual(self.client.post("/api/character", json=self.session.character.model_dump()).status_code, 409)
        self.assertEqual(self.client.post("/api/combat/end").status_code, 409)

    def test_declarations_lock_and_reopen_next_round_with_new_initiative(self):
        self.start()
        self.post("declare", {"actor_id": self.session.character.id, "actions": 2})
        self.post("next")
        response = self.client.post("/api/weg-d6/vehicles/declare", json={"actor_id": self.session.character.id, "actions": 1})
        self.assertEqual(response.status_code, 400)
        for _ in range(8):
            if self.session.vehicle_encounter.round == 2:
                break
            self.post("next")
        self.assertEqual(self.session.vehicle_encounter.round, 2)
        self.assertFalse(self.session.vehicle_encounter.actions_started)
        self.assertEqual(self.session.character.d6.round_state.actions_taken, 0)

    def test_craft_and_active_crew_states_survive_save_load_and_end(self):
        self.start()
        self.post("declare", {"actor_id": self.session.character.id, "actions": 2, "force_point": True})
        party = self.session.vehicle_encounter.craft[0]
        party.shields_lost = 1
        party.damage = "heavily_damaged"
        with tempfile.TemporaryDirectory() as directory:
            manager = SaveManager(directory)
            slot = manager.save_session(self.session, "flight")
            loaded = manager.load_session(slot)
            chronicle = manager.export_markdown_chronicle(loaded)
        self.assertTrue(loaded.vehicle_encounter.craft[0].crew[0].d6.round_state.force_active)
        self.assertIn("heavily damaged", chronicle)
        self.post("end")
        self.assertEqual(self.session.vehicles[0].damage, "heavily_damaged")
        self.assertEqual(self.session.character.d6.force_points, 1)
        self.assertFalse(self.session.character.d6.round_state.force_active)

    def test_generator_can_be_shut_down_and_crews_can_evacuate(self):
        self.start()
        party = self.session.vehicle_encounter.craft[0]
        party.damage = "severely_damaged"
        party.destruction_countdown, party.destruction_cause = 3, "generator"
        self.post("system", {"actor_id": self.session.character.id, "action": "shutdown_generator"})
        self.assertTrue(self.session.vehicles[0].generator_shutdown)
        self.assertIsNone(self.session.vehicles[0].destruction_countdown)

    def test_dodge_after_roll_cp_keeps_raw_dice_and_caps_the_bonus_later(self):
        self.start()
        actor = self.session.character.id
        with patch("dungeonforge.rules.weg_d6.random.randint", return_value=2):
            original = self.post("dodge", {"actor_id": actor})
        raw = original["eval_result"]["roll_result"]["wild_rolls"]
        with patch("dungeonforge.rules.weg_d6.random.randint", side_effect=[6, 5]):
            boosted = self.post("boost", {"points": 1})
        self.assertEqual(boosted["eval_result"]["roll_result"]["wild_rolls"], raw)
        self.assertEqual(self.session.character.d6.character_points, 4)
        self.assertEqual(len(self.session.history), 1)
        dodge = self.session.vehicle_encounter.craft[0].dodge_roll
        self.assertEqual(dodge.bonus_rolls, [6, 5])
        self.assertEqual(capped(dodge, 2).total, 17)  # six 2s + 1 pip + CP capped to 2+2

    def test_failed_shields_can_be_boosted_to_deploy_without_rerolling(self):
        self.start()
        with patch("dungeonforge.rules.weg_d6.random.randint", return_value=2):
            first = self.post("shields", {"actor_id": self.session.character.id, "allocation": {"front": "1D"}})
        self.assertFalse(first["eval_result"]["success"])
        with patch("dungeonforge.rules.weg_d6.random.randint", return_value=5):
            boosted = self.post("boost", {"points": 1})
        self.assertTrue(boosted["eval_result"]["success"])
        self.assertEqual(self.session.vehicle_encounter.craft[0].shield_allocation, {"front": "1D"})

    def test_native_dice_roll_and_next_action_close_craft_boost_window(self):
        self.start()
        self.post("dodge", {"actor_id": self.session.character.id})
        self.client.post("/api/weg-d6/pool", json={"code": "3D"})
        response = self.client.post("/api/weg-d6/vehicles/boost", json={"points": 1})
        self.assertEqual(response.status_code, 400)

    def test_tractor_lock_pull_escape_and_release_are_native_opposed_hull_actions(self):
        self.start("star_destroyer")
        encounter = self.session.vehicle_encounter
        party, target = encounter.craft
        self.post("next")  # Dedicated gunner takes the action after pilot.
        gunner = party.weapons[-1].operator_id
        with patch("dungeonforge.rules.weg_d6.random.randint", return_value=3):
            self.post("attack", {"actor_id": gunner, "target_id": target.id, "weapon_id": "tractor", "distance": 3, "difficulty": 1})
        target = self.session.vehicle_encounter.craft[1]
        self.assertEqual(target.captured_by, party.id)
        self.post("next")
        encounter = self.session.vehicle_encounter
        actor_id = encounter.actor_order[encounter.current_turn_index]
        with patch("dungeonforge.rules.weg_d6.random.randint", return_value=3):
            escaped = self.post("system", {"actor_id": actor_id, "action": "escape_tractor"})
        self.assertFalse(escaped["eval_result"]["success"])
        self.assertEqual(self.session.vehicle_encounter.craft[1].damage, "intact")
        for _ in range(10):
            self.post("next")
            encounter = self.session.vehicle_encounter
            if encounter.actor_order[encounter.current_turn_index] == gunner:
                break
        self.post("system", {"actor_id": gunner, "action": "pull_tractor", "target_id": target.id})
        self.assertEqual(self.session.vehicle_encounter.craft[1].tractor_distance, 2)
        for _ in range(10):
            self.post("next")
            encounter = self.session.vehicle_encounter
            if encounter.actor_order[encounter.current_turn_index] == gunner:
                break
        self.post("system", {"actor_id": gunner, "action": "release_tractor", "target_id": target.id})
        self.assertIsNone(self.session.vehicle_encounter.craft[1].captured_by)

    def test_rest_cannot_evade_timed_craft_destruction_or_repair_the_hull(self):
        self.start()
        party = self.session.vehicle_encounter.craft[0]
        party.damage = "severely_damaged"
        party.destruction_countdown, party.destruction_cause = 1, "structure"
        self.post("end")
        with patch("dungeonforge.rules.weg_d6.random.randint", return_value=3):
            response = self.client.post("/api/weg-d6/recover", json={"method": "rest", "minutes": 1440})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.session.vehicles[0].damage, "destroyed")
        self.assertEqual(self.session.character.d6.wound, "dead")
        self.assertFalse(response.json()["eval_result"]["success"])

    def test_safe_disembarking_protects_crew_from_later_unoccupied_craft_failure(self):
        self.start()
        party = self.session.vehicle_encounter.craft[0]
        party.damage = "severely_damaged"
        party.destruction_countdown, party.destruction_cause = 1, "structure"
        self.post("end")
        self.post(f"disembark/{party.id}")
        self.post("advance")
        self.assertEqual(self.session.vehicles[0].damage, "destroyed")
        self.assertEqual(self.session.character.d6.wound, "healthy")


if __name__ == "__main__":
    unittest.main()
