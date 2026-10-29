from typing import Dict
from dungeonforge.rules.base import BaseRuleSystem, Character, Item, RuleEvaluationResult, AbilityScores, SpellSlot
from dungeonforge.rules.dice import DiceRoller, RollResult
from dungeonforge.rules.dnd2e import DND2eRules
from dungeonforge.rules.dnd35e import DND35eRules
from dungeonforge.rules.dnd5e import DND5eRules
from dungeonforge.rules.weg_d6 import WEGD6Rules

_ENGINES: Dict[str, BaseRuleSystem] = {
    "2e": DND2eRules(),
    "3.5e": DND35eRules(),
    "5e": DND5eRules(),
    "weg_d6": WEGD6Rules(),
}

def get_rule_engine(edition: str = "5e") -> BaseRuleSystem:
    norm = edition.lower().strip()
    if norm in ["2e", "ad&d", "adnd", "second"]:
        return _ENGINES["2e"]
    elif norm in ["3.5e", "3.5", "3e", "d20"]:
        return _ENGINES["3.5e"]
    elif norm in ["weg_d6", "d6", "star_wars_d6", "starwars_d6"]:
        return _ENGINES["weg_d6"]
    elif norm in ["5e", "5"]:
        return _ENGINES["5e"]
    raise ValueError(f"Unsupported rules system: {edition}")
