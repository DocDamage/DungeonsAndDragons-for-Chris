import math
import tempfile
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from pydantic import ValidationError

from dungeonforge.api import routes, weg_explosives_routes as api, weg_force_routes as force_api
from dungeonforge.game.combat import CombatEncounter, Combatant
from dungeonforge.game.models import GameSession
from dungeonforge.game.saves import SaveManager
from dungeonforge.game import weg_combat
from dungeonforge.rules import weg_explosives as rules
from dungeonforge.rules.base import Character, Companion
from dungeonforge.rules.dice import RollResult
from dungeonforge.rules.weg_d6 import D6Roller, WEGD6Rules
from dungeonforge.rules.weg_equipment import make_item
from dungeonforge.rules.weg_models import D6Character
from dungeonforge.rules.weg_cover_models import D6CoverObject
from dungeonforge.rules.weg_force_models import ForcePowerRequest
from dungeonforge.rules.weg_explosives_models import (
    D6BlastPoint, D6BlastPosition, D6BlastPositionsRequest, D6GrenadeIntentRequest,
    D6GrenadeStepRequest, D6GrenadeRethrowRequest, D6GrenadeThrowRequest,
)


def roll(total, dice=1):
    return RollResult(expression=f"{dice}D", dice_count=dice, die_type=6, total=total, system="weg_d6", breakdown=f"controlled actual total {total}")


def native_roll(dice, pips=0, bonus=0, *args, **kwargs):
    return roll(dice * 3 + pips + bonus * 3, dice)


