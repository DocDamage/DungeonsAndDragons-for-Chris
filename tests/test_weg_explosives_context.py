import tempfile
import unittest
from unittest.mock import patch

from dungeonforge.context.weg_explosives_context import native_explosives_summary
from dungeonforge.game import weg_combat
from dungeonforge.game.models import GameSession
from dungeonforge.game.saves import SaveManager
from dungeonforge.rules import weg_explosives as rules
from dungeonforge.rules.base import Character, Companion
from dungeonforge.rules.weg_d6 import D6Roller
from dungeonforge.rules.weg_explosives_models import D6GrenadeIntentRequest, D6GrenadeStepRequest
from tests import test_weg_explosives as fixture_module


class ExplosivesContextTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixture_module.ExplosiveTests()
        self.fixture.setUp()
        self.encounter = self.fixture.encounter
        self.fixture.ally.d6.round_state.declared_actions = 3
        rules.declare_rethrow(self.encounter, D6GrenadeIntentRequest(actor_id="ally", reason="Actual before-landing declaration.", expected_updated_at=1))
        self.grenade, _ = self.fixture.armed()
        weg_combat.next_turn(self.encounter)
        req = D6GrenadeStepRequest(actor_id="ally", grenade_id=self.grenade.id, clear_path_confirmed=True, reason="Actual paid clear approach and grab.", expected_updated_at=1)
        rules.approach(self.encounter, req)
        for _ in range(5):
            weg_combat.next_turn(self.encounter)
            if self.encounter.active_combatant.id == "ally":
                break
        rules.grab(self.encounter, req)
        character = Character(id="hero", name="Actual hero", edition="weg_d6", d6=self.fixture.hero.d6, inventory=[self.fixture.weapon],
            companions=[Companion(id="ally", name="Actual ally", d6=self.fixture.ally.d6)])
        self.session = GameSession(edition="weg_d6", character=character, encounter=self.encounter, source_folders=[])

    def resolved(self):
        with patch.object(D6Roller, "values", side_effect=fixture_module.native_roll):
            rules.end_round(self.encounter, 1)

    def test_pending_actual_positions_fuse_holder_and_paid_stages_are_readonly(self):
        before = self.session.model_dump()
        text = native_explosives_summary(self.session)
        for fact in ("NATIVE WEG GRENADES AND EXPLOSIONS", "actual live fuses 1", "status armed", "actual timer 4",
                     "original due end of round 1", "resolved round not resolved", "holder Actual ally",
                     "Actual blast position — Actual hero", "Actual blast position — Actual ally", "Actual blast position — Actual bystander",
                     "actual paid stages 2/3", "current stage grabbed", "Actual toss-away action: move", "Actual toss-away action: grab",
                     "ceil(seconds/5)", "fractional distance round up", "independent per-target", "printed pp.65–66, 156",
                     "Narration cannot invent positions or victims", "reset or freeze a fuse"):
            self.assertIn(fact, text)
        self.assertNotIn("Saved blast result", text)
        self.assertEqual(before, self.session.model_dump())

    def test_actual_miss_scatter_totals_and_complete_throw_snapshot_are_preserved(self):
        saved = self.grenade.throws[0]
        saved.success = False
        saved.scatter_direction = fixture_module.roll(6)
        saved.scatter_distance = fixture_module.roll(7, 2)
        text = native_explosives_summary(self.session)
        for fact in ("Saved initial throw 1", "success False", "direction 6 (forward-left)", "distance 2D total 7 meters",
                     "no Wild Die added", "Actual complete positions at this throw", "Actual hero [hero] (0, 0)m"):
            self.assertIn(fact, text)

    def test_resolved_per_victim_rolls_injury_and_armor_are_saved_facts(self):
        self.resolved()
        victim = next(victim for victim in self.grenade.victims if victim.actor_id == "ally")
        victim.armor_damage = {"name": "Actual source vest", "before": "intact", "after": "lightly_damaged"}
        victim.point_note = "Actual saved point ruling."
        before = self.session.model_dump()
        text = native_explosives_summary(self.session)
        for fact in ("actual live fuses 0", "status resolved", "resolved round 1", "Saved blast result — Actual ally",
                     "source damage 5D", "wound healthy → wounded", "Actual damage roll", "Actual free full-Strength resistance",
                     "Actual source vest", "lightly_damaged", "Actual saved point ruling", "Actual bystander", "outside blast"):
            self.assertIn(fact, text)
        self.assertEqual(before, self.session.model_dump())

    def test_native_archive_is_frozen_survives_save_load_and_remains_in_context(self):
        self.resolved()
        weg_combat.archive(self.session)
        self.assertEqual(len(self.session.d6_combat_history), 1)
        self.session.encounter = None
        frozen = self.session.d6_combat_history[0].model_dump()
        self.encounter.d6_explosives.grenades[0].reason = "Later mutable encounter text"
        with tempfile.TemporaryDirectory() as directory:
            manager = SaveManager(directory)
            restored = manager.load_session(manager.save_session(self.session, "explosives_archive"))
        self.assertEqual(restored.d6_combat_history[0].model_dump(), frozen)
        text = native_explosives_summary(restored)
        self.assertIn("archived; active False", text)
        self.assertIn("Saved blast result — Actual ally", text)
        self.assertNotIn("Later mutable encounter text", text)

    def test_current_encounter_overrides_duplicate_archive_by_actual_encounter_id(self):
        self.session.d6_combat_history.append(self.encounter.model_copy(deep=True))
        self.resolved()
        text = native_explosives_summary(self.session)
        self.assertEqual(text.count(f"Grenade encounter {self.encounter.id}:"), 1)
        self.assertEqual(text.count(f"Saved grenade {self.grenade.id}:"), 1)
        self.assertIn("current; active True", text)
        self.assertIn("status resolved", text)

    def test_empty_or_other_rules_have_no_native_grenade_claims(self):
        empty = GameSession(edition="weg_d6", character=self.session.character, source_folders=[])
        self.assertEqual(native_explosives_summary(empty), "")
        self.session.edition = "5e"
        self.assertEqual(native_explosives_summary(self.session), "")

    def test_export_mode_uses_actual_history_without_narrative_instruction_suffix(self):
        text = native_explosives_summary(self.session, guidance=False)
        self.assertIn("status armed", text)
        self.assertIn("original due end of round 1", text)
        self.assertNotIn("Only native grenade actions", text)


if __name__ == "__main__":
    unittest.main()
