"""Rapid actions must retain separate narrative cards and edit targets."""

import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from dungeonforge.api import routes
from dungeonforge.game.models import GameSession
from dungeonforge.main import app
from dungeonforge.rules.base import Character, Item, SpellSlot


class TurnIdentityTests(unittest.TestCase):
    def setUp(self):
        self.session = GameSession(character=Character(
            current_hp=1,
            max_hp=50,
            known_spells=["Cure Wounds"],
            spell_slots={"1": SpellSlot(level=1, current=3, max_slots=3)},
            inventory=[Item(name="Potion of Healing", quantity=2, item_type="potion")],
        ))
        self.session_patch = patch.object(routes, "_ACTIVE_SESSION", self.session)
        self.session_patch.start()
        self.addCleanup(self.session_patch.stop)
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def test_same_second_spells_have_independent_edit_targets(self):
        with patch("dungeonforge.api.routes.time.time", return_value=1234567890):
            first = self.client.post("/api/character/cast-spell", json={"spell_name": "Cure Wounds"})
            second = self.client.post("/api/character/cast-spell", json={"spell_name": "Cure Wounds"})
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        first_turn, second_turn = first.json()["turn"], second.json()["turn"]
        self.assertEqual(first_turn["timestamp"], second_turn["timestamp"])
        self.assertNotEqual(first_turn["id"], second_turn["id"])
        response = self.client.post("/api/turn/alter", json={
            "turn_id": second_turn["id"], "new_text": "Only the second spell changed.",
        })
        self.assertEqual(response.status_code, 200)
        turns = response.json()["session"]["history"]
        self.assertEqual(turns[0]["dm_output"], first_turn["dm_output"])
        self.assertEqual(turns[1]["dm_output"], "Only the second spell changed.")
        self.assertEqual(self.session.character.spell_slots["1"].current, 1)

    def test_same_second_item_uses_have_unique_turn_ids(self):
        with patch("dungeonforge.api.routes.time.time", return_value=1234567890):
            first = self.client.post("/api/character/use-item", params={"item_name": "Potion of Healing"})
            second = self.client.post("/api/character/use-item", params={"item_name": "Potion of Healing"})
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        history = second.json()["session"]["history"]
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0]["timestamp"], history[1]["timestamp"])
        self.assertNotEqual(history[0]["id"], history[1]["id"])
        self.assertEqual(self.session.character.inventory, [])


if __name__ == "__main__":
    unittest.main()
