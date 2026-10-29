"""Deterministic dice and combat regressions; run with unittest discover."""

import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from dungeonforge.game.combat import Combatant, CombatEncounter
from dungeonforge.main import app
from dungeonforge.rules.base import AbilityScores, Character, Companion, Item
from dungeonforge.rules.dice import DiceRoller
from dungeonforge.rules.dnd35e import DND35eRules
from dungeonforge.rules.dnd5e import DND5eRules


class DiceTests(unittest.TestCase):
    def roll(self, expression, values):
        with patch("dungeonforge.rules.dice.random.randint", side_effect=values) as rng:
            result = DiceRoller.roll(expression)
        self.assertEqual(rng.call_count, len(values))
        return result

    def test_standard_roll_with_negative_modifier(self):
        result = self.roll(" 2D6 - 3 ", [4, 2])
        self.assertEqual(result.total, 3)
        self.assertEqual(result.modifier, -3)
        self.assertEqual(result.raw_rolls, [4, 2])
        self.assertEqual(result.kept_rolls, [4, 2])

    def test_shorthand_and_flat_values(self):
        self.assertEqual(self.roll("d8", [7]).total, 7)
        for value in (0, 7, -4):
            with self.subTest(value=value):
                result = self.roll(str(value), [])
                self.assertEqual(result.total, value)
                self.assertEqual(result.dice_count, 0)

    def test_keep_highest_keeps_modifier(self):
        result = self.roll("4d6kh3+2", [1, 6, 4, 5])
        self.assertEqual(result.kept_rolls, [6, 5, 4])
        self.assertEqual(result.total, 17)
        self.assertEqual(result.modifier, 2)

    def test_keep_lowest_keeps_modifier(self):
        result = self.roll("2d20kl1+5", [17, 3])
        self.assertEqual(result.kept_rolls, [3])
        self.assertEqual(result.total, 8)

    def test_natural_twenty_and_one_on_kept_d20(self):
        self.assertTrue(self.roll("2d20kh1+5", [1, 20]).is_crit)
        self.assertTrue(self.roll("2d20kl1+5", [20, 1]).is_fumble)
        self.assertFalse(self.roll("2d20+5", [20, 1]).is_crit)

    def test_advantage_aliases(self):
        for flag in ("adv", "advantage"):
            with self.subTest(flag=flag):
                result = self.roll(f"1d20+5 {flag}", [3, 17])
                self.assertEqual(result.total, 22)
                self.assertTrue(result.advantage)
                self.assertFalse(result.disadvantage)

    def test_disadvantage_aliases_do_not_enable_advantage(self):
        for flag in ("dis", "disadvantage"):
            with self.subTest(flag=flag):
                result = self.roll(f"1d20+5 {flag}", [17, 3])
                self.assertEqual(result.total, 8)
                self.assertFalse(result.advantage)
                self.assertTrue(result.disadvantage)

    def test_advantage_and_disadvantage_cancel(self):
        result = self.roll("1d20-2 advantage disadvantage", [11])
        self.assertEqual(result.total, 9)
        self.assertFalse(result.advantage)
        self.assertFalse(result.disadvantage)

    def test_mixed_damage_and_multiple_flat_modifiers(self):
        result = self.roll("2d6+1d4+3-2", [6, 2, 4])
        self.assertEqual(result.total, 13)
        self.assertEqual(result.dice_count, 3)
        self.assertEqual(result.die_type, 0)
        self.assertEqual(result.modifier, 1)

    def test_critical_damage_preserves_flat_modifiers(self):
        expression = DiceRoller.double_dice("1d8+2+1d4-1")
        result = self.roll(expression, [8, 3, 4, 2])
        self.assertEqual(result.total, 18)
        self.assertEqual(result.modifier, 1)

    def test_invalid_expressions_never_roll(self):
        invalid = (
            "", " ", "adv", "garbage", "2d6junk", "1d20+-2", "1d6+",
            "0d6", "1d0", "2d6kh0", "2d6kh3", "2d6kl3", "1d6-1d4",
            "1001d6", "600d6+600d4", "1d1000001", "1d6 adv", "2d20kh1 dis",
            "1d20 " + "x" * 256,
        )
        for expression in invalid:
            with self.subTest(expression=expression):
                with patch("dungeonforge.rules.dice.random.randint") as rng:
                    with self.assertRaises(ValueError):
                        DiceRoller.roll(expression)
                    rng.assert_not_called()

    def test_invalid_api_roll_returns_validation_error(self):
        with TestClient(app) as client:
            response = client.post("/api/dice/roll", json={"expression": "2d0"})
        self.assertEqual(response.status_code, 422)
        self.assertIsInstance(response.json()["detail"], str)

    def test_api_keeps_all_roll_details(self):
        with TestClient(app) as client:
            with patch("dungeonforge.rules.dice.random.randint", side_effect=[19, 1]):
                response = client.post("/api/dice/roll", json={"expression": "1d20+5 disadvantage"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["raw_rolls"], [19, 1])
        self.assertEqual(data["kept_rolls"], [1])
        self.assertEqual(data["total"], 6)
        self.assertTrue(data["is_fumble"])


class CombatDiceTests(unittest.TestCase):
    def setUp(self):
        self.companion = Companion(id="ally", name="Ally", level=2, damage="1d8+2")
        self.encounter = CombatEncounter(combatants=[
            Combatant(id="ally", name="Ally", is_player=True),
            Combatant(id="enemy", name="Enemy", ac=14, current_hp=100, max_hp=100),
        ])

    def test_companion_advantage_adds_attack_bonus(self):
        with patch("dungeonforge.rules.dice.random.randint", side_effect=[2, 10, 5]):
            result = self.encounter.attack_with_companion(self.companion, "enemy", advantage=True)
        self.assertEqual(result.roll_result.total, 14)
        self.assertTrue(result.success)
        self.assertEqual(result.damage_dealt, 7)
        self.assertEqual(self.encounter.combatants[1].current_hp, 93)

    def test_companion_disadvantage_uses_lowest(self):
        with patch("dungeonforge.rules.dice.random.randint", side_effect=[18, 2]):
            result = self.encounter.attack_with_companion(self.companion, "enemy", disadvantage=True)
        self.assertFalse(result.success)
        self.assertEqual(result.roll_result.total, 6)

    def test_companion_flags_cancel(self):
        with patch("dungeonforge.rules.dice.random.randint", side_effect=[10, 5]):
            result = self.encounter.attack_with_companion(
                self.companion, "enemy", advantage=True, disadvantage=True,
            )
        self.assertEqual(result.roll_result.raw_rolls, [10])
        self.assertEqual(result.roll_result.total, 14)

    def test_companion_critical_doubles_weapon_dice(self):
        with patch("dungeonforge.rules.dice.random.randint", side_effect=[20, 8, 3]):
            result = self.encounter.attack_with_companion(self.companion, "enemy")
        self.assertTrue(result.is_crit)
        self.assertEqual(result.damage_dealt, 13)

    def test_companion_natural_one_misses_in_2e(self):
        self.encounter.combatants[1].ac = 20
        with patch("dungeonforge.rules.dice.random.randint", return_value=1):
            result = self.encounter.attack_with_companion(self.companion, "enemy", edition="2e")
        self.assertFalse(result.success)
        self.assertTrue(result.is_fumble)

    def test_negative_initiative_modifiers(self):
        player = Character(abilities=AbilityScores(dex=6))
        with patch("dungeonforge.rules.dice.random.randint", side_effect=[10, 8]):
            self.encounter.start(player, [{"name": "Slow foe", "dex_mod": -3}])
        self.assertEqual([c.initiative for c in self.encounter.combatants], [8, 5])

    def test_negative_ability_modifiers_across_editions(self):
        character = Character(abilities=AbilityScores(str=6))
        for rules in (DND5eRules(), DND35eRules()):
            with self.subTest(rules=type(rules).__name__):
                with patch("dungeonforge.rules.dice.random.randint", return_value=10):
                    result = rules.evaluate_ability_check(character, "str", 9)
                self.assertEqual(result.roll_result.total, 8)
                self.assertFalse(result.success)

    def test_5e_damage_preserves_weapon_bonus_and_negative_strength(self):
        character = Character(abilities=AbilityScores(str=6))
        with patch("dungeonforge.rules.dice.random.randint", side_effect=[15, 6]):
            result = DND5eRules().evaluate_attack(character, 10, Item(name="Mace", damage="1d6+1"))
        self.assertEqual(result.damage_dealt, 5)

    def test_5e_critical_preserves_weapon_bonus(self):
        character = Character(abilities=AbilityScores(str=14))
        with patch("dungeonforge.rules.dice.random.randint", side_effect=[20, 8, 3]):
            result = DND5eRules().evaluate_attack(character, 10, Item(name="Sword", damage="1d8+1"))
        self.assertEqual(result.damage_dealt, 14)
        self.assertTrue(result.is_crit)

    def test_short_rest_with_negative_constitution(self):
        character = Character(current_hp=2, max_hp=10, abilities=AbilityScores(con=6))
        with patch("dungeonforge.rules.dice.random.randint", return_value=5):
            DND5eRules().apply_short_rest(character)
        self.assertEqual(character.current_hp, 5)


if __name__ == "__main__":
    unittest.main()
