import { useEffect, useRef, useState } from 'react';
import { API_BASE } from '../../services/api';
import type { GameSession } from '../../types';

type Actor = { id: string; name: string };
type Spirit = { id: string; name: string; host_id: string | null; host_name: string | null; remains_location: string; carrier_id: string | null; carrier_name: string | null };
type Event = { id: string; action: string; actor_id: string | null; actor_name: string | null; spirit: string | null; spell: string | null; reason: string; effects: string[]; source_path: string };
type Children = { met: boolean; diary_found: boolean; diary_holder_name: string | null; secret_revealed: boolean; burial_promised: boolean; invited: boolean; at_peace: boolean; spirits: Spirit[]; events: Event[]; permissions: { spirit: string; host_id: string; host_name: string; active: boolean; abilities: string[]; note: string; unavailable_reason: string | null }[]; house_status: string; source_path: string; rules: string[]; ability_catalog: Record<string, string[]> };
type State = { updated_at: number; children: Children; actors: Actor[] };
type Payload = { event_id: string; action: string; actor_id: string; spirit: string | null; spell: string | null; actual_event_confirmed: boolean; burial_promise_confirmed: boolean; friendly_host_confirmed: boolean; player_host_confirmed: boolean; host_consent_confirmed: boolean; spell_requirements_confirmed: boolean; reason: string; expected_updated_at: number };
const labels: Record<string, string> = { meet: 'Confirm actual meeting in the Children’s Room', find_diary: 'Record actual discovery of Rose’s diary', rose_bargain: 'Review Rose’s secret-entry bargain and burial promise', invite_children: 'Invite both children to accompany the party', consent_possession: 'Review one child’s consensual possession', release_possession: 'Confirm a recorded possession actually ended', take_remains: 'Record taking one child’s actual remains', transfer_remains: 'Record an actual handoff of remains', place_in_crypt: 'Place remains in the family crypt · does not bring peace', retrieve_remains: 'Retrieve actual remains from the family crypt', use_ability: 'Record an actual temporary ability use already resolved', bury_children: 'Confirm both children’s actual outside burial', leave_children: 'Depart without burial · quest remains unresolved' };
const spiritActions = ['consent_possession', 'release_possession', 'take_remains', 'transfer_remains', 'place_in_crypt', 'retrieve_remains', 'use_ability'];
const words = (value: string) => value.replaceAll('_', ' ');
async function request<T>(action: string, body?: unknown, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`${API_BASE}/strahd/progress/children/${action}`, body === undefined ? { signal } : { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body), signal });
  if (!response.ok) { const value = await response.json().catch(() => null) as { detail?: string | { msg: string }[] } | null; throw new Error(typeof value?.detail === 'string' ? value.detail : Array.isArray(value?.detail) ? value.detail.map(item => item.msg).join('; ') : `Children review failed (${response.status})`); }
  return response.json();
}

