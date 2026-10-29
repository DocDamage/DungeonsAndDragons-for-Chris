import { useEffect, useState } from 'react';
import { API_BASE } from '../../services/api';
import type { D6Character, D6DroidState, D6Vehicle, GameSession, Item } from '../../types';
import '../sidebar/D6.css';

type RouteType = 'major' | 'common' | 'light' | 'infrequent' | 'old' | 'unexplored';
type RouteMemory = { origin: string; destination: string; reason: string };
type NavigationCharacter = D6Character & { droid?: (D6DroidState & { route_memory?: RouteMemory[] }) | null; survival_suit?: string | null; vacuum_unconscious?: boolean };
type Person = { id: string; name: string; d6: NavigationCharacter };
type Craft = D6Vehicle & { location?: string; hyperdrive_multiplier?: number | null; backup_hyperdrive?: number | null; nav_computer?: boolean; nav_computer_disabled?: boolean; hull_breached?: boolean; escape_pods_disabled?: boolean };
type Request = {
  craft_id: string; actor_id: string | null; origin: string; destination: string;
  base_hours: number | null; base_difficulty: number; route_type: RouteType; backup: boolean;
  hasty: boolean; obstacles: number; extra_hours: number; clearance_units: number;
  boarding_confirmed: boolean; plotting_rounds: number; astromech_id: string | null;
  character_points: number; force_point: boolean; destination_visited: boolean; reason: string; expected_updated_at: number | null;
};
type Quote = { difficulty: number; hours: number; rounds: number; has_navigation: boolean; multiplier: number; notes: string[] };
type Exposure = { protected: boolean; phase: string; suit_round?: number; breath_round?: number; suit_name?: string | null; last_action_round?: number; acted_round?: number };
type Journey = { id: string; request: Request; quote: Quote; status: string; remaining_rounds: number; elapsed_rounds: number; roll: { total: number; breakdown?: string }; miss: number; mishap: number | null; auxiliary_rolls: { total: number; breakdown?: string }[]; travellers: string[]; crew_exposure: Record<string, Exposure>; emergency_round: number; resolution: string[] };
type Catalog = { systems: string[]; routes: { origin: string; destination: string; hours: number; printed_duration: string }[]; route_types: Record<RouteType, number>; source: string };
type Mutation = (action: string, payload: unknown) => Promise<boolean>;

const terminal = new Set(['arrived', 'aborted', 'interrupted', 'off_course', 'abandoned']);
const factors: Record<RouteType, number> = { major: 1, common: 1.1, light: 1.25, infrequent: 1.5, old: 2, unexplored: 2.5 };
const words = (value: string) => value.replaceAll('_', ' ');
const hours = (rounds: number) => `${Number((rounds / 720).toFixed(4))} hours`;
const conscious = (person: Person) => {
  const state = person.d6;
  const force = state.force;
  const selfEffects = force?.effects.filter(effect => effect.recipient || effect.target_id == null || effect.target_id === effect.source_id) ?? [];
  if (state.vacuum_unconscious || state.droid?.destroyed || state.corruption?.pending_demand || state.corruption?.dead || state.wound === 'dead' || state.round_state.blocked || force?.remain_pending || (force?.attempt?.preparation_remaining ?? 0) > 0 || selfEffects.some(effect => ['hibernation_trance', 'transfer_force', 'emptiness'].includes(effect.power_id))) return false;
  if (selfEffects.some(effect => ['control_pain', 'control_another_pain'].includes(effect.power_id) && effect.ready_in_rounds === 0)) return true;
  if (force?.remain_actions === 0) return false;
  return ['healthy', 'wounded'].includes(state.wound) && !state.unconscious_rounds || (force?.remain_actions ?? 0) > 0;
};
const routeMatches = (route: { origin: string; destination: string }, origin: string, destination: string) => {
  const endpoints = [route.origin.toLowerCase(), route.destination.toLowerCase()];
  return endpoints.includes(origin.trim().toLowerCase()) && endpoints.includes(destination.trim().toLowerCase()) && origin.trim().toLowerCase() !== destination.trim().toLowerCase();
};

async function request<T>(action: string, payload?: unknown, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`${API_BASE}/weg-d6/navigation/${action}`, payload === undefined ? { signal } : { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload), signal });
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { detail?: string | { msg: string }[] } | null;
    throw new Error(typeof body?.detail === 'string' ? body.detail : Array.isArray(body?.detail) ? body.detail.map(item => item.msg).join('; ') : `Navigation request failed (${response.status})`);
  }
  return response.json();
}

