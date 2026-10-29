"""1992 point-target grenades, plain-dice scatter and persistent round-end blasts."""
import math

from dungeonforge.rules.base import RuleEvaluationResult
from dungeonforge.rules.dice import DiceRoller, RollResult
from dungeonforge.rules.weg_d6 import D6Roller, RANGE_DIFFICULTIES, WEGD6Rules, parse_code
from dungeonforge.rules.weg_equipment import ITEMS
from dungeonforge.rules import weg_force_effects as effects
from dungeonforge.rules.weg_personal_equipment import armor_for_hit, apply_armor_damage, record_shot, refresh_armor
from dungeonforge.rules.weg_explosives_models import (
    D6BlastPoint, D6BlastVictim, D6GrenadeIntent, D6GrenadeRecord, D6GrenadeThrowRecord,
)


SOURCE = "WEG40055 (1992), printed pp.65–66, 156; PDF p.63 scatter diagram visually checked."
SUPPORTED = ("fragmentation_grenade", "thermal_detonator")
DIRECTIONS = {1: "forward", 2: "forward-right", 3: "right", 4: "back", 5: "left", 6: "forward-left"}
NOTES = [
    "Point-target fragmentation grenades and thermal detonators only; mines, scaled blasts, obstructed geometry and unknown bystanders require a separately resolved GM procedure.",
    "All actual encounter actors, including the whole party, need explicit GM positions. No invented occupants, positions, exclusions or automatic Dodge escape bonus.",
    "A miss scatters with plain 1D direction and plain 1D/2D/3D meters at point-blank/short, medium or long range.",
    "Contact detonates immediately. Timers use explicit ceil(seconds/5) round-end checkpoints; less than five seconds detonates at the end of the throwing round. Rethrowing never resets the fuse.",
    "Fuses due at the same coarse five-second boundary resolve in saved throw order, with one blast and immediate-injury reaction checkpoint before the next; these checkpoints add no elapsed rounds.",
    "The book leaves fractional blast meters and shared damage dice unspecified. The GM records up/down distance rounding and confirms independent damage rolls per affected actor.",
    "Tossing away requires an intent before landing, three actual declared actions in sequence (move, grab, throw), native alternating turns and an actual range check. No general movement or free escape is supplied here.",
    "Partial armor needs an actual hit location and side. Damage resistance uses free full Strength; every actual roll, point cost, injury and armor consequence is saved.",
]


def empty_roll(text):
    return RollResult(expression="0D", dice_count=0, die_type=6, total=0, system="weg_d6", breakdown=text)


def pending(encounter):
    return bool(encounter and any(grenade.status == "armed" for grenade in encounter.d6_explosives.grenades))


def roster(encounter):
    return {actor.id: actor for actor in encounter.combatants}


def distance(a, b):
    return math.hypot(a.x - b.x, a.y - b.y)


def actual_positions(encounter, *, validate_geometry=True):
    state = encounter.d6_explosives
    people = roster(encounter)
    if set(state.positions) != set(people) or not all((state.all_scene_actors_confirmed,
            state.same_plane_unobstructed_confirmed, state.independent_damage_rolls_confirmed)):
        raise ValueError("Review exhaustive actual actor positions, unobstructed same-plane geometry and the explicit damage-roll procedure first.")
    for actor in people.values():
        if actor.d6 is None:
            raise ValueError("Every actual blast actor needs a native D6 sheet; unspecified victims cannot be invented.")
        if not validate_geometry:
            continue
        if actor.cover_id and actor.cover_fraction != "none":
            cover = next((item for item in encounter.cover_objects if item.id == actor.cover_id), None)
            if cover and cover.damage_state != "destroyed":
                raise ValueError("Resolve the actual physical-cover/blast geometry before using the unobstructed grenade procedure.")
        armor = actor.armor
        partial = any(set(item.armor_locations) != {"head", "torso", "left_arm", "right_arm", "left_leg", "right_leg"}
            or set(item.armor_sides) != {"front", "back"} for item in armor)
        if partial and state.positions[actor.id].hit_location is None:
            raise ValueError(f"Record {actor.name}'s actual hit location and side for its partial armor.")
    return state, people


