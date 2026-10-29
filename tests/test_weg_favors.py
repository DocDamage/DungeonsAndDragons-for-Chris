"""Rare source offers cannot become routine banked FP, free calls or CP mixtures."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import tempfile
from threading import Barrier
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from dungeonforge.api import routes
from dungeonforge.campaign.campaign_manager import CampaignManager
from dungeonforge.context.pipeline import ContextPipeline
from dungeonforge.game import weg_dark_side as dark_world
from dungeonforge.game.models import GameSession
from dungeonforge.game.saves import SaveManager
from dungeonforge.game.weg_force import advance_scene
from dungeonforge.game.weg_vehicle_presets import vehicle_presets
from dungeonforge.main import app
from dungeonforge.rules import weg_favors as rules
from dungeonforge.rules import weg_rewards
from dungeonforge.rules.base import Character, Companion, Item
from dungeonforge.rules.dice import RollResult
from dungeonforge.rules.weg_advancement_models import D6Instructor
from dungeonforge.rules.weg_d6 import WEGD6Rules
from dungeonforge.rules.weg_dark_models import DarkDemand
from dungeonforge.rules.weg_favor_models import FavorOfferRequest, FavorResolveRequest
from dungeonforge.rules.weg_force_models import ForceAttempt
from dungeonforge.rules.weg_models import D6Character
from dungeonforge.rules.weg_navigation_models import D6Journey, D6NavigationQuote, D6NavigationRequest
from dungeonforge.rules.weg_reward_models import AdventureActorReward, ForceReview


def plain(value=6):
    return RollResult(expression="1D6", dice_count=1, die_type=6, total=value, raw_rolls=[value], kept_rolls=[value],
        system="weg_d6", breakdown=f"Controlled plain corruption die {value}")


def make_session():
    hero = Character(id="hero", name="Actual hero", edition="weg_d6", d6=D6Character(
        force_sensitive=True, force_points=2, character_points=5, skills={"blaster": "5D"}))
    hero.companions = [Companion(id="ally", name="Actual ally", attack_name="Blaster pistol", damage="4D",
        d6=D6Character(), d6_weapon=Item(name="Blaster pistol", item_type="weapon", damage="4D", d6_skill="blaster"))]
    return GameSession(id="favors_scene", edition="weg_d6", character=hero)


def offer_request(session, **changes):
    count = len(session.character.d6.corruption.favors)
    return FavorOfferRequest(**{**dict(offer_id=f"rare_{count}", actor_id=session.character.id,
        moment_key=f"actual-climactic-moment-{count}", eligibility="desperately_recruited", gm_rare_offer_confirmed=True,
        reason="GM confirms the Dark Side is actively and desperately recruiting this actual individual at this exceptional moment.",
        expected_updated_at=session.updated_at), **changes})


def resolve_request(session, **changes):
    return FavorResolveRequest(**{**dict(actor_id=session.character.id,
        offer_id=changes.get("offer_id") or session.character.d6.corruption.favors[-1].id, action="use", reason="Accept the source offer for the declared actual action.",
        current_moment_confirmed=True, consequence_accepted=True, actions=1, expected_updated_at=session.updated_at), **changes})


class FavorRulesTests(unittest.TestCase):
    def setUp(self):
        self.session = make_session()
        roll = patch("dungeonforge.rules.weg_dark_side.plain_die", return_value=plain())
        roll.start()
        self.addCleanup(roll.stop)

    def offered(self, **changes):
        return rules.offer(self.session, offer_request(self.session, **changes))

    def use(self, **changes):
        return rules.resolve(self.session, resolve_request(self.session, **changes))

    def test_supplied_1992_source_distinguishes_rare_offers_unused_and_used_penalty(self):
        source = Path(__file__).resolve().parents[1] / "tmp/weg-source/page-054.txt"
        if not source.exists():
            self.skipTest("The optional user-provided local WEG source extract is not installed.")
        text = " ".join(source.read_text(encoding="utf-8").split())
        for fact in ("A very few individuals", "very powerful evil ones", "actively (and desperately) trying to recruit",
                "free points", "no penalty - unless they are used", "Dark Side Point no matter how the point was used"):
            self.assertIn(fact.lower(), text.lower())

    def test_unused_offer_decline_and_withdraw_never_grant_points_or_spend_actions(self):
        state = self.session.character.d6
        before = (state.force_points, state.character_points, state.dark_side_points, state.round_state.model_dump(), state.force.elapsed_rounds)
        self.offered()
        self.use(action="decline", current_moment_confirmed=False, consequence_accepted=False)
        self.offered()
        self.use(action="withdraw", current_moment_confirmed=False, consequence_accepted=False)
        self.assertEqual((state.force_points, state.character_points, state.dark_side_points, state.round_state.model_dump(), state.force.elapsed_rounds), before)
        self.assertEqual(state.corruption.events, [])
        self.assertEqual(state.rewards.expenditures, [])
        self.assertEqual([item.status for item in state.corruption.favors], ["declined", "withdrawn"])

    def test_unique_offer_and_actual_moment_remain_reserved_after_decline(self):
        first = self.offered()
        with self.assertRaises(ValueError):
            self.offered(offer_id="different", moment_key="another actual moment")
        self.use(action="decline", current_moment_confirmed=False, consequence_accepted=False)
        for changes in (dict(offer_id=first.id, moment_key="another actual moment"), dict(offer_id="new_id", moment_key=first.moment_key),
                dict(offer_id="case_variant", moment_key="  " + first.moment_key.upper() + "  ")):
            with self.assertRaises(ValueError):
                self.offered(**changes)
        with self.assertRaises(ValueError):
            rules.offer(self.session, offer_request(self.session, actor_id="ally", offer_id=first.id))

    def test_gm_rarity_and_actual_eligibility_evidence_cannot_be_omitted(self):
        for changes in (dict(gm_rare_offer_confirmed=False), dict(moment_key="  "), dict(reason="  "), dict(actor_id="imagined")):
            with self.assertRaises(ValueError):
                self.offered(**changes)
        self.assertEqual(self.session.character.d6.corruption.favors, [])

    def test_use_doubles_personal_pools_with_zero_call_action_counter_or_held_fp_change(self):
        self.offered()
        state = self.session.character.d6
        item = self.use()
        self.assertEqual((state.force_points, state.character_points, state.dark_side_points), (2, 5, 1))
        self.assertEqual((state.corruption.calls, state.round_state.actions_taken), (0, 0))
        self.assertEqual(state.round_state.declared_actions, 1)
        self.assertEqual(WEGD6Rules.pool(state, "blaster"), (10, 0))
        self.assertEqual(WEGD6Rules.damage_pool(state, Item(name="Blaster", damage="5D")), (5, 0))
        self.assertEqual(item.status, "used")
        self.assertEqual(state.rewards.expenditures[-1].source, "dark_side_favor")
        self.assertEqual(item.corruption_event_id, state.corruption.events[-1].id)
        self.assertEqual(item.expenditure_id, state.rewards.expenditures[-1].id)

    def test_favor_never_forces_a_fall_outside_the_existing_plain_check(self):
        self.offered()
        state = self.session.character.d6
        with patch("dungeonforge.rules.weg_dark_side.plain_die", return_value=plain(1)):
            self.use()
        self.assertFalse(state.force.dark_side_consumed)  # first DSP: 1 is not below 1
        advance_scene(self.session, 1)
        self.offered()
        with patch("dungeonforge.rules.weg_dark_side.plain_die", return_value=plain(1)):
            self.use()
        self.assertTrue(state.force.dark_side_consumed)
        self.assertEqual(state.corruption.control_mode, "gm")
        self.assertEqual((state.force_points, state.character_points), (2, 5))

    def test_already_consumed_actor_gets_existing_one_cp_per_dsp_no_second_fall_roll(self):
        state = self.session.character.d6
        state.force.dark_side_consumed = True
        self.offered(eligibility="very_powerful_evil")
        with patch("dungeonforge.rules.weg_dark_side.plain_die") as die:
            self.use()
        die.assert_not_called()
        self.assertEqual((state.dark_side_points, state.character_points, state.force_points), (1, 6, 2))
        with self.assertRaisesRegex(ValueError, "Character Points"):
            WEGD6Rules.validate_action(state, "blaster", 1)

    def test_optional_normal_fp_stacks_once_and_keeps_equipment_fixed(self):
        self.offered()
        self.use(force_point=True)
        state = self.session.character.d6
        self.assertEqual(state.force_points, 1)
        self.assertEqual(WEGD6Rules.pool(state, "blaster"), (20, 0))
        self.assertEqual(WEGD6Rules.damage_pool(state, Item(name="Blaster", damage="5D")), (5, 0))
        self.assertEqual([item.source for item in state.rewards.expenditures], ["round_boost", "dark_side_favor"])

    def test_free_favor_works_with_zero_held_fp_but_cannot_fund_an_extra_normal_fp(self):
        state = self.session.character.d6
        state.force_points = 0
        self.offered()
        with self.assertRaises(ValueError):
            self.use(force_point=True)
        self.assertEqual((state.dark_side_points, state.round_state.actions_taken), (0, 0))
        self.use()
        self.assertEqual(state.force_points, 0)
        self.assertEqual(WEGD6Rules.force_factor(state), 2)

    def test_existing_normal_fp_declaration_is_preserved_without_spending_twice(self):
        self.offered()
        state = self.session.character.d6
        WEGD6Rules.declare(state, 1, True)
        before = state.force_points
        with self.assertRaises(ValueError):
            self.use(force_point=True)
        self.use(force_point=False)
        self.assertEqual(state.force_points, before)
        self.assertEqual(WEGD6Rules.force_factor(state), 4)

    def test_actions_defenses_cp_call_and_pending_activation_reject_before_use(self):
        self.offered()
        state = self.session.character.d6
        for field, value in (("actions_taken", 1), ("character_points_spent", True), ("dark_side_called", True), ("full_defense", True), ("defense_skill", "dodge")):
            setattr(state.round_state, field, value)
            with self.assertRaises(ValueError):
                self.use()
            setattr(state.round_state, field, None if field == "defense_skill" else 0 if field == "actions_taken" else False)
        state.force.attempt = ForceAttempt(power_id="control_pain", source_id="hero", skills=["control"])
        with self.assertRaises(ValueError):
            self.use()
        self.assertEqual(state.dark_side_points, 0)
        self.assertEqual(state.corruption.favors[-1].status, "offered")

    def test_one_dark_side_point_per_round_not_a_reusable_offer_or_new_call(self):
        self.offered()
        self.use()
        with self.assertRaises(ValueError):
            self.use()
        self.offered()
        with self.assertRaisesRegex(ValueError, "per round"):
            self.use()
        before_clocks = [person.d6.force.elapsed_rounds for person in [self.session.character, *self.session.character.companions]]
        advance_scene(self.session, 1)
        self.assertEqual([person.d6.force.elapsed_rounds for person in [self.session.character, *self.session.character.companions]], [value + 1 for value in before_clocks])
        self.use()
        self.assertEqual(self.session.character.d6.corruption.calls, 0)

    def test_original_moment_and_adventure_are_not_a_transferable_banked_point(self):
        self.offered()
        for changes in (dict(current_moment_confirmed=False), dict(consequence_accepted=False), dict(actor_id="ally")):
            with self.assertRaises(ValueError):
                rules.resolve(self.session, resolve_request(self.session, **changes))
        self.session.d6_advancement.adventure += 1
        with self.assertRaises(ValueError):
            self.use()
        self.assertEqual(self.session.character.d6.force_points, 2)

    def test_unpaid_demand_and_actual_death_never_gain_a_favor_boost_or_extra_point(self):
        self.offered()
        state = self.session.character.d6
        state.corruption.pending_demand = DarkDemand(cp_loss=2, roll=plain(2))
        with self.assertRaises(ValueError):
            self.use()
        state.corruption.pending_demand = None
        state.wound = "dead"
        with self.assertRaises(ValueError):
            self.use()
        self.assertEqual((state.dark_side_points, state.force_points), (0, 2))
        self.assertEqual(state.corruption.favors[0].status, "offered")

    def test_instructor_summary_cannot_grant_or_receive_action_boost(self):
        self.session.d6_advancement.instructors.append(D6Instructor(id="teacher", name="Summary teacher"))
        with self.assertRaisesRegex(ValueError, "instructor"):
            self.offered(actor_id="teacher")

    def test_reward_review_reuses_favor_corruption_event_instead_of_awarding_second_dsp(self):
        self.offered()
        item = self.use()
        dark_world.synchronize(self.session)
        state = self.session.character.d6
        before = state.dark_side_points
        reward = AdventureActorReward(actor_id="hero", reason="GM reviews actual evil favor use.", reviews=[ForceReview(
            expenditure_id=item.expenditure_id, ruling="evil", reason="Actual use already incurred its DSP.", corruption_event_id=item.corruption_event_id)])
        with patch("dungeonforge.rules.weg_dark_side.plain_die") as die:
            weg_rewards.settle(state, reward, 1)
        die.assert_not_called()
        self.assertEqual(state.dark_side_points, before)
        self.assertEqual(state.force_points, 2)

    def test_saved_offer_state_and_source_context_export_are_readonly_and_legacy_empty(self):
        item = self.offered()
        before = self.session.model_dump()
        text = ContextPipeline.native_travel_summary(self.session)
        self.assertIn(item.id, text)
        self.assertIn("no FP balance granted and no DSP penalty", text)
        self.assertIn("printed p.57", text)
        self.assertEqual(self.session.model_dump(), before)
        with tempfile.TemporaryDirectory() as directory:
            manager = SaveManager(directory)
            loaded = manager.load_session(manager.save_session(self.session, "isolated_favor"))
            chronicle = manager.export_markdown_chronicle(loaded)
        self.assertEqual(loaded.character.d6.corruption.favors, self.session.character.d6.corruption.favors)
        self.assertIn(item.moment_key, chronicle)
        self.assertIn("no DSP penalty", chronicle)
        data = self.session.character.d6.model_dump()
        data["corruption"].pop("favors")
        self.assertEqual(D6Character.model_validate(data).corruption.favors, [])


class FavorAPITests(unittest.TestCase):
    def setUp(self):
        self.session = make_session()
        active = patch.object(routes, "_ACTIVE_SESSION", self.session)
        active.start()
        self.addCleanup(active.stop)
        plain_roll = patch("dungeonforge.rules.weg_dark_side.plain_die", return_value=plain())
        plain_roll.start()
        self.addCleanup(plain_roll.stop)
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def offer(self, **changes):
        response = self.client.post("/api/weg-d6/dark-side/favors/offer", json=offer_request(self.session, **changes).model_dump())
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def use(self, **changes):
        response = self.client.post("/api/weg-d6/dark-side/favors/resolve", json=resolve_request(self.session, **changes).model_dump())
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def rejected(self, action, payload):
        before = self.session.model_dump()
        response = self.client.post(f"/api/weg-d6/dark-side/favors/{action}", json=payload)
        self.assertIn(response.status_code, {400, 409, 422}, response.text)
        self.assertEqual(self.session.model_dump(), before)
        return response

    def test_get_is_readonly_and_stale_offer_or_use_are_atomic(self):
        before = self.session.model_dump()
        response = self.client.get("/api/weg-d6/dark-side/favors/state")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.session.model_dump(), before)
        payload = offer_request(self.session).model_dump()
        self.session.updated_at += 1
        self.rejected("offer", payload)
        self.offer()
        payload = resolve_request(self.session).model_dump()
        self.session.updated_at += 1
        self.rejected("resolve", payload)

    def test_unused_gm_ledger_preserves_pending_roll_history_and_force_attempt(self):
        state = self.session.character.d6
        state.force.attempt = ForceAttempt(power_id="control_pain", source_id="hero", skills=["control"], failed=True)
        before = state.force.attempt.model_dump()
        history = list(self.session.history)
        self.offer()
        self.assertEqual(self.session.character.d6.force.attempt.model_dump(), before)
        self.assertEqual(self.session.history, history)
        self.use(action="decline", current_moment_confirmed=False, consequence_accepted=False)
        self.assertEqual(self.session.character.d6.force.attempt.model_dump(), before)
        self.assertEqual(self.session.history, history)
        self.assertEqual(self.session.character.d6.dark_side_points, 0)

    def test_use_records_plain_corruption_and_expenditure_but_no_call_action_and_no_time(self):
        self.offer()
        before = [person.d6.force.elapsed_rounds for person in [self.session.character, *self.session.character.companions]]
        response = self.use(actions=2)
        state = self.session.character.d6
        self.assertEqual((state.corruption.calls, state.round_state.actions_taken, state.round_state.declared_actions), (0, 0, 2))
        self.assertEqual([person.d6.force.elapsed_rounds for person in [self.session.character, *self.session.character.companions]], before)
        self.assertEqual(len(response["eval_result"]["state_changes"]["corruption_events"]), 1)
        self.assertEqual(state.rewards.expenditures[0].adventure, self.session.d6_advancement.adventure)
        self.assertEqual(state.force_points, 2)
        view = self.client.get("/api/weg-d6/dark-side/favors/state").json()
        actor = next(item for item in view["actors"] if item["id"] == self.session.character.id)
        self.assertEqual(actor["active_favor_id"], state.corruption.favors[0].id)

    def test_real_scene_check_uses_full_favor_round_and_cp_before_after_roll_is_rejected(self):
        self.offer()
        self.use()
        before = self.session.model_dump()
        response = self.client.post("/api/weg-d6/check", json={"skill": "blaster", "difficulty": 10, "character_points": 1})
        self.assertEqual(response.status_code, 400, response.text)
        self.assertEqual(self.session.model_dump(), before)
        with patch("dungeonforge.rules.weg_d6.random.randint", return_value=4):
            response = self.client.post("/api/weg-d6/check", json={"skill": "blaster", "difficulty": 10})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["eval_result"]["roll_result"]["dice_count"], 10)
        self.assertEqual(self.client.post("/api/weg-d6/boost", json={"points": 1}).status_code, 400)
        self.assertEqual(self.session.character.d6.corruption.calls, 0)

    def test_scene_used_round_requires_actual_shared_advance_before_another_favor(self):
        self.offer()
        self.session.character.d6.round_state.actions_taken = 1
        self.rejected("resolve", resolve_request(self.session).model_dump())
        response = self.client.post("/api/weg-d6/force/manage", json={"action": "advance", "rounds": 1})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.session.character.d6.force.elapsed_rounds, 1)
        self.assertEqual(self.session.character.companions[0].d6.force.elapsed_rounds, 1)
        self.use()
        self.assertEqual(self.session.character.d6.round_state.actions_taken, 0)

    def test_concurrent_same_revision_resolve_cannot_duplicate_the_free_point(self):
        self.offer()
        payload = resolve_request(self.session).model_dump()
        barrier = Barrier(2)
        def submit():
            barrier.wait()
            with TestClient(app) as client:
                return client.post("/api/weg-d6/dark-side/favors/resolve", json=payload).status_code
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(lambda _: submit(), range(2)))
        self.assertEqual(sorted(outcomes), [200, 400])
        self.assertEqual(self.session.character.d6.dark_side_points, 1)
        self.assertEqual(len(self.session.character.d6.rewards.expenditures), 1)

    def test_round_declarations_before_personal_actions_include_non_active_actor(self):
        with patch("dungeonforge.rules.weg_d6.random.randint", return_value=4):
            response = self.client.post("/api/combat/start", json={"enemies": [{"name": "Actual enemy", "d6": D6Character().model_dump()}]})
        self.assertEqual(response.status_code, 200, response.text)
        self.offer(actor_id="ally")
        offer = self.session.character.companions[0].d6.corruption.favors[-1]
        response = self.client.post("/api/weg-d6/dark-side/favors/resolve", json={**resolve_request(self.session, offer_id=offer.id).model_dump(), "actor_id": "ally"})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.session.character.companions[0].d6.round_state.actions_taken, 0)
        self.assertFalse(self.session.encounter.d6_actions_started)

    def test_personal_and_craft_actions_started_block_favor_use_before_any_spending(self):
        with patch("dungeonforge.rules.weg_d6.random.randint", return_value=4):
            response = self.client.post("/api/combat/start", json={"enemies": [{"name": "Actual enemy", "d6": D6Character().model_dump()}]})
        self.assertEqual(response.status_code, 200, response.text)
        self.offer()
        self.session.encounter.d6_actions_started = True
        self.rejected("resolve", resolve_request(self.session).model_dump())

    def test_crew_favor_uses_actual_sheet_and_destroyed_station_cannot_activate(self):
        preset = CampaignManager.load_campaign("star_wars_d6")
        self.session.character = preset.starter_character
        self.session.vehicles = [vehicle_presets()["yt1300"]]
        with patch("dungeonforge.rules.weg_d6.random.randint", return_value=4):
            response = self.client.post("/api/weg-d6/vehicles/start", json={"vehicle_id": self.session.vehicles[0].id, "enemies": ["tie_fighter"]})
        self.assertEqual(response.status_code, 200, response.text)
        self.offer()
        player = next(craft for craft in self.session.vehicle_encounter.craft if craft.is_player)
        player.damage = "destroyed"
        self.rejected("resolve", resolve_request(self.session).model_dump())
        self.use(action="withdraw", current_moment_confirmed=False, consequence_accepted=False)
        self.assertEqual(self.session.character.d6.dark_side_points, 0)

    def test_frozen_wall_clock_still_advances_revision_and_saved_spent_offer_cannot_replay(self):
        before = self.session.updated_at
        with patch("dungeonforge.api.weg_favor_routes.time.time", return_value=100):
            self.offer()
            self.assertGreater(self.session.updated_at, before)
            self.use()
        with tempfile.TemporaryDirectory() as directory:
            manager = SaveManager(directory)
            loaded = manager.load_session(manager.save_session(self.session, "spent_favor"))
        routes._ACTIVE_SESSION = self.session = loaded
        self.rejected("resolve", resolve_request(self.session).model_dump())
        self.assertEqual(loaded.character.d6.corruption.favors[0].status, "used")

    def test_wrong_edition_and_invented_actor_cannot_offer(self):
        self.rejected("offer", offer_request(self.session, actor_id="invented").model_dump())
        self.session.edition = "5e"
        self.rejected("offer", offer_request(self.session).model_dump())

    def test_pending_navigation_ruling_and_exposed_crew_emergency_cannot_spend_favor(self):
        self.offer()
        journey = D6Journey(request=D6NavigationRequest(craft_id="actual_ship", origin="A", destination="B", reason="Actual route."),
            quote=D6NavigationQuote(difficulty=15, hours=1, rounds=720, has_navigation=True, multiplier=1),
            status="ten_point_ruling", remaining_rounds=720, roll={"total": 5})
        self.session.d6_navigation.journeys.append(journey)
        for status in ("ten_point_ruling", "emergency"):
            journey.status = status
            self.rejected("resolve", resolve_request(self.session).model_dump())
        self.assertEqual(self.session.character.d6.force_points, 2)
        self.assertEqual(self.session.character.d6.dark_side_points, 0)

    def test_saved_exclusive_work_blocks_favor_use_and_point_spending(self):
        self.offer()
        response = self.client.post("/api/weg-d6/tasks/begin", json={"actor_id": self.session.character.id,
            "label": "Actual focused watch", "reason": "GM reviews the exclusive task.", "exclusive": True,
            "steps": [{"skill": "search", "difficulty": 10, "rounds": 2, "reason": "Focus on the actual watch."}],
            "expected_updated_at": self.session.updated_at})
        self.assertEqual(response.status_code, 200, response.text)
        self.rejected("resolve", resolve_request(self.session).model_dump())

    def test_actual_crew_favor_boost_binds_to_real_party_sheet_without_a_crew_action(self):
        preset = CampaignManager.load_campaign("star_wars_d6")
        self.session.character = preset.starter_character
        self.session.vehicles = [vehicle_presets()["yt1300"]]
        with patch("dungeonforge.rules.weg_d6.random.randint", return_value=4):
            response = self.client.post("/api/weg-d6/vehicles/start", json={"vehicle_id": self.session.vehicles[0].id, "enemies": ["tie_fighter"]})
        self.assertEqual(response.status_code, 200, response.text)
        before = self.session.character.d6.force_points
        self.offer()
        self.use()
        player = next(craft for craft in self.session.vehicle_encounter.craft if craft.is_player)
        station = next(crew for crew in player.crew if crew.character_id == self.session.character.id)
        self.assertTrue(station.d6.round_state.dark_side_active)
        self.assertEqual(station.d6.round_state.actions_taken, 0)
        self.assertEqual(self.session.character.d6.force_points, before)
        self.assertFalse(self.session.vehicle_encounter.actions_started)


if __name__ == "__main__":
    unittest.main()
