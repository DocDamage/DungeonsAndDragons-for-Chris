"""Reloaded fresh starts follow the supplied guide without changing existing saves."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from fastapi.testclient import TestClient

from dungeonforge.api import routes
from dungeonforge.campaign.campaign_manager import CampaignManager
from dungeonforge.campaign.strahd import ACTS, ARCS, ARCHIVE, SOURCES, arc_sources, build_preset, quest_catalog
from dungeonforge.game.models import GameSession
from dungeonforge.game.saves import SaveManager
from dungeonforge.library import SourceLibrary
from dungeonforge.main import app
from dungeonforge.rules.base import Character, Companion, SpellSlot


class StrahdPresetTests(unittest.TestCase):
    def test_five_narrative_acts_include_every_source_arc_once(self):
        quests = quest_catalog()
        self.assertEqual(list(quests), list(ACTS))
        arc_titles = [title for titles in quests.values() for title in titles if title.startswith("Arc ")]
        self.assertEqual(len(arc_titles), 21)
        self.assertEqual(len(set(arc_titles)), 21)
        self.assertEqual([letter for letter, _, _ in ARCS], list("ABCDEFGHIJKLMNOPQRSTU"))
        self.assertFalse(any("Summary" in title for titles in quests.values() for title in titles))

    def test_source_specific_act_and_arc_placement_replaces_placeholder_outline(self):
        quests = quest_catalog()
        self.assertEqual(quests[ACTS[0]], ["Arc A - Escape From Death House", "Arc B - Welcome to Barovia", "Arc C - Into the Valley"])
        self.assertEqual(ACTS[1], "Act II: The Shadowed Town")
        self.assertIn("Arc I - The Walls of Krezk", quests[ACTS[1]])
        self.assertIn("Arc J - The Stolen Gem", quests[ACTS[2]])
        self.assertIn("Arc Q - A Shining Beacon", quests[ACTS[2]])
        self.assertEqual(quests[ACTS[3]], ["Arc R - Trials of the Mountain", "Arc S - A Sword of Sunlight", "Arc T - The Three Fanes"])
        self.assertEqual(quests[ACTS[4]], ["Arc U - Dreams of Dawn", "Epilogue"])

    def test_finale_provenance_preserves_archive_folder_while_using_summary_act_v(self):
        finale = next(item for item in arc_sources() if item["id"] == "U")
        self.assertEqual(finale["act"], "Act V: The Curse of Strahd")
        self.assertIn("Act IV - Secrets of the Ancient/Arc U - Dreams of Dawn.md", finale["path"])
        self.assertEqual(finale["archive"], ARCHIVE)

    def test_fresh_opening_starts_in_daggerford_before_death_house(self):
        preset = build_preset()
        self.assertIn("Daggerford", preset.initial_memory)
        self.assertIn("Nightmare's Bridle", preset.prologue_prompt)
        self.assertIn("Highharvesttide", preset.initial_memory)
        self.assertNotIn("Svalich Woods", preset.prologue_prompt)
        self.assertEqual(preset.starter_character.companions, [])
        self.assertIn("No campaign NPC has joined", preset.initial_memory)

    def test_level_two_ranger_uses_verified_2014_hp_slots_spells_and_saves(self):
        hero = build_preset().starter_character
        self.assertEqual((hero.class_name, hero.level, hero.current_hp, hero.max_hp), ("Ranger", 2, 20, 20))
        self.assertEqual((hero.spell_slots["1"].current, hero.spell_slots["1"].max_slots), (2, 2))
        self.assertEqual(hero.known_spells, ["Hunter's Mark", "Cure Wounds"])
        self.assertEqual(hero.proficiency_bonus, 2)
        self.assertEqual(set(hero.saving_throws), {"str", "dex"})
        self.assertEqual(hero.ac, 12 + hero.abilities.modifier("dex") + 1)
        self.assertIn("Defense fighting style", hero.notes)

    def test_sample_hero_is_one_actual_pc_and_five_pc_balance_is_explicit(self):
        preset = build_preset()
        self.assertEqual(len(preset.starter_character.companions), 0)
        self.assertIn("five 2nd-level player characters", preset.rules_note)
        self.assertIn("one actual PC", preset.rules_note)
        self.assertIn("encounter balance", preset.rules_note)

    def test_reloaded_precedence_and_2014_rules_are_explicit(self):
        preset = CampaignManager.load_campaign("strahd")
        self.assertEqual((preset.source_folder, preset.edition), ("strahd", "5e"))
        self.assertIn("2014", preset.source_rule_system)
        self.assertIn("Reloaded override", preset.rules_note)
        self.assertIn("only where the guide references", preset.rules_note)
        self.assertIn("GM tracked", preset.rules_note)
        self.assertEqual(SOURCES["ranger"], "5e/Player's Handbook.pdf, PDF pp.84–85 / printed pp.90–91")

    def test_alias_returns_same_source_setup(self):
        for id in ("strahd", "curse_of_strahd"):
            preset = CampaignManager.load_campaign(id)
            self.assertEqual(preset.id, "strahd")
            self.assertEqual(preset.starter_character.level, 2)
            self.assertEqual(len(preset.active_quests), 5)

    def test_preset_factory_returns_independent_mutable_collections(self):
        first, second = build_preset(), build_preset()
        first.starter_character.current_hp = 1
        first.starter_character.inventory.clear()
        first.active_quests[ACTS[0]].clear()
        first.story_cards[0].entry = "Player correction"
        self.assertEqual(second.starter_character.current_hp, 20)
        self.assertTrue(second.starter_character.inventory)
        self.assertEqual(len(second.active_quests[ACTS[0]]), 3)
        self.assertNotEqual(second.story_cards[0].entry, "Player correction")

    def test_other_campaigns_still_keep_their_own_native_setup(self):
        for id in ("rick_and_morty", "marvel", "minecraft", "star_wars_d6"):
            preset = CampaignManager.load_campaign(id)
            self.assertNotIn("Nightmare's Bridle", preset.prologue_prompt)
            self.assertNotEqual(preset.source_folder, "strahd")
        self.assertEqual(CampaignManager.load_campaign("star_wars_d6").edition, "weg_d6")

    def test_existing_level_three_party_save_is_preserved(self):
        previous = GameSession(id="session_strahd", character=Character(name="Existing hero", level=3,
            current_hp=28, max_hp=28, spell_slots={"1": SpellSlot(level=1, current=1, max_slots=3)},
            companions=[Companion(id="earned_ireena", name="Ireena Kolyana")]),
            active_quests={"Player campaign act": ["Player custom quest"]})
        previous.memory.pinned_facts.append("A prior player decision remains binding.")
        with tempfile.TemporaryDirectory() as directory:
            manager = SaveManager(directory)
            slot = manager.save_session(previous, "existing_campaign")
            build_preset()
            loaded = manager.load_session(slot)
        self.assertEqual(loaded.character, previous.character)
        self.assertEqual(loaded.character.level, 3)
        self.assertEqual(loaded.character.companions[0].id, "earned_ireena")
        self.assertEqual(loaded.active_quests, {"Player campaign act": ["Player custom quest"]})
        self.assertEqual(loaded.memory, previous.memory)


class StrahdSwitchTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        folder = self.root / "curse of straud"
        folder.mkdir()
        with ZipFile(folder / "Curse_of_Strahd_Reloaded_Part_1_of_3.zip", "w") as archive:
            archive.writestr("vault/Act I - Into the Mists/Act I Summary.md", "# Act I Summary\n" + "Actual source fixture for imported reference. " * 4)
            archive.writestr("vault/Act IV - Secrets of the Ancient/Arc U - Dreams of Dawn.md", "# Arc U\n" + "Actual finale source fixture for reference. " * 4)
        library = SourceLibrary(self.root, self.root / "library.sqlite3")
        library_patch = patch("dungeonforge.library._library", library)
        library_patch.start()
        self.addCleanup(library_patch.stop)
        self.previous = GameSession(character=Character(name="Existing player", level=7))
        self.previous.memory.pinned_facts.append("Existing campaign decision")
        active = patch.object(routes, "_ACTIVE_SESSION", self.previous)
        active.start()
        self.addCleanup(active.stop)
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def test_switch_keeps_canonical_five_acts_despite_raw_archive_folder_quests(self):
        response = self.client.post("/api/campaign/switch/strahd")
        self.assertEqual(response.status_code, 200, response.text)
        state = response.json()["session"]
        self.assertEqual(list(state["active_quests"]), list(ACTS))
        self.assertEqual(state["active_quests"][ACTS[-1]], ["Arc U - Dreams of Dawn", "Epilogue"])
        self.assertEqual(state["character"]["level"], 2)
        self.assertEqual(state["character"]["companions"], [])
        self.assertIn("Daggerford", state["history"][0]["dm_output"])
        self.assertIn("Daggerford", state["memory"]["front_memory"])
        self.assertGreater(len(state["story_cards"]), len(build_preset().story_cards))
        self.assertEqual(self.previous.character.level, 7)
        self.assertEqual(self.previous.memory.pinned_facts, ["Existing campaign decision"])

    def test_campaign_catalog_reports_five_acts_and_2014_source(self):
        response = self.client.get("/api/campaigns")
        self.assertEqual(response.status_code, 200, response.text)
        campaign = next(item for item in response.json()["campaigns"] if item["id"] == "strahd")
        self.assertEqual(campaign["acts_count"], 5)
        self.assertIn("2014", campaign["source_rule_system"])


class LocalStrahdSourceTests(unittest.TestCase):
    def test_catalog_references_match_the_supplied_local_vault(self):
        archive_path = Path(__file__).resolve().parents[2] / ARCHIVE
        if not archive_path.exists():
            self.skipTest("User-provided local Reloaded archive is not installed on this host.")
        with ZipFile(archive_path) as archive:
            names = set(archive.namelist())
            for item in arc_sources():
                self.assertIn(item["path"], names)
            opening = archive.read(SOURCES["opening"]).decode("utf-8-sig")
            self.assertIn("five 2nd-level characters", opening)
            self.assertIn("Daggerford", opening)
            structure = archive.read(SOURCES["structure"]).decode("utf-8-sig")
            self.assertIn("Act V: The Curse of Strahd", structure)


if __name__ == "__main__":
    unittest.main()
