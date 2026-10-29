import asyncio
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, patch
import zipfile

from fastapi.testclient import TestClient

from dungeonforge.api import routes
from dungeonforge.campaign.obsidian_loader import ObsidianCampaignLoader
from dungeonforge.game.engine import GameEngine
from dungeonforge.game.models import GameSession
from dungeonforge.game.saves import SaveManager
from dungeonforge.library import SourceLibrary
from dungeonforge.llm.base import LLMResponse
from dungeonforge.main import app


class LibraryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / "books"
        self.root.mkdir()
        self.library = SourceLibrary(self.root, Path(temporary.name) / "index.sqlite3")
        library_patch = patch("dungeonforge.library._library", self.library)
        library_patch.start()
        self.addCleanup(library_patch.stop)
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def write(self, relative, text):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def seed(self):
        self.write("2e/Classic.txt", "Spectral guardians use descending armor class and THAC0 in this edition.")
        self.write("5e/Core.txt", "Spectral guardians use ascending armor class and a proficiency bonus.")
        self.write("minecraft/Keep.txt", "Spectral guardians protect six lightning rods in the abandoned keep.")
        self.write("rick and morty/Rickedness.txt", "Spectral guardians guard Rick's laboratory and his secret cloning room.")
        self.write("star wars/WEG.txt", "Spectral guardians in this example roll a pool of six sided dice for Dexterity.")
        self.library.index()

    def test_discovery_pairs_ocr_with_pdf_and_ignores_download_artifacts(self):
        self.write("3.5e/Handbook.pdf", "PDF placeholder")
        self.write("3.5e/Handbook_text.pdf", "PDF placeholder")
        self.write("3.5e/Handbook_djvu.txt", "The handbook contains skill ranks and base attack bonuses for adventurers.")
        self.write("3.5e/Handbook_jp2.zip", "archive placeholder")
        self.write("3.5e/Handbook_daisy.zip", "archive placeholder")
        self.write("3.5e/.hidden/Secret.txt", "Must not be imported")
        self.write("3.5e/cache.dat", "Must not be imported")
        sources = self.library.discover()
        self.assertEqual(len(sources), 1)
        self.assertTrue(sources[0]["path"].endswith("_djvu.txt"))
        self.assertTrue(sources[0]["file_path"].endswith("Handbook.pdf"))
        self.library.index()
        self.assertEqual(len(self.library.search("skill ranks")), 1)

    def test_incremental_import_updates_without_duplicate_passages(self):
        path = self.write("5e/Rules.txt", "A unique silverflame ward protects the castle against spectral creatures.")
        self.library.index()
        with patch.object(self.library, "_read_sections", side_effect=AssertionError("Unchanged source was read")):
            self.library.index()
        self.assertEqual(len(self.library.search("silverflame")), 1)
        path.write_text("A unique goldenflame ward now protects the castle from all spectral creatures.", encoding="utf-8")
        self.library.index()
        self.assertEqual(self.library.search("silverflame"), [])
        self.assertEqual(len(self.library.search("goldenflame")), 1)

    def test_removed_sources_stop_contributing_to_context(self):
        path = self.write("5e/Rules.txt", "A unique silverflame ward protects the castle against spectral creatures.")
        self.library.index()
        path.unlink()
        self.library.index()
        self.assertEqual(self.library.search("silverflame"), [])

    def test_campaign_context_includes_matching_rules_and_excludes_other_settings(self):
        self.seed()
        matches = self.library.search("spectral guardians", edition="5e", campaign_folders=["minecraft"])
        self.assertEqual({match["folder_id"] for match in matches}, {"minecraft", "5e"})
        matches = self.library.search("spectral guardians", edition="2e", campaign_folders=["star_wars"])
        self.assertEqual({match["folder_id"] for match in matches}, {"star_wars", "2e"})
        self.assertEqual(self.library.search("Dexterity", edition="2e"), [])
        self.assertEqual(self.library.search("Dexterity", edition="weg_d6")[0]["folder_id"], "star_wars")

    def test_pdf_references_retain_page_numbers(self):
        self.write("5e/Rules.pdf", "placeholder")
        from types import SimpleNamespace
        pages = [SimpleNamespace(extract_text=lambda: ""), SimpleNamespace(extract_text=lambda: "The silverflame ward is an ancient protective spell found in this reference.")]
        with patch("pypdf.PdfReader", return_value=SimpleNamespace(pages=pages)):
            self.library.index()
        result = self.library.search("silverflame")[0]
        self.assertEqual(result["section"], "Page 2")
        self.assertEqual(self.library.catalog()["folders"][2]["sources"][0]["pages"], 2)

    def test_bad_source_is_reported_and_other_books_still_import(self):
        self.write("5e/Broken.pdf", "Not a PDF")
        self.write("5e/Readable.txt", "The silverflame ward is an ancient protective spell found in this reference.")
        self.library.index()
        sources = self.library.catalog()["folders"][2]["sources"]
        self.assertEqual({source["status"] for source in sources}, {"error", "indexed"})
        self.assertEqual(len(self.library.search("silverflame")), 1)

    def test_api_catalog_search_and_local_file_access(self):
        self.seed()
        catalog = self.client.get("/api/library")
        self.assertEqual(catalog.status_code, 200)
        self.assertEqual(len(catalog.json()["folders"]), 8)
        response = self.client.get("/api/library/search", params={"q": 'spectral " OR *', "folder_id": "minecraft"})
        self.assertEqual(response.status_code, 200)
        hits = response.json()["results"]
        self.assertEqual(len(hits), 1)
        self.assertEqual(self.client.get(hits[0]["file_url"]).status_code, 200)
        self.assertEqual(self.client.get("/api/library/sources/not-a-source/file").status_code, 404)
        self.assertEqual(self.client.post("/api/library/index", params={"folder_id": "../outside"}).status_code, 422)
        with self.assertRaises(ValueError):
            self.library.resolve("../outside.txt")

    def test_engine_uses_local_sources_and_keeps_citations_in_saves(self):
        self.seed()
        llm = AsyncMock()
        llm.generate.return_value = LLMResponse(text="The keep's spectral guardians await your next move.")
        session = GameSession(source_folders=["minecraft"])
        turn = asyncio.run(GameEngine(llm).execute_turn(session, "story", "spectral guardians"))
        prompt = "\n".join(message["content"] for message in llm.generate.call_args.args[0])
        self.assertIn("six lightning rods", prompt)
        self.assertNotIn("Rick's laboratory", prompt)
        self.assertTrue(turn.source_references)
        manager = SaveManager(str(self.root.parent / "saves"))
        slot = manager.save_session(session, "citations")
        loaded = manager.load_session(slot)
        self.assertEqual(loaded.source_folders, ["minecraft"])
        self.assertEqual(loaded.history[0].source_references, turn.source_references)

    def test_switch_campaign_clears_old_memory_and_labels_native_star_wars_rules(self):
        previous = GameSession()
        previous.memory.pinned_facts.append("An unrelated old campaign secret.")
        with patch.object(routes, "_ACTIVE_SESSION", previous):
            response = self.client.post("/api/campaign/switch/star_wars_2e")
            self.assertEqual(response.status_code, 200)
            session = response.json()["session"]
            self.assertEqual(session["source_folders"], ["star_wars"])
            self.assertIn("D6", session["source_rule_system"])
            self.assertIn("Native WEG", session["rules_note"])
            self.assertEqual(session["edition"], "weg_d6")
            self.assertIsNotNone(session["character"]["d6"])
            self.assertEqual(session["memory"]["pinned_facts"], [])
            active_id = routes._ACTIVE_SESSION.id
            self.assertEqual(self.client.post("/api/campaign/switch/not-a-campaign").status_code, 404)
            self.assertEqual(routes._ACTIVE_SESSION.id, active_id)

    def test_legacy_campaign_saves_get_correct_source_folder(self):
        import json
        manager = SaveManager(str(self.root.parent / "saves"))
        data = GameSession(id="session_rick_and_morty").model_dump()
        for key in ("source_folders", "source_rule_system", "rules_note"):
            data.pop(key)
        (Path(manager.saves_dir) / "legacy.json").write_text(json.dumps(data), encoding="utf-8")
        self.assertEqual(manager.load_session("legacy").source_folders, ["rick_and_morty"])

    def test_all_split_vaults_contribute_images_and_cards_have_unique_ids(self):
        folder = self.root / "curse of straud"
        folder.mkdir()
        one, two = folder / "part1.zip", folder / "part2.zip"
        with zipfile.ZipFile(one, "w") as archive:
            archive.writestr("vault/Act I/Arc A/Room.md", "# Room\n![[Guardian.png]]\n" + "An ancient guardian protects the abandoned keep. " * 3)
            archive.writestr("vault/Act II/Arc B/Room.md", "# Room\n" + "A different guardian protects the darkened tower. " * 3)
        with zipfile.ZipFile(two, "w") as archive:
            archive.writestr("vault/images/Guardian.png", b"example-image")
            archive.writestr("../outside.png", b"bad")
            archive.writestr("vault/.obsidian/plugin.js", "do not extract")
        destination = self.root.parent / "images"
        cards, quests = ObsidianCampaignLoader.load_from_archives([one, two], images_dir=destination)
        self.assertEqual(len(cards), 2)
        self.assertEqual(len({card.id for card in cards}), 2)
        self.assertTrue(cards[0].image_url.endswith("Guardian.png"))
        self.assertEqual((destination / "Guardian.png").read_bytes(), b"example-image")
        self.assertFalse((self.root.parent / "outside.png").exists())
        self.assertEqual(set(quests), {"Act I", "Act II"})

    def test_offline_narrator_follows_each_selected_campaign(self):
        from dungeonforge.campaign.campaign_manager import CampaignManager
        for campaign_id, anchor in (("minecraft_dnd", "lightning"), ("rick_and_morty", "rick"), ("marvel_5e", "manhattan"), ("star_wars_2e", "imperial")):
            for mode in ("story", "do", "say"):
                with self.subTest(campaign=campaign_id, mode=mode):
                    preset = CampaignManager.load_campaign(campaign_id)
                    session = GameSession(campaign_name=preset.title, source_folders=[preset.source_folder])
                    turn = asyncio.run(GameEngine().execute_turn(session, mode, "I look around."))
                    self.assertIn(anchor, turn.dm_output.lower())
                    self.assertNotIn("barovia", turn.dm_output.lower())


if __name__ == "__main__":
    unittest.main()
