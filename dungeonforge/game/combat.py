import uuid
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from dungeonforge.rules.base import Character, Item, RuleEvaluationResult
from dungeonforge.rules import get_rule_engine
from dungeonforge.rules.dice import DiceRoller, RollResult
from dungeonforge.rules.weg_models import D6Character, D6Options
from dungeonforge.rules.weg_cover_models import D6CoverObject
from dungeonforge.rules.weg_explosives_models import D6ExplosivesState


class Combatant(BaseModel):
    id: str
    name: str
    race: str = "Human"
    is_player: bool = False
    initiative: int = 0
    current_hp: int = 10
    max_hp: int = 10
    ac: int = 10
    conditions: List[str] = Field(default_factory=list)
    image_url: Optional[str] = None
    is_defeated: bool = False
    d6: Optional[D6Character] = None
    weapon: Optional[Item] = None
    armor: List[Item] = Field(default_factory=list)
    inventory: List[Item] = Field(default_factory=list)
    cover_id: str | None = None
    cover_fraction: str = "none"
    concealment_dice: int = 0


class CombatEncounter(BaseModel):
    d6_explosives: D6ExplosivesState = Field(default_factory=D6ExplosivesState)
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    active: bool = True
    round: int = 1
    current_turn_index: int = 0
    combatants: List[Combatant] = Field(default_factory=list)
    combat_log: List[str] = Field(default_factory=list)
    system: str = "dnd"
    d6_actions_started: bool = False
    d6_turn_acted: bool = False
    d6_initiative_winner: bool = True
    cover_objects: List[D6CoverObject] = Field(default_factory=list)
    weapon_fire: Dict[str, Dict[str, int]] = Field(default_factory=dict)
    d6_round_closing: bool = False
    d6_round_results: List[RuleEvaluationResult] = Field(default_factory=list)

    @property
    def active_combatant(self) -> Optional[Combatant]:
        if not self.combatants:
            return None
        valid_indices = [i for i, c in enumerate(self.combatants) if not c.is_defeated]
        if not valid_indices:
            return None
        return self.combatants[self.current_turn_index % len(self.combatants)]

    def start(self, player: Character, enemies: List[Dict[str, Any]], edition: str = "5e"):
        if edition == "weg_d6":
            from dungeonforge.game import weg_combat
            return weg_combat.start(self, player, enemies)
        self.combatants.clear()
        self.combat_log.clear()
        self.round = 1
        self.current_turn_index = 0
        self.active = True

        # Roll Player Initiative
        dex_mod = player.abilities.modifier("dex")
        p_init_roll = DiceRoller.roll(f"1d20{dex_mod:+d}")
        self.combatants.append(Combatant(
            id=player.id,
            name=player.name,
            is_player=True,
            initiative=p_init_roll.total,
            current_hp=player.current_hp,
            max_hp=player.max_hp,
            ac=player.ac,
            conditions=list(player.conditions)
        ))
        self.combat_log.append(f"{player.name} rolled Initiative: {p_init_roll.breakdown}")

        # Roll Companion Initiatives (Allies)
        for comp in getattr(player, "companions", []):
            c_init = DiceRoller.roll("1d20+2")
            self.combatants.append(Combatant(
                id=comp.id,
                name=f"{comp.name} (Ally)",
                is_player=True,
                initiative=c_init.total,
                current_hp=comp.current_hp,
                max_hp=comp.max_hp,
                ac=comp.ac,
                image_url=comp.avatar_url
            ))
            self.combat_log.append(f"{comp.name} (Ally) rolled Initiative: {c_init.breakdown}")

        # Roll Enemy Initiatives
        for idx, enemy_data in enumerate(enemies):
            e_id = f"enemy_{idx}_{str(uuid.uuid4())[:4]}"
            e_dex_mod = enemy_data.get("dex_mod", 1)
            e_init = DiceRoller.roll(f"1d20{e_dex_mod:+d}")
            self.combatants.append(Combatant(
                id=e_id,
                name=enemy_data.get("name", f"Foe {idx+1}"),
                is_player=False,
                initiative=e_init.total,
                current_hp=enemy_data.get("hp", 15),
                max_hp=enemy_data.get("hp", 15),
                ac=enemy_data.get("ac", 13),
                image_url=enemy_data.get("image_url")
            ))
            self.combat_log.append(f"{enemy_data.get('name')} rolled Initiative: {e_init.breakdown}")

        # Sort combatants by initiative descending
        self.combatants.sort(key=lambda c: c.initiative, reverse=True)
        self.combat_log.append(f"Combat begins! First up: {self.active_combatant.name}.")

    def next_turn(self) -> Optional[Combatant]:
        if self.system == "weg_d6":
            from dungeonforge.game import weg_combat
            return weg_combat.next_turn(self)
        # Check if combat ended
        active_enemies = [c for c in self.combatants if not c.is_player and not c.is_defeated]
        active_players = [c for c in self.combatants if c.is_player and not c.is_defeated]

        if not active_enemies:
            self.active = False
            self.combat_log.append("⚔️ VICTORY! All enemies have been vanquished!")
            return None
        if not active_players:
            self.active = False
            self.combat_log.append("💀 DEFEAT! The party has fallen in battle!")
            return None

        # Advance turn index to next non-defeated combatant
        for _ in range(len(self.combatants)):
            self.current_turn_index = (self.current_turn_index + 1) % len(self.combatants)
            if self.current_turn_index == 0:
                self.round += 1
                self.combat_log.append(f"--- Round {self.round} ---")
            curr = self.combatants[self.current_turn_index]
            if not curr.is_defeated:
                self.combat_log.append(f"Turn: {curr.name}")
                return curr
        return None

    def attack_target(
        self,
        attacker: Character,
        target_id: str,
        weapon: Optional[Item] = None,
        advantage: bool = False,
        disadvantage: bool = False,
        edition: str = "5e",
        d6_options: Optional[D6Options] = None,
        attacker_id: Optional[str] = None,
    ) -> RuleEvaluationResult:
        if edition == "weg_d6":
            if advantage or disadvantage:
                raise ValueError("WEG D6 does not use d20 advantage or disadvantage.")
            from dungeonforge.game import weg_combat
            return weg_combat.attack(self, attacker, target_id, weapon, d6_options, attacker_id)
        target = next((c for c in self.combatants if c.id == target_id), None)
        if not target or target.is_defeated:
            raise ValueError("Invalid target or target already defeated.")

        rule_engine = get_rule_engine(edition)
        eval_result = rule_engine.evaluate_attack(
            character=attacker,
            target_ac=target.ac,
            weapon=weapon,
            advantage=advantage,
            disadvantage=disadvantage
        )

        if eval_result.success and eval_result.damage_dealt:
            target.current_hp = max(0, target.current_hp - eval_result.damage_dealt)
            log_msg = f"{attacker.name} attacks {target.name}: {eval_result.summary} (Target HP: {target.current_hp}/{target.max_hp})"
            if target.current_hp == 0:
                target.is_defeated = True
                log_msg += f" -> ☠️ {target.name} is SLAN!"
        else:
            log_msg = f"{attacker.name} attacks {target.name}: {eval_result.summary}"

        self.combat_log.append(log_msg)

        # Check if combat ends after this attack
        if all(c.is_defeated for c in self.combatants if not c.is_player):
            self.active = False
            self.combat_log.append("⚔️ VICTORY! All enemies have been vanquished!")

        return eval_result

    def attack_with_companion(
        self,
        companion: Any,
        target_id: str,
        advantage: bool = False,
        disadvantage: bool = False,
        edition: str = "5e"
    ) -> RuleEvaluationResult:
        if edition == "weg_d6":
            if advantage or disadvantage:
                raise ValueError("WEG D6 does not use d20 advantage or disadvantage.")
            from dungeonforge.game import weg_combat
            native_actor = weg_combat.actor(self, companion.id)
            weg_combat.validate_turn(self, native_actor)
            target = weg_combat.actor(self, target_id)
            from dungeonforge.rules.weg_d6 import WEGD6Rules
            result = WEGD6Rules.resolve_attack(native_actor.d6, target.d6, native_actor.weapon)
            self.d6_actions_started = self.d6_turn_acted = True
            self.combat_log.append(f"{companion.name} → {target.name}: {result.summary}")
            weg_combat.refresh(self)
            companion.d6 = native_actor.d6
            return result
        target = next((c for c in self.combatants if c.id == target_id), None)
        if not target or target.is_defeated:
            raise ValueError("Invalid target or target already defeated.")

        attack_bonus = getattr(companion, "level", 2) + 2
        roll_expr = f"1d20+{attack_bonus}"
        if advantage and not disadvantage:
            roll_expr += " adv"
        elif disadvantage and not advantage:
            roll_expr += " dis"

        roll_result = DiceRoller.roll(roll_expr)
        is_hit = False

        if edition == "2e":
            target_num = 18 - target.ac
            is_hit = (roll_result.total >= target_num or roll_result.is_crit) and not roll_result.is_fumble
        else:
            is_hit = (roll_result.total >= target.ac or roll_result.is_crit) and not roll_result.is_fumble

        dmg_dealt = 0
        if is_hit:
            dmg_expr = getattr(companion, "damage", "1d6+2")
            if roll_result.is_crit:
                dmg_expr = DiceRoller.double_dice(dmg_expr)
            dmg_roll = DiceRoller.roll(dmg_expr)
            dmg_dealt = max(1, dmg_roll.total)
            target.current_hp = max(0, target.current_hp - dmg_dealt)

        eval_result = RuleEvaluationResult(
            action_type="companion_attack",
            success=is_hit,
            is_crit=roll_result.is_crit,
            is_fumble=roll_result.is_fumble,
            roll_result=roll_result,
            target_value=target.ac,
            damage_dealt=dmg_dealt if is_hit else None,
            summary=f"{companion.name} attacked {target.name} with {getattr(companion, 'attack_name', 'weapon')}: {'HIT for ' + str(dmg_dealt) + ' damage!' if is_hit else 'MISS!'}"
        )

        log_msg = f"{companion.name} strikes {target.name}: {eval_result.summary} (Target HP: {target.current_hp}/{target.max_hp})"
        if target.current_hp == 0:
            target.is_defeated = True
            log_msg += f" -> ☠️ {target.name} is DEFEATED!"

        self.combat_log.append(log_msg)

        if all(c.is_defeated for c in self.combatants if not c.is_player):
            self.active = False
            self.combat_log.append("⚔️ VICTORY! All enemies have been vanquished!")

        return eval_result

    def cast_spell_at_target(
        self,
        caster: Character,
        spell_name: str,
        slot_level: int,
        target_id: Optional[str] = None,
        damage_dice: Optional[str] = None,
        healing_dice: Optional[str] = None
    ) -> Dict[str, Any]:
        target = None
        if target_id:
            target = next((c for c in self.combatants if c.id == target_id), None)
            if not target or target.is_defeated:
                raise ValueError("Invalid target or target already defeated.")

        log_msg = f"{caster.name} casts {spell_name} (Level {slot_level})!"
        damage_dealt = 0
        healed_amount = 0

        if healing_dice:
            heal_roll = DiceRoller.roll(healing_dice)
            healed_amount = heal_roll.total
            caster.current_hp = min(caster.max_hp, caster.current_hp + healed_amount)
            log_msg += f" Restored {healed_amount} HP! (Current HP: {caster.current_hp}/{caster.max_hp})"
        elif damage_dice and target:
            dmg_roll = DiceRoller.roll(damage_dice)
            damage_dealt = dmg_roll.total
            target.current_hp = max(0, target.current_hp - damage_dealt)
            log_msg += f" Hits {target.name} for {damage_dealt} damage! (Target HP: {target.current_hp}/{target.max_hp})"
            if target.current_hp == 0:
                target.is_defeated = True
                log_msg += f" -> ☠️ {target.name} is SLAIN by magic!"

        self.combat_log.append(log_msg)

        if all(c.is_defeated for c in self.combatants if not c.is_player):
            self.active = False
            self.combat_log.append("⚔️ VICTORY! All enemies have been vanquished!")

        return {
            "spell_name": spell_name,
            "slot_level": slot_level,
            "target": target.name if target else None,
            "damage_dealt": damage_dealt,
            "healed_amount": healed_amount,
            "summary": log_msg
        }
