import random
import re
from typing import List
from pydantic import BaseModel, Field


class RollResult(BaseModel):
    expression: str
    dice_count: int
    die_type: int
    raw_rolls: List[int] = Field(default_factory=list)
    kept_rolls: List[int] = Field(default_factory=list)
    modifier: int = 0
    total: int = 0
    is_crit: bool = False
    is_fumble: bool = False
    advantage: bool = False
    disadvantage: bool = False
    breakdown: str = ""
    system: str = "dnd"
    wild_rolls: List[int] = Field(default_factory=list)
    mishap: str | None = None
    bonus_rolls: List[int] = Field(default_factory=list)


class DiceRoller:
    """Roll dice pools, keep highest/lowest, additive dice, and d20 advantage."""

    MAX_DICE = 1000
    MAX_SIDES = 1_000_000
    MAX_EXPRESSION_LENGTH = 256
    _TERM = re.compile(
        r"([+-]?)(?:(\d*)d(\d+)(?:k([hl])(\d+))?|(\d+))"
    )

    @staticmethod
    def double_dice(expression: str) -> str:
        """Double damage dice for a critical hit while preserving flat bonuses."""
        return re.sub(
            r"(\d*)d(\d+)",
            lambda match: f"{2 * int(match[1] or 1)}d{match[2]}",
            expression,
            flags=re.IGNORECASE,
        )

    @staticmethod
    def roll(expression: str) -> RollResult:
        if not expression.strip() or len(expression) > DiceRoller.MAX_EXPRESSION_LENGTH:
            raise ValueError("Dice expression must contain 1 to 256 characters.")

        flags = set(re.findall(r"\b(?:advantage|disadvantage|adv|dis)\b", expression.lower()))
        adv = bool(flags & {"adv", "advantage"})
        dis = bool(flags & {"dis", "disadvantage"})
        clean = re.sub(r"\b(?:advantage|disadvantage|adv|dis)\b", "", expression.lower())
        clean = re.sub(r"\s+", "", clean)

        # Validate the entire expression before consuming randomness.
        pools = []
        modifier = 0
        position = 0
        while position < len(clean):
            match = DiceRoller._TERM.match(clean, position)
            if not match or (position > 0 and not match[1]):
                raise ValueError("Invalid dice expression. Try 2d6+3, 4d6kh3, or 1d20+5 dis.")
            sign, count, sides, keep_mode, keep, constant = match.groups()
            if constant is not None:
                modifier += (-1 if sign == "-" else 1) * int(constant)
            else:
                count, sides = int(count or 1), int(sides)
                keep = int(keep) if keep is not None else count
                if sign == "-":
                    raise ValueError("Subtract flat modifiers rather than dice pools.")
                if not 1 <= count <= DiceRoller.MAX_DICE or not 1 <= sides <= DiceRoller.MAX_SIDES:
                    raise ValueError("Use 1 to 1000 dice with 1 to 1000000 sides each.")
                if not 1 <= keep <= count:
                    raise ValueError("The number of kept dice must be between 1 and the dice count.")
                pools.append((count, sides, keep_mode, keep))
            position = match.end()

        if not clean:
            raise ValueError("A dice expression is required.")
        if sum(pool[0] for pool in pools) > DiceRoller.MAX_DICE:
            raise ValueError("Roll at most 1000 dice per expression.")
        if (adv or dis) and (len(pools) != 1 or pools[0] != (1, 20, None, 1)):
            raise ValueError("Advantage and disadvantage require a single d20 roll.")

        raw_rolls = []
        kept_rolls = []
        parts = []
        for count, sides, keep_mode, keep in pools:
            if adv != dis:
                raw = [random.randint(1, sides), random.randint(1, sides)]
                kept = [max(raw) if adv else min(raw)]
                label = "Advantage" if adv else "Disadvantage"
                parts.append(f"{raw} ({label}) -> {kept}")
            else:
                raw = [random.randint(1, sides) for _ in range(count)]
                kept = sorted(raw, reverse=keep_mode == "h")[:keep] if keep_mode else raw.copy()
                label = f" keep {'highest' if keep_mode == 'h' else 'lowest'} {keep} -> {kept}" if keep_mode else ""
                parts.append(f"{raw}{label}")
            raw_rolls.extend(raw)
            kept_rolls.extend(kept)

        total = sum(kept_rolls) + modifier
        natural_d20 = len(pools) == 1 and pools[0][1] == 20 and len(kept_rolls) == 1
        breakdown = " + ".join(parts)
        if modifier or not parts:
            breakdown += f" {'+' if modifier >= 0 else '-'} {abs(modifier)}" if parts else str(modifier)
        if parts:
            breakdown += f" = {total}"

        return RollResult(
            expression=expression,
            dice_count=sum(pool[0] for pool in pools),
            # A mixed pool has no single die type.
            die_type=pools[0][1] if pools and len({pool[1] for pool in pools}) == 1 else 0,
            raw_rolls=raw_rolls,
            kept_rolls=kept_rolls,
            modifier=modifier,
            total=total,
            is_crit=natural_d20 and kept_rolls[0] == 20,
            is_fumble=natural_d20 and kept_rolls[0] == 1,
            advantage=adv and not dis,
            disadvantage=dis and not adv,
            breakdown=breakdown,
        )
