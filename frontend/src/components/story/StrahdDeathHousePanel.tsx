import { useEffect, useRef, useState } from 'react';
import { API_BASE } from '../../services/api';
import type { GameSession } from '../../types';

type Actor = { id: string; name: string };
type Event = { id: string; action: string; reason: string; actors: { actor_id: string; name: string }[]; status_before: string; status_after: string; pips_before: number; pips_after: number; floor: string | null; room: string | null; skill: string | null; chimes: string[]; reminders: string[]; source_path: string };
type Clock = { status: string; remaining_pips: number; dice: number[]; clock_label: string; remaining_minutes: number | null; clock_running: boolean; visited_floors: string[]; events: Event[]; source_path: string; floors: { id: string; title: string; rooms: string[] }[]; rules: string[] };
type State = { updated_at: number; clock: Clock; actors: Actor[] };
type Payload = { event_id: string; action: string; actual_event_confirmed: boolean; actor_ids: string[]; reason: string; floor: string | null; room: string | null; skill: string | null; early_trigger: string | null; expected_updated_at: number };
const labels: Record<string, string> = { start: 'Start when the Main Hall clock strikes six', new_floor: 'Enter a new floor · 1 pip', room_search: 'Whole-room Perception / Investigation check · 1 pip', short_rest: 'Review short-rest time · 3 pips', awakens_early: 'Confirm the mound awakens early', mound_destroyed: 'Confirm actual mound destruction; begin escape', escaped: 'Confirm actual exit into Barovia' };
const words = (value: string) => value.replaceAll('_', ' ');

async function request<T>(action: string, body?: unknown, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`${API_BASE}/strahd/progress/death-house/${action}`, body === undefined ? { signal } : { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body), signal });
  if (!response.ok) {
    const value = await response.json().catch(() => null) as { detail?: string | { msg: string }[] } | null;
    throw new Error(typeof value?.detail === 'string' ? value.detail : Array.isArray(value?.detail) ? value.detail.map(item => item.msg).join('; ') : `Death House review failed (${response.status})`);
  }
  return response.json();
}