def review_positions(encounter, req):
    if pending(encounter):
        raise ValueError("A live grenade uses its saved positions. Only the declared toss-away approach can move an actor; free position edits cannot escape the blast.")
    ids = [position.actor_id for position in req.positions]
    if len(ids) != len(set(ids)) or set(ids) != set(roster(encounter)):
        raise ValueError("Supply each actual encounter actor exactly once, including every party member and actual bystander.")
    state = encounter.d6_explosives
    state.positions = {position.actor_id: position.model_copy(deep=True) for position in req.positions}
    state.position_round, state.position_reason = encounter.round, req.reason.strip()
    state.all_scene_actors_confirmed = req.all_scene_actors_confirmed
    state.same_plane_unobstructed_confirmed = req.same_plane_unobstructed_confirmed
    state.independent_damage_rolls_confirmed = req.independent_damage_rolls_confirmed
    state.distance_rounding = req.distance_rounding
    actual_positions(encounter)
    state.history.append({"operation": "GM position review", "round": encounter.round,
        "reason": req.reason.strip(), "positions": [position.model_dump() for position in req.positions], "distance_rounding": req.distance_rounding})


def acting(encounter, actor_id):
    from dungeonforge.game import weg_combat
    if getattr(encounter, "d6_round_closing", False):
        raise ValueError("Resolve the saved immediate injury reactions before starting another grenade action.")
    actor = weg_combat.actor(encounter, actor_id)
    weg_combat.validate_turn(encounter, actor)
    if actor.d6.round_state.full_defense or not actor.d6.can_act or actor.d6.round_state.actions_taken >= actor.d6.round_state.declared_actions:
        raise ValueError("This actor needs an actual unused declared action and must be able to act.")
    return actor


def action_done(encounter):
    encounter.d6_actions_started = encounter.d6_turn_acted = True


def declare_rethrow(encounter, req):
    if encounter.d6_actions_started:
        raise ValueError("Declare the toss-away intent before the action phase and before the grenade lands.")
    actor = roster(encounter).get(req.actor_id)
    if not actor or not actor.d6.can_act or actor.d6.round_state.declared_actions < 3 or actor.d6.round_state.actions_taken:
        raise ValueError("The actual actor must first declare at least three unused native actions for move, grab and throw.")
    if actor.d6.round_state.full_defense:
        raise ValueError("A full defense cannot also reserve a three-action toss-away.")
    if any(intent.actor_id == actor.id and intent.declared_round == encounter.round for intent in encounter.d6_explosives.intents):
        raise ValueError("This actor already has a saved toss-away intent this round.")
    intent = D6GrenadeIntent(actor_id=actor.id, declared_round=encounter.round, reason=req.reason.strip())
    encounter.d6_explosives.intents.append(intent)
    return intent


def band_for(ranges, meters):
    low, short, medium, long = ranges
    if meters > long:
        raise ValueError("The actual landing point is beyond the grenade's printed long range.")
    return "point_blank" if meters < low else "short" if meters <= short else "medium" if meters <= medium else "long"


def throw_facts(encounter, actor, catalog_id, req, origin, *, rethrow=False):
    meters = distance(origin, req.target)
    band = band_for(ITEMS[catalog_id]["item"]["d6_ranges"], meters)
    if req.visible_landing and req.unseen_modifier is not None or not req.visible_landing and req.unseen_modifier is None:
        raise ValueError("A visible point has no unseen modifier; an unseen landing point needs the actual +5 to +10 GM modifier.")
    if meters == 0 and (req.heading is None or distance(origin, req.heading) == 0):
        raise ValueError("A coincident target point needs an explicit distinct heading point for the scatter direction.")
    base = RANGE_DIFFICULTIES[band]
    if rethrow and req.throw_as_far:
        if not req.far_throw_ruling.strip() or req.lowered_difficulty is None or req.lowered_difficulty >= base:
            raise ValueError("For an as-far-as-possible toss, record the actual landing point, lower GM difficulty and ruling; a native roll is still required.")
        base = req.lowered_difficulty
    elif rethrow and (req.lowered_difficulty is not None or req.far_throw_ruling):
        raise ValueError("A normal specific-point toss uses its native range difficulty.")
    if actor.d6.origin.template_id == "protocol_droid":
        scatter_max = (1 if band in {"point_blank", "short"} else 2 if band == "medium" else 3) * 6
        radius = ITEMS[catalog_id]["blast_radius"][-1]
        for person in encounter.combatants:
            if person.d6.sentient and person.d6.wound != "dead" and distance(encounter.d6_explosives.positions[person.id].point, req.target) <= radius + scatter_max:
                raise ValueError("This Protocol Droid's life-preservation programming forbids a grenade throw that could injure an actual sentient, including a missed scatter.")
    return meters, band, base + (req.unseen_modifier or 0)