function CrewEmergency({ journey, people, inventory, pending, combat, run }: { journey: Journey; people: Person[]; inventory: Item[]; pending: boolean; combat: boolean; run: Mutation }) {
  const [targetId, setTargetId] = useState('');
  const [rescuerId, setRescuerId] = useState('');
  const [suitName, setSuitName] = useState('');
  const [method, setMethod] = useState<'suit' | 'breathe' | 'rescue' | 'wait'>('suit');
  const [cp, setCp] = useState(0);
  const [fp, setFp] = useState(false);
  const [actions, setActions] = useState(1);
  const [gamorreanRetry, setGamorreanRetry] = useState(false);
  const [retryCP, setRetryCP] = useState(0);
  const [reason, setReason] = useState('');
  const exposed = people.filter(person => journey.travellers.includes(person.id) && journey.crew_exposure[person.id]);
  const unprotected = exposed.filter(person => !journey.crew_exposure[person.id].protected);
  const target = unprotected.find(person => person.id === targetId) ?? unprotected[0];
  const entry = target ? journey.crew_exposure[target.id] : undefined;
  const rescuers = people.filter(person => person.id !== target?.id && conscious(person) && (!journey.crew_exposure[person.id] || journey.crew_exposure[person.id].protected));
  const rescuer = rescuers.find(person => person.id === rescuerId) ?? rescuers[0];
  const source = method === 'rescue' ? rescuer : target;
  const suits = inventory.filter(item => (item as Item & { sealed_survival_suit?: boolean }).sealed_survival_suit && item.quantity > 0);
  const suit = suits.find(item => item.name === suitName) ?? suits[0];
  const assigned = suit ? people.filter(person => person.d6.survival_suit === suit.name).length : 0;
  const suitAvailable = Boolean(suit && (target?.d6.survival_suit === suit.name || assigned < suit.quantity));
  const round = journey.emergency_round;
  const alreadyActed = Boolean(source && journey.crew_exposure[`actor_round:${source.id}`]?.last_action_round === round);
  const forceActive = alreadyActed && source?.d6.round_state.force_active;
  const suitReady = Boolean(target && conscious(target) && entry?.suit_round !== round && (round === 0 || entry?.breath_round === round));
  const breatheReady = Boolean(target && conscious(target) && round > 0 && entry?.breath_round !== round);
  const rescueReady = Boolean(rescuer && journey.crew_exposure[`rescuer:${rescuer.id}`]?.acted_round !== round);
  const actionAvailable = !alreadyActed || Boolean(source && source.d6.round_state.actions_taken < source.d6.round_state.declared_actions);
  const ready = method === 'wait' ? Boolean(target && conscious(target) && round === 0 && entry?.suit_round !== 0) : actionAvailable && (method === 'suit' ? suitReady && suitAvailable : method === 'breathe' ? breatheReady : rescueReady && suitAvailable);
  const nextRoundReady = unprotected.every(person => !conscious(person) || (round === 0 ? journey.crew_exposure[person.id].suit_round === 0 : journey.crew_exposure[person.id].breath_round === round));
  const useRetry = method === 'breathe' && source?.d6.species_id === 'gamorrean' && gamorreanRetry;
  const validPoints = method === 'wait' || Boolean(source && cp + (useRetry && !fp && !forceActive ? retryCP : 0) <= source.d6.character_points && (!fp || source.d6.force_points > 0));
  return <section className="native-training-card" aria-label="Hull breach crew emergency">
    <fieldset disabled={pending} style={{ border: 0, padding: 0, margin: 0, minWidth: 0 }}>
    <h4>Hull breach · emergency round {round + 1}</h4>
    <p className="native-help">First round: each conscious exposed character attempts a sealed suit at Moderate (15). Following rounds: breathe with Stamina first (10, 15, 20, 30, then 31), then try a suit again. A protected, conscious rescuer can fit a suit to another character. Two actions impose the normal multiple action penalty.</p>
    {exposed.map(person => <p key={person.id}>{person.name}: {journey.crew_exposure[person.id].protected ? 'protected' : words(journey.crew_exposure[person.id].phase)} · {words(person.d6.wound)}{journey.crew_exposure[person.id].suit_name ? ` · ${journey.crew_exposure[person.id].suit_name}` : ''}</p>)}
    <div className="native-form-row"><label>Exposed character<select aria-label="Navigation exposed character" value={target?.id ?? ''} onChange={event => { setTargetId(event.target.value); setCp(0); setFp(false); }}>{unprotected.map(person => <option key={person.id} value={person.id}>{person.name}</option>)}</select></label><label>Emergency action<select aria-label="Navigation emergency action" value={method} onChange={event => { setMethod(event.target.value as typeof method); setCp(0); setFp(false); }}><option value="suit">Put on sealed survival suit</option><option value="breathe">Hold breath · Stamina</option><option value="rescue">Protected rescuer fits a suit</option>{round === 0 && <option value="wait">No suit attempt this round</option>}</select></label></div>
    {method === 'rescue' && <label>Protected rescuer<select aria-label="Navigation rescuer" value={rescuer?.id ?? ''} onChange={event => { setRescuerId(event.target.value); setCp(0); setFp(false); }}>{rescuers.map(person => <option key={person.id} value={person.id}>{person.name} · {person.d6.character_points} CP · {person.d6.force_points} FP</option>)}</select></label>}
    {['suit', 'rescue'].includes(method) && <label>Actual sealed suit in party inventory<select aria-label="Navigation survival suit" value={suit?.name ?? ''} onChange={event => setSuitName(event.target.value)}>{suits.length ? suits.map(item => <option key={item.name} value={item.name}>{item.name} ×{item.quantity} · {people.filter(person => person.d6.survival_suit === item.name).length} assigned</option>) : <option value="">No sealed survival suits available</option>}</select></label>}
    {source && method !== 'wait' && <p className="native-help">Rolling: {source.name} · {method === 'breathe' ? source.d6.skills.stamina ?? source.d6.attributes.strength : source.d6.skills.survival ?? source.d6.attributes.knowledge} · {source.d6.character_points} CP · {source.d6.force_points} FP{forceActive ? ' · Force Point active this round' : ''}</p>}
    {method !== 'wait' && <div className="native-form-row"><label>Declared actions this round<select aria-label="Navigation emergency declared actions" disabled={alreadyActed} value={alreadyActed ? source?.d6.round_state.declared_actions : actions} onChange={event => setActions(Number(event.target.value))}><option value={1}>1 action</option><option value={2}>2 actions · breathe and suit / rescue</option></select></label><label>Emergency Character Points<input aria-label="Navigation emergency Character Points" type="number" min={0} max={Math.min(2, source?.d6.character_points ?? 0)} value={cp} disabled={fp || forceActive} onChange={event => setCp(Number(event.target.value))} /></label><label className="native-checkbox"><input type="checkbox" checked={fp} disabled={alreadyActed || !source?.d6.force_points} onChange={event => { setFp(event.target.checked); setCp(0); }} />Declare a Force Point on first action</label></div>}
    {method === 'wait' && <p className="native-help">Record that this character's initial suit opportunity passes without an attempt. No dice, Character Points, Force Points, or declared actions are used. Breathing checks begin next round.</p>}
    <label>Emergency action / next round facts<textarea aria-label="Navigation emergency reason" rows={2} maxLength={1000} value={reason} onChange={event => setReason(event.target.value)} /></label>
    {method === 'breathe' && source?.d6.species_id === 'gamorrean' && <><label className="native-checkbox"><input type="checkbox" checked={gamorreanRetry} onChange={event => setGamorreanRetry(event.target.checked)} />Use one immediate Gamorrean Stamina retry if the first breathing check fails</label>{gamorreanRetry && <label>Retry Character Points<input aria-label="Navigation breathing retry Character Points" type="number" min={0} max={Math.min(2, source.d6.character_points)} disabled={fp || forceActive} value={retryCP} onChange={event => setRetryCP(Number(event.target.value))} /></label>}</>}
    <div className="native-button-row"><button className="hp-btn" disabled={pending || combat || !ready || !validPoints || !reason.trim()} onClick={async () => {
      if (await run('crew-emergency', { journey_id: journey.id, actor_id: target?.id, method, suit_name: ['suit', 'rescue'].includes(method) ? suit?.name ?? '' : '', rescuer_id: method === 'rescue' ? rescuer?.id : null, character_points: method === 'wait' || fp || forceActive ? 0 : cp, force_point: method !== 'wait' && !alreadyActed && fp, actions: method === 'wait' ? 1 : alreadyActed ? source?.d6.round_state.declared_actions : actions, gamorrean_retry: useRetry, retry_character_points: useRetry && !fp && !forceActive ? retryCP : 0, reason })) { setCp(0); setFp(false); setRetryCP(0); }
    }}>Resolve crew action</button><button className="hp-btn" disabled={pending || combat || !nextRoundReady || !reason.trim()} onClick={async () => { if (await run('resolve', { journey_id: journey.id, action: 'next_round', reason })) { setFp(false); setCp(0); setMethod('breathe'); } }}>Advance emergency 1 round</button></div>
    {!ready && <p className="native-help">{method === 'wait' ? 'The initial suit opportunity can pass only once, in the first emergency round.' : method === 'breathe' ? 'Breathing checks begin after the initial suit round and are made once per character per round.' : method === 'suit' ? 'A conscious character needs an available suit, one suit attempt per round, and their breathing check first after the initial round.' : 'Choose an available sealed suit and a different protected, conscious rescuer who has not already rescued this round.'}</p>}
    {!actionAvailable && method !== 'wait' && <p className="native-help">This character has used all declared actions this round. Advance the emergency after required checks; declare two actions on the next round's first action to breathe and use a suit.</p>}
    {!nextRoundReady && <p className="native-help">Resolve every conscious exposed character's initial suit attempt or this round's breathing check before advancing.</p>}
    </fieldset>
  </section>;
}

export function D6NavigationPanel({ session, onSessionChanged }: { session: GameSession; onSessionChanged: (session: GameSession) => void }) {
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [craftId, setCraftId] = useState('');
  const [actorId, setActorId] = useState('');
  const [form, setForm] = useState({ origin: null as string | null, destination: 'Corellia', baseHours: '', base_difficulty: 15, route_type: 'major' as RouteType, backup: false, hasty: false, obstacles: 0, extra_hours: 0, clearance_units: 50, boarding_confirmed: false, plotting_rounds: 1, astromech_id: '', character_points: 0, force_point: false, destination_visited: false, reason: '' });
  const [review, setReview] = useState<{ signature: string; quote: Quote } | null>(null);
  const [rulingReason, setRulingReason] = useState('');
  const [dropout, setDropout] = useState('');
  const [damagedSystem, setDamagedSystem] = useState('nav_computer');
  const [exposedIds, setExposedIds] = useState<string[]>([]);
  const [advanceAmount, setAdvanceAmount] = useState(1);
  const [advanceUnit, setAdvanceUnit] = useState<'hours' | 'rounds'>('hours');
  const [memoryActorId, setMemoryActorId] = useState('');
  const [memoryOrigin, setMemoryOrigin] = useState('');
  const [memoryDestination, setMemoryDestination] = useState('');
  const [memoryReason, setMemoryReason] = useState('');
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');
  const patch = (value: Partial<typeof form>) => setForm(previous => ({ ...previous, ...value }));
  useEffect(() => {
    const controller = new AbortController();
    request<Catalog>('catalog', undefined, controller.signal).then(setCatalog).catch(err => { if (!controller.signal.aborted) setError(err instanceof Error ? err.message : String(err)); });
    return () => controller.abort();
  }, []);

  const people: Person[] = [session.character, ...(session.character.companions ?? [])].filter(person => person.d6).map(person => ({ id: person.id, name: person.name, d6: person.d6 as NavigationCharacter }));
  const fleet = (session.vehicles ?? []).filter(craft => craft.kind === 'starship') as Craft[];
  const craft = fleet.find(item => item.id === craftId) ?? fleet[0];
  const assigned = people.filter(person => craft?.crew.some(crew => crew.character_id === person.id));
  const actor = assigned.find(person => person.id === actorId) ?? assigned.find(person => person.id === session.character.id) ?? assigned[0];
  const astromechs = assigned.filter(person => person.d6.droid?.model === 'r2');
  const astromech = astromechs.find(person => person.id === form.astromech_id);
  const origin = form.origin ?? (craft?.location || catalog?.systems[0] || 'Tatooine');
  const destinationVisited = actor?.d6.species_context?.visited_locations.some(location => location.trim().toLowerCase() === form.destination.trim().toLowerCase()) ?? false;
  const payload: Request = { craft_id: craft?.id ?? '', actor_id: actor?.id ?? null, origin, destination: form.destination, base_hours: form.baseHours.trim() ? Number(form.baseHours) : null, base_difficulty: form.base_difficulty, route_type: form.route_type, backup: form.backup, hasty: form.hasty, obstacles: form.obstacles, extra_hours: form.extra_hours, clearance_units: form.clearance_units, boarding_confirmed: form.boarding_confirmed, plotting_rounds: form.plotting_rounds, astromech_id: astromech?.id ?? null, character_points: form.character_points, force_point: form.force_point, destination_visited: actor?.d6.species_id === 'sullustan' && form.destination_visited, reason: form.reason, expected_updated_at: session.updated_at ?? null };
  const signature = JSON.stringify({ session: session.id, revision: session.updated_at, payload, craft, actors: assigned.map(person => person.d6) });
  const quote = review?.signature === signature ? review.quote : null;
  const gazetteer = catalog?.routes.find(route => routeMatches(route, origin, form.destination));
  const programmed = astromech?.d6.droid?.route_memory?.some(route => routeMatches(route, origin, form.destination));
  const journeys = (session as GameSession & { d6_navigation?: { journeys: Journey[] } }).d6_navigation?.journeys ?? [];
  const current = [...journeys].reverse().find(journey => !terminal.has(journey.status));
  const combat = Boolean(session.encounter?.active || session.vehicle_encounter);
  const canReview = Boolean(craft && actor && conscious(actor) && !actor.d6.force?.attempt && form.boarding_confirmed && form.reason.trim() && origin.trim() && form.destination.trim() && origin.trim().toLowerCase() !== form.destination.trim().toLowerCase() && (gazetteer || Number(form.baseHours) > 0));
  const pointChoiceValid = Boolean(actor && form.character_points <= actor.d6.character_points && (!form.force_point || actor.d6.force_points > 0));
  const advanceRounds = Math.round(advanceAmount * (advanceUnit === 'hours' ? 720 : 1));
  const r2Units = people.filter(person => person.d6.droid?.model === 'r2');
  const memoryUnit = r2Units.find(person => person.id === memoryActorId) ?? r2Units[0];
  const memory = memoryUnit?.d6.droid?.route_memory ?? [];

  async function run(action: string, data: unknown) {
    if (pending) return false;
    setPending(true); setError('');
    try { const result = await request<{ session: GameSession }>(action, data); onSessionChanged(result.session); return true; }
    catch (err) { setError(err instanceof Error ? err.message : String(err)); return false; }
    finally { setPending(false); }
  }
  async function preview() {
    if (pending) return;
    setPending(true); setError(''); setReview(null);
    try { const result = await request<{ quote: Quote }>('quote', payload); setReview({ signature, quote: result.quote }); }
    catch (err) { setError(err instanceof Error ? err.message : String(err)); }
    finally { setPending(false); }
  }
  async function resolve(action: string, extra: Record<string, unknown> = {}) {
    if (await run('resolve', { journey_id: current?.id, action, reason: rulingReason, ...extra })) { setRulingReason(''); setDropout(''); setExposedIds([]); }
  }

  return <details name="native-tools" className="native-force-panel native-navigation-panel" style={{ maxHeight: 'min(55vh, calc(100dvh - 350px))' }}>
    <summary>Hyperspace navigation{current ? ` · ${words(current.status)}` : ''}</summary>
    <p className="native-help">Astrogation, the 1992 gazetteer and saved hyperspace mishaps. Review the route before rolling. Plotting and travel advance time for the entire scene and fleet.</p>
    {error && <p role="alert" className="native-error">{error}</p>}
    {combat && <p className="native-help">End the character or craft encounter before plotting, advancing travel, or resolving a navigation event.</p>}
    {current ? <section className="native-training-card">
      <h4>{fleet.find(item => item.id === current.request.craft_id)?.name ?? 'Starship'} · {current.request.origin} → {current.request.destination}</h4>
      <p><strong>{words(current.status)}</strong> · elapsed {hours(current.elapsed_rounds)} · remaining {hours(current.remaining_rounds)}</p>
      <p className="native-help">Astrogation {current.roll.total} vs. {current.quote.difficulty} · missed by {current.miss}{current.mishap !== null ? ` · plain 2D mishap ${current.mishap}` : ''}. {current.roll.breakdown}</p>
      {current.resolution.map((line, index) => <p key={index} className="native-help">{line}</p>)}
      {current.status === 'travelling' ? <>
        <progress aria-label="Hyperspace journey progress" style={{ width: '100%' }} max={current.elapsed_rounds + current.remaining_rounds} value={current.elapsed_rounds} />
        <div className="native-form-row"><label>Advance travel<input aria-label="Hyperspace time amount" type="number" min={advanceUnit === 'hours' ? 1 / 720 : 1} max={advanceUnit === 'hours' ? 8760 : 6307200} step={advanceUnit === 'hours' ? 'any' : 1} value={advanceAmount} onChange={event => setAdvanceAmount(Number(event.target.value))} /></label><label>Time unit<select aria-label="Hyperspace time unit" value={advanceUnit} onChange={event => setAdvanceUnit(event.target.value as typeof advanceUnit)}><option value="hours">Hours</option><option value="rounds">Rounds · 5 seconds</option></select></label><button className="hp-btn" disabled={pending || combat || !Number.isFinite(advanceRounds) || advanceRounds < 1 || advanceRounds > 6307200} onClick={() => run('advance', { rounds: advanceRounds })}>Advance travel</button><button className="hp-btn" disabled={pending || combat} onClick={() => run('advance', { rounds: Math.min(current.remaining_rounds, 6307200) })}>{current.remaining_rounds > 6307200 ? 'Advance 365 days toward arrival' : 'Advance to arrival'}</button></div>
        <p className="native-help">Travel stops at arrival. Craft damage, Force durations, wounds and other scene clocks still advance.</p>
      </> : current.status === 'emergency' ? <CrewEmergency key={current.id} journey={current} people={people} inventory={session.character.inventory} pending={pending} combat={combat} run={run} /> : <>
        {current.status === 'awaiting_location' && <label>Actual dropout system / realspace location<input aria-label="Navigation dropout location" list="navigation-systems" maxLength={120} value={dropout} onChange={event => setDropout(event.target.value)} /></label>}
        {current.status === 'close_call_pending' && <label>System actually damaged in the close call<select aria-label="Navigation close call damaged system" value={damagedSystem} onChange={event => setDamagedSystem(event.target.value)}><option value="nav_computer">Navigation computer</option><option value="drives">Sublight drives</option><option value="weapons">Weapons</option><option value="escape_pods">Escape pods</option></select></label>}
        {current.status === 'exposure_pending' && <><p>Identify every party member actually exposed to vacuum. Droids are protected automatically.</p>{people.filter(person => current.travellers.includes(person.id)).map(person => <label key={person.id} className="native-checkbox"><input type="checkbox" checked={exposedIds.includes(person.id)} onChange={event => setExposedIds(previous => event.target.checked ? [...previous, person.id] : previous.filter(id => id !== person.id))} />{person.name}{person.d6.droid ? ' · Droid' : ''}</label>)}<p className="native-help">No selection records that no party member was exposed. The breached craft must still be abandoned.</p></>}
        <label>GM navigation ruling and actual scene facts<textarea aria-label="Navigation ruling reason" rows={2} maxLength={1000} value={rulingReason} onChange={event => setRulingReason(event.target.value)} /></label>
        <div className="native-button-row">
          {current.status === 'ten_point_ruling' && <><p className="native-help">The printed rule omits a miss of exactly ten. Choose a ruling using the saved astrogation roll.</p><button className="hp-btn" disabled={pending || combat || !rulingReason.trim()} onClick={() => resolve('abort')}>Rule no hyperspace entry</button><button className="hp-btn" disabled={pending || combat || !rulingReason.trim()} onClick={() => resolve('roll_mishap')}>Rule plain 2D mishap</button></>}
          {current.status === 'awaiting_location' && <button className="hp-btn" disabled={pending || combat || !rulingReason.trim() || !dropout.trim()} onClick={() => resolve('location', { location: dropout })}>Record actual dropout location</button>}
          {current.status === 'close_call_pending' && <button className="hp-btn" disabled={pending || combat || !rulingReason.trim()} onClick={() => resolve('close_call', { system: damagedSystem })}>Apply system damage and continue</button>}
          {current.status === 'exposure_pending' && <button className="hp-btn" disabled={pending || combat || !rulingReason.trim()} onClick={() => resolve('exposure', { actor_ids: exposedIds.filter(id => current.travellers.includes(id)) })}>Confirm exposed crew</button>}
        </div>
      </>}
    </section> : <>
      {!craft ? <p className="native-help">Add a starship and assign party crew in Vehicles & starships before plotting a jump.</p> : <>
        <div className="native-form-row"><label>Fleet starship<select aria-label="Navigation fleet starship" value={craft.id} onChange={event => { const selected = fleet.find(item => item.id === event.target.value); setCraftId(event.target.value); setActorId(''); patch({ origin: selected?.location || null, astromech_id: '', backup: false, character_points: 0, force_point: false, destination_visited: false, boarding_confirmed: false }); }}>{fleet.map(item => <option key={item.id} value={item.id}>{item.name} · {words(item.damage)}</option>)}</select></label><label>Assigned astrogator<select aria-label="Navigation astrogator" value={actor?.id ?? ''} onChange={event => { setActorId(event.target.value); patch({ character_points: 0, force_point: false, destination_visited: false }); }}>{assigned.length ? assigned.map(person => <option key={person.id} value={person.id}>{person.name} · Astrogation {person.d6.skills.astrogation ?? person.d6.attributes.mechanical}</option>) : <option value="">Assign a party member to this craft first</option>}</select></label></div>
        <p className="native-help">Location: {craft.location || 'not recorded'} · main hyperdrive {craft.hyperdrive_multiplier == null ? 'absent' : `×${craft.hyperdrive_multiplier}`}{craft.hyperdrive_disabled ? ' (disabled)' : ''} · backup {craft.backup_hyperdrive == null ? 'absent' : `×${craft.backup_hyperdrive}`} · navigation computer {craft.nav_computer && !craft.nav_computer_disabled ? 'working' : 'unavailable'}</p>
        <div className="native-form-row"><label>Origin system<input aria-label="Navigation origin" list="navigation-systems" maxLength={120} value={origin} onChange={event => patch({ origin: event.target.value })} /></label><label>Destination system<input aria-label="Navigation destination" list="navigation-systems" maxLength={120} value={form.destination} onChange={event => patch({ destination: event.target.value, destination_visited: false })} /></label></div>
        {actor?.d6.species_id === 'sullustan' && <>{destinationVisited ? <p className="native-help">{form.destination} is already recorded in {actor.name}'s visited locations; the Sullustan Astrogation bonus applies.</p> : <label className="native-checkbox"><input aria-label="Navigation destination previously visited" type="checkbox" checked={form.destination_visited} onChange={event => patch({ destination_visited: event.target.checked })} />GM confirms this destination was previously visited</label>}</>}
        <p className="native-help">{gazetteer ? `Gazetteer base duration: ${gazetteer.printed_duration} (${gazetteer.hours} hours), either direction.` : 'Outside the printed gazetteer: enter a GM base duration.'}</p>
        <div className="native-form-row"><label>{gazetteer ? 'GM base hours override (optional)' : 'GM base duration in hours'}<input aria-label="Navigation base hours" type="number" min={0.000001} max={100000} step="any" placeholder={gazetteer ? String(gazetteer.hours) : 'Required for a custom route'} value={form.baseHours} onChange={event => patch({ baseHours: event.target.value })} /></label><label>Route frequency<select aria-label="Navigation route frequency" value={form.route_type} onChange={event => patch({ route_type: event.target.value as RouteType })}>{Object.entries(catalog?.route_types ?? factors).map(([key, factor]) => <option key={key} value={key}>{words(key)} · ×{factor}</option>)}</select></label><label>GM base difficulty<input aria-label="Navigation base difficulty" type="number" min={1} max={1000} value={form.base_difficulty} onChange={event => patch({ base_difficulty: Number(event.target.value) })} /></label></div>
        <div className="native-form-row"><label>Obstacle difficulty increase<input aria-label="Navigation obstacle difficulty" type="number" min={0} max={1000} value={form.obstacles} onChange={event => patch({ obstacles: Number(event.target.value) })} /></label><label>Actual extra travel hours<input aria-label="Navigation extra travel hours" type="number" min={-100000} max={100000} value={form.extra_hours} onChange={event => patch({ extra_hours: Number(event.target.value) })} /></label><label>Plotting time (rounds)<input aria-label="Navigation plotting rounds" type="number" min={1} max={172800} value={form.plotting_rounds} onChange={event => patch({ plotting_rounds: Number(event.target.value) })} /></label><label>Planet clearance (space units)<input aria-label="Navigation planetary clearance" type="number" min={0} max={1000000} step="any" value={form.clearance_units} onChange={event => patch({ clearance_units: Number(event.target.value) })} /></label></div>
        <p className="native-help">Extra actual hours reduce difficulty one per hour; negative hours shorten travel and increase difficulty. Clearance must be at least 50 space units. Hasty entry doubles the subtotal difficulty and duration.</p>
        <div className="native-button-row"><label className="native-checkbox"><input type="checkbox" checked={form.backup} onChange={event => patch({ backup: event.target.checked })} />Use installed backup hyperdrive</label><label className="native-checkbox"><input type="checkbox" checked={form.hasty} onChange={event => patch({ hasty: event.target.checked })} />Hasty entry</label><label className="native-checkbox"><input type="checkbox" checked={form.boarding_confirmed} onChange={event => patch({ boarding_confirmed: event.target.checked })} />Confirm party and assigned crew are aboard</label></div>
        <label>Assigned R2 with preprogrammed jump<select aria-label="Navigation astromech" value={astromech?.id ?? ''} onChange={event => patch({ astromech_id: event.target.value })}><option value="">Use ship navigation computer / unaided astrogation</option>{astromechs.map(person => <option key={person.id} value={person.id}>{person.name} · {person.d6.droid?.route_memory?.length ?? 0}/10 routes stored</option>)}</select></label>
        {astromech && <p className="native-help">{programmed ? `${astromech.name} has this jump preprogrammed.` : `${astromech.name} has no stored data for this route. Record actual downloaded/preprogrammed data below before using R2 navigation support.`}</p>}
        <div className="native-form-row"><label>Astrogation Character Points<input aria-label="Navigation Character Points" type="number" min={0} max={Math.min(2, actor?.d6.character_points ?? 0)} disabled={form.force_point} value={form.character_points} onChange={event => patch({ character_points: Number(event.target.value) })} /></label><label className="native-checkbox"><input type="checkbox" checked={form.force_point} disabled={!actor?.d6.force_points} onChange={event => patch({ force_point: event.target.checked, character_points: 0 })} />Spend astrogator's Force Point</label><span>{actor?.d6.character_points ?? 0} CP · {actor?.d6.force_points ?? 0} FP available</span></div>
        <label>GM route facts and conditions<textarea aria-label="Navigation route reason" rows={2} maxLength={1000} value={form.reason} onChange={event => patch({ reason: event.target.value })} /></label>
        <div className="native-button-row"><button className="hp-btn" disabled={pending || combat || !canReview || !pointChoiceValid} onClick={preview}>Review route calculation</button><button className="hp-btn" disabled={pending || combat || !quote || !canReview || !pointChoiceValid || session.updated_at == null} onClick={() => run('plot', payload)}>Plot route and roll Astrogation</button></div>
        {quote && <section className="native-training-card" aria-label="Reviewed hyperspace route"><strong>Difficulty {quote.difficulty} · {quote.hours} hours · hyperdrive ×{quote.multiplier}</strong><p>{quote.has_navigation ? 'Navigation computer / stored R2 route available' : 'Unaided astrogation: +30 difficulty and doubled travel subtotal'} · {quote.rounds} travel rounds · {form.plotting_rounds} plotting rounds</p>{quote.notes.map((note, index) => <p key={index} className="native-help">{note}</p>)}</section>}
        {review && !quote && <p className="native-help">The route, craft, crew, or adventure changed. Review the current calculation before plotting.</p>}
        {session.updated_at == null && <p className="native-help">Refresh this adventure to obtain its current revision before plotting.</p>}
      </>}
    </>}
    <datalist id="navigation-systems">{catalog?.systems.map(system => <option key={system} value={system} />)}</datalist>
    {!!r2Units.length && <details><summary>R2 preprogrammed route memory</summary><p className="native-help">An R2 stores up to ten actual preprogrammed jumps, in either direction. Record GM-confirmed downloaded route data; completed travel alone does not install a route.</p><label>R2 astromech<select aria-label="Navigation route memory R2" value={memoryUnit?.id ?? ''} onChange={event => setMemoryActorId(event.target.value)}>{r2Units.map(person => <option key={person.id} value={person.id}>{person.name}</option>)}</select></label><p>{memory.length}/10 preprogrammed jump slots used</p>{memory.map((route, index) => <p className="native-help" key={index}>{route.origin} ↔ {route.destination} · {route.reason}</p>)}<div className="native-form-row"><label>Stored route origin<input aria-label="Navigation route memory origin" list="navigation-systems" maxLength={120} value={memoryOrigin} onChange={event => setMemoryOrigin(event.target.value)} /></label><label>Stored route destination<input aria-label="Navigation route memory destination" list="navigation-systems" maxLength={120} value={memoryDestination} onChange={event => setMemoryDestination(event.target.value)} /></label></div><label>Actual downloaded / preprogrammed data and GM reason<textarea aria-label="Navigation route memory reason" rows={2} maxLength={1000} value={memoryReason} onChange={event => setMemoryReason(event.target.value)} /></label><button className="hp-btn" disabled={pending || memory.length >= 10 || !memoryOrigin.trim() || !memoryDestination.trim() || memoryOrigin.trim().toLowerCase() === memoryDestination.trim().toLowerCase() || !memoryReason.trim() || memory.some(route => routeMatches(route, memoryOrigin, memoryDestination))} onClick={async () => { if (await run('route-memory', { actor_id: memoryUnit?.id, origin: memoryOrigin, destination: memoryDestination, reason: memoryReason })) setMemoryReason(''); }}>Record preprogrammed route data</button></details>}
    {!!journeys.length && <details><summary>Saved journeys ({journeys.length})</summary>{[...journeys].reverse().map(journey => <section key={journey.id} className="native-training-card"><strong>{journey.request.origin} → {journey.request.destination} · {words(journey.status)}</strong><p className="native-help">Astrogation {journey.roll.total} vs. {journey.quote.difficulty} · {hours(journey.elapsed_rounds)} elapsed{journey.mishap !== null ? ` · mishap ${journey.mishap}` : ''}</p>{journey.auxiliary_rolls.map((roll, index) => <p className="native-help" key={`roll-${index}`}>Plain dice: {roll.breakdown || roll.total}</p>)}{journey.resolution.map((line, index) => <p className="native-help" key={index}>{line}</p>)}</section>)}</details>}
    <p className="native-help">{catalog?.source ?? 'WEG Second Edition (1992), printed pp.110–112.'}</p>
  </details>;
}
