"""1992 pp.63,65–68,154–158: physical gear, scope and persistence edges."""
import unittest
from unittest.mock import patch

from dungeonforge.campaign.campaign_manager import CampaignManager
from dungeonforge.game import weg_combat
from dungeonforge.game.combat import CombatEncounter, Combatant
from dungeonforge.game.models import GameSession
from dungeonforge.rules.base import Character
from dungeonforge.rules.dice import RollResult
from dungeonforge.rules.weg_d6 import D6Roller, WEGD6Rules
from dungeonforge.rules.weg_equipment import make_item
from dungeonforge.rules.weg_models import D6Character, D6Options, D6RoundState
from dungeonforge.rules import weg_personal_equipment as gear


def roll(total):
    return RollResult(expression="Controlled gear roll", dice_count=3, die_type=6, total=total,
        system="weg_d6", breakdown=f"Controlled total {total}")


class CombatEquipmentEdges(unittest.TestCase):
    def test_missed_shots_consume_real_ammunition_and_do_not_invent_a_fire_rate(self):
        shooter, target, weapon = D6Character(), D6Character(), make_item("blaster_dl18")
        shooter.round_state.declared_actions = 3
        with patch.object(D6Roller, "values", return_value=roll(1)):
            for _ in range(3):
                result = WEGD6Rules.resolve_attack(shooter, target, weapon)
                self.assertFalse(result.success)
        self.assertEqual((weapon.ammo, shooter.round_state.actions_taken), (97, 3))
        self.assertIsNone(weapon.d6_fire_rate)

    def test_generator_is_real_and_only_suppresses_source_generator_compatible_ammo(self):
        for id in ("light_repeating_blaster", "e_web"):
            weapon = make_item(id)
            weapon.generator_connected = True
            if weapon.ammo is not None:
                weapon.ammo = 0
            with patch.object(D6Roller, "values", return_value=roll(1)):
                WEGD6Rules.resolve_attack(D6Character(), D6Character(), weapon)
            self.assertIn(weapon.ammo, (0, None))
        pistol = make_item("blaster_dl18")
        pistol.ammo, pistol.generator_connected = 0, True
        with self.assertRaisesRegex(ValueError, "ammunition"):
            WEGD6Rules.resolve_attack(D6Character(), D6Character(), pistol)
        eweb = make_item("e_web")
        with self.assertRaisesRegex(ValueError, "generator"):
            WEGD6Rules.resolve_attack(D6Character(), D6Character(), eweb)

    def test_printed_whole_and_fractional_fire_rates_survive_new_rounds(self):
        shooter, target, weapon = D6Character(), D6Character(), make_item("e_web")
        weapon.generator_connected = True
        shooter.round_state.declared_actions = 2
        with patch.object(D6Roller, "values", return_value=roll(1)):
            WEGD6Rules.resolve_attack(shooter, target, weapon)
            with self.assertRaisesRegex(ValueError, "fire rate"):
                WEGD6Rules.resolve_attack(shooter, target, weapon)
            WEGD6Rules.next_round(shooter)
            WEGD6Rules.resolve_attack(shooter, target, weapon)
        slower = make_item("blaster_dl18")
        slower.d6_fire_rate = 0.5  # GM source-profile fixture, not a new catalog claim.
        shooter = D6Character()
        with patch.object(D6Roller, "values", return_value=roll(1)):
            WEGD6Rules.resolve_attack(shooter, target, slower)
            WEGD6Rules.next_round(shooter)
            with self.assertRaisesRegex(ValueError, "waited"):
                WEGD6Rules.resolve_attack(shooter, target, slower)
            WEGD6Rules.next_round(shooter)
            WEGD6Rules.resolve_attack(shooter, target, slower)
        self.assertEqual(slower.ammo, 98)

    def test_damage_penalties_reduce_weapon_damage_and_heavy_damage_adds_ten_difficulty(self):
        for condition, dice, difficulty in (("intact", 4, 10), ("lightly_damaged", 3, 10), ("heavily_damaged", 2, 20)):
            with self.subTest(condition=condition):
                weapon = make_item("blaster_dl18")
                weapon.weapon_damage_state = condition
                self.assertEqual(WEGD6Rules.damage_pool(D6Character(), weapon), (dice, 0))
                with patch.object(D6Roller, "values", return_value=roll(1)):
                    result = WEGD6Rules.resolve_attack(D6Character(), D6Character(), weapon)
                self.assertEqual(result.target_value, difficulty)
        for condition in ("severely_damaged", "destroyed"):
            weapon = make_item("blaster_dl18")
            weapon.weapon_damage_state = condition
            actor = D6Character()
            before = actor.model_dump(), weapon.model_dump()
            with self.assertRaises(ValueError):
                WEGD6Rules.resolve_attack(actor, D6Character(), weapon)
            self.assertEqual(before, (actor.model_dump(), weapon.model_dump()))

    def test_source_melee_maximum_applies_before_actual_weapon_damage_penalty(self):
        actor = D6Character(attributes=dict.fromkeys(D6Character().attributes, "6D"))
        actor.round_state.force_active = True
        weapon = make_item("vibroaxe")
        self.assertEqual(WEGD6Rules.damage_pool(actor, weapon), (7, 0))
        weapon.weapon_damage_state = "lightly_damaged"
        self.assertEqual(WEGD6Rules.damage_pool(actor, weapon), (6, 0))

    def test_actual_partial_armor_ignores_aggregate_armor_for_uncovered_location_or_side(self):
        actor = D6Character(armor_energy="9D", armor_physical="9D")
        helmet, vest = make_item("blast_helmet"), make_item("blast_vest")
        self.assertEqual(WEGD6Rules.resistance_pool(actor, "energy", [helmet, vest], "head", "back"), (3, 1))
        self.assertEqual(WEGD6Rules.resistance_pool(actor, "physical", [helmet, vest], "torso", "front"), (4, 0))
        self.assertEqual(WEGD6Rules.resistance_pool(actor, "physical", [helmet, vest], "torso", "back"), (3, 0))
        self.assertEqual(WEGD6Rules.resistance_pool(actor, "physical", [helmet, vest], "left_arm"), (3, 0))
        self.assertEqual(WEGD6Rules.resistance_pool(actor, "physical", None), (12, 0))

    def test_damaged_armor_loses_one_pip_one_die_or_all_protection_without_repair(self):
        armor = make_item("bounty_hunter_armor")
        for condition, physical, energy in (("intact", 6, 3), ("lightly_damaged", 5, 2),
                ("heavily_damaged", 3, 0), ("severely_damaged", 0, 0), ("destroyed", 0, 0)):
            armor.armor_damage_state = condition
            self.assertEqual(gear.armor_pips(armor, "physical"), physical)
            self.assertEqual(gear.armor_pips(armor, "energy"), energy)
        gear.apply_armor_damage(armor, "wounded")
        self.assertEqual(armor.armor_damage_state, "destroyed")

    def test_only_hit_armor_is_damaged_and_wound_uses_current_profile(self):
        for location, expected in (("head", "lightly_damaged"), ("torso", "intact")):
            target, helmet = D6Character(), make_item("blast_helmet")
            with patch.object(D6Roller, "values", side_effect=[roll(20), roll(17), roll(10)]) as rolling:
                result = WEGD6Rules.resolve_attack(D6Character(), target, make_item("blaster_dl18"),
                    D6Options(hit_location=location, called_shot=True), armor_items=[helmet])
            self.assertEqual(result.wound_result, "wounded")
            self.assertEqual(helmet.armor_damage_state, expected)
            self.assertEqual(rolling.call_args_list[2].args[:2], (3, 1 if location == "head" else 0))

    def test_optional_location_damage_and_called_shot_cost_have_source_die_effects(self):
        for location, dice in (("head", 5), ("torso", 3), ("left_arm", 4)):
            with patch.object(D6Roller, "values", side_effect=[roll(20), roll(10), roll(30)]) as rolling:
                WEGD6Rules.resolve_attack(D6Character(), D6Character(), make_item("blaster_dl18"),
                    D6Options(hit_location=location, called_shot=True, location_damage=True))
            self.assertEqual(rolling.call_args_list[0].args[0], 2)  # Actual -1D attack.
            self.assertEqual(rolling.call_args_list[1].args[0], dice)

    def test_bowcaster_additional_shot_strength_is_free_and_ignores_multiple_action_penalty(self):
        actor, weapon = D6Character(), make_item("bowcaster")
        actor.round_state.declared_actions = 2
        with patch.object(D6Roller, "values", side_effect=[roll(1), roll(10), roll(1)]) as rolling:
            WEGD6Rules.resolve_attack(actor, D6Character(), weapon)
            result = WEGD6Rules.resolve_attack(actor, D6Character(), weapon, D6Options(bowcaster_strength_character_points=1))
        self.assertEqual([call.args[0] for call in rolling.call_args_list], [2, 3, 2])
        self.assertTrue(result.state_changes["bowcaster_strength"]["success"])
        self.assertEqual((actor.round_state.actions_taken, weapon.ammo, weapon.power_ammo, actor.character_points), (2, 4, 48, 4))

    def test_failed_bowcaster_free_check_consumes_its_cp_but_no_attack_action_or_ammo(self):
        actor, weapon = D6Character(), make_item("bowcaster")
        actor.round_state.declared_actions = 2
        with patch.object(D6Roller, "values", side_effect=[roll(1), roll(1)]) as rolling:
            WEGD6Rules.resolve_attack(actor, D6Character(), weapon)
            result = WEGD6Rules.resolve_attack(actor, D6Character(), weapon, D6Options(bowcaster_strength_character_points=1))
        self.assertTrue(result.state_changes["no_attack_action"])
        self.assertEqual((actor.round_state.actions_taken, weapon.ammo, weapon.power_ammo, actor.character_points), (1, 5, 49, 4))
        with self.assertRaisesRegex(ValueError, "failed this round"):
            WEGD6Rules.resolve_attack(actor, D6Character(), weapon)
        self.assertEqual(rolling.call_count, 2)
        WEGD6Rules.next_round(actor)
        with patch.object(D6Roller, "values", return_value=roll(1)):
            WEGD6Rules.resolve_attack(actor, D6Character(), weapon)

    def test_bowcaster_both_declared_cp_must_be_affordable_before_any_free_roll(self):
        actor, weapon = D6Character(character_points=1), make_item("bowcaster")
        actor.round_state.declared_actions = 2
        actor.round_state.weapon_shots[weapon.id] = 1
        before = actor.model_dump(), weapon.model_dump()
        with patch.object(D6Roller, "values") as rolling, self.assertRaisesRegex(ValueError, "afford both"):
            WEGD6Rules.resolve_attack(actor, D6Character(), weapon, D6Options(character_points=1, bowcaster_strength_character_points=1))
        self.assertFalse(rolling.called)
        self.assertEqual(before, (actor.model_dump(), weapon.model_dump()))

    def test_loaded_pc_and_companion_weapon_copies_bind_back_to_empty_actual_inventory(self):
        character = CampaignManager.load_campaign("star_wars_d6").starter_character
        actual = make_item("blaster_dl18")
        actual.equipped, actual.equipped_by, actual.ammo = True, character.companions[0].id, 0
        character.inventory = [actual]
        character.companions[0].d6_weapon = actual.model_copy(deep=True, update={"ammo": 100})
        actor = Combatant(id=character.companions[0].id, name="Crew", is_player=True, d6=character.companions[0].d6,
            weapon=actual.model_copy(deep=True, update={"ammo": 100}))
        session = GameSession(edition="weg_d6", character=character,
            encounter=CombatEncounter(system="weg_d6", combatants=[actor]))
        loaded = GameSession.model_validate_json(session.model_dump_json())
        weg_combat.bind_party(loaded.encounter, loaded.character)
        self.assertIs(loaded.encounter.combatants[0].weapon, loaded.character.inventory[0])
        self.assertIs(loaded.character.companions[0].d6_weapon, loaded.character.inventory[0])
        before = loaded.model_dump()
        with self.assertRaisesRegex(ValueError, "ammunition"):
            WEGD6Rules.resolve_attack(loaded.encounter.combatants[0].d6, D6Character(), loaded.encounter.combatants[0].weapon)
        self.assertEqual(before, loaded.model_dump())

    def test_combat_can_start_with_unusable_drawn_weapon_then_actor_can_choose_spare(self):
        broken, spare = make_item("blaster_dl18"), make_item("heavy_blaster_dl44")
        broken.equipped, broken.equipped_by, broken.weapon_damage_state = True, "hero", "severely_damaged"
        hero = Character(id="hero", name="Hero", edition="weg_d6", d6=D6Character(), inventory=[broken, spare])
        encounter = CombatEncounter()
        with patch("dungeonforge.game.weg_combat.roll_initiative"):
            weg_combat.start(encounter, hero, [{"name": "Foe", "d6": D6Character().model_dump(), "weapon": make_item("blaster_dl18").model_dump()}])
        self.assertTrue(encounter.active)
        self.assertEqual(hero.inventory[1].id, spare.id)

    def test_removed_actual_weapon_is_not_retained_as_cached_combat_inventory(self):
        removed = make_item("blaster_dl18")
        hero = Character(id="hero", name="Hero", edition="weg_d6", d6=D6Character(), inventory=[])
        encounter = CombatEncounter(system="weg_d6", combatants=[Combatant(id="hero", name="Hero", is_player=True, d6=hero.d6, weapon=removed)])
        weg_combat.bind_party(encounter, hero)
        drawn = encounter.combatants[0].weapon
        self.assertNotEqual(drawn.id if drawn else None, removed.id)

    def test_transferred_actual_weapon_does_not_remain_drawn_by_previous_actor(self):
        character = CampaignManager.load_campaign("star_wars_d6").starter_character
        crew = character.companions[0]
        weapon = make_item("blaster_dl18")
        weapon.equipped, weapon.equipped_by = True, crew.id
        character.inventory = [weapon]
        encounter = CombatEncounter(system="weg_d6", combatants=[
            Combatant(id=character.id, name=character.name, is_player=True, d6=character.d6, weapon=weapon.model_copy(deep=True)),
            Combatant(id=crew.id, name=crew.name, is_player=True, d6=crew.d6, weapon=None)])
        weg_combat.bind_party(encounter, character)
        prior = encounter.combatants[0].weapon
        self.assertNotEqual(prior.id if prior else None, weapon.id)
        self.assertIs(encounter.combatants[1].weapon, character.inventory[0])

    def test_eweb_once_per_round_limit_follows_physical_weapon_when_transferred(self):
        character = CampaignManager.load_campaign("star_wars_d6").starter_character
        crew = character.companions[0]
        weapon = make_item("e_web")
        weapon.equipped, weapon.equipped_by, weapon.generator_connected = True, character.id, True
        character.inventory = [weapon]
        encounter = CombatEncounter(system="weg_d6", combatants=[
            Combatant(id=character.id, name=character.name, is_player=True, d6=character.d6, weapon=weapon),
            Combatant(id=crew.id, name=crew.name, is_player=True, d6=crew.d6, weapon=None),
            Combatant(id="foe", name="Foe", d6=D6Character())])
        with patch.object(D6Roller, "values", return_value=roll(1)):
            weg_combat.attack(encounter, character, "foe", weapon)
            # The GM-confirmed transfer does not make the same physical gun cycle faster.
            weapon.equipped_by = crew.id
            encounter.current_turn_index, encounter.d6_turn_acted = 1, False
            with self.assertRaisesRegex(ValueError, "fire rate|fired|round"):
                weg_combat.attack(encounter, character, "foe", actor_id=crew.id)
