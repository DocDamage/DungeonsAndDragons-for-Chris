import { useEffect, useState } from 'react';
import { API_BASE } from '../../services/api';
import type { D6Character, GameSession } from '../../types';
import '../sidebar/D6.css';

type Drowning = { round: number; initial_difficulty: number; rescue_difficulty: number; attempted_round: number; declared_round: number };
type Hazards = { fatigue_failures: number; fatigued: boolean; exhausted: boolean; willpower_driven: boolean; exertion_rounds: number; rest_rounds: number; swim_round?: number | string; drowning: Drowning | null; history: Record<string, unknown>[] };
type HazardCharacter = D6Character & { hazards?: Hazards };
type Person = { id: string; name: string; d6: HazardCharacter };
type Catalog = { falling: { min: number; max: number | null; dice: number }[]; bands: { name: string; min: number; max: number }[]; source: string };
type Mode = 'exert' | 'rest' | 'swim' | 'fall';
type EmergencyAction = 'swim' | 'other' | 'pass' | 'rescued';
const empty: Hazards = { fatigue_failures: 0, fatigued: false, exhausted: false, willpower_driven: false, exertion_rounds: 0, rest_rounds: 0, drowning: null, history: [] };
const words = (value: string) => value.replaceAll('_', ' ');
const roundCount = (rounds: number) => `${rounds} ${rounds === 1 ? 'round' : 'rounds'}`;
const duration = (rounds: number) => {
  if (rounds < 12) return roundCount(rounds);
  const amount = Number((rounds / (rounds >= 720 ? 720 : 12)).toFixed(3));
  return `${amount} ${rounds >= 720 ? amount === 1 ? 'hour' : 'hours' : amount === 1 ? 'minute' : 'minutes'}`;
};
const integer = (value: number, min: number, max: number) => Number.isInteger(value) && value >= min && value <= max;
function conscious(person: Person) {
  const state = person.d6;
  const force = state.force;
  const effects = force?.effects.filter(effect => effect.recipient || effect.target_id == null || effect.target_id === effect.source_id) ?? [];
  if (state.hazards?.exhausted || state.vacuum_unconscious || state.droid?.destroyed || state.corruption?.pending_demand || state.corruption?.dead || state.wound === 'dead' || state.round_state.blocked || force?.remain_pending || (force?.attempt?.preparation_remaining ?? 0) > 0 || effects.some(effect => ['hibernation_trance', 'transfer_force', 'emptiness'].includes(effect.power_id))) return false;
  if (effects.some(effect => ['control_pain', 'control_another_pain'].includes(effect.power_id) && effect.ready_in_rounds === 0)) return true;
  return force?.remain_actions !== 0 && (['healthy', 'wounded'].includes(state.wound) && !state.unconscious_rounds || (force?.remain_actions ?? 0) > 0);
}
async function hazardRequest<T>(action: string, payload?: unknown, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`${API_BASE}/weg-d6/hazards/${action}`, payload === undefined ? { signal } : { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload), signal });
  if (!response.ok) {
    const data = await response.json().catch(() => null) as { detail?: string | { msg: string }[] } | null;
    throw new Error(typeof data?.detail === 'string' ? data.detail : Array.isArray(data?.detail) ? data.detail.map(item => item.msg).join('; ') : `Hazard request failed (${response.status})`);
  }
  return response.json();
}

function Points({ person, cp, fp, onCP, onFP, label, declared = false, forceActive = false }: { person: Person; cp: number; fp: boolean; onCP: (value: number) => void; onFP: (value: boolean) => void; label: string; declared?: boolean; forceActive?: boolean }) {
  return <div className="native-form-row"><label>{label} Character Points<input aria-label={`${label} Character Points`} type="number" min={0} max={Math.min(2, person.d6.character_points)} disabled={fp || forceActive} value={cp} onChange={event => onCP(Number(event.target.value))} /></label><label className="native-checkbox"><input aria-label={`${label} Force Point`} type="checkbox" checked={fp} disabled={declared || (!person.d6.force_points && !fp)} onChange={event => { onFP(event.target.checked); onCP(0); }} />Spend a Force Point{declared ? ' (must be declared on first action)' : ''}</label><span>{person.d6.character_points} CP · {person.d6.force_points} FP{forceActive ? ' · Force Point active this round' : ''}</span></div>;
}

