import { useState } from 'react';
import type { Character, CombatEncounter, D6BoostWindow, GameSession } from '../../types';
import { api } from '../../services/api';
import './D6.css';

const title = (value: string) => value.replaceAll('_', ' ');

export function D6Sidebar({ character, encounter, selectedTargetId, onEdit, onSessionChanged, boost, vehicleCombatActive = false }: {
  character: Character;
  encounter?: CombatEncounter | null;
  selectedTargetId: string | null;
  onEdit: () => void;
  onSessionChanged: (session: GameSession) => void;
  boost?: D6BoostWindow | null;
  vehicleCombatActive?: boolean;
}) {
  const state = character.d6!;
  const painControlled = state.force?.effects.some(effect => ['control_pain', 'control_another_pain'].includes(effect.power_id) && !effect.ready_in_rounds && (effect.recipient || effect.target_id === effect.source_id));
  const upkeep = state.force?.effects.filter(effect => effect.maintained && !effect.recipient && !effect.activation_round).reduce((total, effect) => total + effect.skills.length, 0) ?? 0;
  const combat = encounter?.active ? encounter : null;
  const [skill, setSkill] = useState('astrogation');
  const [difficulty, setDifficulty] = useState(10);
  const [cp, setCp] = useState(0);
  const [mishap, setMishap] = useState<'penalty' | 'complication'>('penalty');
  const [sceneForce, setSceneForce] = useState(false);
  const [actions, setActions] = useState(1);
  const [actorId, setActorId] = useState('');
  const [force, setForce] = useState(false);
  const [defense, setDefense] = useState('dodge');
  const [full, setFull] = useState(false);
  const [useRoll, setUseRoll] = useState(true);
  const [healer, setHealer] = useState(character.id);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const actor = combat?.combatants.find(person => person.id === actorId) ?? combat?.combatants.find(person => person.id === character.id);
  const current = combat?.combatants[combat.current_turn_index];
  const canCheck = !vehicleCombatActive && (!combat || (current?.id === character.id && !combat.d6_turn_acted));
  const skills = [...new Set([...Object.keys(state.attributes), ...Object.keys(state.skills), 'sneak', 'search', 'dodge', 'bargain', 'con', 'first_aid', 'astrogation', 'space_transports', 'computer_programming_repair', 'control', 'sense', 'alter'])];

  async function run(request: () => Promise<{ session: GameSession }>) {
    if (pending) return;
    setPending(true);
    setError(null);
    try { onSessionChanged((await request()).session); }
    catch (err) { setError(err instanceof Error ? err.message : 'Native D6 action failed'); }
    finally { setPending(false); }
  }

  return <aside className="panel-sidebar native-sheet" aria-label="Native WEG D6 character sheet">
    <div className="native-sheet-heading"><div><h2>{character.name}</h2><p>{character.race} · {character.class_name}</p></div><button className="hp-btn" onClick={onEdit} disabled={vehicleCombatActive}>Edit D6 sheet</button></div>
    <div className="native-sheet-scroll">
      {error && <p className="native-error" role="alert">{error}</p>}
      <section className="native-status" aria-label="Native wound state">
        <strong>{state.droid ? `Chassis: ${state.droid.destroyed ? 'Destroyed' : ({ healthy: 'Operational', wounded: 'Lightly damaged', incapacitated: 'Heavily damaged', mortally_wounded: 'Severely damaged', dead: 'Nearly obliterated' })[state.wound]}` : `Wound: ${title(state.wound)}`}</strong>
        <span>Stuns: {state.stun_count} · Injury/stun penalties: −{painControlled ? 0 : state.stun_durations.length + (state.wound === 'wounded' ? 1 : 0)}D{painControlled ? ' · pain controlled' : ''}</span>
        {state.unconscious_rounds > 0 && !painControlled && state.force?.remain_actions == null && !state.force?.remain_pending && <span>Unconscious: {state.unconscious_rounds} rounds remaining</span>}
        {!!state.force?.known_powers.length && <span>Learned powers: {state.force.known_powers.length} · Upkeep: −{upkeep}D</span>}
        <span>Armor: energy +{state.armor_energy} · physical +{state.armor_physical}</span>
        <span>{state.credits} credits · {state.force_sensitive ? 'Force sensitive' : 'Not Force sensitive'}</span>
        <span>Move: {state.move ?? 10}m</span>
        {state.force?.dark_side_consumed && <strong className="native-error">Consumed · {state.corruption?.control_mode === 'redemption' ? `redemption arc until boundary ${state.corruption.redemption_deadline}` : 'GM controlled'}</strong>}
        {state.corruption?.atonement && <span>Atonement: {state.corruption.atonement.consecutive}/2 approved adventures</span>}
        {state.corruption?.pending_demand && <strong className="native-error">Unpaid Dark Side demand · actions blocked</strong>}
        {state.advancement?.project && <span>Training {title(state.advancement.project.quote.key)} · {state.advancement.project.days_completed}/{state.advancement.project.quote.days} days</span>}
      </section>
      <div className="native-resources"><span>CP <strong>{state.character_points}</strong></span><span>Force <strong>{state.force_points}</strong></span><span>Dark Side <strong>{state.dark_side_points}</strong></span></div>
      <div className="native-attributes">{Object.entries(state.attributes).map(([name, code]) => <div key={name}><span>{name}</span><strong>{code}</strong></div>)}</div>
      <details><summary>Skills & Force training</summary><ul>{Object.entries({ ...state.skills, ...state.force_skills }).map(([name, code]) => <li key={name}>{title(name)} <strong>{code}</strong></li>)}</ul></details>
      <section>
        {vehicleCombatActive && <p className="native-help">Use the vehicle encounter crew stations for actions and points. End the craft encounter before personal checks or recovery.</p>}
        <h3>{combat ? 'Skill action' : 'Scene skill check'}</h3>
        <form onSubmit={event => { event.preventDefault(); void run(async () => {
          const response = await api.nativeCheck({ skill, difficulty, character_points: cp, force_point: combat ? false : sceneForce, mishap });
          setSceneForce(false);
          setCp(0);
          return response;
        }); }}>
          <label>Skill or attribute<input list="native-skill-list" value={skill} onChange={event => setSkill(event.target.value)} required /></label>
          <datalist id="native-skill-list">{skills.map(name => <option key={name} value={name} />)}</datalist>
          <div className="native-form-row"><label>Difficulty<input type="number" min={1} max={1000} value={difficulty} onChange={event => setDifficulty(Number(event.target.value))} required /></label><label>Character Points<input type="number" min={0} max={5} value={cp} onChange={event => setCp(Number(event.target.value))} required /></label></div>
          <p className="native-help">Very Easy 1–5 · Easy 6–10 · Moderate 11–15 · Difficult 16–20 · Very Difficult 21–30 · Heroic 31+</p>
          <label>Wild 1 handling<select value={mishap} onChange={event => setMishap(event.target.value as 'penalty' | 'complication')}><option value="penalty">Discard Wild + highest die</option><option value="complication">Discard Wild; GM complication</option></select></label>
          {!combat && <label className="native-checkbox"><input type="checkbox" checked={sceneForce} onChange={event => setSceneForce(event.target.checked)} />Spend a Force Point for this check</label>}
          <button className="send-btn" disabled={pending || !canCheck}>Roll native check</button>
        </form>
        {boost && <div className="native-status" style={{ marginTop: 10 }}>
          <strong>Last roll: {boost.total} · {title(boost.skill)}</strong>
          <span>{boost.points_spent}/{boost.limit} Character Points used on this roll</span>
          {boost.force_used ? <p className="native-help">Force Point used; Character Points cannot be added.</p> : <div className="native-button-row">
            {[1, 2].map(points => <button key={points} className="hp-btn" disabled={pending || boost.points_spent + points > boost.limit} onClick={() => run(() => api.nativeBoost(points))}>Add {points} CP to last roll</button>)}
          </div>}
          <p className="native-help">Add points before another roll or advancing the action.</p>
        </div>}
      </section>
      {combat && <section>
        <h3>Round {combat.round} declarations</h3><p className="native-help">{combat.d6_actions_started ? 'Action phase. New declarations open next round.' : 'Declare all actions and defenses before the action phase.'}</p>
        <label>Declare for<select value={actor?.id ?? character.id} onChange={event => setActorId(event.target.value)}>{combat.combatants.map(person => <option key={person.id} value={person.id}>{person.name}</option>)}</select></label>
        <p className="native-help">Used {actor?.d6?.round_state.actions_taken ?? 0} / {actor?.d6?.round_state.declared_actions ?? 1} · {actor?.d6?.round_state.force_active ? 'Force Point active' : `${actor?.d6?.force_points ?? 0} Force Points available`}{actor?.d6?.round_state.dark_side_called ? ` · Dark Side call${actor.d6.round_state.dark_side_active ? ' active' : ' failed'}; CP dice forbidden` : ''}</p>
        <label>Declared actions<input type="number" min={1} max={10} value={actions} onChange={event => setActions(Number(event.target.value))} /></label>
        <label className="native-checkbox"><input type="checkbox" checked={force} onChange={event => setForce(event.target.checked)} />Spend Force Point for the round</label>
        <button className="hp-btn" disabled={pending || combat.d6_actions_started} onClick={() => run(async () => {
          const response = await api.nativeDeclare({ actor_id: actor?.id, actions, force_point: force });
          setForce(false);
          return response;
        })}>Declare round</button>
        <label>Defensive skill<select value={defense} onChange={event => setDefense(event.target.value)}><option value="dodge">Dodge</option><option value="melee_parry">Melee parry</option><option value="brawling_parry">Brawling parry</option><option value="lightsaber">Lightsaber parry</option></select></label>
        <label className="native-checkbox"><input type="checkbox" checked={full} onChange={event => setFull(event.target.checked)} />Full defense (only one skill action)</label>
        {!full && <label className="native-checkbox"><input type="checkbox" checked={useRoll} onChange={event => setUseRoll(event.target.checked)} />Use rolled defense instead of base difficulty</label>}
        <button className="hp-btn" disabled={pending || combat.d6_actions_started} onClick={() => run(() => api.nativeDefend({ actor_id: actor?.id, skill: defense, full, use_roll: useRoll, character_points: cp }))}>Roll defense</button>
        <div className="native-button-row"><button className="hp-btn" disabled={pending || combat.d6_actions_started} onClick={() => run(() => api.nativeInitiative(true))}>Winner acts first</button><button className="hp-btn" disabled={pending || combat.d6_actions_started} onClick={() => run(() => api.nativeInitiative(false))}>Winner acts last</button></div>
      </section>}
      {!combat && !vehicleCombatActive && <section><h3>Recovery</h3><p className="native-help">{state.droid ? 'Use Droid programming & repairs for chassis damage. Rest clears temporary stuns; medpacs and natural healing do not repair a Droid.' : 'A minute clears stuns. Wounds need first aid or days of complete rest. Points do not regenerate on rest.'}</p>
        <div className="native-button-row"><button className="hp-btn" disabled={pending} onClick={() => run(() => api.nativeRecover({ method: 'rest' }))}>Rest 1 minute</button><button className="hp-btn" disabled={pending} onClick={() => run(() => api.nativeRecover({ method: 'rest', minutes: 1440 }))}>Rest 24 hours</button></div>
        <label>Medpac healer<select value={healer} onChange={event => setHealer(event.target.value)}><option value={character.id}>{character.name} (self: −1D)</option>{character.companions?.filter(comp => comp.d6).map(comp => <option key={comp.id} value={comp.id}>{comp.name}</option>)}</select></label>
        <button className="hp-btn" disabled={pending || !!state.droid} onClick={() => run(() => api.nativeRecover({ method: 'medpac', healer_id: healer }))}>Use medpac</button>
        {state.wound !== 'healthy' && state.wound !== 'dead' && <button className="hp-btn" disabled={pending} onClick={() => run(() => api.nativeRecover({ method: 'natural', days: { wounded: 3, incapacitated: 14, mortally_wounded: 30 }[state.wound as 'wounded' | 'incapacitated' | 'mortally_wounded'] }))}>Rest & roll natural healing ({state.wound === 'wounded' ? 3 : state.wound === 'incapacitated' ? 14 : 30} days)</button>}
      </section>}
      <section><h3>Equipment</h3><ul>{character.inventory.map((item, index) => <li key={`${item.name}-${index}`}>{item.name} ×{item.quantity} {item.damage && <strong>{item.damage}</strong>}</li>)}</ul></section>
      <section><h3>Crew</h3>{character.companions?.map(comp => <div key={comp.id} className="native-crew"><span>{comp.name} · {title(comp.d6?.wound ?? 'no native sheet')}</span>{combat && <button className="hp-btn" disabled={pending || current?.id !== comp.id || !selectedTargetId || combat.d6_turn_acted || comp.d6?.round_state.blocked} onClick={() => run(() => api.companionAttack({ companion_id: comp.id, target_id: selectedTargetId! }))}>Crew attack</button>}</div>)}</section>
    </div>
  </aside>;
}
