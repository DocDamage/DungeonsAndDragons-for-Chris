import random
from typing import Optional
from dungeonforge.rules.base import BaseRuleSystem, Character, Item, RuleEvaluationResult
from dungeonforge.rules.dice import DiceRoller, RollResult


class DND35eRules(BaseRuleSystem):
    """D&D 3.5e Rules Engine (BAB, Ascending AC, Fort/Ref/Will, Critical Confirmations)."""

    def get_bab(self, character: Character) -> int:
        if character.bab is not None:
            return character.bab
        lvl = max(1, character.level)
        cls = character.class_name.lower()
        if any(w in cls for w in ["fighter", "barbarian", "paladin", "ranger"]):
            return lvl
        elif any(w in cls for w in ["cleric", "druid", "monk", "rogue", "bard"]):
            return (3 * lvl) // 4
        else:  # Wizard / Sorcerer
            return lvl // 2

    def evaluate_attack(
        self,
        character: Character,
        target_ac: int,
        weapon: Optional[Item] = None,
        advantage: bool = False,
        disadvantage: bool = False,
        bonus_mod: int = 0
    ) -> RuleEvaluationResult:
        bab = self.get_bab(character)
        # Determine ability modifier (Dex for ranged or Finesse, Str for melee)
        is_ranged = weapon and any(w in weapon.name.lower() for w in ["bow", "crossbow", "sling", "dart"])
        stat_mod = character.abilities.modifier("dex") if is_ranged else character.abilities.modifier("str")
        total_attack_bonus = bab + stat_mod + bonus_mod

        roll = DiceRoller.roll(f"1d20{total_attack_bonus:+d}")
        nat_roll = roll.raw_rolls[0]

        threat_range = 20
        crit_mult = 2
        if weapon:
            w_name = weapon.name.lower()
            if any(k in w_name for k in ["rapier", "scimitar", "falchion"]):
                threat_range = 18
            elif any(k in w_name for k in ["longsword", "greatsword"]):
                threat_range = 19
            if any(k in w_name for k in ["axe", "scythe"]):
                crit_mult = 3

        is_threat = nat_roll >= threat_range
        is_fumble = (nat_roll == 1)
        hit = (roll.total >= target_ac or nat_roll == 20) and not is_fumble

        confirmed_crit = False
        damage_dealt = None

        if hit:
            dmg_expr = weapon.damage if weapon and weapon.damage else "1d8"
            # Add strength mod to melee damage
            if not is_ranged:
                dmg_expr = f"{dmg_expr}{stat_mod:+d}"

            # Check critical confirmation roll
            if is_threat:
                confirm_roll = DiceRoller.roll(f"1d20{total_attack_bonus:+d}")
                if confirm_roll.total >= target_ac:
                    confirmed_crit = True

            dmg_roll = DiceRoller.roll(dmg_expr)
            damage_dealt = dmg_roll.total
            if confirmed_crit:
                damage_dealt *= crit_mult

        summary = (
            f"[3.5e Attack] BAB +{bab}, Mod {stat_mod:+d} vs AC {target_ac}. "
            f"Roll {roll.breakdown} -> {'HIT' if hit else 'MISS'}"
        )
        if confirmed_crit:
            summary += f" [CRITICAL HIT x{crit_mult}!]"
        elif is_threat and not confirmed_crit:
            summary += " (Critical threat not confirmed)"
        if hit and damage_dealt is not None:
            summary += f" Deals {damage_dealt} damage."

        return RuleEvaluationResult(
            action_type="attack",
            success=hit,
            is_crit=confirmed_crit,
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
        s_lower = save_name.lower()
        if "fort" in s_lower:
            stat_mod = character.abilities.modifier("con")
            base = character.saving_throws.get("fortitude", character.level // 2 + 2)
        elif "ref" in s_lower:
            stat_mod = character.abilities.modifier("dex")
            base = character.saving_throws.get("reflex", character.level // 3)
        else:  # will
            stat_mod = character.abilities.modifier("wis")
            base = character.saving_throws.get("will", character.level // 2 + 2)

        total_save_bonus = base + stat_mod
        roll = DiceRoller.roll(f"1d20{total_save_bonus:+d}")
        nat_roll = roll.raw_rolls[0]

        success = (roll.total >= dc and nat_roll != 1) or nat_roll == 20
        summary = (
            f"[3.5e Save: {save_name}] Base +{base}, Mod {stat_mod:+d} vs DC {dc}. "
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
        ranks = character.skills.get(skill_name.lower(), 0) if skill_name else 0
        total_bonus = stat_mod + ranks

        roll = DiceRoller.roll(f"1d20{total_bonus:+d}")
        success = roll.total >= dc_or_target
        name = f"Skill: {skill_name}" if skill_name else f"Ability: {ability.upper()}"
        summary = (
            f"[3.5e {name}] Ranks {ranks}, Mod {stat_mod:+d} vs DC {dc_or_target}. "
            f"Roll {roll.breakdown} -> {'SUCCESS' if success else 'FAILURE'}"
        )
        return RuleEvaluationResult(
            action_type="skill_check" if skill_name else "ability_check",
            success=success,
            is_crit=(roll.raw_rolls[0] == 20),
            is_fumble=(roll.raw_rolls[0] == 1),
            roll_result=roll,
            target_value=dc_or_target,
            summary=summary
        )

    def apply_short_rest(self, character: Character, hit_dice_spent: int = 1) -> Character:
        # In 3.5e, short break / bind wounds: 1 HP
        healed = min(1, character.max_hp - character.current_hp)
        character.current_hp += healed
        return character

    def apply_long_rest(self, character: Character) -> Character:
        # 3.5e: 1 HP per character level per 8 hours rest
        healed = min(character.level, character.max_hp - character.current_hp)
        character.current_hp += healed
        for slot in character.spell_slots.values():
            slot.current = slot.max_slots
        return character