function HazardHistory({ entries }: { entries: Record<string, unknown>[] }) {
  return <details><summary>Saved hazard history ({entries.length})</summary>{[...entries].reverse().map((entry, index) => {
    const title = String(entry.kind ?? entry.action ?? entry.operation ?? entry.type ?? 'Hazard event');
    const summary = typeof entry.summary === 'string' ? entry.summary : '';
    const reason = typeof entry.reason === 'string' ? entry.reason : '';
    const details = entry.details !== null && typeof entry.details === 'object' ? entry.details as Record<string, unknown> : {};
    const combined = { ...entry, ...details };
    const facts = Object.entries(combined).filter(([key, value]) => !['kind', 'action', 'operation', 'type', 'summary', 'reason', 'actor_id'].includes(key) && !key.startsWith('_') && (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean'));
    const rolls = Object.entries(combined).filter(([key, value]) => value !== null && typeof value === 'object' && 'total' in value && !(key === 'roll' && Array.isArray(details.rolls)));
    if (Array.isArray(details.rolls)) details.rolls.forEach((roll, number) => { if (roll !== null && typeof roll === 'object' && 'total' in roll) rolls.push([`roll ${number + 1}`, roll]); });
    return <section className="native-training-card" key={index}><strong>{words(title)}</strong>{summary && <p>{summary}</p>}{reason && reason !== summary && <p className="native-help">{reason}</p>}{!!facts.length && <p className="native-help">{facts.map(([key, value]) => `${words(key)}: ${typeof value === 'boolean' ? value ? 'yes' : 'no' : value}`).join(' · ')}</p>}{rolls.map(([key, value]) => {
      const roll = value as { total: number; breakdown?: string; expression?: string };
      return <p className="native-help" key={key}>{words(key)}: {roll.breakdown || roll.expression || 'dice'} → {roll.total}</p>;
    })}</section>;
  })}</details>;
}

export function D6HazardsPanel({ session, onSessionChanged }: { session: GameSession; onSessionChanged: (session: GameSession) => void }) {
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [actorId, setActorId] = useState('');
  const [mode, setMode] = useState<Mode>('exert');
  const [reason, setReason] = useState('');
  const [amount, setAmount] = useState(1);
  const [unit, setUnit] = useState<'hours' | 'minutes' | 'rounds'>('hours');
  const [difficulty, setDifficulty] = useState(15);
  const [cp, setCP] = useState(0);
  const [fp, setFP] = useState(false);
  const [push, setPush] = useState(false);
  const [willpowerCP, setWillpowerCP] = useState(0);
  const [willpowerOverride, setWillpowerOverride] = useState('');
  const [rescueOverride, setRescueOverride] = useState('');
  const [gamorreanRetry, setGamorreanRetry] = useState(false);
  const [retryCP, setRetryCP] = useState(0);
  const [failureDamageMargin, setFailureDamageMargin] = useState('');
  const [swimActions, setSwimActions] = useState(1);
  const [breathingRisk, setBreathingRisk] = useState(true);
  const [meters, setMeters] = useState(6);
  const [standardGravity, setStandardGravity] = useState(true);
  const [damageCode, setDamageCode] = useState('');
  const [resistanceCP, setResistanceCP] = useState(0);
  const [emergencyActorId, setEmergencyActorId] = useState('');
  const [emergencyAction, setEmergencyAction] = useState<EmergencyAction>('swim');
  const [emergencySkill, setEmergencySkill] = useState('search');
  const [emergencyDifficulty, setEmergencyDifficulty] = useState(10);
  const [emergencyActions, setEmergencyActions] = useState(1);
  const [emergencyCP, setEmergencyCP] = useState(0);
  const [emergencyFP, setEmergencyFP] = useState(false);
  const [emergencyReason, setEmergencyReason] = useState('');
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  useEffect(() => {
    const controller = new AbortController();
    hazardRequest<Catalog>('catalog', undefined, controller.signal).then(setCatalog).catch(err => { if (!controller.signal.aborted) setError(err instanceof Error ? err.message : String(err)); });
    return () => controller.abort();
  }, []);
  const people: Person[] = [session.character, ...(session.character.companions ?? [])].filter(person => person.d6).map(person => ({ id: person.id, name: person.name, d6: person.d6 as HazardCharacter }));
  const actor = people.find(person => person.id === actorId) ?? people[0];
  const state = actor?.d6.hazards ?? empty;
  const drowning = people.filter(person => person.d6.hazards?.drowning && person.d6.wound !== 'dead');
  const hazardRound = (session as GameSession & { d6_hazard_round?: number | string }).d6_hazard_round;
  const alreadySwam = drowning.length > 0 && hazardRound !== undefined && state.swim_round === hazardRound;
  const otherSwimmers = people.filter(person => !person.d6.hazards?.drowning && conscious(person) && !person.d6.force?.attempt && (hazardRound === undefined || person.d6.hazards?.swim_round !== hazardRound));
  const target = drowning.find(person => person.id === emergencyActorId) ?? drowning.find(conscious) ?? drowning[0];
  const water = target?.d6.hazards?.drowning;
  const declared = Boolean(water && water.declared_round === water.round);
  const forceActive = declared && Boolean(target?.d6.round_state.force_active || target?.d6.round_state.dark_side_called);
  const acted = Boolean(water && water.attempted_round === water.round);
  const diceAction = emergencyAction === 'swim' || emergencyAction === 'other';
  const actionLeft = !declared || Boolean(target && target.d6.round_state.actions_taken < target.d6.round_state.declared_actions);
  const emergencyReady = Boolean(target && (emergencyAction === 'rescued' || conscious(target) && (emergencyAction === 'pass' ? !acted : actionLeft && (emergencyAction !== 'swim' || !acted))));
  const emergencyPointsValid = !diceAction || Boolean(target && integer(emergencyCP, 0, 2) && emergencyCP <= target.d6.character_points && (!emergencyFP || target.d6.force_points > 0));
  const nextReady = drowning.every(person => !conscious(person) || person.d6.hazards!.drowning!.attempted_round === person.d6.hazards!.drowning!.round);
  const combat = Boolean(session.encounter?.active || session.vehicle_encounter);
  const navigation = [...(session.d6_navigation?.journeys ?? [])].reverse().find(journey => !['arrived', 'aborted', 'interrupted', 'off_course', 'abandoned'].includes(journey.status));
  const navigationHold = Boolean(navigation && navigation.status !== 'travelling');
  const rounds = Math.round(amount * (unit === 'hours' ? 720 : unit === 'minutes' ? 12 : 1));
  const validTime = Number.isFinite(amount) && amount > 0 && integer(rounds, 1, 6307200);
  const restRequired = state.exertion_rounds * (state.exhausted || state.willpower_driven ? 2 : 1);
  const restRemaining = Math.max(0, restRequired - state.rest_rounds);
  const fallBand = catalog?.falling.find(band => Math.ceil(meters) >= band.min && (band.max === null || Math.ceil(meters) <= band.max));
  const needsDamageCode = !standardGravity || meters < 3;
  const validCode = !damageCode.trim() ? !needsDamageCode : /^(?:[1-9]|[1-4]\d|50)[dD](?:\+[12])?$/.test(damageCode.trim());
  const retryAvailable = actor?.d6.species_id === 'gamorrean' && !state.willpower_driven;
  const useRetry = mode === 'exert' && retryAvailable && gamorreanRetry;
  const useWillpower = mode === 'exert' && (push || state.willpower_driven);
  const extraCP = (useRetry ? retryCP : 0) + (mode === 'exert' && push && !state.willpower_driven ? willpowerCP : 0);
  const pointsValid = Boolean(actor && integer(cp, 0, 2) && cp + extraCP <= actor.d6.character_points && (!fp || actor.d6.force_points > 0 && cp + extraCP === 0) && (!useRetry || integer(retryCP, 0, 2)) && (!useWillpower || state.willpower_driven || integer(willpowerCP, 0, 2)));
  const harderBand = catalog?.bands.findIndex(band => difficulty >= band.min && difficulty <= band.max) ?? -1;
  const nextBand = harderBand >= 0 ? catalog?.bands[harderBand + 1] : undefined;
  const willpowerDifficulty = willpowerOverride.trim() ? Number(willpowerOverride) : nextBand?.min;
  const needsHigherOverride = difficulty >= 31;
  const validHigher = (value: string) => value.trim() === '' ? !needsHigherOverride : integer(Number(value), nextBand?.min ?? difficulty + 1, nextBand?.max ?? 1000);
  const validDifficulties = (!useWillpower || validHigher(willpowerOverride)) && (mode !== 'swim' || !breathingRisk || Boolean(actor?.d6.droid) || validHigher(rescueOverride));
  const actionReady = Boolean(actor && conscious(actor) && !actor.d6.force?.attempt);
  const validNormal = Boolean(actor && actor.d6.wound !== 'dead' && reason.trim() && (mode === 'fall' ? Number.isFinite(meters) && meters > 0 && meters <= 100000 && validCode && integer(resistanceCP, 0, 5) && resistanceCP <= actor.d6.character_points : mode === 'rest' ? validTime : actionReady && pointsValid && validDifficulties && integer(difficulty, 1, 1000) && (mode === 'exert' ? validTime && (failureDamageMargin.trim() === '' || integer(Number(failureDamageMargin), 0, 1000)) : !state.drowning && !alreadySwam && integer(swimActions, 1, 10))));

  async function run(action: string, payload: unknown) {
    if (pending) return false;
    setPending(true); setError(''); setMessage('');
    try {
      const result = await hazardRequest<{ session: GameSession; eval_result?: { summary?: string } }>(action, payload);
      onSessionChanged(result.session); setMessage(result.eval_result?.summary ?? 'Hazard state saved.'); return true;
    } catch (err) { setError(err instanceof Error ? err.message : String(err)); return false; }
    finally { setPending(false); }
  }
  async function resolveNormal() {
    const base = { actor_id: actor?.id, reason };
    const data = mode === 'fall' ? { ...base, meters, standard_gravity: standardGravity, damage_code: damageCode.trim() || null, resistance_character_points: resistanceCP }
      : mode === 'rest' ? { ...base, rounds }
        : mode === 'swim' ? { ...base, difficulty, character_points: cp, force_point: fp, actions: swimActions, breathing_risk: !actor?.d6.droid && breathingRisk, rescue_difficulty: rescueOverride.trim() ? Number(rescueOverride) : null }
          : { ...base, rounds, difficulty, character_points: cp, force_point: fp, push_with_willpower: push && !state.willpower_driven, willpower_character_points: push && !state.willpower_driven && !fp ? willpowerCP : 0, willpower_difficulty: willpowerOverride.trim() ? Number(willpowerOverride) : null, gamorrean_retry: useRetry, retry_character_points: useRetry && !fp ? retryCP : 0, failure_damage_margin: failureDamageMargin.trim() === '' ? null : Number(failureDamageMargin) };
    if (await run(mode, data)) { setCP(0); setFP(false); setWillpowerCP(0); setRetryCP(0); setResistanceCP(0); }
  }

  if (!actor) return null;
  return <details name="native-tools" className="native-force-panel native-hazards-panel" style={{ maxHeight: 'min(55vh, max(160px, calc(100dvh - 350px)))' }}>
    <summary>Environmental hazards{drowning.length ? ` · ${drowning.length} drowning` : ''}</summary>
    <p className="native-help">Record actual exertion, fatigue, swimming, drowning and falling impacts. Work and recovery time advance the whole scene and fleet. Fatigue and drowning remain part of the saved character.</p>
    {error && <p role="alert" className="native-error">{error}</p>}{message && <p role="status">{message}</p>}
    <label>Party member<select aria-label="Environmental hazard character" value={actor.id} onChange={event => { setActorId(event.target.value); setCP(0); setFP(false); setWillpowerCP(0); setResistanceCP(0); setRetryCP(0); setGamorreanRetry(false); setFailureDamageMargin(''); setPush(false); }}>{people.map(person => <option key={person.id} value={person.id}>{person.name} · {words(person.d6.wound)}</option>)}</select></label>
    <section className="native-training-card" aria-label="Saved environmental condition"><strong>{actor.name} · {state.exhausted ? 'exhausted · ordinary actions blocked' : state.fatigued ? 'fatigued · −1D to actions' : 'no fatigue penalty'}</strong><p>{state.fatigue_failures}/3 Stamina failures · exertion {duration(state.exertion_rounds)} · credited rest {duration(state.rest_rounds)}{state.willpower_driven ? ' · driving on with Willpower' : ''}</p>{(state.fatigued || state.exhausted || state.willpower_driven) && <p className="native-help">{duration(restRemaining)} more actual rest required{state.exhausted || state.willpower_driven ? ' · twice accumulated exertion' : ' · equal to accumulated exertion'}. Resting while Willpower-driven ends the push and requires double recovery.</p>}{state.drowning && <p role="alert" className="native-error">Drowning · {roundCount(state.drowning.round)} elapsed · self-rescue Swimming difficulty {state.drowning.rescue_difficulty}</p>}</section>
    {!!drowning.length && <section className="native-training-card" aria-label="Group drowning emergency">
      <h4>Drowning emergency · resolve each character before advancing</h4>
      <p className="native-help">At the start of each new drowning round, plain 2D is rolled. A total lower than the number of drowning rounds means death. Each conscious character has one self-rescue Swimming opportunity per round, at one difficulty level above the original failed swim. Other skill actions suffer −3D.</p>
      {drowning.map(person => { const saved = person.d6.hazards!.drowning!; return <p key={person.id}><strong>{person.name}</strong> · {roundCount(saved.round)} elapsed · rescue difficulty {saved.rescue_difficulty} · {saved.attempted_round === saved.round ? 'self-rescue opportunity resolved' : conscious(person) ? 'self-rescue / pass required' : 'cannot act; actual rescue needed'} · {words(person.d6.wound)}</p>; })}
      {!!otherSwimmers.length && <button className="hp-btn" onClick={() => { setActorId(otherSwimmers[0].id); setMode('swim'); setCP(0); setFP(false); setWillpowerCP(0); }}>Check another party member's Swimming in this round</button>}
      <div className="native-form-row"><label>Drowning character<select aria-label="Drowning character" value={target?.id ?? ''} onChange={event => { setEmergencyActorId(event.target.value); setEmergencyCP(0); setEmergencyFP(false); if (emergencyAction === 'rescued') setEmergencyReason(''); }}>{drowning.map(person => <option key={person.id} value={person.id}>{person.name}</option>)}</select></label><label>Emergency action<select aria-label="Drowning action" value={emergencyAction} onChange={event => { setEmergencyAction(event.target.value as EmergencyAction); setEmergencyCP(0); setEmergencyFP(false); if (emergencyAction === 'rescued') setEmergencyReason(''); }}><option value="swim">Attempt self-rescue · Swimming</option><option value="other">Other skill action · −3D</option><option value="pass">Pass this round's self-rescue opportunity</option><option value="rescued">GM confirms actual rescue to safety</option></select></label></div>
      {emergencyAction === 'swim' && <p>Saved self-rescue difficulty: {water?.rescue_difficulty} · the drowning −3D penalty does not apply to this Swimming attempt.</p>}
      {emergencyAction === 'other' && <div className="native-form-row"><label>Other emergency skill<input aria-label="Drowning other skill" list="hazard-emergency-skills" value={emergencySkill} onChange={event => setEmergencySkill(event.target.value)} /></label><label>GM skill difficulty<input aria-label="Drowning other difficulty" type="number" min={1} max={1000} value={emergencyDifficulty} onChange={event => setEmergencyDifficulty(Number(event.target.value))} /></label><datalist id="hazard-emergency-skills">{[...new Set([...Object.keys(target?.d6.skills ?? {}), ...Object.keys(target?.d6.attributes ?? {})])].filter(skill => skill !== 'swimming').map(skill => <option key={skill} value={skill} />)}</datalist></div>}
      {diceAction && target && <><label>Declared actions this drowning round<input aria-label="Drowning declared actions" type="number" min={1} max={10} disabled={declared} value={declared ? target.d6.round_state.declared_actions : emergencyActions} onChange={event => setEmergencyActions(Number(event.target.value))} /></label><Points person={target} cp={emergencyCP} fp={emergencyFP} onCP={setEmergencyCP} onFP={setEmergencyFP} label="Drowning action" declared={declared} forceActive={forceActive} /><p className="native-help">Declare the full action count on this character's first roll of the round. Multiple action penalties and existing Force Point use apply to all their drowning actions.</p></>}
      {emergencyAction === 'rescued' && <p className="native-help">Record the actual completed rescue and who or what brought this character to safety. This GM fact makes no skill roll and spends no Character Points or Force Points.</p>}
      {emergencyAction === 'pass' && <p className="native-help">Record that the self-rescue opportunity passes. This makes no roll and spends no points; the character remains in danger.</p>}
      <label>Actual emergency action / next round facts<textarea aria-label="Drowning reason" rows={2} maxLength={1000} value={emergencyReason} onChange={event => setEmergencyReason(event.target.value)} /></label>
      <div className="native-button-row"><button className="hp-btn" disabled={pending || combat || navigationHold || !emergencyReady || !emergencyPointsValid || !emergencyReason.trim() || diceAction && (!integer(declared ? target?.d6.round_state.declared_actions ?? 0 : emergencyActions, 1, 10) || emergencyAction === 'other' && (!emergencySkill.trim() || !integer(emergencyDifficulty, 1, 1000)))} onClick={async () => {
        if (await run('drowning-action', { actor_id: target?.id, action: emergencyAction, skill: emergencySkill, difficulty: emergencyDifficulty, reason: emergencyReason, character_points: diceAction && !forceActive ? emergencyCP : 0, force_point: diceAction && !declared && emergencyFP, actions: diceAction ? declared ? target?.d6.round_state.declared_actions : emergencyActions : 1 })) { setEmergencyCP(0); setEmergencyFP(false); if (emergencyAction === 'rescued') setEmergencyReason(''); }
      }}>{emergencyAction === 'rescued' ? 'Record completed rescue' : emergencyAction === 'pass' ? 'Pass self-rescue opportunity' : 'Resolve drowning action'}</button><button className="hp-btn" disabled={pending || combat || navigationHold || !nextReady || !emergencyReason.trim()} onClick={async () => { if (await run('drowning-next', { reason: emergencyReason })) { setEmergencyCP(0); setEmergencyFP(false); if (emergencyAction === 'rescued') setEmergencyReason(''); } }}>Advance 1 round · roll drowning checks</button></div>
      {!nextReady && <p className="native-help">Each conscious drowning character must attempt self-rescue or pass before the group clock advances.</p>}{diceAction && !actionLeft && <p className="native-help">All declared actions are used. Passing an unresolved self-rescue opportunity still allows this round to end.</p>}
    </section>}
    {(!drowning.length || mode === 'swim') && <>
      {combat && <p className="native-help">Exertion, recovery and swimming controls require the character and craft encounters to end. The GM can still apply an actual falling impact during combat.</p>}{navigationHold && <p className="native-help">Resolve the pending hyperspace ruling or hull breach before another environmental procedure.</p>}
      <label>Hazard procedure<select aria-label="Environmental procedure" value={mode} onChange={event => { setMode(event.target.value as Mode); setCP(0); setFP(false); setWillpowerCP(0); setResistanceCP(0); }}>{!drowning.length && <><option value="exert">Sustained exertion · Stamina / Willpower</option><option value="rest">Actual rest · recover fatigue</option></>}<option value="swim">{drowning.length ? 'Another initial Swimming check · same saved round' : 'Swimming check'}</option>{!drowning.length && <option value="fall">Actual falling impact</option>}</select></label>
      {['exert', 'rest'].includes(mode) && <div className="native-form-row"><label>{mode === 'rest' ? 'Actual rest duration' : 'Actual exertion duration'}<input aria-label="Environmental time amount" type="number" min={unit === 'hours' ? 1 / 720 : unit === 'minutes' ? 1 / 12 : 1} max={unit === 'hours' ? 8760 : unit === 'minutes' ? 525600 : 6307200} step={unit === 'rounds' ? 1 : 'any'} value={amount} onChange={event => setAmount(Number(event.target.value))} /></label><label>Duration unit<select aria-label="Environmental time unit" value={unit} onChange={event => setUnit(event.target.value as typeof unit)}><option value="hours">Hours</option><option value="minutes">Minutes</option><option value="rounds">Rounds · 5 seconds</option></select></label>{mode === 'rest' && restRemaining > 0 && <button className="hp-btn" onClick={() => { setUnit('rounds'); setAmount(Math.min(restRemaining, 6307200)); }}>Use remaining required rest</button>}</div>}
      {mode === 'exert' && <><p className="native-help">A failed Stamina check causes a nonstacking −1D fatigue penalty; the third failure means complete exhaustion. Willpower can drive the character onward. Ending or failing a Willpower push requires twice the accumulated exertion in actual rest.</p><p>Current exertion roll: <strong>{state.willpower_driven ? 'Willpower' : 'Stamina'}</strong> · {state.willpower_driven ? actor.d6.skills.willpower ?? actor.d6.attributes.knowledge : actor.d6.skills.stamina ?? actor.d6.attributes.strength}{state.willpower_driven && willpowerDifficulty ? ` · actual Willpower difficulty ${willpowerDifficulty} (one band above the base Stamina difficulty)` : ''}</p>{!state.willpower_driven && <label className="native-checkbox"><input type="checkbox" checked={push} onChange={event => { setPush(event.target.checked); setWillpowerCP(0); }} />Predeclare two actions: try Willpower if Stamina fails</label>}{push && !state.willpower_driven && <><p className="native-help">Both rolls take the two-action penalty. The follow-up Willpower check uses the next source band{willpowerDifficulty ? ` (${willpowerDifficulty})` : ''}.</p><label>Follow-up Willpower Character Points<input aria-label="Follow-up Willpower Character Points" type="number" min={0} max={Math.max(0, Math.min(2, actor.d6.character_points - cp))} disabled={fp} value={willpowerCP} onChange={event => setWillpowerCP(Number(event.target.value))} /></label></>}{state.willpower_driven && <button className="hp-btn" disabled={pending || combat || navigationHold || !reason.trim()} onClick={() => run('stop-pushing', { actor_id: actor.id, reason })}>Stop driving on · mark exhausted</button>}</>}
      {(mode === 'exert' || mode === 'swim') && <><label>GM {mode === 'swim' ? 'Swimming difficulty' : 'base Stamina difficulty'}<input aria-label="Environmental skill difficulty" type="number" min={1} max={1000} value={difficulty} onChange={event => { setDifficulty(Number(event.target.value)); setWillpowerOverride(''); setRescueOverride(''); }} /></label><p className="native-help">{catalog?.bands.map(band => `${band.name} ${band.min}${band.max === 1000 ? '+' : `–${band.max}`}`).join(' · ')}</p><Points person={actor} cp={cp} fp={fp} onCP={setCP} onFP={value => { setFP(value); if (value) { setWillpowerCP(0); setRetryCP(0); } }} label={mode === 'swim' ? 'Swimming' : state.willpower_driven ? 'Willpower' : 'Stamina'} /></>}
      {useWillpower && <><label>GM harder Willpower difficulty{needsHigherOverride ? ' (required above Heroic)' : ' (optional within next band)'}<input aria-label="Environmental Willpower difficulty override" type="number" min={nextBand?.min ?? difficulty + 1} max={nextBand?.max ?? 1000} placeholder={nextBand ? `${nextBand.name}: ${nextBand.min}–${nextBand.max}` : 'GM must choose a difficulty above the original'} value={willpowerOverride} onChange={event => setWillpowerOverride(event.target.value)} /></label>{needsHigherOverride && <p className="native-help">The source has no named difficulty level above Heroic. Record the GM's actual harder difficulty; the engine does not add a fixed modifier.</p>}</>}
      {mode === 'exert' && retryAvailable && <><label className="native-checkbox"><input aria-label="Gamorrean immediate Stamina retry" type="checkbox" checked={gamorreanRetry} onChange={event => { setGamorreanRetry(event.target.checked); setRetryCP(0); }} />Use the Gamorrean's one immediate retry if Stamina fails</label>{gamorreanRetry && <><label>Immediate retry Character Points<input aria-label="Gamorrean retry Character Points" type="number" min={0} max={Math.max(0, Math.min(2, actor.d6.character_points - cp - (push ? willpowerCP : 0)))} disabled={fp} value={retryCP} onChange={event => setRetryCP(Number(event.target.value))} /></label><p className="native-help">The one retry uses no extra declared action and occurs before fatigue, injury or a possible Willpower follow-up. All potential CP expenditures must be available; a Force Point cannot be combined with any CP dice.</p></>}</>}
      {mode === 'exert' && <><label>Actual failure damage margin after resistance (optional)<input aria-label="Exertion actual failure damage margin" type="number" min={0} max={1000} step={1} placeholder="Blank when failure causes no actual injury" value={failureDamageMargin} onChange={event => setFailureDamageMargin(event.target.value)} /></label><p className="native-help">Use only when this environmental failure actually inflicts injury. The GM records the already-resisted net damage margin; no damage is added when this field is blank. A failed check applies the native wound result. A Willpower push worsens that actual injury by one wound level, as recorded in the saved history.</p></>}
      {mode === 'swim' && <>{!!drowning.length && <p className="native-help">Another party member's initial swim uses this saved drowning round; scene time does not advance again. Choose a conscious party member who is not already drowning and has not made an initial swim check this round.</p>}{state.drowning && <p className="native-help">{actor.name} is already drowning. Use their saved self-rescue action above, or select another party member for an initial Swimming check.</p>}{alreadySwam && !state.drowning && <p className="native-help">{actor.name} already made their initial Swimming check in this saved round.</p>}<label>Declared skill actions<input aria-label="Swimming declared actions" type="number" min={1} max={10} value={swimActions} onChange={event => setSwimActions(Number(event.target.value))} /></label>{actor.d6.droid ? <p className="native-help">Droid chassis: a failed Swimming check does not start a breathing emergency.</p> : <label className="native-checkbox"><input type="checkbox" checked={breathingRisk} onChange={event => setBreathingRisk(event.target.checked)} />Actual breathing risk · failed Swimming starts drowning</label>}<p className="native-help">The GM can clear breathing risk for actual protection or scene facts, with the reason recorded below.</p></>}
      {mode === 'swim' && breathingRisk && !actor.d6.droid && <><label>GM self-rescue Swimming difficulty{needsHigherOverride ? ' (required above Heroic)' : ' (optional within next band)'}<input aria-label="Environmental self-rescue difficulty override" type="number" min={nextBand?.min ?? difficulty + 1} max={nextBand?.max ?? 1000} placeholder={nextBand ? `${nextBand.name}: ${nextBand.min}–${nextBand.max}` : 'GM must choose a difficulty above the original'} value={rescueOverride} onChange={event => setRescueOverride(event.target.value)} /></label><p className="native-help">This actual higher difficulty is saved if the character begins drowning{needsHigherOverride ? '; the source requires a GM ruling above Heroic' : '; blank uses the next source band’s minimum'}.</p></>}
      {mode === 'fall' && <><div className="native-form-row"><label>Actual distance fallen (meters)<input aria-label="Falling distance" type="number" min={0.001} max={100000} step="any" value={meters} onChange={event => setMeters(Number(event.target.value))} /></label><label>GM damage code{needsDamageCode ? ' (required)' : ' override (optional)'}<input aria-label="Falling damage code" placeholder={fallBand ? `${fallBand.dice}D from source table` : 'GM damage code, e.g. 2D'} value={damageCode} onChange={event => setDamageCode(event.target.value)} /></label><label>Resistance Character Points<input aria-label="Falling resistance Character Points" type="number" min={0} max={Math.min(5, actor.d6.character_points)} value={resistanceCP} onChange={event => setResistanceCP(Number(event.target.value))} /></label></div><label className="native-checkbox"><input type="checkbox" checked={standardGravity} onChange={event => setStandardGravity(event.target.checked)} />Standard gravity · use the printed falling table</label><p>{damageCode.trim() ? `GM impact damage: ${damageCode.trim()}` : fallBand && standardGravity && meters >= 3 ? `Source impact damage: ${fallBand.dice}D` : 'A GM damage code is required for this fall.'} · full Strength physical resistance</p><p className="native-help">Damage uses the falling character's own scale. Fractional distances round up to the source's whole-meter bands. Below three meters or in other gravity, the GM supplies actual damage. Falling impact is applied to a living character without spending a skill action.</p><details><summary>Printed standard gravity falling table</summary>{catalog?.falling.map(band => <p className="native-help" key={band.min}>{band.min}{band.max === null ? '+' : `–${band.max}`} meters · {band.dice}D</p>)}</details></>}
      <label>Actual scene facts and GM reason<textarea aria-label="Environmental hazard reason" rows={2} maxLength={1000} value={reason} onChange={event => setReason(event.target.value)} /></label>
      <button className="hp-btn" disabled={pending || navigationHold || mode !== 'fall' && combat || !validNormal} onClick={resolveNormal}>{mode === 'exert' ? `Advance ${duration(rounds)} and roll ${state.willpower_driven ? 'Willpower' : 'Stamina'}` : mode === 'rest' ? `Credit ${duration(rounds)} actual rest` : mode === 'swim' ? 'Resolve Swimming check' : 'Apply falling damage and resistance'}</button>
    </>}
    <HazardHistory entries={state.history} />
    <p className="native-help">{catalog?.source ?? 'WEG Second Edition (1992), printed pp.79, 86, 97.'}</p>
  </details>;
}