export function StrahdChildrenPanel({ session, onSessionChanged }: { session: GameSession; onSessionChanged: (session: GameSession) => void }) {
  const [data, setData] = useState<State | null>(null);
  const [loaded, setLoaded] = useState('');
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [eventId, setEventId] = useState(() => crypto.randomUUID());
  const [actionId, setActionId] = useState('meet');
  const [actorId, setActorId] = useState('');
  const [spiritId, setSpiritId] = useState('rose');
  const [spellId, setSpellId] = useState('');
  const [reason, setReason] = useState('');
  const [confirmed, setConfirmed] = useState(false);
  const [promise, setPromise] = useState(false);
  const [friendly, setFriendly] = useState(false);
  const [playerHost, setPlayerHost] = useState(false);
  const [consent, setConsent] = useState(false);
  const [requirements, setRequirements] = useState(false);
  const [review, setReview] = useState<{ signature: string; payload: Payload; event: Event } | null>(null);
  const ownRevision = useRef<number | null>(null);
  const query = JSON.stringify({ id: session.id, revision: session.updated_at, actors: session.character });
  useEffect(() => { const controller = new AbortController(); request<State>('state', undefined, controller.signal).then(value => { setData(value); if (ownRevision.current !== value.updated_at) { setNotice(''); setReview(null); } }).catch(err => { if (!controller.signal.aborted) setError(String(err)); }).finally(() => { if (!controller.signal.aborted) setLoaded(query); }); return () => controller.abort(); }, [query]);
  const children = data?.children;
  const inside = children?.house_status !== 'escaped';
  const actions = !children || children.at_peace ? [] : !children.met ? ['meet'] : [
    ...(inside && !children.diary_found ? ['find_diary'] : []), ...(inside && !children.secret_revealed ? ['rose_bargain'] : []),
    ...(inside && children.secret_revealed && !children.invited ? ['invite_children'] : []),
    ...(inside && children.invited && children.spirits.some(item => !item.host_id) ? ['consent_possession'] : []),
    ...(children.spirits.some(item => item.host_id) ? ['release_possession'] : []),
    ...(inside && children.spirits.some(item => item.remains_location === 'unreviewed') ? ['take_remains'] : []),
    ...(children.spirits.some(item => item.remains_location === 'carried') && (data?.actors.length ?? 0) > 1 ? ['transfer_remains'] : []),
    ...(inside && children.spirits.some(item => item.remains_location === 'carried') ? ['place_in_crypt'] : []),
    ...(inside && children.spirits.some(item => item.remains_location === 'family_crypt') ? ['retrieve_remains'] : []),
    ...(children.permissions.some(item => item.active) ? ['use_ability'] : []),
    ...(!inside && children.spirits.every(item => item.remains_location === 'carried') ? ['bury_children'] : []),
    ...(!inside && children.invited ? ['leave_children'] : []),
  ];
  const action = actions.includes(actionId) ? actionId : actions[0] ?? '';
  const spirits = children?.spirits.filter(item => action === 'consent_possession' ? !item.host_id : action === 'release_possession' ? Boolean(item.host_id) : action === 'take_remains' ? item.remains_location === 'unreviewed' : ['transfer_remains', 'place_in_crypt'].includes(action) ? item.remains_location === 'carried' : action === 'retrieve_remains' ? item.remains_location === 'family_crypt' : action === 'use_ability' ? children.permissions.some(permission => permission.spirit === item.id && permission.active) : true) ?? [];
  const spirit = spirits.find(item => item.id === spiritId) ?? spirits[0];
  const actors = data?.actors.filter(item => action === 'place_in_crypt' ? item.id === spirit?.carrier_id : action === 'transfer_remains' ? item.id !== spirit?.carrier_id : action === 'use_ability' ? item.id === spirit?.host_id : true) ?? [];
  const actor = actors.find(item => item.id === actorId) ?? actors[0];
  const spells = children?.ability_catalog[spirit?.id ?? ''] ?? [];
  const spell = spells.includes(spellId) ? spellId : spells[0];
  const payload: Payload = { event_id: eventId, action, actor_id: actor?.id ?? '', spirit: spiritActions.includes(action) ? spirit?.id ?? null : null, spell: action === 'use_ability' ? spell ?? null : null, actual_event_confirmed: confirmed, burial_promise_confirmed: action === 'rose_bargain' && promise, friendly_host_confirmed: ['invite_children', 'consent_possession'].includes(action) && friendly, player_host_confirmed: action === 'consent_possession' && playerHost, host_consent_confirmed: action === 'consent_possession' && consent, spell_requirements_confirmed: action === 'use_ability' && requirements, reason, expected_updated_at: Math.max(data?.updated_at ?? 0, session.updated_at ?? 0) };
  const signature = JSON.stringify({ query, payload });
  const quote = review?.signature === signature ? review : null;
  const disabled = pending || loaded !== query || Boolean(session.encounter?.active || session.vehicle_encounter);
  const canReview = Boolean(action && actor && confirmed && reason.trim() && (!spiritActions.includes(action) || spirit) && (action !== 'rose_bargain' || promise) && (!['invite_children', 'consent_possession'].includes(action) || friendly) && (action !== 'consent_possession' || playerHost && consent) && (action !== 'use_ability' || spell && requirements));
  return <details className="native-training-card" aria-label="Durst children GM quest">
    <summary>Rose & Thorn · actual alliance & burial quest</summary>
    <p className="native-help">GM source workflow for the children’s actual conversation, willing hosts and remains. Temporary spirit permissions stay in this ledger; permanent known spells, class features and generic companion sheets are unchanged.</p>
    {error && <p className="native-error" role="alert">{error}</p>}{notice && <p role="status">{notice}</p>}
    {children && <section aria-label="Saved Durst children quest"><strong>{children.at_peace ? 'Both children are at peace' : children.met ? 'Actual meeting recorded · outside burial unresolved' : 'Meeting and prior aid unreviewed'}</strong><p>Rose’s bargain: {children.secret_revealed ? 'secret entry revealed; burial promised' : 'not reviewed'} · children accompanying: {children.invited ? 'actually invited' : 'not recorded as accompanying'}</p>{children.diary_found && <p>Actual diary holder: {children.diary_holder_name}. Discovery grants no permanent known spells.</p>}{children.spirits.map(item => <p key={item.id}><strong>{item.name}</strong> · host: {item.host_name ?? 'none recorded'} · remains: {words(item.remains_location)}{item.carrier_name ? ` by ${item.carrier_name}` : ''}{item.remains_location === 'family_crypt' ? ' · this does not bring peace' : ''}</p>)}{children.permissions.map(permission => <section className="native-training-card" key={permission.spirit}><strong>{permission.host_name} · {permission.spirit}’s temporary aid</strong><p>{permission.active ? permission.abilities.join(' · ') : permission.unavailable_reason}</p><p className="native-help">{permission.note}</p></section>)}{!inside && children.invited && !children.at_peace && <p>The invited children refuse to proceed farther into Barovia and ask for their actual outside burial. House exit has ended their possessions.</p>}</section>}
    <fieldset disabled={disabled} style={{ border: 0, padding: 0, margin: 0, minWidth: 0 }}>
      {Boolean(session.encounter?.active || session.vehicle_encounter) && <p>Finish the active encounter before reviewing these actual source events.</p>}
      {!!actions.length && <><label>Actual children event<select aria-label="Durst children event" value={action} onChange={event => { setActionId(event.target.value); setConfirmed(false); setPromise(false); setFriendly(false); setPlayerHost(false); setConsent(false); setRequirements(false); setReview(null); }}>{actions.map(id => <option key={id} value={id}>{labels[id]}</option>)}</select></label>
        {spiritActions.includes(action) && <label>Actual child / remains<select aria-label="Durst child spirit" value={spirit?.id ?? ''} onChange={event => { setSpiritId(event.target.value); setConsent(false); setPlayerHost(false); setReview(null); }}>{spirits.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>}
        <label>{action === 'consent_possession' ? 'Actual willing player host' : ['take_remains', 'transfer_remains', 'retrieve_remains', 'place_in_crypt'].includes(action) ? 'Actual remains carrier' : 'Actual party actor'}<select aria-label="Durst children actor" value={actor?.id ?? ''} onChange={event => { setActorId(event.target.value); setConsent(false); setPlayerHost(false); setReview(null); }}>{actors.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
        {action === 'rose_bargain' && <label className="native-checkbox"><input type="checkbox" aria-label="Durst burial promise" checked={promise} onChange={event => setPromise(event.target.checked)} />GM confirms the party actually agreed to take both children’s bones and bury them outside</label>}
        {['invite_children', 'consent_possession'].includes(action) && <label className="native-checkbox"><input type="checkbox" aria-label="Durst friendly invitation or host" checked={friendly} onChange={event => setFriendly(event.target.checked)} />GM confirms the actual friendly invitation / host relationship</label>}
        {action === 'consent_possession' && <><label className="native-checkbox"><input type="checkbox" aria-label="Durst actual player host" checked={playerHost} onChange={event => setPlayerHost(event.target.checked)} />GM confirms this is an actual player-controlled character</label><label className="native-checkbox"><input type="checkbox" aria-label="Durst explicit host consent" checked={consent} onChange={event => setConsent(event.target.checked)} />This actual player explicitly permits this child’s possession</label><p className="native-help">Permission is temporary. Another host cannot be added to the same spirit until the current possession actually ends.</p></>}
        {action === 'use_ability' && <><label>Actual temporary ability<select aria-label="Durst temporary ability" value={spell ?? ''} onChange={event => setSpellId(event.target.value)}>{spells.map(name => <option key={name} value={name}>{name}</option>)}</select></label><label className="native-checkbox"><input type="checkbox" aria-label="Durst actual spell requirements reviewed" checked={requirements} onChange={event => setRequirements(event.target.checked)} />GM confirms the normal time, range, required components, checks and actual effects were separately resolved</label><p className="native-help">Record an actual use after normal Cast / GM resolution. This button does not roll an attack, apply a spell effect or spend a slot. Thorn’s invisible Mage Hand takes an action without components.</p></>}
        {action === 'place_in_crypt' && <p className="native-help">The source explicitly says dungeon coffins do not bring peace. Possession and the promised outside burial remain unresolved.</p>}
        {action === 'bury_children' && <p className="native-help">Both sets of actual remains must be carried by present party members after actual house exit. This review releases the children and grants no XP or permanent magic.</p>}
        {action === 'leave_children' && <p className="native-help">Record an actual departure without burial. The children do not follow farther into Barovia; their promised burial remains unfinished.</p>}
        <label>Actual event evidence and GM ruling<textarea aria-label="Durst children event evidence" rows={2} maxLength={2000} value={reason} onChange={event => setReason(event.target.value)} /></label><label className="native-checkbox"><input type="checkbox" aria-label="Confirm actual Durst children event" checked={confirmed} onChange={event => setConfirmed(event.target.checked)} />GM confirms this actual event occurred and has not already been recorded</label>
        <button className="hp-btn" disabled={!canReview} onClick={async () => { setPending(true); setError(''); setReview(null); try { const response = await request<{ event: Event }>('quote', payload); setReview({ signature, payload, event: response.event }); } catch (err) { setError(err instanceof Error ? err.message : String(err)); } finally { setPending(false); } }}>Preview Durst children event</button>
        {quote && <section className="native-training-card" aria-label="Reviewed Durst children event"><strong>{words(quote.event.action)}</strong>{quote.event.effects.map(text => <p key={text}>{text}</p>)}<p className="native-help">Preview has changed no saved allies, hosts, remains, spells or XP.</p><button className="hp-btn" onClick={async () => { setPending(true); setError(''); try { const response = await request<{ session: GameSession; eval_result: { summary: string } }>('event', quote.payload); ownRevision.current = response.session.updated_at ?? null; onSessionChanged(response.session); setNotice(response.eval_result.summary); setReview(null); setConfirmed(false); setReason(''); setPromise(false); setFriendly(false); setPlayerHost(false); setConsent(false); setRequirements(false); setEventId(crypto.randomUUID()); } catch (err) { setReview(null); setError(err instanceof Error ? err.message : String(err)); await request<State>('state').then(setData).catch(() => {}); } finally { setPending(false); } }}>Commit reviewed Durst children event</button></section>}
      </>}
    </fieldset>
    {!!children?.events.length && <details><summary>Saved actual children events ({children.events.length})</summary>{[...children.events].reverse().map(event => <section className="native-training-card" key={event.id}><strong>{words(event.action)}{event.actor_name ? ` · ${event.actor_name}` : ''}</strong><p>{event.reason}</p>{event.effects.map(text => <p className="native-help" key={text}>{text}</p>)}<p className="native-help">{event.source_path}</p></section>)}</details>}
    <details><summary>Children source procedures and limits</summary>{children?.rules.map(note => <p className="native-help" key={note}>{note}</p>)}<p className="native-help">{children?.source_path} · Children’s Room; Family Crypts; Outside Death House.</p></details>
  </details>;
}