def scatter(origin, target, heading, band):
    direction = DiceRoller.roll("1d6")
    deviation = DiceRoller.roll(f"{1 if band in {'point_blank', 'short'} else 2 if band == 'medium' else 3}d6")
    aim = target if distance(origin, target) else heading
    length = distance(origin, aim)
    forward_x, forward_y = (aim.x - origin.x) / length, (aim.y - origin.y) / length
    right_x, right_y = forward_y, -forward_x
    forward, right = {1: (1, 0), 2: (1 / math.sqrt(2), 1 / math.sqrt(2)), 3: (0, 1),
        4: (-1, 0), 5: (0, -1), 6: (1 / math.sqrt(2), -1 / math.sqrt(2))}[direction.total]
    landing = D6BlastPoint(x=target.x + deviation.total * (forward * forward_x + right * right_x),
        y=target.y + deviation.total * (forward * forward_y + right * right_y))
    return direction, deviation, landing


def roll_throw(encounter, actor, catalog_id, req, origin, *, rethrow=False):
    meters, band, difficulty = throw_facts(encounter, actor, catalog_id, req, origin, rethrow=rethrow)
    result = WEGD6Rules.roll_skill(actor.d6, "grenade", difficulty, req.character_points, req.mishap)
    direction, deviation, landing = (None, None, req.target.model_copy(deep=True)) if result.success else scatter(origin, req.target, req.heading, band)
    saved = D6GrenadeThrowRecord(actor_id=actor.id, name=actor.name, round=encounter.round, origin=origin.model_copy(deep=True),
        target=req.target.model_copy(deep=True), distance=meters, range_band=band, difficulty=difficulty, roll=result.roll_result,
        success=result.success, character_points=req.character_points, force_point_active=actor.d6.round_state.force_active,
        scatter_direction=direction, scatter_distance=deviation, landing=landing, rethrow=rethrow, reason=req.reason.strip())
    saved.positions = {id: position.model_copy(deep=True) for id, position in encounter.d6_explosives.positions.items()}
    result.summary += f" Actual landing ({landing.x:g}, {landing.y:g})m." + (f" Plain scatter: {DIRECTIONS[direction.total]}, {deviation.total}m." if direction else "")
    action_done(encounter)
    return saved, result


def throw(encounter, req):
    state, _ = actual_positions(encounter)
    actor = acting(encounter, req.actor_id)
    weapon = actor.weapon
    if (weapon is None or weapon.id != req.item_id or not weapon.equipped or weapon.equipped_by != actor.id
            or weapon.quantity != 1 or weapon.ammo != 1 or weapon.catalog_id not in SUPPORTED
            or weapon.d6_skill != "grenade" or weapon.d6_scale != "character" or weapon.weapon_damage_state != "intact"):
        raise ValueError("Throw an actual assigned, drawn, intact single-use fragmentation grenade or thermal detonator; draw one physical grenade from a stack first.")
    origin = state.positions[actor.id].point
    saved, result = roll_throw(encounter, actor, weapon.catalog_id, req, origin)
    grenade = D6GrenadeRecord(item_id=weapon.id, catalog_id=weapon.catalog_id, name=weapon.name, source=SOURCE,
        created_round=encounter.round, trigger=req.trigger, timer_seconds=req.timer_seconds,
        due_round=encounter.round if req.trigger == "contact" else encounter.round + math.ceil(req.timer_seconds / 5) - 1,
        position=saved.landing.model_copy(deep=True), item_snapshot=weapon.model_dump(mode="json"), throws=[saved], reason=req.reason.strip(),
        distance_rounding=state.distance_rounding, position_reason=state.position_reason)
    state.grenades.append(grenade)
    record_shot(actor.d6, weapon)
    result.state_changes["grenade_id"] = grenade.id
    result.summary += f" {'Contact detonation now.' if req.trigger == 'contact' else f'Live timer due at end of round {grenade.due_round}; tossing never resets it.'}"
    if req.trigger == "contact":
        blast = detonate(encounter, grenade, encounter.round)
        result.state_changes["detonation"] = blast.state_changes
        result.state_changes["force_injury_targets"] = blast.state_changes["force_injury_targets"]
        result.summary += " " + blast.summary
    result.state_changes["grenade"] = grenade.model_dump(mode="json")
    return result


def live_grenade(encounter, id):
    grenade = next((item for item in encounter.d6_explosives.grenades if item.id == id), None)
    if not grenade or grenade.status != "armed" or grenade.trigger != "timer":
        raise ValueError("Choose an actual still-live timed grenade; contact/resolved explosions cannot be grabbed or rerolled.")
    if grenade.due_round < encounter.round:
        raise ValueError("This saved grenade is overdue; resolve its actual detonation before another toss action.")
    return grenade