export function StrahdDeathHousePanel({ session, onSessionChanged }: { session: GameSession; onSessionChanged: (session: GameSession) => void }) {
  const [data, setData] = useState<State | null>(null);
  const [loaded, setLoaded] = useState('');
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [eventId, setEventId] = useState(() => crypto.randomUUID());
  const [actionId, setActionId] = useState('start');
  const [floorId, setFloorId] = useState('');
  const [roomId, setRoomId] = useState('');
  const [skill, setSkill] = useState('perception');
  const [earlyTrigger, setEarlyTrigger] = useState('');
  const [actors, setActors] = useState<string[]>([]);
  const [confirmed, setConfirmed] = useState(false);
  const [reason, setReason] = useState('');
  const [review, setReview] = useState<{ signature: string; payload: Payload; event: Event; clock: Clock } | null>(null);
  const ownRevision = useRef<number | null>(null);
  const query = JSON.stringify({ id: session.id, revision: session.updated_at, actors: session.character });
  useEffect(() => {
    const controller = new AbortController();
    request<State>('state', undefined, controller.signal).then(value => { setData(value); if (ownRevision.current !== value.updated_at) { setNotice(''); setReview(null); } }).catch(err => { if (!controller.signal.aborted) setError(String(err)); }).finally(() => { if (!controller.signal.aborted) setLoaded(query); });
    return () => controller.abort();
  }, [query]);
  const clock = data?.clock;
  const actions = clock?.status === 'unstarted' ? ['start'] : clock?.status === 'exploring' ? [...(clock.visited_floors.length < clock.floors.length ? ['new_floor'] : []), 'room_search', 'short_rest', 'awakens_early', 'mound_destroyed'] : ['hunting', 'awakened_early'].includes(clock?.status ?? '') ? ['mound_destroyed'] : clock?.status === 'escaping' ? ['escaped'] : [];
  const action = actions.includes(actionId) ? actionId : actions[0] ?? '';
  const needsFloor = ['new_floor', 'room_search', 'short_rest'].includes(action);
  const floors = clock?.floors.filter(floor => action === 'new_floor' ? !clock.visited_floors.includes(floor.id) : clock.visited_floors.includes(floor.id)) ?? [];
  const floor = floors.find(item => item.id === floorId) ?? floors[0];
  const room = floor?.rooms.includes(roomId) ? roomId : floor?.rooms[0] ?? '';
  const present = data?.actors.map(actor => actor.id) ?? [];
  const payload: Payload = { event_id: eventId, action, actual_event_confirmed: confirmed, actor_ids: actors.filter(id => present.includes(id)), reason, floor: needsFloor ? floor?.id ?? null : null, room: action === 'room_search' ? room : null, skill: action === 'room_search' ? skill : null, early_trigger: action === 'awakens_early' ? earlyTrigger || null : null, expected_updated_at: Math.max(data?.updated_at ?? 0, session.updated_at ?? 0) };
  const signature = JSON.stringify({ query, payload });
  const quote = review?.signature === signature ? review : null;
  const disabled = pending || loaded !== query || Boolean(session.encounter?.active || session.vehicle_encounter);
  const canReview = Boolean(action && confirmed && reason.trim() && payload.actor_ids.length && (!needsFloor || floor) && (action !== 'awakens_early' || earlyTrigger));
  return <details className="native-training-card" aria-label="Death House GM clock">
    <summary>Death House · GM source clock & actual events</summary>
    <p className="native-help">Start only after the Main Hall clock actually strikes six. This is a GM ledger for Arc A. Source events change its dice clock; encounters, rest recovery and XP require separate actual resolution.</p>
    {error && <p className="native-error" role="alert">{error}</p>}{notice && <p role="status">{notice}</p>}
    {clock && <section aria-label="Saved Death House clock"><strong>{words(clock.status)} · {clock.clock_label}</strong><p>{clock.status === 'unstarted' ? 'Prior elapsed time and house events are unknown.' : `${clock.remaining_pips} pips · ${clock.remaining_minutes} countdown minutes remain${clock.clock_running ? '' : ' · exploration clock stopped'}`}</p>{clock.status !== 'unstarted' && <p aria-label="Death House dice" style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>{clock.dice.length ? clock.dice.map((value, index) => <span key={index} style={{ border: '1px solid currentColor', borderRadius: 5, minWidth: 32, padding: '5px 8px', textAlign: 'center', fontWeight: 700 }}>{value}</span>) : 'No dice remain · midnight reached'}</p>}{clock.status === 'hunting' && <p className="native-error">The mound is awake and pursuing the party. Allow at least one minute before contact; Heavy Sleeper has expired on arrival. Resolve pursuit / combat with the GM.</p>}{clock.status === 'awakened_early' && <p>The mound woke before midnight. Resolve its first minute of Heavy Sleeper, any surprise and the portcullis with the GM.</p>}{clock.status === 'escaping' && <p>The front door is open. Gustav and the cult figments still need actual resolution; exit is not yet recorded.</p>}{clock.status === 'escaped' && <p>The actual exit is recorded. Review the first long-rest milestone separately; this clock awarded no XP or class levels.</p>}</section>}
    <fieldset disabled={disabled} style={{ border: 0, padding: 0, margin: 0, minWidth: 0 }}>
      {Boolean(session.encounter?.active || session.vehicle_encounter) && <p>Finish the active encounter before reviewing its actual outcome.</p>}
      {!!actions.length && <><label>Actual source event<select aria-label="Death House event" value={action} onChange={event => { setActionId(event.target.value); setConfirmed(false); setReview(null); }}>{actions.map(id => <option key={id} value={id}>{labels[id]}</option>)}</select></label>
        {needsFloor && <label>Actual floor<select aria-label="Death House floor" value={floor?.id ?? ''} onChange={event => { setFloorId(event.target.value); setRoomId(''); }}>{floors.map(item => <option key={item.id} value={item.id}>{item.title}</option>)}</select></label>}
        {action === 'room_search' && <><label>Whole room searched<select aria-label="Death House room" value={room} onChange={event => setRoomId(event.target.value)}>{floor?.rooms.map(name => <option key={name} value={name}>{name}</option>)}</select></label><label>Actual check<select aria-label="Death House search skill" value={skill} onChange={event => setSkill(event.target.value)}><option value="perception">Perception</option><option value="investigation">Investigation</option></select></label><p className="native-help">Use this after the actual entire-room check. It records time without rerolling the check. Targeted inspections do not automatically count as whole-room searches.</p></>}
        {action === 'awakens_early' && <label>Actual cause<select aria-label="Death House awakening cause" value={earlyTrigger} onChange={event => setEarlyTrigger(event.target.value)}><option value="">Select the actual source trigger</option><option value="mound_attacked">The sleeping mound was attacked</option><option value="tendrils_damaged">Its tendrils were damaged</option></select></label>}
        {action === 'short_rest' && <p className="native-help">A short rest costs three pips. Main-house rests bring one or more hauntings. At midnight resolve the approaching mound and whether the rest can finish. This review does not heal or restore resources; record actual recovery separately.</p>}
        {action === 'mound_destroyed' && <p className="native-help">Confirm actual destruction after resolving the encounter. Sacrifice cannot satisfy its hunger or open the exit.</p>}
        {action === 'escaped' && <p className="native-help">Confirm the party actually passed the escape obstacles and exited into Barovia. This review does not remove, recruit or relocate any sheet actor.</p>}
        <p>Actual party actors involved</p>{data?.actors.map(person => <label className="native-checkbox" key={person.id}><input type="checkbox" aria-label={`Death House actor ${person.name}`} checked={actors.includes(person.id)} onChange={event => setActors(previous => event.target.checked ? [...previous, person.id] : previous.filter(id => id !== person.id))} />{person.name}</label>)}
        <label>Actual event evidence and GM ruling<textarea aria-label="Death House event evidence" maxLength={2000} rows={2} value={reason} onChange={event => setReason(event.target.value)} /></label><label className="native-checkbox"><input type="checkbox" aria-label="Confirm actual Death House event" checked={confirmed} onChange={event => setConfirmed(event.target.checked)} />GM confirms the selected event actually occurred and has not already been accounted for</label>
        <button className="hp-btn" disabled={!canReview} onClick={async () => { setPending(true); setError(''); setReview(null); try { const response = await request<{ event: Event; clock: Clock }>('quote', payload); setReview({ signature, payload, ...response }); } catch (err) { setError(err instanceof Error ? err.message : String(err)); } finally { setPending(false); } }}>Preview Death House event</button>
        {quote && <section className="native-training-card" aria-label="Reviewed Death House event"><strong>{words(quote.event.status_after)} · {quote.clock.clock_label} · dice {quote.clock.dice.join(', ') || 'none'}</strong><p>Pips {quote.event.pips_before} → {quote.event.pips_after}{quote.event.chimes.length ? ` · chimes: ${quote.event.chimes.join(', ')}` : ''}</p>{quote.event.reminders.map(text => <p key={text}>{text}</p>)}<p className="native-help">Preview has changed no saved time, outcome, HP or XP.</p><button className="hp-btn" onClick={async () => { setPending(true); setError(''); try { const response = await request<{ session: GameSession; eval_result: { summary: string } }>('event', quote.payload); ownRevision.current = response.session.updated_at ?? null; onSessionChanged(response.session); setNotice(response.eval_result.summary); setReview(null); setConfirmed(false); setReason(''); setEventId(crypto.randomUUID()); } catch (err) { setReview(null); setError(err instanceof Error ? err.message : String(err)); await request<State>('state').then(setData).catch(() => {}); } finally { setPending(false); } }}>Commit reviewed Death House event</button></section>}
      </>}
    </fieldset>
    {!!clock?.events.length && <details><summary>Saved actual house events ({clock.events.length})</summary>{[...clock.events].reverse().map(event => <section className="native-training-card" key={event.id}><strong>{words(event.action)} · {event.pips_before} → {event.pips_after} pips</strong><p>{event.reason}</p><p>{event.actors.map(person => person.name).join(', ')}{event.floor ? ` · ${event.floor}` : ''}{event.room ? ` · ${event.room}` : ''}{event.skill ? ` · ${event.skill}` : ''}</p>{event.reminders.map(text => <p className="native-help" key={text}>{text}</p>)}<p className="native-help">{event.source_path}</p></section>)}</details>}
    <details><summary>Source procedures and limits</summary>{clock?.rules.map(note => <p className="native-help" key={note}>{note}</p>)}<p className="native-help">{clock?.source_path} · Main Hall / Time in Death House; Ritual Chamber; Escape From Death House; Outside Death House.</p></details>
  </details>;
}
