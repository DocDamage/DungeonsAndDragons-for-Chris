"""Source-backed child allies never become free permanent spell or XP rewards."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from fastapi.testclient import TestClient

from dungeonforge.api import routes
from dungeonforge.campaign.strahd import build_preset
from dungeonforge.campaign import strahd_children as rules
from dungeonforge.campaign import strahd_death_house as clock
from dungeonforge.context.pipeline import ContextPipeline
from dungeonforge.game.combat import CombatEncounter
from dungeonforge.game.models import GameSession
from dungeonforge.game.saves import SaveManager
from dungeonforge.main import app
from dungeonforge.rules.base import Companion
from dungeonforge.rules.strahd_children_models import DurstChildrenRequest
from dungeonforge.rules.strahd_models import DeathHouseRequest


def make_session():
    preset = build_preset()
    preset.starter_character.companions = [Companion(id="actual_second", name="Second actual PC")]
    return GameSession(id="session_strahd", edition="5e", source_folders=["strahd"],
        character=preset.starter_character, campaign_name=preset.title, active_quests=preset.active_quests)


class DurstChildrenSourceTests(unittest.TestCase):
    def test_local_arc_confirms_exact_cantrips_consent_and_crypt_exception(self):
        archive = Path(__file__).resolve().parents[2] / rules.SOURCE.split("!/", 1)[0]
        if not archive.exists():
            self.skipTest("The optional user-provided local Reloaded archive is not installed.")
        with ZipFile(archive) as source:
            text = source.read(rules.SOURCE.split("!/", 1)[1]).decode("utf-8-sig")
        for fact in ("_mending_, _light_, and _shocking grasp_", "attempts to possess a friendly player if permitted",
                "_mage hand_ cantrip as an action, without the use of components", "spectral hand is invisible",
                "cannot help Rose or Thorn’s ghosts find peace by placing their remains in their coffins",
                "spirits end their possessions", "children's spirits will not proceed further into Barovia",
                "children’s spirits thank them before vanishing"):
            self.assertIn(fact, text)
        self.assertEqual(rules.ABILITIES, {"rose": ["Mending", "Light", "Shocking Grasp"], "thorn": ["Mage Hand"]})


class DurstChildrenAPITests(unittest.TestCase):
    def setUp(self):
        self.session = make_session()
        active = patch.object(routes, "_ACTIVE_SESSION", self.session)
        active.start()
        self.addCleanup(active.stop)
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def request(self, action="meet", **changes):
        return {**dict(event_id=f"child_{len(self.session.strahd_progress.children.events)}", action=action,
            actor_id=self.session.character.id, actual_event_confirmed=True,
            reason="GM confirms this actual source event in play.", expected_updated_at=self.session.updated_at), **changes}

    def post(self, action="meet", **changes):
        response = self.client.post("/api/strahd/progress/children/event", json=self.request(action, **changes))
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def rejected(self, payload):
        before = self.session.model_dump()
        response = self.client.post("/api/strahd/progress/children/event", json=payload)
        self.assertIn(response.status_code, {400, 409, 422}, response.text)
        self.assertEqual(self.session.model_dump(), before)
        return response

    def allied(self):
        self.post()
        self.post("rose_bargain", burial_promise_confirmed=True)
        self.post("invite_children", friendly_host_confirmed=True)

    def consent(self, spirit="rose", **changes):
        return self.post("consent_possession", **{**dict(spirit=spirit, friendly_host_confirmed=True,
            player_host_confirmed=True, host_consent_confirmed=True), **changes})

    def exit_house(self):
        for action in ("start", "mound_destroyed", "escaped"):
            response = self.client.post("/api/strahd/progress/death-house/event", json=DeathHouseRequest(
                event_id=f"clock_{action}", action=action, actual_event_confirmed=True,
                actor_ids=[self.session.character.id], reason="GM confirms this actual house event.",
                expected_updated_at=self.session.updated_at).model_dump())
            self.assertEqual(response.status_code, 200, response.text)

    def test_readonly_legacy_state_does_not_invent_allies_items_or_spells(self):
        before = self.session.model_dump()
        data = self.client.get("/api/strahd/progress/children/state").json()
        self.assertFalse(data["children"]["met"])
        self.assertFalse(data["children"]["invited"])
        self.assertEqual(data["children"]["permissions"], [])
        self.assertTrue(all(item["remains_location"] == "unreviewed" for item in data["children"]["spirits"]))
        self.assertEqual(self.session.model_dump(), before)

    def test_quote_readonly_then_stale_actor_revision_and_duplicate_event_are_atomic(self):
        payload = self.request()
        before = self.session.model_dump()
        response = self.client.post("/api/strahd/progress/children/quote", json=payload)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(response.json()["children"]["met"])
        self.assertEqual(self.session.model_dump(), before)
        self.session.updated_at += 1
        self.rejected(payload)
        payload["expected_updated_at"] = self.session.updated_at
        response = self.client.post("/api/strahd/progress/children/event", json=payload)
        self.assertEqual(response.status_code, 200, response.text)
        payload["expected_updated_at"] = self.session.updated_at
        self.rejected(payload)

    def test_real_actor_evidence_and_relevant_fields_required_before_mutation(self):
        for changes in (dict(actor_id="invented"), dict(actual_event_confirmed=False), dict(reason="  "),
                dict(spirit="rose"), dict(spell="Light"), dict(friendly_host_confirmed=True),
                dict(host_consent_confirmed=True), dict(player_host_confirmed=True),
                dict(burial_promise_confirmed=True), dict(event_id="system_madeup")):
            self.rejected(self.request(**changes))
        self.rejected(self.request("rose_bargain", burial_promise_confirmed=True))

    def test_rose_bargain_requires_actual_promise_without_automatic_unlock_or_xp(self):
        self.post()
        self.rejected(self.request("rose_bargain"))
        self.post("rose_bargain", burial_promise_confirmed=True)
        state = self.session.strahd_progress.children
        self.assertTrue(state.secret_revealed)
        self.assertTrue(state.burial_promised)
        self.assertFalse(state.invited)
        self.assertEqual(state.spirits[0].remains_location, "unreviewed")
        self.assertEqual(self.session.strahd_progress.death_house.status, "unstarted")
        self.assertEqual(self.session.strahd_progress.awards, [])
        self.assertIn("amber lock", state.events[-1].effects[0])
        self.rejected(self.request("rose_bargain", burial_promise_confirmed=True))

    def test_invitation_does_not_impose_possession_and_host_must_be_actual_friendly_willing_pc(self):
        self.post()
        self.rejected(self.request("invite_children", friendly_host_confirmed=True))
        self.post("rose_bargain", burial_promise_confirmed=True)
        self.post("invite_children", friendly_host_confirmed=True)
        self.assertTrue(all(item.host_id is None for item in self.session.strahd_progress.children.spirits))
        base = dict(spirit="rose", friendly_host_confirmed=True, player_host_confirmed=True, host_consent_confirmed=True)
        for flag in ("friendly_host_confirmed", "player_host_confirmed", "host_consent_confirmed"):
            self.rejected(self.request("consent_possession", **{**base, flag: False}))
        self.consent()
        confirmations = self.session.strahd_progress.children.events[-1].confirmations
        self.assertTrue(confirmations["player_host_confirmed"])
        self.assertTrue(confirmations["host_consent_confirmed"])
        self.assertTrue(confirmations["friendly_host_confirmed"])
        self.rejected(self.request("consent_possession", **base))

    def test_temporary_cantrips_do_not_change_existing_spells_slots_inventory_or_class(self):
        self.session.character.known_spells.append("Light")
        sheet = self.session.character.model_dump()
        self.allied()
        self.consent("rose")
        self.consent("thorn")
        data = self.client.get("/api/strahd/progress/children/state").json()["children"]
        self.assertEqual(data["permissions"][0]["abilities"], ["Mending", "Light", "Shocking Grasp"])
        self.assertEqual(data["permissions"][1]["abilities"], ["Mage Hand"])
        self.assertIn("invisible", data["permissions"][1]["note"])
        self.assertEqual(self.session.character.model_dump(), sheet)
        self.post("release_possession", spirit="rose")
        self.post("release_possession", spirit="thorn")
        self.assertEqual(rules.view(self.session)["permissions"], [])
        self.assertEqual(self.session.character.model_dump(), sheet)

    def test_actual_diary_discovery_is_not_required_for_rose_host_and_never_grants_permanent_magic(self):
        self.allied()
        self.consent()
        self.assertFalse(self.session.strahd_progress.children.diary_found)
        self.assertTrue(rules.view(self.session)["permissions"][0]["active"])
        spells = list(self.session.character.known_spells)
        self.post("find_diary", actor_id="actual_second")
        self.assertEqual(self.session.strahd_progress.children.diary_holder_id, "actual_second")
        self.assertEqual(self.session.character.known_spells, spells)
        self.rejected(self.request("find_diary"))

    def test_ability_use_requires_current_available_host_source_ability_and_requirements_review(self):
        self.allied()
        self.consent("rose")
        self.rejected(self.request("use_ability", spirit="rose", spell="Mage Hand", spell_requirements_confirmed=True))
        self.rejected(self.request("use_ability", spirit="rose", spell="Light"))
        self.rejected(self.request("use_ability", actor_id="actual_second", spirit="rose", spell="Light", spell_requirements_confirmed=True))
        sheet = self.session.character.model_dump()
        self.post("use_ability", spirit="rose", spell="Mending", spell_requirements_confirmed=True)
        self.assertEqual(self.session.character.model_dump(), sheet)
        self.session.character.conditions = ["Unconscious"]
        self.assertFalse(rules.view(self.session)["permissions"][0]["active"])
        self.rejected(self.request("use_ability", spirit="rose", spell="Light", spell_requirements_confirmed=True))

    def test_absent_host_has_no_usable_permissions_and_does_not_duplicate_possession(self):
        self.allied()
        self.consent(actor_id="actual_second")
        self.session.character.companions = []
        self.assertFalse(rules.view(self.session)["permissions"][0]["active"])
        self.rejected(self.request("consent_possession", spirit="rose", friendly_host_confirmed=True,
            player_host_confirmed=True, host_consent_confirmed=True))
        self.post("release_possession", spirit="rose", reason="GM confirms the departed actual host released Rose.")
        self.consent()
        self.assertEqual(self.session.strahd_progress.children.spirits[0].host_id, self.session.character.id)

    def test_two_actual_remains_have_single_real_carriers_and_no_inventory_duplication(self):
        self.post()
        inventory = [item.model_dump() for item in self.session.character.inventory]
        self.post("take_remains", spirit="rose")
        self.rejected(self.request("take_remains", spirit="rose"))
        self.post("take_remains", spirit="thorn", actor_id="actual_second")
        self.post("transfer_remains", spirit="rose", actor_id="actual_second")
        self.assertTrue(all(item.carrier_id == "actual_second" for item in self.session.strahd_progress.children.spirits))
        self.rejected(self.request("transfer_remains", spirit="rose", actor_id="actual_second"))
        self.assertEqual([item.model_dump() for item in self.session.character.inventory], inventory)

    def test_dungeon_coffin_does_not_end_possession_or_bring_peace_and_can_be_retrieved(self):
        self.allied()
        self.consent()
        self.post("take_remains", spirit="rose")
        self.post("place_in_crypt", spirit="rose")
        state = self.session.strahd_progress.children
        self.assertFalse(state.at_peace)
        self.assertEqual(state.spirits[0].host_id, self.session.character.id)
        self.assertEqual(state.spirits[0].remains_location, "family_crypt")
        self.assertIn("does NOT bring peace", state.events[-1].effects[0])
        self.rejected(self.request("bury_children"))
        self.post("retrieve_remains", spirit="rose", actor_id="actual_second")
        self.assertEqual(self.session.strahd_progress.children.spirits[0].carrier_id, "actual_second")

    def test_actual_exit_ends_existing_possessions_readonly_preview_does_not(self):
        self.allied()
        self.consent("rose")
        self.consent("thorn", actor_id="actual_second")
        for action in ("start", "mound_destroyed"):
            clock.apply(self.session, DeathHouseRequest(event_id=f"exit_{action}", action=action,
                actual_event_confirmed=True, actor_ids=[self.session.character.id], reason="Actual reviewed event."))
        before = self.session.model_dump()
        payload = DeathHouseRequest(event_id="actual_exit", action="escaped", actual_event_confirmed=True,
            actor_ids=[self.session.character.id], reason="Actual party exit into Barovia.", expected_updated_at=self.session.updated_at).model_dump()
        response = self.client.post("/api/strahd/progress/death-house/quote", json=payload)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.session.model_dump(), before)
        response = self.client.post("/api/strahd/progress/death-house/event", json=payload)
        self.assertEqual(response.status_code, 200, response.text)
        state = self.session.strahd_progress.children
        self.assertTrue(all(item.host_id is None for item in state.spirits))
        self.assertEqual(state.events[-1].action, "house_exit")
        self.assertIn("actual_exit", state.events[-1].id)
        self.assertTrue(state.invited)
        self.assertFalse(state.at_peace)
        self.rejected(self.request("use_ability", spirit="rose", spell="Light", spell_requirements_confirmed=True))

    def test_outside_burial_needs_actual_exit_and_both_present_remains_then_once_only_peace(self):
        self.allied()
        self.consent()
        self.post("take_remains", spirit="rose")
        self.rejected(self.request("bury_children"))
        self.exit_house()
        self.rejected(self.request("bury_children"))
        self.rejected(self.request("take_remains", spirit="thorn"))

    def test_successful_burial_ends_all_aid_without_xp_healing_or_permanent_spell_changes(self):
        self.allied()
        self.consent("rose")
        self.post("take_remains", spirit="rose")
        self.post("take_remains", spirit="thorn", actor_id="actual_second")
        sheet = self.session.character.model_dump()
        self.exit_house()
        self.post("bury_children")
        state = self.session.strahd_progress.children
        self.assertTrue(state.at_peace)
        self.assertFalse(state.invited)
        self.assertTrue(all(item.remains_location == "buried_outside" for item in state.spirits))
        self.assertEqual(rules.view(self.session)["permissions"], [])
        self.assertEqual(self.session.character.model_dump(), sheet)
        self.assertEqual(self.session.strahd_progress.awards, [])
        self.assertEqual(self.session.strahd_progress.arc_reviews, [])
        self.rejected(self.request("bury_children"))
        self.rejected(self.request("consent_possession", spirit="rose", friendly_host_confirmed=True,
            player_host_confirmed=True, host_consent_confirmed=True))

    def test_leaving_without_burial_never_fakes_peace_or_spirits_following_into_barovia(self):
        self.allied()
        self.exit_house()
        self.post("leave_children")
        state = self.session.strahd_progress.children
        self.assertFalse(state.invited)
        self.assertFalse(state.at_peace)
        self.assertTrue(state.burial_promised)
        self.assertIn("will not proceed farther", ContextPipeline.strahd_progress_summary(self.session))

    def test_legacy_nested_state_defaults_unknown_and_preserves_real_earned_sheet(self):
        data = self.session.model_dump()
        data["strahd_progress"].pop("children")
        data["character"]["known_spells"].append("Mending")
        restored = GameSession.model_validate(data)
        self.assertFalse(restored.strahd_progress.children.met)
        self.assertEqual(restored.strahd_progress.children.events, [])
        self.assertIn("Mending", restored.character.known_spells)

    def test_save_load_and_chronicle_retain_real_host_carrier_consent_and_source(self):
        self.allied()
        self.consent("thorn", actor_id="actual_second", reason="Actual player consents to Thorn's friendly aid.")
        self.post("take_remains", spirit="rose")
        before = self.session.model_dump()
        text = ContextPipeline.strahd_progress_summary(self.session)
        for fact in ("Thorn", "Second actual PC", "Mage Hand", "spectral hand is invisible", "Actual player consents", "Children's Room; Family Crypts; Outside Death House"):
            self.assertIn(fact, text)
        self.assertEqual(self.session.model_dump(), before)
        with tempfile.TemporaryDirectory() as directory:
            manager = SaveManager(directory)
            loaded = manager.load_session(manager.save_session(self.session, "isolated_children"))
            chronicle = manager.export_markdown_chronicle(loaded)
        self.assertEqual(loaded.strahd_progress.children, self.session.strahd_progress.children)
        self.assertIn("Actual player consents", chronicle)
        self.assertIn("carrier Varis Holimion", chronicle)
        self.assertIn("Arc A - Escape From Death House.md", chronicle)
        self.assertNotIn("Do not invent hosts", chronicle)

    def test_wrong_campaign_and_active_encounter_reject_without_mutation(self):
        self.session.encounter = CombatEncounter(active=True)
        self.rejected(self.request())
        self.session.encounter = None
        self.session.id, self.session.source_folders = "other", ["minecraft"]
        self.rejected(self.request())


if __name__ == "__main__":
    unittest.main()