def intent_for(encounter, actor, grenade, stage):
    intent = next((entry for entry in reversed(encounter.d6_explosives.intents)
        if entry.actor_id == actor.id and entry.stage == stage and (entry.grenade_id in {None, grenade.id})), None)
    if not intent or intent.declared_round > grenade.created_round or stage == "declared" and intent.declared_round != grenade.created_round:
        raise ValueError("Use the actual saved intent declared before this grenade landed, following move, grab and throw in order.")
    return intent


def approach(encounter, req):
    state, _ = actual_positions(encounter)
    actor = acting(encounter, req.actor_id)
    grenade = live_grenade(encounter, req.grenade_id)
    intent = intent_for(encounter, actor, grenade, "declared")
    if grenade.holder_id or not req.clear_path_confirmed or distance(state.positions[actor.id].point, grenade.position) > actor.d6.move:
        raise ValueError("Confirm a clear actual approach within one native Move to this unheld live grenade; this endpoint supplies no general movement or escape.")
    before = state.positions[actor.id].point.model_dump()
    state.positions[actor.id].point = grenade.position.model_copy(deep=True)
    effects.take_action(actor.d6)
    effects.settle_consciousness(actor.d6)
    intent.grenade_id, intent.stage = grenade.id, "approached"
    intent.actions.append({"operation": "move", "round": encounter.round, "from": before, "to": grenade.position.model_dump(), "reason": req.reason.strip()})
    action_done(encounter)
    return RuleEvaluationResult(action_type="grenade_toss", success=True, roll_result=empty_roll("Actual clear approach costs one declared action; no skill check is invented."),
        summary=f"{actor.name} spends actual toss-away action 1/3 moving to {grenade.name}; its timer remains end of round {grenade.due_round}.",
        state_changes={"grenade": grenade.model_dump(mode="json"), "intent": intent.model_dump(mode="json")})


def grab(encounter, req):
    state, _ = actual_positions(encounter)
    actor = acting(encounter, req.actor_id)
    grenade = live_grenade(encounter, req.grenade_id)
    intent = intent_for(encounter, actor, grenade, "approached")
    if grenade.holder_id or distance(state.positions[actor.id].point, grenade.position) > 1e-8:
        raise ValueError("The actual actor must first reach this unheld grenade's current saved position.")
    effects.take_action(actor.d6)
    effects.settle_consciousness(actor.d6)
    grenade.holder_id, intent.stage = actor.id, "grabbed"
    intent.actions.append({"operation": "grab", "round": encounter.round, "reason": req.reason.strip()})
    action_done(encounter)
    return RuleEvaluationResult(action_type="grenade_toss", success=True, roll_result=empty_roll("Actual grab costs one declared action; no skill check is invented."),
        summary=f"{actor.name} spends actual toss-away action 2/3 grabbing {grenade.name}; the live fuse is unchanged.",
        state_changes={"grenade": grenade.model_dump(mode="json"), "intent": intent.model_dump(mode="json")})


def rethrow(encounter, req):
    state, _ = actual_positions(encounter)
    actor = acting(encounter, req.actor_id)
    grenade = live_grenade(encounter, req.grenade_id)
    intent = intent_for(encounter, actor, grenade, "grabbed")
    if grenade.holder_id != actor.id:
        raise ValueError("The actor must actually hold the saved live grenade before the third throw action.")
    saved, result = roll_throw(encounter, actor, grenade.catalog_id, req, state.positions[actor.id].point, rethrow=True)
    grenade.throws.append(saved)
    grenade.position, grenade.holder_id, intent.stage = saved.landing.model_copy(deep=True), None, "thrown"
    intent.actions.append({"operation": "throw", "round": encounter.round, "throw_index": len(grenade.throws) - 1, "reason": req.reason.strip()})
    result.summary += f" Actual toss-away action 3/3; original fuse still ends in round {grenade.due_round}."
    result.state_changes["grenade_id"] = grenade.id
    result.state_changes["grenade"] = grenade.model_dump(mode="json")
    result.state_changes["intent"] = intent.model_dump(mode="json")
    return result


def blast_code(catalog_id, meters):
    entry = ITEMS[catalog_id]
    return next((code for high, code in zip(entry["blast_radius"][1:], entry["blast_damage"]) if meters <= high), None)


