"""Force lifecycle helpers shared by character and crew rules, without session globals."""


PAIN = {"control_pain", "control_another_pain"}


def find_effect(state, power_id, ready=True):
    return next((effect for effect in state.force.effects if effect.power_id == power_id and (not ready or effect.ready_in_rounds == 0)), None)


def pain(state, ready=True):
    return next((effect for effect in state.force.effects if effect.power_id in PAIN and (effect.recipient or effect.target_id in {None, effect.source_id}) and (not ready or effect.ready_in_rounds == 0)), None)


def sleeping(state):
    return any(effect.power_id in {"hibernation_trance", "transfer_force", "emptiness"} and (effect.recipient or effect.target_id in {None, effect.source_id}) for effect in state.force.effects)


def preparing(state):
    return state.force.attempt is not None and state.force.attempt.preparation_remaining > 0


def upkeep(state):
    return sum(len(effect.skills) for effect in state.force.effects if effect.maintained and not effect.recipient and not effect.activation_round)


def force_bonus(state):
    return max(0, 6 - state.dark_side_points) if find_effect(state, "emptiness_bonus") else 0


def can_act(state):
    if state.corruption.pending_demand or state.corruption.dead:
        return False
    if state.wound == "dead" or sleeping(state) or preparing(state) or state.force.remain_pending or state.round_state.blocked:
        return False
    if pain(state):
        return True
    if state.force.remain_actions == 0:
        return False
    return (state.wound in {"healthy", "wounded"} and state.unconscious_rounds == 0) or (state.force.remain_actions is not None and state.force.remain_actions > 0)


def can_take_turn(state):
    if state.corruption.pending_demand or state.corruption.dead:
        return False
    return can_act(state) or (state.wound != "dead" and not state.round_state.blocked and not sleeping(state) and (state.force.remain_pending or preparing(state)))


def out_of_fight(state):
    if state.wound == "dead":
        return True
    if sleeping(state):
        return True
    protected = state.force.remain_pending or state.force.remain_actions is not None or pain(state, ready=False)
    return not protected and (state.wound in {"incapacitated", "mortally_wounded"} or state.unconscious_rounds > 0)


def settle_consciousness(state):
    if pain(state):
        state.force.remain_actions = None
        state.force.remain_pending = False
    elif state.force.remain_actions == 0 and not pain(state, ready=False):
        state.force.remain_actions = None


def take_action(state):
    state.combat_preparation = None
    state.round_state.actions_taken += 1
    if state.force.remain_actions is not None:
        state.force.remain_actions = max(0, state.force.remain_actions - 1)


def finalize_failure(state):
    attempt = state.force.attempt
    if attempt and attempt.failed:
        if attempt.power_id == "lightsaber_combat" and attempt.parameters.get("_in_combat"):
            state.force.saber_locked = True
        if attempt.power_id == "remain_conscious":
            state.force.remain_pending = False
        state.force.attempt = None


def cancel_attempt(state):
    if state.force.attempt and state.force.attempt.power_id == "remain_conscious":
        state.force.remain_pending = False
    finalize_failure(state)
    state.force.attempt = None


def drop_on_injury(state):
    state.combat_preparation = None
    for effect in state.force.effects:
        if effect.power_id == "emptiness" and state.wound != "healthy":
            effect.parameters["injury_exit"] = True
    state.force.effects = [effect for effect in state.force.effects if not effect.maintained and effect.power_id not in {"lightsaber_combat", "control_pain", "control_another_pain", "transfer_force", "hibernation_trance"}]
    cancel_attempt(state)
    state.force.remain_actions = None
    if state.round_state.defense_skill == "lightsaber":
        state.round_state.defense_skill = None
        state.round_state.defense_total = None


def injury_reactions(state, severe_injury=False):
    state.force.reduce_injury_available = severe_injury and state.wound in {"incapacitated", "mortally_wounded", "dead"} and "reduce_injury" in state.force.known_powers
    state.force.remain_pending = state.wound != "dead" and (state.wound in {"incapacitated", "mortally_wounded"} or state.unconscious_rounds > 0) and "remain_conscious" in state.force.known_powers


def skip_turn(state):
    state.combat_preparation = None
    if preparing(state):
        cancel_attempt(state)
    if state.force.remain_pending:
        state.force.remain_pending = False


def tick(state, rounds=1):
    state.force.elapsed_rounds += rounds
    state.force.reduce_injury_available = False
    attempt = state.force.attempt
    if attempt:
        if attempt.failed:
            finalize_failure(state)
        elif attempt.preparation_remaining:
            if attempt.preparation_committed:
                attempt.preparation_remaining = max(0, attempt.preparation_remaining - rounds)
                attempt.preparation_committed = False
            else:
                state.force.attempt = None
        elif attempt.rolls and state.force.elapsed_rounds > attempt.parameters.get("_last_component_round", state.force.elapsed_rounds) + 1:
            state.force.attempt = None
    for effect in state.force.effects:
        effect.activation_round = False
        effect.ready_in_rounds = max(0, effect.ready_in_rounds - rounds)
        if effect.rounds_remaining is not None:
            effect.rounds_remaining = max(0, effect.rounds_remaining - rounds)
        if effect.power_id == "emptiness":
            effect.parameters["meditated_rounds"] = effect.parameters.get("meditated_rounds", 0) + rounds
    state.force.effects = [effect for effect in state.force.effects if effect.rounds_remaining is None or effect.rounds_remaining > 0]
    if state.force.remain_actions is not None and not pain(state, ready=False):
        state.force.remain_actions = None
    day = state.force.elapsed_rounds // 17280
    if state.force.healing_day != day:
        state.force.healing_rolls_remaining = state.force.healing_rolls_used = 0
    settle_consciousness(state)
