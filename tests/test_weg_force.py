"""Native 1992 Force rules: action economy, lasting effects and API persistence."""
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from dungeonforge.api import routes
from dungeonforge.campaign.campaign_manager import CampaignManager
from dungeonforge.game.models import GameSession
from dungeonforge.game.saves import SaveManager
from dungeonforge.main import app
from dungeonforge.rules import weg_force as force, weg_force_effects as effects
from dungeonforge.rules.base import Item
from dungeonforge.rules.weg_d6 import D6Roller, WEGD6Rules
from dungeonforge.rules.weg_force_catalog import POWERS, training_errors
from dungeonforge.rules.weg_force_models import ForceEffect, ForcePowerRequest
from dungeonforge.rules.weg_models import D6Character, D6Options, D6RoundState


def jedi():
    state = D6Character(force_sensitive=True, force_skills={"control": "8D", "sense": "7D", "alter": "8D"}, skills={"lightsaber": "5D"}, force_points=4, character_points=8)
    state.force.known_powers = list(POWERS)
    return state


class ForceRulesTests(unittest.TestCase):
    def setUp(self):
        self.state = jedi()
        dice = patch("dungeonforge.rules.weg_d6.random.randint", return_value=4)
        dice.start()
        self.addCleanup(dice.stop)

    def activate(self, id, target=None, **options):
        spec = POWERS[id]
        req = ForcePowerRequest(power_id=id, actor_id="jedi", target_id="patient" if target else "jedi", relationship="close_relative", proximity="touching", **options)
        WEGD6Rules.declare(self.state, 1 if spec.preparation_rounds > 1 else len(spec.skills))
        result = force.begin(self.state, req, "jedi", target)
        if spec.preparation_rounds > 1:
            effects.tick(self.state, spec.preparation_rounds - 1)
            self.state.round_state = D6RoundState(declared_actions=len(spec.skills))
            result = force.roll_next(self.state, target)
        while self.state.force.attempt and not self.state.force.attempt.failed:
            result = force.roll_next(self.state, target)
        return result

    def test_core_catalog_and_prerequisites_require_actual_training(self):
        self.assertEqual(len(POWERS), 22)
        self.assertNotIn("force_lightning", POWERS)
        state = D6Character()
        state.force.known_powers = ["reduce_injury"]
        self.assertTrue(any("Control Pain" in error for error in training_errors(state)))
        self.assertTrue(any("trained control" in error for error in training_errors(state)))
        self.assertFalse(training_errors(self.state))

    def test_multiskill_activation_is_not_effective_until_every_roll_passes(self):
        WEGD6Rules.declare(self.state, 2)
        req = ForcePowerRequest(power_id="lightsaber_combat", keep_up=True)
        first = force.begin(self.state, req, "jedi")
        self.assertFalse(first.state_changes["complete"])
        self.assertEqual(first.force_rolls[0].roll.dice_count, 7)
        self.assertFalse(effects.find_effect(self.state, "lightsaber_combat"))
        final = force.roll_next(self.state, None)
        self.assertTrue(final.state_changes["complete"])
        self.assertEqual(self.state.round_state.actions_taken, 2)
        self.assertEqual(effects.upkeep(self.state), 0)
        WEGD6Rules.next_round(self.state)
        self.assertEqual(effects.upkeep(self.state), 2)
        self.assertEqual(WEGD6Rules.pool(self.state, "alter")[0], 6)

    def test_consecutive_round_components_use_full_pool_without_map(self):
        first = force.begin(self.state, ForcePowerRequest(power_id="lightsaber_combat", keep_up=True, same_round=False), "jedi")
        WEGD6Rules.next_round(self.state)
        second = force.roll_next(self.state, None)
        self.assertEqual(first.roll_result.dice_count, 8)
        self.assertEqual(second.roll_result.dice_count, 7)
        self.assertTrue(second.state_changes["complete"])

    def test_skipping_a_consecutive_component_round_abandons_activation(self):
        force.begin(self.state, ForcePowerRequest(power_id="lightsaber_combat"), "jedi")
        WEGD6Rules.next_round(self.state)
        WEGD6Rules.next_round(self.state)
        self.assertIsNone(self.state.force.attempt)

    def test_all_twenty_two_corebook_powers_have_a_resolvable_activation(self):
        for id, spec in POWERS.items():
            with self.subTest(power=id):
                self.state = jedi()
                target = D6Character(wound="wounded") if spec.target == "person" else None
                options = {"description": "Declared GM effect", "resistance_total": 1}
                if id == "accelerate_healing":
                    self.state.wound = "wounded"
                elif id == "reduce_injury":
                    WEGD6Rules.apply_damage(self.state, 10)
                elif id == "remain_conscious":
                    WEGD6Rules.apply_damage(self.state, 10)
                    WEGD6Rules.next_round(self.state)
                elif id in {"return_another_consciousness", "transfer_force"}:
                    target.wound = "incapacitated" if id == "return_another_consciousness" else "mortally_wounded"
                # Immediate injury reaction bypasses ordinary declaration guard.
                if id == "reduce_injury":
                    result = force.begin(self.state, ForcePowerRequest(power_id=id), "jedi")
                else:
                    result = self.activate(id, target, **options)
                self.assertTrue(result.state_changes["complete"])

    def test_remain_conscious_cannot_be_carried_unused_into_another_round(self):
        WEGD6Rules.apply_damage(self.state, 10)
        WEGD6Rules.next_round(self.state)
        WEGD6Rules.declare(self.state, 2)
        force.begin(self.state, ForcePowerRequest(power_id="remain_conscious"), "jedi")
        WEGD6Rules.next_round(self.state)
        self.assertFalse(self.state.can_act)
        self.assertTrue(self.state.out_of_fight)

    def test_remain_conscious_can_activate_pain_before_collapsing(self):
        WEGD6Rules.apply_damage(self.state, 10)
        WEGD6Rules.next_round(self.state)
        WEGD6Rules.declare(self.state, 2)
        force.begin(self.state, ForcePowerRequest(power_id="remain_conscious"), "jedi")
        force.begin(self.state, ForcePowerRequest(power_id="control_pain", keep_up=True), "jedi")
        self.assertFalse(self.state.can_act)
        self.assertFalse(self.state.out_of_fight)
        WEGD6Rules.next_round(self.state)
        self.assertTrue(self.state.can_act)
        self.assertEqual(self.state.wound, "incapacitated")

    def test_saber_main_prose_sense_skill_control_damage_and_equipment_fp(self):
        self.activate("lightsaber_combat", keep_up=True)
        WEGD6Rules.next_round(self.state)
        saber = Item(name="Lightsaber", damage="5D", d6_skill="lightsaber")
        self.assertEqual(WEGD6Rules.pool(self.state, "lightsaber"), (10, 0))
        self.assertEqual(WEGD6Rules.damage_pool(self.state, saber), (13, 0))
        self.assertEqual(WEGD6Rules.damage_pool(self.state, saber, -4), (1, 0))
        self.state.round_state.force_active = True
        self.assertEqual(WEGD6Rules.damage_pool(self.state, saber), (21, 0))
        self.assertEqual(WEGD6Rules.pool(self.state, "lightsaber"), (22, 0))
        self.assertEqual(WEGD6Rules.damage_pool(self.state, Item(name="Blaster", damage="4D")), (4, 0))

    def test_saber_failure_locks_reactivation_for_battle(self):
        with patch("dungeonforge.rules.weg_d6.random.randint", return_value=2):
            self.state.force_skills["control"] = "1D"
            result = force.begin(self.state, ForcePowerRequest(power_id="lightsaber_combat"), "jedi", in_combat=True)
        self.assertFalse(result.success)
        effects.cancel_attempt(self.state)
        self.assertTrue(self.state.force.saber_locked)
        with self.assertRaisesRegex(ValueError, "earlier in this battle"):
            force.begin(self.state, ForcePowerRequest(power_id="lightsaber_combat"), "jedi")

    def test_stun_drops_saber_and_invalidates_lightsaber_defense(self):
        self.activate("lightsaber_combat", keep_up=True)
        self.state.round_state.defense_skill = "lightsaber"
        self.state.round_state.defense_total = 40
        WEGD6Rules.apply_damage(self.state, 1)
        self.assertFalse(effects.find_effect(self.state, "lightsaber_combat"))
        self.assertIsNone(self.state.round_state.defense_total)

    def test_saber_self_injury_uses_base_difficulty_not_opposed_parry(self):
        saber = Item(name="Lightsaber", damage="5D", d6_skill="lightsaber")
        self.state.skills["lightsaber"] = "1D"
        target = D6Character()
        result = WEGD6Rules.resolve_attack(self.state, target, saber)
        self.assertEqual(result.target_value, 20)
        self.assertIn("self_injury", result.state_changes)
        self.state = jedi()
        target.round_state.defense_skill, target.round_state.defense_total = "melee_parry", 100
        result = WEGD6Rules.resolve_attack(self.state, target, saber)
        self.assertFalse(result.success)
        self.assertNotIn("self_injury", result.state_changes)

    def test_preparation_is_exclusive_and_can_be_interrupted(self):
        req = ForcePowerRequest(power_id="magnify_senses")
        first = force.begin(self.state, req, "jedi")
        self.assertFalse(first.state_changes["complete"])
        self.assertFalse(self.state.can_act)
        self.assertTrue(self.state.can_take_turn)
        with self.assertRaises(ValueError):
            WEGD6Rules.roll_skill(self.state, "search", 10)
        WEGD6Rules.next_round(self.state)
        force.roll_next(self.state, None)
        WEGD6Rules.next_round(self.state)
        self.assertEqual(self.state.force.attempt.preparation_remaining, 0)
        final = force.roll_next(self.state, None)
        self.assertTrue(final.state_changes["complete"])
        self.state = jedi()
        force.begin(self.state, req, "jedi")
        WEGD6Rules.apply_damage(self.state, 1)
        self.assertIsNone(self.state.force.attempt)

    def test_resist_stun_requires_minute_and_converts_unconscious_to_stun(self):
        result = self.activate("resist_stun", keep_up=True)
        self.assertTrue(result.success)
        self.assertEqual(WEGD6Rules.apply_damage(self.state, 2), "stun resisted")
        self.assertIsNotNone(effects.find_effect(self.state, "resist_stun"))
        self.assertEqual(WEGD6Rules.apply_damage(self.state, 6, stun=True), "stunned")
        self.assertEqual(self.state.unconscious_rounds, 0)
        self.assertIsNone(effects.find_effect(self.state, "resist_stun"))

    def test_control_pain_waits_one_round_and_does_not_heal(self):
        self.state.wound = "wounded"
        self.activate("control_pain", keep_up=True)
        self.assertIsNone(effects.pain(self.state))
        WEGD6Rules.next_round(self.state)
        self.assertEqual(WEGD6Rules.pool(self.state, "perception")[0], 2)  # 3D - 1D upkeep, no injury penalty
        self.assertEqual(self.state.wound, "wounded")
        WEGD6Rules.apply_damage(self.state, 4)
        self.assertIsNone(effects.pain(self.state))
        self.assertEqual(self.state.wound, "incapacitated")

    def test_remain_conscious_first_next_round_then_one_action_only(self):
        WEGD6Rules.apply_damage(self.state, 10)
        self.assertTrue(self.state.force.remain_pending)
        self.assertFalse(self.state.can_act)
        with self.assertRaises(ValueError):
            force.begin(self.state, ForcePowerRequest(power_id="remain_conscious"), "jedi")
        WEGD6Rules.next_round(self.state)
        WEGD6Rules.declare(self.state, 2)
        result = force.begin(self.state, ForcePowerRequest(power_id="remain_conscious"), "jedi")
        self.assertTrue(result.success)
        WEGD6Rules.roll_skill(self.state, "control", 1)
        self.assertFalse(self.state.can_act)
        self.assertTrue(self.state.out_of_fight)

    def test_reduce_injury_is_immediate_costs_fp_without_doubling_and_records_sacrifice(self):
        self.state.round_state.actions_taken = 1
        WEGD6Rules.apply_damage(self.state, 20)
        result = force.begin(self.state, ForcePowerRequest(power_id="reduce_injury", permanent_injury="Lost left hand"), "jedi")
        self.assertTrue(result.success)
        self.assertEqual(result.roll_result.dice_count, 8)
        self.assertEqual(self.state.force_points, 3)
        self.assertFalse(self.state.round_state.force_active)
        self.assertEqual(self.state.wound, "wounded")
        self.assertIn("Lost left hand", self.state.force.permanent_injuries)

    def test_accelerated_healing_grants_only_two_rolls_with_plus_two(self):
        self.state.wound = "incapacitated"
        # Another conscious Jedi can grant accelerated healing to this patient.
        patient = self.state
        self.state = jedi()
        self.activate("accelerate_another_healing", patient)
        self.assertEqual(patient.force.healing_rolls_remaining, 2)
        with self.assertRaisesRegex(ValueError, "touching"):
            force.accelerated_heal(patient, touching=False)
        first = force.accelerated_heal(patient)
        self.assertEqual(first.roll_result.total, 14)
        self.assertEqual(patient.wound, "wounded")
        force.accelerated_heal(patient)
        self.assertEqual(patient.wound, "healthy")
        with self.assertRaises(ValueError):
            force.accelerated_heal(patient)

    def test_transfer_force_stabilizes_mortal_patient_without_healing_or_refunding(self):
        patient = D6Character(wound="mortally_wounded")
        self.activate("transfer_force", patient)
        self.assertEqual(patient.wound, "mortally_wounded")
        self.assertFalse(patient.can_act)
        self.assertEqual(self.state.force_points, 3)
        self.assertEqual(self.state.force.heroic_force_returns, 1)
        WEGD6Rules.advance_mortality(patient, 10000)
        self.assertEqual(patient.mortal_rounds, 0)
        WEGD6Rules.apply_damage(patient, 1)
        self.assertIsNone(effects.find_effect(patient, "transfer_force"))

    def test_pain_control_never_suppresses_mortal_death_checks(self):
        self.state.wound = "mortally_wounded"
        self.state.force.effects.append(ForceEffect(power_id="control_pain", source_id="jedi", target_id="jedi", maintained=True, skills=["control"]))
        self.assertTrue(self.state.can_act)
        WEGD6Rules.advance_mortality(self.state, 12)
        self.assertEqual(self.state.wound, "dead")
        self.assertFalse(self.state.can_act)

    def test_emptiness_ward_and_bonus_are_flat_and_reduced_by_dark_side(self):
        self.activate("emptiness", duration_rounds=12)
        self.assertFalse(self.state.can_act)
        attacker = jedi()
        req = ForcePowerRequest(power_id="affect_mind", description="See an empty hallway", profile="perception", resistance_total=10, proximity="touching")
        number, _ = force.difficulty(attacker, req, self.state, "sense")
        self.assertEqual(number, 42)  # opposed 10 + Emptiness entry Control 32
        self.state.force.effects = [ForceEffect(power_id="emptiness_bonus", source_id="jedi")]
        self.state.dark_side_points = 2
        self.assertEqual(WEGD6Rules.pool(self.state, "control"), (8, 4))
        self.state.round_state.force_active = True
        self.assertEqual(WEGD6Rules.pool(self.state, "control"), (16, 4))

    def test_affect_mind_requires_declared_effect_and_cannot_target_droids(self):
        target = D6Character()
        with self.assertRaisesRegex(ValueError, "Describe"):
            force.begin(self.state, ForcePowerRequest(power_id="affect_mind"), "jedi", target)
        self.state.force.attempt = None
        with self.assertRaisesRegex(ValueError, "Droids"):
            force.begin(self.state, ForcePowerRequest(power_id="affect_mind", description="Ignore us", target_is_droid=True), "jedi", target)

    def test_relationship_proximity_opposition_and_telekinetic_mass_speed(self):
        target = D6Character()
        req = ForcePowerRequest(power_id="life_sense", relationship="friend", proximity="same_system", willing=False, resistance_total=12)
        self.assertEqual(force.difficulty(self.state, req, target, "sense")[0], 42)
        req = ForcePowerRequest(power_id="telekinesis", mass_kg=100, speed_m_per_round=21, maneuver_modifier=3, proximity="line_of_sight", willing=False, resistance_total=9)
        self.assertEqual(force.difficulty(self.state, req, target, "alter")[0], 39)

    def test_injure_kill_strict_tie_fails_still_awards_dark_side(self):
        target = D6Character()
        result = self.activate("injure_kill", target, resistance_total=32)
        self.assertFalse(result.success)
        self.assertEqual(self.state.dark_side_points, 1)
        self.assertEqual(target.wound, "healthy")
        effects.cancel_attempt(self.state)
        self.state.round_state = D6RoundState()
        result = self.activate("injure_kill", target, resistance_total=20)
        self.assertEqual(target.wound, "incapacitated")
        self.assertEqual(result.damage_roll.total, 32)
        self.assertEqual(result.resistance_roll.total, 20)

    def test_injure_kill_requires_successful_brawling_contact_in_combat(self):
        with self.assertRaisesRegex(ValueError, "brawling"):
            force.begin(self.state, ForcePowerRequest(power_id="injure_kill", target_id="foe", proximity="touching"), "jedi", D6Character(), in_combat=True)

    def test_telekinetic_attack_uses_object_scale_caps_and_dark_side(self):
        self.activate("telekinesis", keep_up=True, mass_kg=200, description="Cargo container")
        held = effects.find_effect(self.state, "telekinesis")
        WEGD6Rules.next_round(self.state)
        target = D6Character()
        result = force.telekinetic_attack(self.state, target, held.id)
        self.assertTrue(result.success)
        self.assertEqual(result.damage_roll.total, 12)
        self.assertEqual(result.resistance_roll.total, 9)  # character Strength dice capped to 3
        self.assertEqual(result.wound_result, "stunned")
        self.assertEqual(self.state.dark_side_points, 1)

    def test_life_detection_free_scan_does_not_spend_declared_action(self):
        target = D6Character(force_sensitive=True)
        self.activate("life_detection", target, keep_up=True)
        WEGD6Rules.next_round(self.state)
        result = force.life_detection_scan(self.state, target)
        self.assertTrue(result.success)
        self.assertEqual(self.state.round_state.actions_taken, 0)
        self.assertIn("Force sensitive: True", result.summary)

    def test_prepared_absorption_uses_actual_damage_and_consumes_one_reaction(self):
        self.state.round_state.absorb_energy = {"character_points": 0, "mishap": "penalty"}
        shooter = D6Character(skills={"blaster": "5D"})
        result = WEGD6Rules.resolve_attack(shooter, self.state, Item(name="Blaster", damage="2D", d6_skill="blaster"))
        self.assertTrue(result.state_changes["absorbed"])
        self.assertEqual(result.force_rolls[0].difficulty, 23)
        self.assertEqual(self.state.wound, "healthy")
        self.assertEqual(self.state.round_state.actions_taken, 1)
        self.assertIsNone(self.state.round_state.absorb_energy)

    def test_redirect_is_extra_control_action_and_preserves_original_bolt_damage(self):
        self.activate("lightsaber_combat", keep_up=True)
        WEGD6Rules.next_round(self.state)
        WEGD6Rules.declare(self.state, 2)
        WEGD6Rules.defense(self.state, "lightsaber")
        target = D6Character()
        from dungeonforge.rules.base import RuleEvaluationResult
        result = RuleEvaluationResult(action_type="attack", success=False, roll_result=force.empty_roll("Parried"), summary="Parried")
        force.redirect_bolt(self.state, target, Item(name="Blaster", damage="3D"), {"difficulty": 10, "range_band": "short", "character_points": 0, "mishap": "penalty", "target_id": "foe"}, result)
        self.assertEqual(self.state.round_state.actions_taken, 2)
        self.assertEqual(result.state_changes["redirected_injury"]["damage"]["dice_count"], 3)


