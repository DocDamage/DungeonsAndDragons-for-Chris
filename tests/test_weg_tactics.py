"""Actual combat gear, exclusive preparation, physical cover and optional locations."""
import asyncio
import tempfile
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from dungeonforge.api import routes
from dungeonforge.api.schemas import CombatAttackRequest
from dungeonforge.api.weg_tactics_routes import D6GearAction, gear, cover_facts
from dungeonforge.game.combat import CombatEncounter, Combatant
from dungeonforge.game.models import GameSession
from dungeonforge.game.saves import SaveManager
from dungeonforge.game import weg_combat
from dungeonforge.rules.base import Character
from dungeonforge.rules.dice import RollResult
from dungeonforge.rules.weg_cover_models import D6CoverObject, D6CoverFacts
from dungeonforge.rules.weg_d6 import WEGD6Rules
from dungeonforge.rules.weg_equipment import make_item
from dungeonforge.rules.weg_models import D6Character, D6Options, D6RoundState


def roll(total):
    return RollResult(expression="3D", dice_count=3, die_type=6, total=total, system="weg_d6", breakdown=str(total))


class TacticsTests(unittest.TestCase):
    def setUp(self):
        self.original = routes._ACTIVE_SESSION
        weapon = make_item("blaster_dl18")
        weapon.equipped, weapon.equipped_by = True, "hero"
        hero = Character(id="hero", name="Hero", d6=D6Character(), inventory=[weapon])
        encounter = CombatEncounter(system="weg_d6", combatants=[
            Combatant(id="hero", name="Hero", is_player=True, d6=hero.d6, weapon=weapon),
            Combatant(id="foe", name="Foe", d6=D6Character(), weapon=make_item("blaster_dl18")),
        ])
        routes._ACTIVE_SESSION = GameSession(edition="weg_d6", character=hero, encounter=encounter)

    def tearDown(self):
        routes._ACTIVE_SESSION = self.original

    @property
    def session(self):
        return routes._ACTIVE_SESSION

    def action(self, action, **changes):
        return gear(D6GearAction(actor_id="hero", action=action, item_id=self.session.character.inventory[0].id,
            expected_updated_at=self.session.updated_at, **changes))

    def test_setting_uses_real_action_and_attack_must_match_actual_setting(self):
        self.session.character.d6.round_state.declared_actions = 2
        self.session.encounter.combatants[0].d6 = self.session.character.d6
        self.action("setting", stun=True)
        self.assertTrue(self.session.character.inventory[0].stun_mode)
        self.assertEqual(self.session.character.d6.round_state.actions_taken, 1)
        self.assertTrue(self.session.encounter.d6_turn_acted)
        self.session.encounter.d6_turn_acted = False
        before = self.session.model_dump()
        with self.assertRaises(HTTPException):
            asyncio.run(routes.combat_attack(CombatAttackRequest(target_id="foe", d6_options=D6Options(stun=False))))
        self.assertEqual(self.session.model_dump(), before)

    def test_reload_consumes_only_actual_compatible_supply_and_one_action(self):
        self.session.character.inventory[0].ammo = 0
        pack = make_item("standard_blaster_power_pack")
        self.session.character.inventory.append(pack)
        self.action("reload")
        self.assertEqual(self.session.character.inventory[0].ammo, 100)
        self.assertFalse(any(item.id == pack.id for item in self.session.character.inventory))
        self.assertEqual(self.session.character.d6.round_state.actions_taken, 1)

    def test_no_supply_reload_is_atomic(self):
        self.session.character.inventory[0].ammo = 0
        before = self.session.model_dump()
        with self.assertRaises(HTTPException):
            self.action("reload")
        self.assertEqual(self.session.model_dump(), before)

    def test_draw_changes_actual_owner_and_prevents_phantom_weapon_selection(self):
        spare = make_item("heavy_blaster_dl44")
        self.session.character.inventory.append(spare)
        gear(D6GearAction(actor_id="hero", action="draw", item_id=spare.id, expected_updated_at=self.session.updated_at))
        self.assertIs(self.session.encounter.combatants[0].weapon, self.session.character.inventory[1])
        self.assertFalse(self.session.character.inventory[0].equipped)
        self.assertEqual(self.session.character.inventory[1].equipped_by, "hero")
        self.session.encounter.d6_turn_acted = False
        self.session.character.d6.round_state.declared_actions = 2
        with self.assertRaises(HTTPException):
            asyncio.run(routes.combat_attack(CombatAttackRequest(target_id="foe", weapon_id=self.session.character.inventory[0].id)))

    def test_preparation_earns_one_die_only_next_round_same_target_exclusive(self):
        self.action("prepare", target_id="foe")
        self.session.encounter.round = 2
        self.session.encounter.d6_turn_acted = False
        self.session.character.d6.round_state = D6RoundState()
        with patch("dungeonforge.rules.weg_d6.D6Roller.values", return_value=roll(1)) as rolling:
            result = weg_combat.attack(self.session.encounter, self.session.character, "foe", self.session.character.inventory[0])
        self.assertEqual(rolling.call_args.args[:2], (4, 0))
        self.assertEqual(result.state_changes["preparation_bonus"], "1D")
        self.assertIsNone(self.session.character.d6.combat_preparation)

    def test_preparation_cannot_use_a_melee_skill_or_multiple_declared_actions(self):
        self.session.character.inventory[0].d6_skill = "melee_combat"
        with self.assertRaises(HTTPException):
            self.action("prepare", target_id="foe")
        self.session.character.inventory[0].d6_skill = "blaster"
        self.session.character.d6.round_state.declared_actions = 2
        self.session.encounter.combatants[0].d6 = self.session.character.d6
        with self.assertRaises(HTTPException):
            self.action("prepare", target_id="foe")

    def test_full_cover_blocks_direct_attack_without_spending_anything(self):
        cover = D6CoverObject(name="Blast door", body="6D", reason="Actual door")
        self.session.encounter.cover_objects.append(cover)
        target = self.session.encounter.combatants[1]
        target.cover_id, target.cover_fraction = cover.id, "full"
        before = self.session.model_dump()
        with self.assertRaises(HTTPException):
            asyncio.run(routes.combat_attack(CombatAttackRequest(target_id="foe")))
        self.assertEqual(self.session.model_dump(), before)

    def test_saved_cover_cannot_be_restored_by_reassigning_it(self):
        cover = D6CoverObject(name="Wood", body="1D", damage_state="destroyed", reason="Actual broken door")
        self.session.encounter.cover_objects.append(cover)
        with self.assertRaises(HTTPException):
            cover_facts(D6CoverFacts(target_id="foe", fraction="half", object_id=cover.id,
                reason="Still broken", expected_updated_at=self.session.updated_at))
        self.assertEqual(self.session.encounter.cover_objects[0].damage_state, "destroyed")

    def test_cover_facts_reuse_one_actual_object_and_revision(self):
        cover_facts(D6CoverFacts(target_id="foe", fraction="half", new_name="Metal door", new_body="3D",
            reason="Actual metal door", expected_updated_at=self.session.updated_at))
        obj = self.session.encounter.cover_objects[0]
        obj.damage_state = "heavily_damaged"
        cover_facts(D6CoverFacts(target_id="hero", fraction="quarter", object_id=obj.id,
            reason="Same door", expected_updated_at=self.session.updated_at))
        self.assertEqual(len(self.session.encounter.cover_objects), 1)
        self.assertEqual(self.session.encounter.cover_objects[0].damage_state, "heavily_damaged")
        self.assertEqual(self.session.encounter.combatants[0].cover_id, obj.id)


