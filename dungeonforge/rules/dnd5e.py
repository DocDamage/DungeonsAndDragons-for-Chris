import random
from typing import Optional
from dungeonforge.rules.base import BaseRuleSystem, Character, Item, RuleEvaluationResult
from dungeonforge.rules.dice import DiceRoller, RollResult


class DND5eRules(BaseRuleSystem):
    """D&D 5e Rules Engine (Proficiency Bonus, Advantage/Disadvantage, 6 Ability Saves, Death Saves)."""

    def get_proficiency_bonus(self, character: Character) -> int:
        if character.proficiency_bonus is not None:
            return character.proficiency_bonus
        return (max(1, character.level) - 1) // 4 + 2

    def evaluate_attack(
        self,
        character: Character,
        target_ac: int,
        weapon: Optional[Item] = None,
        advantage: bool = False,
        disadvantage: bool = False,
        bonus_mod: int = 0
    ) -> RuleEvaluationResult:
        prof = self.get_proficiency_bonus(character)
        is_ranged = weapon and any(w in weapon.name.lower() for w in ["bow", "crossbow", "dart", "sling"])
        is_finesse = weapon and any(w in weapon.name.lower() for w in ["rapier", "dagger", "scimitar", "shortsword"])

        dex_mod = character.abilities.modifier("dex")
        str_mod = character.abilities.modifier("str")
        stat_mod = dex_mod if (is_ranged or (is_finesse and dex_mod > str_mod)) else str_mod

        total_mod = prof + stat_mod + bonus_mod

        expr = f"1d20{total_mod:+d}"
        if advantage and not disadvantage:
            expr += " adv"
        elif disadvantage and not advantage:
            expr += " dis"

        roll = DiceRoller.roll(expr)
        nat_roll = roll.kept_rolls[0]

        is_crit = (nat_roll == 20)
        is_fumble = (nat_roll == 1)
        hit = (roll.total >= target_ac or is_crit) and not is_fumble
        damage_dealt = None

        if hit:
            dmg_base = weapon.damage if weapon and weapon.damage else "1d8"
            # In 5e, critical hit doubles the damage dice!
            if is_crit:
                dmg_base = DiceRoller.double_dice(dmg_base)

            dmg_expr = f"{dmg_base}{stat_mod:+d}"
            dmg_roll = DiceRoller.roll(dmg_expr)
            damage_dealt = max(1, dmg_roll.total)

        summary = (
            f"[5e Attack] Prof +{prof}, Mod {stat_mod:+d} vs AC {target_ac}. "
            f"Roll {roll.breakdown} -> {'HIT!' if hit else 'MISS!'}"
        )
        if is_crit:
            summary += " [CRITICAL HIT!]"
        elif is_fumble:
            summary += " [CRITICAL FUMBLE!]"
        if hit and damage_dealt is not None:
            summary += f" Deals {damage_dealt} damage."

        return RuleEvaluationResult(
            action_type="attack",
            success=hit,
            is_crit=is_crit,
            is_fumble=is_fumble,
            roll_result=roll,
            target_value=target_ac,
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
        ability = save_name.lower()[:3]  # str, dex, con, int, wis, cha
        stat_mod = character.abilities.modifier(ability)
        prof = self.get_proficiency_bonus(character) if character.saving_throws.get(ability, 0) > 0 else 0
        total_bonus = stat_mod + prof

        expr = f"1d20{total_bonus:+d}"
        if advantage and not disadvantage:
            expr += " adv"
        elif disadvantage and not advantage:
            expr += " dis"

        roll = DiceRoller.roll(expr)
        nat_roll = roll.kept_rolls[0]

        success = (roll.total >= dc and nat_roll != 1) or nat_roll == 20
        summary = (
            f"[5e Save: {save_name.upper()}] Mod {stat_mod:+d}, Prof +{prof} vs DC {dc}. "
            f"Roll {roll.breakdown} -> {'SUCCESS' if success else 'FAILED'}"
        )
        return RuleEvaluationResult(
            action_type="saving_throw",
            success=success,
            is_crit=(nat_roll == 20),
            is_fumble=(nat_roll == 1),
            roll_result=roll,
            target_value=dc,
            summary=summary
        )

    def evaluate_ability_check(
        self,
        character: Character,
        ability: str,
        dc_or_target: int,
        skill_name: Optional[str] = None
    ) -> RuleEvaluationResult:
        stat_mod = character.abilities.modifier(ability)
        is_proficient = character.skills.get(skill_name.lower(), 0) > 0 if skill_name else False
        prof = self.get_proficiency_bonus(character) if is_proficient else 0
        total_bonus = stat_mod + prof

        roll = DiceRoller.roll(f"1d20{total_bonus:+d}")
        success = roll.total >= dc_or_target
        name = f"Skill: {skill_name}" if skill_name else f"Check: {ability.upper()}"
        summary = (
            f"[5e {name}] Mod {stat_mod:+d}, Prof +{prof} vs DC {dc_or_target}. "
            f"Roll {roll.breakdown} -> {'SUCCESS' if success else 'FAILURE'}"
        )
        return RuleEvaluationResult(
            action_type="skill_check" if skill_name else "ability_check",
            success=success,
            is_crit=(roll.kept_rolls[0] == 20),
            is_fumble=(roll.kept_rolls[0] == 1),
            roll_result=roll,
            target_value=dc_or_target,
            summary=summary
        )

    def evaluate_death_save(self, character: Character) -> RuleEvaluationResult:
        roll = DiceRoller.roll("1d20")
        nat = roll.kept_rolls[0]
        state_changes = {}

        if nat == 20:
            character.current_hp = 1
            character.death_saves_success = 0
            character.death_saves_failure = 0
            if "Unconscious" in character.conditions:
                character.conditions.remove("Unconscious")
            summary = "Natural 20! You regain consciousness with 1 HP!"
            success = True
        elif nat == 1:
            character.death_saves_failure += 2
            summary = f"Natural 1! Two death save failures recorded ({character.death_saves_failure}/3)."
            success = False
        elif nat >= 10:
            character.death_saves_success += 1
            summary = f"Death save passed ({character.death_saves_success}/3 successes)."
            success = True
        else:
            character.death_saves_failure += 1
            summary = f"Death save failed ({character.death_saves_failure}/3 failures)."
            success = False

        state_changes["death_saves_success"] = character.death_saves_success
        state_changes["death_saves_failure"] = character.death_saves_failure
        state_changes["current_hp"] = character.current_hp

        return RuleEvaluationResult(
            action_type="death_save",
            success=success,
            is_crit=(nat == 20),
            is_fumble=(nat == 1),
            roll_result=roll,
            summary=f"[5e Death Save] {summary}",
            state_changes=state_changes
        )

    def apply_short_rest(self, character: Character, hit_dice_spent: int = 1) -> Character:
        # In 5e, roll hit die + Con modifier
        con_mod = character.abilities.modifier("con")
        heal_roll = DiceRoller.roll(f"{hit_dice_spent}d8{con_mod * hit_dice_spent:+d}")
        healed = min(heal_roll.total, character.max_hp - character.current_hp)
        character.current_hp += max(0, healed)
        return character

    def apply_long_rest(self, character: Character) -> Character:
        # 5e: restore all HP, reset death saves, restore spell slots
        character.current_hp = character.max_hp
        character.death_saves_success = 0
        character.death_saves_failure = 0
        for slot in character.spell_slots.values():
            slot.current = slot.max_slots
        return character