class ForceAPITests(unittest.TestCase):
    def setUp(self):
        preset = CampaignManager.load_campaign("star_wars_d6")
        self.session = GameSession(edition="weg_d6", character=preset.starter_character)
        self.session.character.d6 = jedi()
        session_patch = patch.object(routes, "_ACTIVE_SESSION", self.session)
        session_patch.start()
        self.addCleanup(session_patch.stop)
        dice_patch = patch("dungeonforge.rules.weg_d6.random.randint", return_value=4)
        dice_patch.start()
        self.addCleanup(dice_patch.stop)
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def post(self, endpoint, **payload):
        response = self.client.post(f"/api/weg-d6/force/{endpoint}", json=payload)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_catalog_unavailable_powers_and_invalid_costs_are_atomic(self):
        self.assertEqual(len(self.client.get("/api/weg-d6/force/catalog").json()["powers"]), 22)
        before = self.session.model_dump()
        response = self.client.post("/api/weg-d6/force/begin", json={"power_id": "invented", "force_point": True})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(before, self.session.model_dump())
        response = self.client.post("/api/weg-d6/force/begin", json={"power_id": "control_pain", "force_point": True, "character_points": 1})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(before, self.session.model_dump())

    def test_editor_rejects_missing_power_prerequisites(self):
        char = self.session.character.model_dump()
        char["d6"]["force"]["known_powers"] = ["reduce_injury"]
        response = self.client.post("/api/character", json=char)
        self.assertEqual(response.status_code, 422)
        self.assertIn("Control Pain", response.text)

    def test_persistent_multistep_activation_and_upkeep_survive_save_load(self):
        self.post("begin", power_id="lightsaber_combat", keep_up=True)
        with tempfile.TemporaryDirectory() as directory:
            manager = SaveManager(directory)
            name = manager.save_session(self.session, "force-test")
            loaded = manager.load_session(name)
        self.assertEqual(loaded.character.d6.force.attempt.rolls[0].skill, "control")
        self.assertIsNotNone(loaded.force_boost)
        self.post("continue")
        self.assertEqual(len(self.session.character.d6.force.effects), 1)
        self.post("manage", action="advance", rounds=1)
        self.assertEqual(effects.upkeep(self.session.character.d6), 2)

    def test_failed_component_accepts_cp_without_rerolling_then_finishes(self):
        self.session.character.d6.force_skills["control"] = "3D"
        first = self.post("begin", power_id="control_pain", keep_up=True, base_difficulties={"control": 15})
        self.assertFalse(first["eval_result"]["success"])
        wild = first["eval_result"]["roll_result"]["wild_rolls"]
        boosted = self.post("boost", points=1)
        self.assertTrue(boosted["eval_result"]["state_changes"]["complete"])
        self.assertEqual(boosted["eval_result"]["roll_result"]["wild_rolls"], wild)
        self.assertEqual(self.session.character.d6.character_points, 7)
        self.assertEqual(len(self.session.history), 1)

    def test_raw_roll_closes_force_cp_window(self):
        self.post("begin", power_id="lightsaber_combat", keep_up=True)
        self.client.post("/api/dice/roll", json={"expression": "1d6"})
        self.assertIsNone(self.session.force_boost)
        self.assertEqual(self.client.post("/api/weg-d6/force/boost", json={"points": 1}).status_code, 400)

    def test_scene_preparation_can_advance_quiet_time_without_free_roll(self):
        self.post("begin", power_id="magnify_senses")
        self.post("manage", action="advance", rounds=1)
        self.post("manage", action="advance", rounds=1)
        self.assertEqual(self.session.character.d6.force.attempt.preparation_remaining, 0)
        self.assertEqual(len(self.session.character.d6.force.attempt.rolls), 0)
        self.post("continue")
        self.assertIsNone(self.session.character.d6.force.attempt)

    def test_another_pain_link_ends_when_caster_drops_power(self):
        target = self.session.character.companions[0]
        target.d6.wound = "incapacitated"
        self.post("begin", power_id="control_another_pain", target_id=target.id, relationship="close_friend", proximity="touching", keep_up=True)
        self.post("continue")
        self.post("manage", action="advance", rounds=1)
        self.assertTrue(self.session.character.companions[0].d6.can_act)
        source = self.session.character.d6
        self.post("manage", action="drop", effect_id=source.force.effects[0].id)
        self.assertFalse(self.session.character.companions[0].d6.can_act)

    def test_combat_force_actions_follow_turn_passes(self):
        response = self.client.post("/api/combat/start", json={})
        self.assertEqual(response.status_code, 200, response.text)
        self.session.encounter.current_turn_index = next(i for i, person in enumerate(self.session.encounter.combatants) if person.id == self.session.character.id)
        self.client.post("/api/weg-d6/declare", json={"actions": 2})
        self.post("begin", power_id="lightsaber_combat", keep_up=True)
        self.assertEqual(self.client.post("/api/weg-d6/force/continue", json={}).status_code, 400)
        for _ in range(10):
            self.client.post("/api/combat/next")
            if self.session.encounter.active_combatant.id == self.session.character.id:
                break
        self.post("continue")
        self.assertIsNotNone(effects.find_effect(self.session.character.d6, "lightsaber_combat"))

    def test_force_power_is_available_to_ship_crew_and_upkeep_affects_piloting(self):
        self.client.post("/api/weg-d6/vehicles/add", json={"preset": "yt1300"})
        craft = self.session.vehicles[0]
        response = self.client.post("/api/weg-d6/vehicles/start", json={"vehicle_id": craft.id, "enemies": ["tie_fighter"], "environment": "space"})
        self.assertEqual(response.status_code, 200, response.text)
        encounter = self.session.vehicle_encounter
        encounter.current_turn_index = encounter.actor_order.index(self.session.character.id)
        self.post("begin", power_id="telekinesis", keep_up=True, description="A loose tool", proximity="touching")
        self.assertTrue(self.session.vehicle_encounter.turn_acted)
        self.assertEqual(self.session.character.d6.round_state.actions_taken, 1)
        self.assertIsNotNone(effects.find_effect(self.session.character.d6, "telekinesis"))
        WEGD6Rules.next_round(self.session.character.d6)
        self.assertEqual(WEGD6Rules.pool(self.session.character.d6, "space_transports")[0], 2)  # jedi's 3D Mechanical, minus upkeep

    def test_emptiness_exit_duration_and_early_exit_rejection(self):
        self.post("begin", power_id="emptiness", duration_rounds=12)
        effect = self.session.character.d6.force.effects[0]
        response = self.client.post("/api/weg-d6/force/manage", json={"action": "leave_emptiness", "effect_id": effect.id})
        self.assertEqual(response.status_code, 400)
        self.post("manage", action="advance", rounds=12)
        self.post("manage", action="leave_emptiness", effect_id=effect.id)
        bonus = effects.find_effect(self.session.character.d6, "emptiness_bonus")
        self.assertEqual(bonus.rounds_remaining, 12)
        self.assertTrue(self.session.character.d6.can_act)

    def test_timed_hibernation_blocks_other_actions_and_wakes_at_declared_time(self):
        self.post("begin", power_id="hibernation_trance", keep_up=True, duration_rounds=12, description="A touch on the shoulder")
        self.assertFalse(self.session.character.d6.can_act)
        self.assertEqual(self.client.post("/api/weg-d6/check", json={"skill": "search"}).status_code, 400)
        self.post("manage", action="advance", rounds=11)
        self.assertFalse(self.session.character.d6.can_act)
        self.post("manage", action="advance", rounds=1)
        self.assertTrue(self.session.character.d6.can_act)

    def test_unlearned_campaign_starter_receives_no_automatic_powers(self):
        preset = CampaignManager.load_campaign("star_wars_d6")
        self.assertTrue(preset.starter_character.d6.force_sensitive)
        self.assertFalse(preset.starter_character.d6.force.known_powers)
        self.assertEqual(preset.starter_character.d6.force_skills["control"], "0D")

    def test_another_roll_closes_immediate_injury_reduction_window(self):
        state = self.session.character.d6
        WEGD6Rules.apply_damage(state, 16)
        self.assertTrue(state.force.reduce_injury_available)
        before = state.force_points
        self.client.post("/api/weg-d6/pool", json={"code": "2D"})
        response = self.client.post("/api/weg-d6/force/begin", json={"power_id": "reduce_injury", "permanent_injury": "Lost hand"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.session.character.d6.force_points, before)

    def test_prepared_absorption_is_declared_before_shot_and_not_ship_hull_protection(self):
        self.client.post("/api/combat/start", json={})
        self.post("prepare-reaction", action="absorb_energy")
        self.assertIsNotNone(self.session.character.d6.round_state.absorb_energy)
        self.assertEqual(self.session.character.d6.round_state.actions_taken, 0)
        self.client.post("/api/combat/end")
        self.client.post("/api/weg-d6/vehicles/add", json={"preset": "yt1300"})
        self.client.post("/api/weg-d6/vehicles/start", json={"vehicle_id": self.session.vehicles[0].id, "enemies": ["tie_fighter"]})
        self.assertEqual(self.client.post("/api/weg-d6/force/prepare-reaction", json={"action": "absorb_energy"}).status_code, 400)

    def test_brawling_touch_marks_only_this_round_and_uses_its_action_pass(self):
        self.session.character.d6.skills["brawling"] = "6D"
        self.client.post("/api/combat/start", json={})
        encounter = self.session.encounter
        encounter.current_turn_index = next(i for i, person in enumerate(encounter.combatants) if person.id == self.session.character.id)
        target = next(person for person in encounter.combatants if not person.is_player)
        self.client.post("/api/weg-d6/declare", json={"actions": 2})
        self.post("touch", target_id=target.id)
        self.assertIn(target.id, self.session.character.d6.round_state.touched_targets)
        self.assertEqual(target.d6.wound, "healthy")
        self.assertTrue(self.session.encounter.d6_turn_acted)
        self.assertEqual(self.client.post("/api/weg-d6/force/begin", json={"power_id": "injure_kill", "target_id": target.id, "proximity": "touching"}).status_code, 400)
        for _ in range(10):
            self.client.post("/api/combat/next")
            if self.session.encounter.active_combatant.id == self.session.character.id:
                break
        self.post("begin", power_id="injure_kill", target_id=target.id, proximity="touching", resistance_total=20)
        self.assertEqual(self.session.character.d6.dark_side_points, 1)
        WEGD6Rules.next_round(self.session.character.d6)
        self.assertFalse(self.session.character.d6.round_state.touched_targets)

    def test_force_cp_window_closes_on_next_ship_action(self):
        self.client.post("/api/weg-d6/vehicles/add", json={"preset": "yt1300"})
        self.client.post("/api/weg-d6/vehicles/start", json={"vehicle_id": self.session.vehicles[0].id, "enemies": ["tie_fighter"]})
        encounter = self.session.vehicle_encounter
        encounter.current_turn_index = encounter.actor_order.index(self.session.character.id)
        self.client.post("/api/weg-d6/vehicles/declare", json={"actor_id": self.session.character.id, "actions": 2})
        self.post("begin", power_id="lightsaber_combat", keep_up=True)
        self.assertIsNotNone(self.session.force_boost)
        self.client.post("/api/weg-d6/vehicles/next")
        self.assertIsNone(self.session.force_boost)

    def test_failed_emptiness_exit_observes_hourly_retry_limit(self):
        self.post("begin", power_id="emptiness", duration_rounds=12)
        self.post("manage", action="advance", rounds=12)
        self.session.character.d6.force_skills["control"] = "3D"
        effect = self.session.character.d6.force.effects[0]
        first = self.post("manage", action="leave_emptiness", effect_id=effect.id)
        self.assertFalse(first["eval_result"]["success"])
        response = self.client.post("/api/weg-d6/force/manage", json={"action": "leave_emptiness", "effect_id": effect.id})
        self.assertEqual(response.status_code, 400)
        self.post("manage", action="advance", rounds=720)
        self.session.character.d6.force_skills["control"] = "8D"
        self.post("manage", action="leave_emptiness", effect_id=effect.id)
        self.assertEqual(effects.find_effect(self.session.character.d6, "emptiness_bonus").rounds_remaining, 732)

    def test_rest_advances_other_characters_force_durations(self):
        patient = self.session.character.companions[0]
        patient.d6.force.effects.append(ForceEffect(power_id="emptiness_bonus", source_id=patient.id, rounds_remaining=5))
        response = self.client.post("/api/weg-d6/recover", json={"method": "rest", "minutes": 1})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIsNone(effects.find_effect(patient.d6, "emptiness_bonus"))
        self.assertEqual(patient.d6.force.elapsed_rounds, 12)

    def test_chronicle_includes_training_and_pending_force_activation(self):
        self.post("begin", power_id="lightsaber_combat", keep_up=True)
        with tempfile.TemporaryDirectory() as directory:
            chronicle = SaveManager(directory).export_markdown_chronicle(self.session)
        self.assertIn("Lightsaber Combat", chronicle)
        self.assertIn("skills resolved 1/2", chronicle)
        self.assertIn("Control 8D", chronicle)

    def test_cp_boosted_reduce_injury_can_reopen_an_encounter_after_a_killing_blow(self):
        self.session.character.companions = []
        self.session.character.d6.force_skills["control"] = "6D"
        self.client.post("/api/combat/start", json={})
        from dungeonforge.game import weg_combat
        WEGD6Rules.apply_damage(self.session.character.d6, 16)
        weg_combat.refresh(self.session.encounter)
        self.assertFalse(self.session.encounter.active)
        first = self.post("begin", power_id="reduce_injury", permanent_injury="Lost hand")
        self.assertFalse(first["eval_result"]["success"])
        self.post("boost", points=2)
        self.assertEqual(self.session.character.d6.wound, "wounded")
        self.assertEqual(self.session.character.d6.force_points, 3)
        self.assertTrue(self.session.encounter.active)

    def test_declared_saber_parry_redirects_the_specified_attack_in_combat(self):
        self.session.character.inventory = [Item(name="Lightsaber", damage="5D", d6_skill="lightsaber", equipped=True, item_type="weapon")]
        self.post("begin", power_id="lightsaber_combat", keep_up=True)
        self.post("continue")
        self.client.post("/api/combat/start", json={})
        foe = next(person for person in self.session.encounter.combatants if not person.is_player)
        response = self.client.post("/api/weg-d6/declare", json={"actions": 2})
        self.assertEqual(response.status_code, 200, response.text)
        response = self.client.post("/api/weg-d6/defend", json={"skill": "lightsaber"})
        self.assertEqual(response.status_code, 200, response.text)
        self.post("prepare-reaction", action="redirect_blaster", attacker_id=foe.id, target_id=foe.id)
        self.session.encounter.current_turn_index = next(index for index, actor in enumerate(self.session.encounter.combatants) if actor.id == foe.id)
        response = self.client.post("/api/combat/attack", json={"attacker_id": foe.id, "target_id": self.session.character.id})
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()["eval_result"]
        self.assertTrue(result["state_changes"]["parried_blaster"])
        self.assertIn("redirected_injury", result["state_changes"])
        self.assertEqual(self.session.character.d6.round_state.actions_taken, 2)
        self.assertEqual(result["state_changes"]["redirected_injury"]["damage"]["expression"], foe.weapon.damage)


if __name__ == "__main__":
    unittest.main()
