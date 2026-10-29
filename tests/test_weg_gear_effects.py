"""Actual 1992 source functions: target/action scope, damage, FP and real prep."""
import unittest
from unittest.mock import patch

from fastapi import HTTPException

from dungeonforge.api import routes
from dungeonforge.api import weg_gear_effect_routes as api
from dungeonforge.api.weg_routes import check as native_check
from dungeonforge.api.weg_tactics_routes import gear as combat_gear, D6GearAction
from dungeonforge.campaign.campaign_manager import CampaignManager
from dungeonforge.context.pipeline import ActionTurn
from dungeonforge.game.combat import CombatEncounter, Combatant
from dungeonforge.game.models import GameSession
from dungeonforge.rules import weg_gear_effects as gear
from dungeonforge.rules.base import Item
from dungeonforge.rules.weg_d6 import WEGD6Rules, D6Roller
from dungeonforge.rules.dice import RollResult
from dungeonforge.rules.weg_equipment import make_item
from dungeonforge.rules.weg_gear_effect_models import D6GearContext, GearFactsRequest, GearPrepareRequest, MacroPreparation
from dungeonforge.rules.weg_models import D6Character, D6Options, D6CheckRequest


class GearEffectsTests(unittest.TestCase):
    def setUp(self):
        character = CampaignManager.load_campaign("star_wars_d6").starter_character
        character.inventory = []
        character.d6.skills.update(blaster="4D", search="3D")
        self.session = GameSession(edition="weg_d6", character=character)
        active = patch.object(routes, "_ACTIVE_SESSION", self.session)
        active.start()
        self.addCleanup(active.stop)

    @property
    def state(self):
        return self.session.character.d6

    def item(self, catalog, *, worn=True):
        item = make_item(catalog)
        item.equipped, item.equipped_by = worn, self.session.character.id if worn else None
        self.session.character.inventory.append(item)
        return item

    def facts(self, **changes):
        result = api.configure(GearFactsRequest(actor_id=self.session.character.id,
            reason="GM confirms actual functioning source equipment and this visual task/target/position.",
            expected_updated_at=self.session.updated_at, **changes))
        gear.refresh(self.session)
        return result

    def scope(self, skill):
        gear.refresh(self.session)
        gear.bind_check(self.state, skill)
        return WEGD6Rules.pool(self.state, skill)

    def macro_facts(self, macro, weapon=None, **changes):
        facts = {"macro_item_id": macro.id, "macro_functional": True, "macro_mode": "linked" if weapon else "view",
            "visual_task_confirmed": True, "visual_skill": "search", "target_id": "Actual distant patrol",
            "view_distance_m": 200}
        if weapon:
            facts.update(linked_weapon_id=weapon.id, software_confirmed=True,
                software_facts="Actual installed compatibility software and physical linkage.", steady_rest=True)
        return self.facts(**(facts | changes))

    def prepare(self):
        context = self.state.gear_context
        result = api.prepare(GearPrepareRequest(actor_id=self.session.character.id,
            target_id=context.target_id, reason="Actual full round in the unchanged steady sniper position.",
            expected_updated_at=self.session.updated_at))
        gear.refresh(self.session)
        return result

    def test_unknown_legacy_items_and_payload_bonus_numbers_cannot_grant_source_functions(self):
        unknown = Item(name="PowerSuit", item_type="armor", equipped=True, equipped_by=self.session.character.id)
        self.session.character.inventory.append(unknown)
        before = self.session.model_dump()
        with self.assertRaises(HTTPException):
            self.facts(powersuit_id=unknown.id, powersuit_functional=True)
        self.assertEqual(self.session.model_dump(), before)
        self.state.gear_context = D6GearContext.model_validate({"bonus": 999, "_inventory": [unknown.model_dump()], "_session_id": "fake", "reason": "Client bonus claim."})
        self.assertEqual(WEGD6Rules.pool(self.state, "lifting"), (3, 0))

    def test_powersuit_lifting_only_and_external_dice_are_not_force_doubled(self):
        suit = self.item("bounty_hunter_armor")
        self.facts(powersuit_id=suit.id, powersuit_functional=True)
        self.assertEqual(self.scope("lifting"), (4, 0))
        self.assertEqual(self.scope("strength"), (3, 0))
        self.state.round_state.force_active = True
        self.assertEqual(self.scope("lifting"), (7, 0))
        self.assertEqual(WEGD6Rules.damage_pool(self.state, None), (6, 0))
        self.state.skills["lifting_cargo"] = "4D"
        self.state.specialization_parents["lifting_cargo"] = "lifting"
        self.state.skill_attributes["lifting_cargo"] = "strength"
        self.assertEqual(self.scope("lifting_cargo"), (9, 0))

    def test_current_owner_and_damage_are_rechecked_instead_of_trusting_cached_bonus(self):
        suit = self.item("bounty_hunter_armor")
        self.facts(powersuit_id=suit.id, powersuit_functional=True)
        actual = self.session.character.inventory[0]
        self.assertEqual(self.scope("lifting"), (4, 0))
        actual.armor_damage_state = "lightly_damaged"
        self.assertEqual(self.scope("lifting"), (3, 0))
        self.facts(powersuit_id=actual.id, powersuit_functional=True)
        self.assertEqual(self.scope("lifting"), (4, 0))
        actual = self.session.character.inventory[0]
        actual.equipped_by = self.session.character.companions[0].id
        self.assertEqual(self.scope("lifting"), (3, 0))
        actual.equipped_by = self.session.character.id
        actual.armor_damage_state = "severely_damaged"
        self.assertEqual(self.scope("lifting"), (3, 0))
        with self.assertRaises(HTTPException):
            self.facts(powersuit_id=actual.id, powersuit_functional=True)

    def test_mftas_is_literal_perception_in_obscured_visibility_with_real_head_coverage(self):
        armor = self.item("stormtrooper_armor")
        self.facts(mftas_id=armor.id, mftas_functional=True, visual_task_confirmed=True,
            visual_skill="perception", visibility_obscured=True)
        self.assertEqual(self.scope("perception"), (5, 0))
        self.assertEqual(self.scope("per"), (5, 0))
        self.assertEqual(self.scope("search"), (3, 0))
        self.state.gear_context.visibility_obscured = False
        self.assertEqual(self.scope("perception"), (3, 0))
        self.state.gear_context.visibility_obscured = True
        self.session.character.inventory[0].armor_locations = ["torso"]
        self.assertEqual(self.scope("perception"), (3, 0))

    def test_mftas_moving_target_is_strictly_more_than_ten_and_matches_current_target(self):
        armor, weapon = self.item("stormtrooper_armor"), self.item("blaster_rifle")
        self.facts(mftas_id=armor.id, mftas_functional=True, target_id="Actual patrol", target_movement_m=10)
        gear.bind_attack(self.session, self.session.character.id, "Actual patrol", self.session.character.inventory[1], D6Options())
        self.assertEqual(WEGD6Rules.pool(self.state, "blaster"), (4, 0))  # Starter blaster4D.
        self.facts(mftas_id=armor.id, mftas_functional=True, target_id="Actual patrol", target_movement_m=10.001)
        gear.bind_attack(self.session, self.session.character.id, "Actual patrol", self.session.character.inventory[1], D6Options())
        self.assertEqual(WEGD6Rules.pool(self.state, "blaster"), (6, 0))
        gear.bind_attack(self.session, self.session.character.id, "Different target", self.session.character.inventory[1], D6Options())
        self.assertEqual(WEGD6Rules.pool(self.state, "blaster"), (4, 0))

    def test_action_history_and_encounter_round_expire_target_facts(self):
        armor, weapon = self.item("stormtrooper_armor"), self.item("blaster_rifle")
        self.session.encounter = CombatEncounter(system="weg_d6", combatants=[
            Combatant(id=self.session.character.id, name="Hero", is_player=True, d6=self.state, weapon=weapon),
            Combatant(id="foe", name="Actual foe", d6=D6Character())])
        self.facts(mftas_id=armor.id, mftas_functional=True, target_id="foe", target_movement_m=12)
        gear.bind_attack(self.session, self.session.character.id, "foe", self.session.character.inventory[1], D6Options())
        self.assertEqual(WEGD6Rules.pool(self.state, "blaster"), (6, 0))
        self.session.history.append(ActionTurn(id="actual_other_action", mode="check", player_input="Other actual action", dm_output="Resolved."))
        gear.bind_attack(self.session, self.session.character.id, "foe", self.session.character.inventory[1], D6Options())
        self.assertEqual(WEGD6Rules.pool(self.state, "blaster"), (4, 0))
        self.facts(mftas_id=armor.id, mftas_functional=True, target_id="foe", target_movement_m=12)
        self.session.encounter.round += 1
        gear.bind_attack(self.session, self.session.character.id, "foe", self.session.character.inventory[1], D6Options())
        self.assertEqual(WEGD6Rules.pool(self.state, "blaster"), (4, 0))

    def test_macro_view_strict_distance_range_and_actual_visual_skill(self):
        macro = self.item("macrobinoculars", worn=False)
        for distance, expected in ((100, 3), (100.001, 6), (1000, 6), (1000.001, 3)):
            self.macro_facts(macro, view_distance_m=distance)
            self.assertEqual(self.scope("search"), (expected, 0))
            self.assertEqual(self.scope("perception"), (3, 0))
        self.state.gear_context.visual_task_confirmed = False
        self.assertEqual(self.scope("search"), (3, 0))

    def test_macro_cannot_boost_unrelated_skill_or_serve_two_actual_owners(self):
        macro = self.item("macrobinoculars", worn=False)
        before = self.session.model_dump()
        with self.assertRaises(HTTPException):
            self.macro_facts(macro, visual_skill="first_aid")
        self.assertEqual(self.session.model_dump(), before)
        self.macro_facts(macro)
        before = self.session.model_dump()
        with self.assertRaises(HTTPException):
            api.configure(GearFactsRequest(actor_id=self.session.character.companions[0].id,
                reason="An actual second actor cannot use the same held instrument.", expected_updated_at=self.session.updated_at,
                macro_item_id=macro.id, macro_mode="view", macro_functional=True,
                target_id="Actual distant target", view_distance_m=200))
        self.assertEqual(self.session.model_dump(), before)

    def test_linked_macro_needs_actual_software_steady_rest_and_unforged_preparation(self):
        macro, weapon = self.item("macrobinoculars", worn=False), self.item("blaster_rifle")
        for changes in ({"software_confirmed": False}, {"software_facts": ""}, {"steady_rest": False}):
            before = self.session.model_dump()
            with self.assertRaises(HTTPException):
                self.macro_facts(macro, weapon, **changes)
            self.assertEqual(self.session.model_dump(), before)
        self.macro_facts(macro, weapon)
        self.assertEqual(self.scope("blaster"), (4, 0))
        self.state.gear_context.preparation = MacroPreparation(macro_item_id=macro.id, weapon_id=weapon.id,
            target_id="Actual distant patrol", completed_elapsed_round=0)
        self.state.gear_context.position_maintained = True
        self.assertEqual(self.scope("blaster"), (4, 0))  # No actual source action history witness.

    def test_genuine_preparation_cannot_transfer_to_another_actor_with_the_items(self):
        macro, weapon = self.item("macrobinoculars", worn=False), self.item("blaster_rifle")
        self.macro_facts(macro, weapon)
        self.prepare()
        ally = self.session.character.companions[0]
        ally.d6.gear_context = self.state.gear_context.model_copy(deep=True)
        macro.equipped_by = weapon.equipped_by = ally.id
        gear.refresh(self.session)
        gear.bind_check(ally.d6, "blaster")
        self.assertEqual(WEGD6Rules.pool(ally.d6, "blaster"), (3, 2))

    def test_real_downtime_preparation_advances_party_once_then_linked_bonus_has_native_range_limits(self):
        macro, weapon = self.item("macrobinoculars", worn=False), self.item("blaster_rifle")
        self.macro_facts(macro, weapon)
        self.prepare()
        self.assertEqual((self.state.force.elapsed_rounds, self.session.character.companions[0].d6.force.elapsed_rounds), (1, 1))
        self.assertEqual(self.scope("blaster"), (7, 0))
        context = self.state.gear_context
        self.assertEqual(self.session.history[context.preparation.history_index].rule_result.state_changes["macro_preparation"], context.preparation.model_dump())
        for band, expected in (("point_blank", 4), ("short", 4), ("medium", 7), ("long", 7)):
            gear.bind_attack(self.session, self.session.character.id, context.target_id, self.session.character.inventory[1], D6Options(range_band=band))
            self.assertEqual(WEGD6Rules.pool(self.state, "blaster"), (expected, 0))
        gear.bind_attack(self.session, self.session.character.id, context.target_id, self.session.character.inventory[1], D6Options(distance_m=301))
        self.assertEqual(WEGD6Rules.pool(self.state, "blaster"), (4, 0))

    def test_preparation_and_actual_conditions_survive_save_but_runtime_authority_does_not(self):
        macro, weapon = self.item("macrobinoculars", worn=False), self.item("blaster_rifle")
        self.macro_facts(macro, weapon)
        self.prepare()
        loaded = GameSession.model_validate_json(self.session.model_dump_json())
        self.assertEqual(loaded.character.d6.gear_context._inventory, [])
        self.assertEqual(WEGD6Rules.pool(loaded.character.d6, "blaster"), (4, 0))
        gear.refresh(loaded)
        gear.bind_check(loaded.character.d6, "blaster")
        self.assertEqual(WEGD6Rules.pool(loaded.character.d6, "blaster"), (7, 0))
        loaded.character.inventory[0].equipped_by = loaded.character.companions[0].id
        self.assertEqual(WEGD6Rules.pool(loaded.character.d6, "blaster"), (4, 0))

    def test_wrong_target_or_new_damage_cannot_reuse_a_real_preparation_nonce(self):
        macro, weapon = self.item("macrobinoculars", worn=False), self.item("blaster_rifle")
        self.macro_facts(macro, weapon)
        self.prepare()
        self.assertEqual(self.scope("blaster"), (7, 0))
        self.state.gear_context.preparation.target_id = "Different target"
        self.assertEqual(self.scope("blaster"), (4, 0))
        self.prepare()
        self.session.character.inventory[0].weapon_damage_state = "lightly_damaged"
        self.assertEqual(self.scope("blaster"), (4, 0))

    def test_stale_configure_is_atomic_and_link_never_changes_actual_weapon_statistics(self):
        macro, weapon = self.item("macrobinoculars", worn=False), self.item("blaster_rifle")
        before_weapon = weapon.model_dump()
        self.macro_facts(macro, weapon)
        self.prepare()
        self.assertEqual(self.session.character.inventory[1].model_dump(), before_weapon)
        before = self.session.model_dump()
        with self.assertRaises(HTTPException):
            api.configure(GearFactsRequest(actor_id=self.session.character.id, reason="Stale actual facts.",
                expected_updated_at=self.session.updated_at - 1))
        self.assertEqual(self.session.model_dump(), before)

    def test_distinct_applicable_visual_source_effects_add_without_force_multiplication(self):
        armor, macro = self.item("stormtrooper_armor"), self.item("macrobinoculars", worn=False)
        self.macro_facts(macro, mftas_id=armor.id, mftas_functional=True, visual_skill="perception", visibility_obscured=True)
        self.assertEqual(self.scope("perception"), (8, 0))  # 3D base +2D MFTAS +3D actual macro.
        self.state.round_state.force_active = True
        self.assertEqual(self.scope("perception"), (11, 0))

    def test_native_check_route_refreshes_working_copy_and_expires_visual_facts(self):
        armor = self.item("stormtrooper_armor")
        self.facts(mftas_id=armor.id, mftas_functional=True, visual_task_confirmed=True,
            visual_skill="perception", visibility_obscured=True)
        controlled = RollResult(expression="Controlled gear roll", dice_count=3, die_type=6,
            total=1, system="weg_d6", breakdown="Controlled miss1")
        with patch.object(D6Roller, "values", return_value=controlled) as rolling:
            native_check(D6CheckRequest(skill="perception"))
            self.assertEqual(rolling.call_args.args[:2], (5, 0))
            native_check(D6CheckRequest(skill="perception"))
            self.assertEqual(rolling.call_args.args[:2], (3, 0))

    def test_native_check_route_keeps_powersuit_external_to_force_doubling(self):
        suit = self.item("bounty_hunter_armor")
        self.facts(powersuit_id=suit.id, powersuit_functional=True)
        controlled = RollResult(expression="Controlled gear roll", dice_count=3, die_type=6,
            total=1, system="weg_d6", breakdown="Controlled miss1")
        with patch.object(D6Roller, "values", return_value=controlled) as rolling:
            native_check(D6CheckRequest(skill="lifting", force_point=True))
        self.assertEqual(rolling.call_args.args[:2], (7, 0))

    def test_native_combat_prepare_has_real_witness_and_can_support_the_next_actual_shot(self):
        macro, weapon = self.item("macrobinoculars", worn=False), self.item("blaster_rifle")
        self.session.encounter = CombatEncounter(system="weg_d6", combatants=[
            Combatant(id=self.session.character.id, name="Hero", is_player=True, d6=self.state, weapon=weapon),
            Combatant(id="foe", name="Actual foe", d6=D6Character())])
        self.macro_facts(macro, weapon, target_id="foe")
        combat_gear(D6GearAction(actor_id=self.session.character.id, action="prepare", item_id=weapon.id,
            target_id="foe", expected_updated_at=self.session.updated_at))
        proof = self.state.gear_context.preparation
        self.assertEqual(self.session.history[proof.history_index].rule_result.state_changes["macro_preparation"], proof.model_dump())
        self.session.encounter.round = 2
        self.session.encounter.d6_turn_acted = False
        WEGD6Rules.next_round(self.state)
        self.macro_facts(macro, weapon, target_id="foe", position_maintained=True)
        actual = self.session.character.inventory[1]
        options = D6Options(range_band="long")
        gear.bind_attack(self.session, self.session.character.id, "foe", actual, options)
        controlled = RollResult(expression="Controlled gear roll", dice_count=3, die_type=6,
            total=1, system="weg_d6", breakdown="Controlled miss1")
        from dungeonforge.game import weg_combat
        with patch.object(D6Roller, "values", return_value=controlled) as rolling:
            result = weg_combat.attack(self.session.encounter, self.session.character, "foe", actual, options)
        self.assertFalse(result.success)
        self.assertEqual(rolling.call_args.args[:2], (8, 0))  # 4D native +1D exclusive generic prep +3D physical linked macro.
        self.assertEqual(actual.ammo, 99)
