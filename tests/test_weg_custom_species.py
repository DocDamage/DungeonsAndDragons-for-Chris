import tempfile
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from pydantic import ValidationError

from dungeonforge.api import routes, weg_creation_routes as api
from dungeonforge.game.models import GameSession
from dungeonforge.game.saves import SaveManager
from dungeonforge.context.pipeline import ContextPipeline
from dungeonforge.context.story_cards import StoryCardManager
from dungeonforge.rules import weg_creation as creation, weg_advancement as advancement, weg_species
from dungeonforge.rules.weg_advancement_models import D6TrainingRequest
from dungeonforge.rules.weg_advancement_models import D6PowerGrant
from dungeonforge.rules.weg_templates import choose_starting_power, eligible_starting_powers
from dungeonforge.api import weg_template_routes as power_api
from dungeonforge.rules.weg_creation_models import D6CreationRequest
from dungeonforge.rules.weg_custom_species_models import D6CustomSpecies, SOURCE
from dungeonforge.rules.weg_models import ATTRIBUTES
from dungeonforge.rules.base import Companion


def species(**changes):
    return D6CustomSpecies(**{**dict(id="custom_tidefolk", name="Tidefolk", average_attribute_dice=11,
        minimums=dict.fromkeys(ATTRIBUTES, "2D"), maximums=dict.fromkeys(ATTRIBUTES, "4D"), move=9, move_maximum=14,
        concept="An original species approved for this campaign.", biology="Amphibious humanoids.", breathing_needs="Water breathers; approved breathing apparatus needed on land.",
        culture="Independent reef settlements with spaceflight.", special_abilities="GM resolves water adaptation in actual scenes; no automatic dice bonus.",
        disadvantages="Reduced average dice and breathing constraints.", story_factors="Rare visitors off-world.",
        gm_rationale="GM approves the reduced 11D average and all six limits as the balance tradeoff.", source="GM campaign species write-up, reviewed at creation."), **changes})


def request(**changes):
    return D6CreationRequest(**{**dict(name="Mira", occupation="Rebel scout", species_id="custom", custom_species=species(),
        attributes={**dict.fromkeys(ATTRIBUTES, "3D"), "knowledge": "2D"},
        skill_dice={"blaster": 2, "dodge": 2, "hide": 1, "first_aid": 1, "space_transports": 1},
        gm_approval="GM approves this template and actual starting equipment.", equipment=[], include_medic=False), **changes})