def detonate(encounter, grenade, completed_round):
    if grenade.status != "armed":
        raise ValueError("This actual grenade has already resolved; saved damage cannot be rerolled.")
    state, people = actual_positions(encounter, validate_geometry=False)
    for actor in people.values():
        position = state.positions[actor.id]
        actual_distance = distance(position.point, grenade.position)
        rounded = math.ceil(actual_distance) if grenade.distance_rounding == "up" else math.floor(actual_distance)
        damage = blast_code(grenade.catalog_id, rounded)
        before = actor.d6.wound
        victim = D6BlastVictim(actor_id=actor.id, name=actor.name, point=position.point.model_copy(deep=True),
            distance=actual_distance, blast_distance=rounded, affected=damage is not None, damage_code=damage,
            hit_location=position.hit_location, side=position.side, before=before, after=before)
        if damage is not None and before != "dead":
            if actor.cover_id and actor.cover_fraction != "none":
                cover = next((item for item in encounter.cover_objects if item.id == actor.cover_id), None)
                if cover and cover.damage_state != "destroyed":
                    victim.point_note = "Physical cover changed after the saved unobstructed review; no unreviewed blast attenuation or timer freeze was invented."
            requested = position.resistance_character_points
            points = requested if requested <= actor.d6.character_points and not (actor.d6.round_state.force_active or actor.d6.round_state.dark_side_called) else 0
            if requested and not points:
                victim.point_note += " Previously requested resistance CP are no longer available/legal; no points spent and the fuse is not frozen."
            armor_items = actor.armor
            if position.hit_location is None and armor_items:
                armor_items = [item for item in armor_items if set(item.armor_locations) == {"head", "torso", "left_arm", "right_arm", "left_leg", "right_leg"} and set(item.armor_sides) == {"front", "back"}]
                if len(armor_items) != len(actor.armor):
                    victim.point_note += " Newly added partial armor has no reviewed hit location; no blanket protection was invented and the fuse was not frozen."
            dice, pips = WEGD6Rules.resistance_pool(actor.d6, "physical", armor_items if actor.armor else None, position.hit_location, position.side)
            victim.damage_roll = WEGD6Rules.damage_roll(*parse_code(damage))
            if dice < 1:
                points = 0
            victim.resistance_roll = D6Roller.values(dice, pips, points) if dice else WEGD6Rules.damage_roll(0, pips)
            actor.d6.character_points -= points
            actor.d6.round_state.character_points_spent |= points > 0
            victim.character_points = points
            victim.margin = victim.damage_roll.total - victim.resistance_roll.total
            victim.injury = WEGD6Rules.apply_damage(actor.d6, victim.margin)
            victim.after = actor.d6.wound
            armor = armor_for_hit(armor_items, "physical", position.hit_location, position.side)
            victim.armor_damage = apply_armor_damage(armor, victim.injury)
            if actor.armor:
                refresh_armor(actor.d6, actor.armor)
            actor.is_defeated = actor.d6.out_of_fight
        grenade.victims.append(victim)
    grenade.status, grenade.resolved_round = "resolved", completed_round
    summary = f"[WEG Grenade Detonation] {grenade.name} at ({grenade.position.x:g}, {grenade.position.y:g})m, round {completed_round}. "
    summary += "; ".join(f"{victim.name}: {victim.distance:g}m → {victim.damage_code or 'outside blast'}, {victim.before} → {victim.after}" for victim in grenade.victims)
    return RuleEvaluationResult(action_type="explosion", success=True, roll_result=empty_roll("Actual per-victim damage and free Strength rolls are saved separately."),
        summary=summary, state_changes={"grenade_id": grenade.id, "victims": [victim.model_dump() for victim in grenade.victims],
            "grenade": grenade.model_dump(mode="json"),
            "force_injury_targets": [victim.actor_id for victim in grenade.victims if victim.margin is not None and victim.margin >= 4]})


def end_round(encounter, completed_round, *, limit=None):
    """Resolve saved throw order before clock reset; each result already applies damage.

    Combat calls limit=1 to permit an immediate-injury reaction checkpoint between
    blasts sharing the explicitly GM-approved coarse five-second boundary.
    """
    if limit is not None and (not isinstance(limit, int) or isinstance(limit, bool) or limit < 0):
        raise ValueError("The internal blast limit must be a nonnegative integer or None.")
    due = [grenade for grenade in encounter.d6_explosives.grenades if grenade.status == "armed" and grenade.due_round <= completed_round]
    if limit is not None:
        due = due[:limit]
    return [detonate(encounter, grenade, completed_round) for grenade in due]
