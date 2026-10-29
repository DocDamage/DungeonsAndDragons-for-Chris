import random
from typing import Optional
from dungeonforge.rules.base import BaseRuleSystem, Character, Item, RuleEvaluationResult
from dungeonforge.rules.dice import DiceRoller, RollResult


class DND2eRules(BaseRuleSystem):
    """AD&D 2nd Edition Rules Engine (THAC0, Descending AC, 5 Save Categories)."""

    SAVE_CATEGORIES = {
        "poison": "Paralyzation, Poison, or Death Magic",
        "paralyzation": "Paralyzation, Poison, or Death Magic",
        "death": "Paralyzation, Poison, or Death Magic",
        "wand": "Rod, Staff, or Wand",
        "rod": "Rod, Staff, or Wand",
        "petrification": "Petrification or Polymorph",
        "polymorph": "Petrification or Polymorph",
        "breath": "Breath Weapon",
        "spell": "Spell"
    }

    def get_thac0(self, character: Character) -> int:
        if character.thac0 is not None:
            return character.thac0
        # Default THAC0 based on level and class type
        lvl = max(1, character.level)
        cls = character.class_name.lower()
        if any(w in cls for w in ["fighter", "paladin", "ranger"]):
            return max(1, 20 - (lvl - 1))
        elif any(w in cls for w in ["cleric", "druid"]):
            return max(1, 20 - (2 * ((lvl - 1) // 3)))
        elif any(w in cls for w in ["thief", "bard", "rogue"]):
            return max(1, 20 - (2 * ((lvl - 1) // 4)))
        else:  # Mage / Specialist
            return max(1, 20 - (lvl - 1) // 3)

    def evaluate_attack(
        self,
        character: Character,
        target_ac: int,
        weapon: Optional[Item] = None,
        advantage: bool = False,
        disadvantage: bool = False,
        bonus_mod: int = 0
    ) -> RuleEvaluationResult:
        thac0 = self.get_thac0(character)
        # 2e Formula: Roll needed on d20 = THAC0 - Target AC
        target_roll_needed = thac0 - target_ac - bonus_mod

        roll = DiceRoller.roll("1d20")
        nat_roll = roll.kept_rolls[0]

        is_crit = (nat_roll == 20)
        is_fumble = (nat_roll == 1)

        hit = (nat_roll >= target_roll_needed or is_crit) and not is_fumble
        damage_dealt = None

        if hit:
            dmg_expr = weapon.damage if weapon and weapon.damage else "1d6"
            dmg_roll = DiceRoller.roll(dmg_expr)
            damage_dealt = max(1, dmg_roll.total)

        summary = (
            f"[2e Attack] THAC0 {thac0} vs AC {target_ac} (Need {target_roll_needed}+). "
            f"Rolled {nat_roll} -> {'HIT!' if hit else 'MISS!'}"
        )
        if hit and damage_dealt is not None:
            summary += f" Damage: {damage_dealt} HP."

        return RuleEvaluationResult(
            action_type="attack",
            success=hit,
            is_crit=is_crit,
            is_fumble=is_fumble,
            roll_result=roll,
            target_value=target_roll_needed,
            damage_dealt=damage_dealt,
            summary=summary
        )

    def evaluate_saving_throw(
        self,
        character: Character,
        save_name: str,
        dc: int,
        advantage: bool = False,
        disadvantage: bool = False
    ) -> RuleEvaluationResult:
        # In 2e, target number is on character sheet or dc argument
        save_target = character.saving_throws.get(save_name.lower(), dc or 14)
        roll = DiceRoller.roll("1d20")
        nat_roll = roll.kept_rolls[0]

        success = (nat_roll >= save_target and nat_roll != 1) or nat_roll == 20
        summary = (
            f"[2e Save: {save_name}] Need {save_target}+. "
            f"Rolled {nat_roll} -> {'SUCCESS' if success else 'FAILED'}"
        )
        return RuleEvaluationResult(
            action_type="saving_throw",
            success=success,
            is_crit=(nat_roll == 20),
            is_fumble=(nat_roll == 1),
            roll_result=roll,
            target_value=save_target,
            summary=summary
        )

    def evaluate_ability_check(
        self,
        character: Character,
        ability: str,
        dc_or_target: int,
        skill_name: Optional[str] = None
    ) -> RuleEvaluationResult:
        # 2e Ability Check: Roll 1d20 <= Ability Score!
        score = getattr(character.abilities, ability.lower(), 10)
        roll = DiceRoller.roll("1d20")
        nat_roll = roll.kept_rolls[0]

        # Roll under rule
        success = (nat_roll <= score and nat_roll != 20) or nat_roll == 1
        summary = (
            f"[2e Ability Check: {ability.upper()}] Stat is {score}. "
            f"Rolled {nat_roll} (Roll under) -> {'SUCCESS' if success else 'FAILURE'}"
        )
        return RuleEvaluationResult(
            action_type="ability_check",
            success=success,
            is_crit=(nat_roll == 1),
            is_fumble=(nat_roll == 20),
            roll_result=roll,
            target_value=score,
            summary=summary
        )

    def apply_short_rest(self, character: Character, hit_dice_spent: int = 1) -> Character:
        # In 2e, short breather: recover 1 HP if bandage applied
        healed = min(1, character.max_hp - character.current_hp)
        character.current_hp += healed
        return character

    def apply_long_rest(self, character: Character) -> Character:
        # 2e Long rest: recover 1-3 HP per day
        healed = min(3, character.max_hp - character.current_hp)
        character.current_hp += healed
        # Restore spell slots
        for slot in character.spell_slots.values():
            slot.current = slot.max_slots
        return character