class CoverRulesTests(unittest.TestCase):
    def test_unopposed_native_attack_still_consumes_actual_ammunition(self):
        gun = make_item("blaster_dl18")
        character = Character(d6=D6Character())
        with patch("dungeonforge.rules.weg_d6.D6Roller.values", return_value=roll(1)):
            WEGD6Rules().evaluate_attack(character, 10, gun)
        self.assertEqual(gun.ammo, 99)
        gun.ammo = 0
        before = character.model_dump()
        with self.assertRaisesRegex(ValueError, "ammunition"):
            WEGD6Rules().evaluate_attack(character, 10, gun)
        self.assertEqual(character.model_dump(), before)

    def test_unopposed_bowcaster_additional_shot_needs_its_free_strength_check(self):
        bow = make_item("bowcaster")
        character = Character(d6=D6Character())
        character.d6.round_state.declared_actions = 2
        with patch("dungeonforge.rules.weg_d6.D6Roller.values", side_effect=[roll(20), roll(1)]):
            WEGD6Rules().evaluate_attack(character, 10, bow)
            result = WEGD6Rules().evaluate_attack(character, 10, bow)
        self.assertFalse(result.success)
        self.assertEqual((bow.ammo, bow.power_ammo), (5, 49))
        self.assertEqual(character.d6.round_state.actions_taken, 1)

    def test_called_weapon_shot_damages_actual_object_without_injuring_its_holder(self):
        held = make_item("blaster_dl18")
        victim = D6Character()
        with patch("dungeonforge.rules.weg_d6.D6Roller.values", side_effect=[roll(20), roll(18), roll(8)]) as rolling:
            result = WEGD6Rules.resolve_attack(D6Character(), victim, make_item("blaster_dl18"), D6Options(target_weapon=True), target_weapon=held)
        self.assertEqual(rolling.call_args_list[0].args[0], 2)
        self.assertEqual(held.weapon_damage_state, "heavily_damaged")
        self.assertEqual(victim.wound, "healthy")
        self.assertIsNone(result.wound_result)
        self.assertEqual(result.state_changes["target_weapon_damage"]["id"], held.id)

    def test_called_weapon_needs_a_real_target_and_rejects_conflicting_body_selection(self):
        for options, held in [(D6Options(target_weapon=True), None),
                              (D6Options(target_weapon=True, hit_location="head"), make_item("blaster_dl18"))]:
            with self.assertRaises(ValueError):
                WEGD6Rules.resolve_attack(D6Character(), D6Character(), make_item("blaster_dl18"), options, target_weapon=held)

    def test_cover_intercepts_miss_and_light_damage_transmits_four_fewer_dice(self):
        cover = D6CoverObject(name="Wood door", body="2D", reason="Actual wood")
        with patch("dungeonforge.rules.weg_d6.DiceRoller.roll", return_value=roll(6)), patch("dungeonforge.rules.weg_d6.D6Roller.values", side_effect=[roll(12), roll(16), roll(10), roll(8), roll(10)]) as rolling:
            result = WEGD6Rules.resolve_attack(D6Character(), D6Character(), make_item("blaster_dl18"), cover=cover, cover_fraction="half")
        self.assertEqual(result.state_changes["cover_impact"]["outcome"], "lightly_damaged")
        self.assertEqual(result.state_changes["cover_impact"]["transmitted_penalty_dice"], 4)
        self.assertEqual(result.damage_roll.total, 0)  # 4D minus4D has no Wild Die.
        self.assertEqual(cover.damage_state, "lightly_damaged")
        self.assertEqual(rolling.call_count, 4)

    def test_full_cover_object_can_absorb_everything(self):
        cover = D6CoverObject(name="Blast door", body="6D", reason="Actual cover")
        with patch("dungeonforge.rules.weg_d6.D6Roller.values", side_effect=[roll(20), roll(10), roll(20)]):
            result = WEGD6Rules.resolve_attack(D6Character(), D6Character(), make_item("blaster_dl18"), D6Options(attack_cover=True), cover=cover, cover_fraction="full")
        self.assertIsNone(result.wound_result)
        self.assertIn("absorbs all", result.summary)

    def test_called_head_shot_costs_one_attack_die_and_adds_optional_damage_die(self):
        with patch("dungeonforge.rules.weg_d6.D6Roller.values", side_effect=[roll(20), roll(10), roll(20)]) as rolling:
            result = WEGD6Rules.resolve_attack(D6Character(), D6Character(), make_item("blaster_dl18"), D6Options(called_shot=True, hit_location="head", location_damage=True))
        self.assertEqual(rolling.call_args_list[0].args[0], 2)
        self.assertEqual(rolling.call_args_list[1].args[0], 5)
        self.assertEqual(result.state_changes["hit_location"], "head")

    def test_actual_partial_armor_cannot_protect_an_uncovered_leg(self):
        helmet = make_item("blast_helmet")
        target = D6Character(armor_energy="4D")
        with patch("dungeonforge.rules.weg_d6.D6Roller.values", side_effect=[roll(20), roll(10), roll(20)]) as rolling:
            WEGD6Rules.resolve_attack(D6Character(), target, make_item("blaster_dl18"), D6Options(hit_location="left_leg"), armor_items=[helmet])
        self.assertEqual(rolling.call_args_list[2].args[:2], (3, 0))
        self.assertEqual(helmet.armor_damage_state, "intact")

    def test_side_and_severe_damage_remove_actual_armor_protection(self):
        helmet = make_item("blast_helmet")
        helmet.armor_sides = ["front"]
        self.assertEqual(WEGD6Rules.resistance_pool(D6Character(), "energy", [helmet], "head", "back"), (3, 0))
        helmet.armor_damage_state = "severely_damaged"
        self.assertEqual(WEGD6Rules.resistance_pool(D6Character(), "energy", [helmet], "head"), (3, 0))


if __name__ == "__main__":
    unittest.main()
