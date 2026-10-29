import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from fastapi.testclient import TestClient
from dungeonforge.main import app

client = TestClient(app)

print("=== 1. TEST SESSION INITIALIZATION ===")
res = client.get("/api/session")
assert res.status_code == 200, res.text
session = res.json()
char = session["character"]
print(f"Player: {char['name']} ({char['race']} {char['class_name']} Lvl {char['level']})")
assert len(char["companions"]) >= 2, "Companions missing"
print(f"Active Companions: {[c['name'] for c in char['companions']]}")
assert "1" in char["spell_slots"], "Spell slots missing"
print(f"Spell Slots Lvl 1: {char['spell_slots']['1']['current']}/{char['spell_slots']['1']['max_slots']}")
print(f"Known Spells: {char['known_spells']}")

print("\n=== 2. TEST SCENE ILLUSTRATION API ===")
res = client.post("/api/scene/illustrate", json={
    "prompt": "ancient vampire crypt with gargoyles and blood-red altar",
    "style_preset": "gothic horror fantasy oil painting"
})
assert res.status_code == 200, res.text
assert "pollinations.ai" in res.json()["image_url"]
print("Generated Scene Art URL:", res.json()["image_url"][:75] + "...")

print("\n=== 3. TEST SPELLCASTING & SPELL SLOTS ===")
# Cast Cure Wounds
res = client.post("/api/character/cast-spell", json={
    "spell_name": "Cure Wounds",
    "slot_level": 1
})
assert res.status_code == 200, res.text
data = res.json()
print("Spell Cast Turn:", data["turn"]["player_input"], "->", data["turn"]["dm_output"][:50] + "...")
print("Remaining Lvl 1 Slots:", data["slots_remaining"])
assert data["slots_remaining"] == 2, "Slot should have decremented from 3 to 2"

# Restore Spell Slots
res = client.post("/api/character/spell-slots/restore")
assert res.status_code == 200
assert res.json()["spell_slots"]["1"]["current"] == 3
print("Spell Slots Restored:", res.json()["spell_slots"]["1"]["current"])

# Learn and Unlearn Spell
res = client.post("/api/character/spells/learn", json={"spell_name": "Pass Without Trace"})
assert res.status_code == 200
assert "Pass Without Trace" in res.json()["known_spells"]
print("Learned new spell:", res.json()["known_spells"])

res = client.delete("/api/character/spells/Pass%20Without%20Trace")
assert res.status_code == 200
assert "Pass Without Trace" not in res.json()["known_spells"]
print("Unlearned spell successfully.")

print("\n=== 4. TEST PARTY COMPANIONS MANAGEMENT ===")
# Recruit new companion
res = client.post("/api/character/companions", json={
    "name": "Ezmerelda d'Avenir",
    "race": "Human",
    "class_name": "Monster Hunter",
    "level": 5,
    "current_hp": 45,
    "max_hp": 45,
    "ac": 16,
    "attack_name": "+1 Rapier",
    "damage": "1d8+4",
    "notes": "Protege of Rudolph van Richten."
})
assert res.status_code == 200
ez = res.json()["companion"]
print("Recruited:", ez["name"], f"(HP: {ez['current_hp']}/{ez['max_hp']}, AC: {ez['ac']})")

# Adjust companion HP
res = client.post(f"/api/character/companions/{ez['id']}/hp", json={"hp_change": -5})
assert res.status_code == 200
assert res.json()["companion"]["current_hp"] == 40
print(f"{ez['name']} took damage, HP now: {res.json()['companion']['current_hp']}")

# Dismiss companion
res = client.delete(f"/api/character/companions/{ez['id']}")
assert res.status_code == 200
print("Dismissed recruited companion.")

print("\n=== 5. TEST TACTICAL COMBAT WITH COMPANION STRIKE & SPELL ===")
res = client.post("/api/combat/start", json={
    "enemies": [{"name": "Strahd Zombie", "hp": 22, "ac": 8, "dex_mod": -2}]
})
assert res.status_code == 200
combat = res.json()["encounter"]
enemy = [c for c in combat["combatants"] if not c["is_player"]][0]
print("Ambush started against:", enemy["name"], f"(HP: {enemy['current_hp']}, AC: {enemy['ac']})")

# Ally Companion Strike
comp_id = session["character"]["companions"][0]["id"]
res = client.post("/api/combat/companion-attack", json={
    "companion_id": comp_id,
    "target_id": enemy["id"]
})
assert res.status_code == 200
print("Companion Attack Result:", res.json()["eval_result"]["summary"])

# Spell Strike in Combat
res = client.post("/api/character/cast-spell", json={
    "spell_name": "Hail of Thorns",
    "slot_level": 1,
    "target_id": enemy["id"]
})
assert res.status_code == 200
print("Combat Spell Cast Result:", res.json()["turn"]["dm_output"][:65] + "...")

print("\n=== 6. TEST SEE MODE ACTION ===")
res = client.post("/api/action", json={
    "mode": "see",
    "text": "the parapets of Castle Ravenloft under thunderstorm"
})
assert res.status_code == 200
turn = res.json()["turn"]
assert turn["image_url"] is not None, "See mode must generate image_url"
print("See Mode Action Turn image_url:", turn["image_url"][:75] + "...")

print("\n=== ALL VERIFICATION TESTS PASSED SUCCESSFULLY! ===")