class ExplosiveTests(unittest.TestCase):
    def setUp(self):
        self.weapon = make_item("fragmentation_grenade")
        self.weapon.equipped, self.weapon.equipped_by = True, "hero"
        self.hero = Combatant(id="hero", name="Actual hero", is_player=True,
            d6=D6Character(skills={"grenade": "6D"}), weapon=self.weapon)
        self.ally = Combatant(id="ally", name="Actual ally", is_player=True, d6=D6Character(skills={"grenade": "6D"}))
        self.enemy = Combatant(id="enemy", name="Actual enemy", d6=D6Character())
        self.outside = Combatant(id="outside", name="Actual bystander", d6=D6Character())
        self.encounter = CombatEncounter(system="weg_d6", combatants=[self.hero, self.ally, self.enemy, self.outside])
        rules.review_positions(self.encounter, self.positions())

    def positions(self, **changes):
        data = dict(positions=[D6BlastPosition(actor_id=id, point=D6BlastPoint(x=x, y=0), side="front")
            for id, x in [("hero", 0), ("ally", 5), ("enemy", 10), ("outside", 30)]],
            all_scene_actors_confirmed=True, same_plane_unobstructed_confirmed=True,
            independent_damage_rolls_confirmed=True, distance_rounding="up", reason="GM confirms actual exhaustive scene occupants and unobstructed positions.", expected_updated_at=1)
        return D6BlastPositionsRequest(**{**data, **changes})

    def throw_request(self, **changes):
        return D6GrenadeThrowRequest(**{**dict(actor_id="hero", item_id=self.weapon.id, target=D6BlastPoint(x=10, y=0),
            trigger="timer", timer_seconds=4, timer_rounding_confirmed=True,
            reason="Actual assigned grenade and GM landing point/fuse reviewed.", expected_updated_at=1), **changes})

    def armed(self, **changes):
        with patch.object(D6Roller, "values", return_value=roll(30, 6)):
            result = rules.throw(self.encounter, self.throw_request(**changes))
        return self.encounter.d6_explosives.grenades[-1], result

    def test_positions_are_exhaustive_actual_roster_and_cannot_hide_party(self):
        for positions in (self.positions().positions[:-1], self.positions().positions + [self.positions().positions[0]]):
            with self.assertRaisesRegex(ValueError, "each actual"):
                rules.review_positions(self.encounter, self.positions(positions=positions))
        with self.assertRaisesRegex(ValueError, "Review exhaustive"):
            rules.review_positions(self.encounter, self.positions(all_scene_actors_confirmed=False))
        with self.assertRaises(ValidationError):
            D6BlastPoint(x=float("nan"), y=0)

    def test_plain_scatter_all_six_visual_directions_and_range_dice(self):
        expected = {1: (0, 6), 2: (math.sqrt(18), math.sqrt(18)), 3: (6, 0),
            4: (0, -6), 5: (-6, 0), 6: (-math.sqrt(18), math.sqrt(18))}
        for direction, (x, y) in expected.items():
            with self.subTest(direction=direction), patch.object(rules.DiceRoller, "roll", side_effect=[roll(direction), roll(6)]) as dice:
                _, _, actual = rules.scatter(D6BlastPoint(x=0, y=0), D6BlastPoint(x=0, y=10), None, "short")
                self.assertAlmostEqual(actual.x, x)
                self.assertAlmostEqual(actual.y, 10 + y)
                self.assertEqual([call.args[0] for call in dice.call_args_list], ["1d6", "1d6"])
        for band, expression in [("point_blank", "1d6"), ("medium", "2d6"), ("long", "3d6")]:
            with patch.object(rules.DiceRoller, "roll", side_effect=[roll(1), roll(3)]) as dice:
                rules.scatter(D6BlastPoint(x=0, y=0), D6BlastPoint(x=10, y=0), None, band)
            self.assertEqual(dice.call_args_list[1].args[0], expression)

    def test_miss_saves_actual_scatter_and_single_physical_grenade_is_spent_once(self):
        with patch.object(D6Roller, "values", return_value=roll(1)), patch.object(rules.DiceRoller, "roll", side_effect=[roll(3), roll(4, 2)]):
            rules.throw(self.encounter, self.throw_request(character_points=1))
        grenade = self.encounter.d6_explosives.grenades[0]
        self.assertEqual((grenade.position.x, grenade.position.y), (10, -4))
        self.assertEqual((grenade.throws[0].range_band, grenade.throws[0].scatter_direction.total, grenade.throws[0].scatter_distance.total), ("medium", 3, 4))
        self.assertEqual((self.weapon.quantity, self.weapon.ammo, self.hero.d6.character_points), (0, 0, 4))
        self.assertTrue(rules.pending(self.encounter))
        self.encounter.d6_turn_acted = False
        self.hero.d6.round_state.declared_actions = 2
        with self.assertRaisesRegex(ValueError, "single-use"):
            rules.throw(self.encounter, self.throw_request())

    def test_drawn_assigned_single_grenade_and_native_turn_are_required_before_roll(self):
        for field, value in [("quantity", 2), ("equipped", False), ("equipped_by", "ally"), ("ammo", 0), ("catalog_id", "anti_vehicle_mine")]:
            original = getattr(self.weapon, field)
            setattr(self.weapon, field, value)
            with self.subTest(field=field), patch.object(D6Roller, "values") as dice, self.assertRaises(ValueError):
                rules.throw(self.encounter, self.throw_request())
            dice.assert_not_called()
            setattr(self.weapon, field, original)
        with self.assertRaisesRegex(ValueError, "current|Advance"):
            rules.throw(self.encounter, self.throw_request(actor_id="ally"))

    def test_short_timer_contact_long_timer_and_no_resolved_reroll(self):
        grenade, _ = self.armed(timer_seconds=4.9)
        self.assertEqual((grenade.due_round, grenade.status), (1, "armed"))
        with patch.object(D6Roller, "values", side_effect=native_roll) as dice:
            results = rules.end_round(self.encounter, 1)
            calls = dice.call_count
            self.assertEqual(len(results), 1)
            self.assertEqual(rules.end_round(self.encounter, 1), [])
            self.assertEqual(dice.call_count, calls)
        self.assertEqual(grenade.status, "resolved")
        with self.assertRaisesRegex(ValueError, "already resolved"):
            rules.detonate(self.encounter, grenade, 1)
        self.setUp()
        grenade, _ = self.armed(timer_seconds=10.1)
        self.assertEqual(grenade.due_round, 3)
        self.assertEqual(rules.end_round(self.encounter, 1), [])
        self.assertEqual(rules.end_round(self.encounter, 2), [])
        self.setUp()
        grenade, result = self.armed(trigger="contact", timer_seconds=None)
        self.assertEqual(grenade.status, "resolved")
        self.assertIn("detonation", result.state_changes)
        with self.assertRaisesRegex(ValueError, "still-live"):
            rules.live_grenade(self.encounter, grenade.id)

    def test_blast_hits_party_actual_distance_bands_and_free_full_strength(self):
        self.hero.d6.round_state.declared_actions = 3
        grenade, _ = self.armed()
        with patch.object(D6Roller, "values", side_effect=native_roll):
            rules.end_round(self.encounter, 1)
        victims = {victim.actor_id: victim for victim in grenade.victims}
        self.assertEqual({id: victim.damage_code for id, victim in victims.items()}, {"hero": "2D", "ally": "3D", "enemy": "5D", "outside": None})
        self.assertEqual(victims["hero"].resistance_roll.dice_count, 3)
        self.assertEqual(victims["enemy"].after, "wounded")
        self.assertEqual(self.enemy.d6.wound, "wounded")
        self.assertFalse(victims["outside"].affected)
        self.assertEqual(len(victims), 4)

    def test_native_timer_never_freezes_for_predeclared_resistance_points_spent_elsewhere(self):
        self.encounter.d6_explosives.positions["enemy"].resistance_character_points = 5
        grenade, _ = self.armed()
        self.enemy.d6.character_points = 0
        with patch.object(D6Roller, "values", side_effect=native_roll):
            rules.end_round(self.encounter, 1)
        enemy = next(victim for victim in grenade.victims if victim.actor_id == "enemy")
        self.assertEqual((enemy.character_points, self.enemy.d6.character_points, grenade.status), (0, 0, "resolved"))
        self.assertIn("no longer available", enemy.point_note)

    def test_later_partial_armor_or_cover_cannot_freeze_a_live_timer_or_gain_blanket_protection(self):
        grenade, _ = self.armed()
        vest = make_item("blast_vest")
        self.enemy.armor = [vest]
        self.enemy.cover_id, self.enemy.cover_fraction = "later_cover", "full"
        self.encounter.cover_objects.append(D6CoverObject(id="later_cover", name="Later actual barrier", body="4D", reason="Actual unsupported geometry drift cannot freeze the saved fuse."))
        with patch.object(D6Roller, "values", side_effect=native_roll):
            rules.end_round(self.encounter, 1)
        victim = next(victim for victim in grenade.victims if victim.actor_id == "enemy")
        self.assertEqual(grenade.status, "resolved")
        self.assertEqual(victim.resistance_roll.dice_count, 3)
        self.assertIn("no blanket protection", victim.point_note)
        self.assertIsNone(victim.armor_damage)

    def test_partial_armor_uses_actual_location_and_damage_persists(self):
        vest = make_item("blast_vest")
        vest.equipped, vest.equipped_by = True, "enemy"
        self.enemy.armor = [vest]
        with self.assertRaisesRegex(ValueError, "actual hit location"):
            rules.actual_positions(self.encounter)
        self.encounter.d6_explosives.positions["enemy"].hit_location = "torso"
        grenade, _ = self.armed()
        with patch.object(D6Roller, "values", side_effect=lambda dice, pips=0, bonus=0, **kwargs: roll(20, 5) if dice == 5 else native_roll(dice, pips, bonus)):
            rules.end_round(self.encounter, 1)
        enemy = next(victim for victim in grenade.victims if victim.actor_id == "enemy")
        self.assertEqual(enemy.resistance_roll.dice_count, 4)
        self.assertEqual(vest.armor_damage_state, "lightly_damaged")
        self.assertEqual(enemy.armor_damage["after"], "lightly_damaged")

    def test_live_position_rewrites_are_not_free_escape_and_intent_must_precede_landing(self):
        self.armed()
        with self.assertRaisesRegex(ValueError, "free position edits"):
            rules.review_positions(self.encounter, self.positions())
        self.ally.d6.round_state.declared_actions = 3
        with self.assertRaisesRegex(ValueError, "before"):
            rules.declare_rethrow(self.encounter, D6GrenadeIntentRequest(actor_id="ally", reason="Too late", expected_updated_at=1))

    def test_toss_away_is_three_native_action_passes_and_never_resets_fuse_or_spawns_grenade(self):
        self.ally.d6.round_state.declared_actions = 3
        req = D6GrenadeIntentRequest(actor_id="ally", reason="Actual declaration before incoming grenade lands.", expected_updated_at=1)
        rules.declare_rethrow(self.encounter, req)
        grenade, _ = self.armed(target=D6BlastPoint(x=5, y=0))
        due = grenade.due_round
        weg_combat.next_turn(self.encounter)
        step = D6GrenadeStepRequest(actor_id="ally", grenade_id=grenade.id, clear_path_confirmed=True, reason="Actual clear approach, grab and toss.", expected_updated_at=1)
        rules.approach(self.encounter, step)
        self.assertEqual(self.ally.d6.round_state.actions_taken, 1)
        with self.assertRaisesRegex(ValueError, "action pass"):
            rules.grab(self.encounter, step)
        for _ in range(5):
            weg_combat.next_turn(self.encounter)
            if self.encounter.active_combatant.id == "ally":
                break
        rules.grab(self.encounter, step)
        self.assertEqual((self.ally.d6.round_state.actions_taken, grenade.holder_id), (2, "ally"))
        weg_combat.next_turn(self.encounter)
        rethrow = D6GrenadeRethrowRequest(**step.model_dump(), target=D6BlastPoint(x=30, y=0))
        with patch.object(D6Roller, "values", return_value=roll(30)):
            rules.rethrow(self.encounter, rethrow)
        intent = self.encounter.d6_explosives.intents[0]
        self.assertEqual([action["operation"] for action in intent.actions], ["move", "grab", "throw"])
        self.assertEqual((self.ally.d6.round_state.actions_taken, intent.stage, grenade.due_round, self.weapon.quantity, self.weapon.ammo), (3, "thrown", due, 0, 0))
        self.assertEqual(len(grenade.throws), 2)
        self.assertEqual(grenade.position.x, 30)

    def test_pending_fuse_scatter_positions_and_actual_spent_inventory_survive_save_load(self):
        grenade, _ = self.armed(timer_seconds=9)
        character = Character(id="hero", name="Actual hero", edition="weg_d6", d6=self.hero.d6, inventory=[self.weapon],
            companions=[Companion(id="ally", name="Actual ally", d6=self.ally.d6)])
        session = GameSession(edition="weg_d6", character=character, encounter=self.encounter, source_folders=[])
        with tempfile.TemporaryDirectory() as directory:
            manager = SaveManager(directory)
            restored = manager.load_session(manager.save_session(session, "live_grenade"))
        self.assertEqual(restored.encounter.d6_explosives.model_dump(), self.encounter.d6_explosives.model_dump())
        self.assertEqual((restored.character.inventory[0].quantity, restored.character.inventory[0].ammo), (0, 0))
        with patch.object(D6Roller, "values", side_effect=native_roll):
            rules.end_round(restored.encounter, grenade.due_round)
        self.assertEqual(restored.encounter.d6_explosives.grenades[0].status, "resolved")

    def test_api_invalid_or_stale_attempts_are_transactional(self):
        character = Character(id="hero", name="Actual hero", edition="weg_d6", d6=self.hero.d6, inventory=[self.weapon],
            companions=[Companion(id="ally", name="Actual ally", d6=self.ally.d6)])
        session = GameSession(edition="weg_d6", character=character, encounter=self.encounter, source_folders=[])
        with patch.object(routes, "_ACTIVE_SESSION", session):
            before = session.model_dump()
            with self.assertRaises(HTTPException):
                api.throw(self.throw_request())
            self.assertEqual(before, session.model_dump())
            bad = self.throw_request(expected_updated_at=session.updated_at, visible_landing=False)
            with patch.object(D6Roller, "values") as dice, self.assertRaises(HTTPException):
                api.throw(bad)
            dice.assert_not_called()
            self.assertEqual(before, session.model_dump())

    def test_actual_blast_band_boundaries_and_explicit_fractional_ruling(self):
        self.assertEqual([rules.blast_code("fragmentation_grenade", meters) for meters in [0, 2, 3, 4, 5, 6, 7, 10, 11]],
            ["5D", "5D", "4D", "4D", "3D", "3D", "2D", "2D", None])
        self.assertEqual([rules.blast_code("thermal_detonator", meters) for meters in [2, 3, 8, 9, 12, 13, 20, 21]],
            ["10D", "8D", "8D", "5D", "5D", "2D", "2D", None])
        self.encounter.d6_explosives.positions["ally"].point = D6BlastPoint(x=7.99, y=0)
        grenade, _ = self.armed()
        with patch.object(D6Roller, "values", side_effect=native_roll):
            rules.end_round(self.encounter, 1)
        self.assertEqual(next(victim for victim in grenade.victims if victim.actor_id == "ally").damage_code, "4D")

    def test_timer_can_detonate_between_actual_toss_steps(self):
        self.ally.d6.round_state.declared_actions = 3
        rules.declare_rethrow(self.encounter, D6GrenadeIntentRequest(actor_id="ally", reason="Before landing", expected_updated_at=1))
        grenade, _ = self.armed(target=D6BlastPoint(x=5, y=0))
        weg_combat.next_turn(self.encounter)
        step = D6GrenadeStepRequest(actor_id="ally", grenade_id=grenade.id, clear_path_confirmed=True, reason="Actual approach", expected_updated_at=1)
        rules.approach(self.encounter, step)
        with patch.object(D6Roller, "values", side_effect=native_roll):
            rules.end_round(self.encounter, 1)
        self.assertEqual(grenade.status, "resolved")
        self.assertEqual(self.encounter.d6_explosives.intents[0].stage, "approached")
        with self.assertRaisesRegex(ValueError, "still-live"):
            rules.live_grenade(self.encounter, grenade.id)

    def test_contact_api_preserves_actual_immediate_reduce_injury_window(self):
        self.ally.d6.force_sensitive = True
        self.ally.d6.force_skills["control"] = "6D"
        self.ally.d6.force.known_powers = ["control_pain", "reduce_injury"]
        character = Character(id="hero", name="Actual hero", edition="weg_d6", d6=self.hero.d6, inventory=[self.weapon],
            companions=[Companion(id="ally", name="Actual ally", d6=self.ally.d6)])
        session = GameSession(edition="weg_d6", character=character, encounter=self.encounter, source_folders=[])
        with patch.object(routes, "_ACTIVE_SESSION", session), patch.object(D6Roller, "values", side_effect=[roll(30), roll(9), roll(9), roll(20), roll(9), roll(9), roll(9)]):
            result = api.throw(self.throw_request(expected_updated_at=session.updated_at, target=D6BlastPoint(x=5, y=0), trigger="contact", timer_seconds=None))
        self.assertIn("ally", result["eval_result"].state_changes["force_injury_targets"])
        self.assertEqual(session.character.companions[0].d6.wound, "incapacitated")
        self.assertTrue(session.character.companions[0].d6.force.reduce_injury_available)

    def test_native_round_end_resolves_due_timer_before_round_reset_and_once(self):
        grenade, _ = self.armed()
        for actor in self.encounter.combatants:
            actor.d6.round_state.actions_taken = actor.d6.round_state.declared_actions
        before = self.hero.d6.force.elapsed_rounds
        with patch.object(D6Roller, "values", side_effect=native_roll):
            weg_combat.next_turn(self.encounter)
        self.assertEqual(grenade.status, "resolved")
        self.assertTrue(self.encounter.d6_round_closing)
        self.assertEqual(self.encounter.round, 1)
        self.assertEqual(self.hero.d6.force.elapsed_rounds, before)
        self.assertEqual(len(self.encounter.d6_round_results), 1)
        with patch.object(weg_combat, "roll_initiative"):
            weg_combat.next_turn(self.encounter)
        self.assertFalse(self.encounter.d6_round_closing)
        self.assertEqual(self.encounter.round, 2)
        self.assertEqual(self.hero.d6.force.elapsed_rounds, before + 1)
        self.assertEqual(self.encounter.d6_round_results, [])

    def test_two_due_blasts_allow_actual_reduce_injury_between_checkpoints_before_any_tick(self):
        self.ally.d6.force_sensitive = True
        self.ally.d6.force_skills["control"] = "6D"
        self.ally.d6.force.known_powers = ["control_pain", "reduce_injury"]
        self.ally.d6.force_points = self.ally.d6.rewards.starting_force_points = 2
        second_weapon = make_item("fragmentation_grenade")
        second_weapon.equipped, second_weapon.equipped_by = True, self.enemy.id
        self.enemy.weapon, self.enemy.inventory = second_weapon, [second_weapon]
        first, _ = self.armed(target=D6BlastPoint(x=5, y=0))
        weg_combat.next_turn(self.encounter)  # Actual ally action pass.
        weg_combat.next_turn(self.encounter)  # Ally skips, then actual enemy pass.
        with patch.object(D6Roller, "values", return_value=roll(30, 6)):
            rules.throw(self.encounter, self.throw_request(actor_id="enemy", item_id=second_weapon.id, target=D6BlastPoint(x=5, y=0)))
        second = self.encounter.d6_explosives.grenades[1]
        character = Character(id="hero", name="Actual hero", edition="weg_d6", d6=self.hero.d6, inventory=[self.weapon],
            companions=[Companion(id="ally", name="Actual ally", d6=self.ally.d6)])
        session = GameSession(edition="weg_d6", character=character, encounter=self.encounter, source_folders=[])
        before_clock = self.ally.d6.force.elapsed_rounds
        def blast_roll(dice, pips=0, bonus=0, *args, **kwargs):
            return roll(20, 5) if dice == 5 else native_roll(dice, pips, bonus)
        with patch.object(routes, "_ACTIVE_SESSION", session):
            with patch.object(D6Roller, "values", side_effect=blast_roll):
                for _ in range(5):
                    weg_combat.next_turn(session.encounter)
                    if session.encounter.d6_round_closing:
                        break
            self.assertEqual([item.status for item in session.encounter.d6_explosives.grenades], ["resolved", "armed"])
            self.assertEqual(session.encounter.round, 1)
            self.assertEqual(session.character.companions[0].d6.force.elapsed_rounds, before_clock)
            self.assertTrue(session.character.companions[0].d6.force.reduce_injury_available)
            with patch.object(D6Roller, "values", return_value=roll(30, 6)):
                force_api.begin(ForcePowerRequest(actor_id="ally", power_id="reduce_injury"))
            self.assertEqual((session.character.companions[0].d6.wound, session.character.companions[0].d6.force_points), ("wounded", 1))
            with patch.object(D6Roller, "values", side_effect=blast_roll):
                weg_combat.next_turn(session.encounter)
            self.assertEqual([item.status for item in session.encounter.d6_explosives.grenades], ["resolved", "resolved"])
            self.assertTrue(session.encounter.d6_round_closing)
            self.assertEqual(session.encounter.round, 1)
            self.assertEqual(session.character.companions[0].d6.force.elapsed_rounds, before_clock)
            self.assertEqual(session.character.companions[0].d6.wound, "incapacitated")
            self.assertTrue(session.character.companions[0].d6.force.reduce_injury_available)
            with patch.object(D6Roller, "values", return_value=roll(30, 6)):
                force_api.begin(ForcePowerRequest(actor_id="ally", power_id="reduce_injury"))
            self.assertEqual((session.character.companions[0].d6.wound, session.character.companions[0].d6.force_points), ("wounded", 0))
            with patch.object(weg_combat, "roll_initiative"):
                weg_combat.next_turn(session.encounter)
        self.assertEqual(session.encounter.round, 2)
        self.assertFalse(session.encounter.d6_round_closing)
        self.assertEqual(session.character.companions[0].d6.force.elapsed_rounds, before_clock + 1)
        self.assertEqual((first.item_id, second.item_id), (self.weapon.id, second_weapon.id))


if __name__ == "__main__":
    unittest.main()