class CustomSpeciesRulesTests(unittest.TestCase):
    def test_variable_average_adds_exactly_six_player_dice_and_seven_skill_dice(self):
        hero, notes = creation.build(request())
        self.assertEqual(sum(creation.pips(code) for code in hero.d6.attributes.values()), 17 * 3)
        self.assertEqual((hero.d6.origin.attribute_budget, hero.d6.origin.skill_budget), (17, 7))
        self.assertEqual((hero.d6.move, hero.d6.move_maximum, hero.race, hero.d6.species_id), (9, 14, "Tidefolk", "custom_tidefolk"))
        self.assertTrue(any("11D + 6D" in note for note in notes))
        self.assertEqual((hero.d6.character_points, hero.d6.force_points, hero.d6.credits), (5, 1, 250))

    def test_force_skills_cost_actual_attribute_dice_and_still_require_background(self):
        attrs = {**dict.fromkeys(ATTRIBUTES, "2D"), "dexterity": "3D", "mechanical": "3D", "perception": "3D"}
        hero, _ = creation.build(request(attributes=attrs, force_skills=["control", "sense"], force_background="A qualified former Jedi taught these skills."))
        self.assertEqual((hero.d6.force_skills["control"], hero.d6.force_skills["sense"], hero.d6.force_points), ("1D", "1D", 2))
        self.assertEqual(sum(creation.pips(code) for code in attrs.values()) + 6, 17 * 3)
        with self.assertRaisesRegex(ValueError, "exactly 17D"):
            creation.build(request(force_skills=["control"], force_background="Teacher."))
        with self.assertRaisesRegex(ValueError, "plausible"):
            creation.build(request(attributes=attrs, force_skills=["control", "sense"]))

    def test_all_six_limits_are_real_constraints_and_budget_must_match(self):
        for changes in ({"attributes": {**request().attributes, "dexterity": "4D+1", "strength": "1D+2"}},
                        {"attributes": {**request().attributes, "dexterity": "2D+2"}},
                        {"attributes": {"dexterity": "17D"}}, {"skill_dice": {"blaster": 2}}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                creation.build(request(**changes))

    def test_one_to_five_dice_are_guidelines_not_hidden_hard_limits(self):
        record = species(minimums={**dict.fromkeys(ATTRIBUTES, "2D"), "dexterity": "0D"},
            maximums={**dict.fromkeys(ATTRIBUTES, "4D"), "dexterity": "6D"})
        hero, _ = creation.build(request(custom_species=record,
            attributes={"dexterity": "5D", "knowledge": "3D", "mechanical": "3D", "perception": "2D", "strength": "2D", "technical": "2D"}))
        self.assertEqual(hero.d6.attributes["dexterity"], "5D")
        self.assertEqual(hero.d6.species_attribute_maximums["dexterity"], "6D")

    def test_malformed_species_missing_bounds_or_unreviewed_designs_reject(self):
        cases = [{"minimums": {"dexterity": "2D"}}, {"maximums": {**dict.fromkeys(ATTRIBUTES, "4D"), "extra": "3D"}},
                 {"minimums": dict.fromkeys(ATTRIBUTES, "5D")}, {"maximums": dict.fromkeys(ATTRIBUTES, "2D")},
                 {"minimums": {**dict.fromkeys(ATTRIBUTES, "2D"), "strength": "3D+3"}},
                 {"average_attribute_dice": True}, {"average_attribute_dice": 11.5}, {"move": 15},
                 {"gm_rationale": "  "}, {"biology": ""}, {"source": ""}, {"creation_bonus_skills": ["hide"]}]
        for changes in cases:
            with self.subTest(changes=changes), self.assertRaises(ValidationError):
                species(**changes)

    def test_custom_identity_cannot_impersonate_printed_species_or_droid(self):
        with self.assertRaises(ValidationError):
            species(id="ewok")
        for changes in ({"species_id": "ewok"}, {"species_id": "human"}, {"droid_model": "r2"}, {"custom_species": None}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                creation.build(request(**changes))

    def test_prose_never_grants_bonus_dice_powers_equipment_or_species_aliases(self):
        hero, _ = creation.build(request(custom_species=species(id="custom_ewok", name="Ewok", special_abilities="+20D Hide; knows all Force powers; immune to vacuum.")))
        self.assertEqual(hero.d6.skills["hide"], "4D")
        self.assertEqual(weg_species.check_bonus(hero.d6, "search", "perception"), 0)
        self.assertEqual(hero.d6.force.known_powers, [])
        self.assertEqual(hero.inventory, [])
        self.assertEqual((hero.d6.armor_energy, hero.d6.armor_physical), ("0D", "0D"))

    def test_complete_origin_snapshot_is_independent_and_preserves_source_rationale(self):
        req = request()
        hero, _ = creation.build(req)
        self.assertEqual(hero.d6.origin.custom_species.model_dump(), req.custom_species.model_dump())
        self.assertIn(SOURCE, hero.d6.origin.source)
        self.assertEqual(hero.d6.species_attribute_maximums, req.custom_species.maximums)
        req.custom_species.name = "Changed draft"
        req.custom_species.maximums["strength"] = "1D"
        self.assertEqual(hero.d6.origin.custom_species.name, "Tidefolk")
        self.assertEqual(hero.d6.species_attribute_maximums["strength"], "4D")

    def test_saved_custom_maxima_drive_existing_native_advancement(self):
        hero, _ = creation.build(request(custom_species=species(maximums={**dict.fromkeys(ATTRIBUTES, "4D"), "dexterity": "5D+2"})))
        q = advancement.quote(hero.d6, D6TrainingRequest(kind="attribute", key="dexterity"), 1, race=hero.race)
        self.assertEqual((q.species_maximum, q.cp_cost), ("5D+2", 30))
        move = advancement.quote(hero.d6, D6TrainingRequest(kind="move"), 1, race=hero.race)
        self.assertEqual((move.old_code, move.new_code, move.cp_cost), ("9", "10", 9))
        hero.d6.move = 14
        with self.assertRaisesRegex(ValueError, "maximum"):
            advancement.quote(hero.d6, D6TrainingRequest(kind="move"), 1, race=hero.race)

    def test_ordinary_and_custom_species_births_save_only_unselected_earned_choices(self):
        human = D6CreationRequest(name="Human", occupation="Student", attributes={**dict.fromkeys(ATTRIBUTES, "3D"), "technical": "2D"},
            skill_dice={"blaster": 2, "dodge": 2, "search": 1, "first_aid": 1, "space_transports": 1},
            force_skills=["control"], force_background="Actual Jedi teacher.", powers=["control_pain"], gm_approval="Actual custom template approved.")
        for req in (human, request(attributes={**dict.fromkeys(ATTRIBUTES, "2D"), "dexterity": "4D", "mechanical": "4D"},
            force_skills=["control"], force_background="Actual teacher.", powers=["control_pain"])):
            with self.subTest(species=req.species_id):
                hero, _ = creation.build(req)
                grants = hero.d6.advancement.power_grants
                self.assertEqual(hero.d6.origin.starting_force_skills, ["control"])
                self.assertEqual(len(grants), 1)
                self.assertEqual((grants[0].remaining, grants[0].teacher_id, grants[0].project_id), (2, "starting:custom", f"origin:{hero.id}"))
                self.assertEqual(hero.d6.force.known_powers, ["control_pain"])
                self.assertEqual(hero.d6.force_skills["control"], "1D")
                self.assertEqual((hero.d6.character_points, hero.d6.force_points), (5, 2))

    def test_deferred_ordinary_choices_enforce_prerequisites_duplicates_and_preserve_paid_grants(self):
        hero, _ = creation.build(request(attributes={**dict.fromkeys(ATTRIBUTES, "2D"), "dexterity": "4D", "mechanical": "4D"},
            force_skills=["control"], force_background="Actual previous teacher."))
        grant = hero.d6.advancement.power_grants[0]
        paid = D6PowerGrant(skill="control", remaining=1, teacher_id="actual_paid_instructor", project_id="actual_paid_course", allowed_powers=["control_pain"])
        hero.d6.advancement.power_grants.append(paid)
        paid_before = paid.model_dump()
        before = hero.d6.model_dump()
        with self.assertRaises(ValueError):
            choose_starting_power(hero, grant.id, "reduce_injury")
        self.assertEqual(before, hero.d6.model_dump())
        choose_starting_power(hero, grant.id, "control_pain")
        self.assertEqual(grant.remaining, 2)
        self.assertIn("reduce_injury", eligible_starting_powers(hero, grant))
        before = hero.d6.model_dump()
        with self.assertRaises(ValueError):
            choose_starting_power(hero, grant.id, "control_pain")
        with self.assertRaises(ValueError):
            choose_starting_power(hero, paid.id, "accelerate_healing")
        self.assertEqual(before, hero.d6.model_dump())
        self.assertEqual(paid_before, paid.model_dump())
        hero.d6.force_skills["sense"] = "1D"
        later = D6PowerGrant(skill="sense", remaining=3, teacher_id="starting:custom", project_id=f"origin:{hero.id}", allowed_powers=["life_detection"])
        self.assertEqual(eligible_starting_powers(hero, later), [])

    def test_ordinary_starting_power_endpoint_uses_actual_origin_without_template_id(self):
        hero, _ = creation.build(request(attributes={**dict.fromkeys(ATTRIBUTES, "2D"), "dexterity": "4D", "mechanical": "4D"},
            force_skills=["control"], force_background="Actual previous teacher."))
        session = GameSession(edition="weg_d6", character=hero, source_folders=[])
        with patch.object(routes, "_ACTIVE_SESSION", session):
            state = power_api.state()
            self.assertEqual(state["actors"][0]["template_id"], "")
            self.assertEqual(state["actors"][0]["grants"][0]["remaining"], 3)
            from dungeonforge.rules.weg_templates import D6StartingPowerChoice
            result = power_api.power_choice(D6StartingPowerChoice(actor_id=hero.id,
                grant_id=hero.d6.advancement.power_grants[0].id, power_id="control_pain", reason="Actual earned ordinary starting choice.", expected_updated_at=session.updated_at))
        saved = result["session"].character.d6
        self.assertEqual(saved.advancement.power_grants[0].remaining, 2)
        self.assertEqual((saved.character_points, saved.force_points, saved.force_skills["control"]), (5, 2, "1D"))


class CustomSpeciesPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.session = GameSession(edition="weg_d6", character=creation.build(request())[0], source_folders=[])
        self.active = patch.object(routes, "_ACTIVE_SESSION", self.session)
        self.active.start()
        self.addCleanup(self.active.stop)

    def test_preview_is_readonly_recruit_retains_pc_and_typed_snapshot(self):
        before = self.session.model_dump()
        preview = api.preview(request(name="Recruit"))
        self.assertEqual(before, self.session.model_dump())
        self.assertEqual(preview["character"].d6.origin.custom_species.breathing_needs, species().breathing_needs)
        result = api.recruit(request(name="Recruit", expected_updated_at=self.session.updated_at))
        self.assertEqual(result["session"].character.id, self.session.character.id)
        self.assertEqual(result["session"].character.companions[-1].d6.origin.custom_species.name, "Tidefolk")
        with self.assertRaises(HTTPException):
            api.recruit(request(expected_updated_at=0))

    def test_species_record_and_advancement_limits_survive_save_load(self):
        with tempfile.TemporaryDirectory() as directory:
            manager = SaveManager(directory)
            restored = manager.load_session(manager.save_session(self.session, "custom_species"))
        self.assertEqual(restored.character.d6.model_dump(), self.session.character.d6.model_dump())
        self.assertEqual(restored.character.d6.origin.custom_species.gm_rationale, species().gm_rationale)
        self.assertEqual(restored.character.d6.move_maximum, 14)
        self.assertEqual(restored.character.d6.species_attribute_maximums, species().maximums)

    def test_start_backs_up_actual_old_species_record_before_new_birth(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(api, "SaveManager", lambda: SaveManager(directory)):
            result = api.start(request(name="New hero", expected_updated_at=self.session.updated_at))
            saved = SaveManager(directory).load_session(result["backup_slot"])
        self.assertEqual(saved.character.name, "Mira")
        self.assertEqual(saved.character.d6.origin.custom_species.model_dump(), species().model_dump())
        self.assertEqual(result["session"].character.name, "New hero")

    def test_custom_needs_rationale_and_limits_reach_prompt_and_chronicle_for_each_actor(self):
        hero, _ = creation.build(request(name="Custom companion"))
        self.session.character.companions.append(Companion(id=hero.id, name=hero.name, d6=hero.d6))
        before = self.session.model_dump()
        messages = ContextPipeline.assemble(character=self.session.character, memory=self.session.memory,
            story_card_manager=StoryCardManager(), authors_note=self.session.authors_note, history=[],
            current_input="Describe this alien party", current_mode="story")
        text = messages[1]["content"]
        self.assertIn("SAVED GM SPECIES — Custom companion", text)
        with tempfile.TemporaryDirectory() as directory:
            chronicle = SaveManager(directory).export_markdown_chronicle(self.session)
        for fact in (species().breathing_needs, species().gm_rationale, species().source, "dexterity 2D–4D", "Prose alone grants no automatic"):
            self.assertIn(fact, text)
            self.assertIn(fact, chronicle)
        self.assertIn("GM-defined species — Mira", chronicle)
        self.assertIn("GM-defined species — Custom companion", chronicle)
        self.assertEqual(before, self.session.model_dump())


if __name__ == "__main__":
    unittest.main()
