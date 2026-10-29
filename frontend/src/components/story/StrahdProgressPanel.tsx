import { useEffect, useRef, useState } from 'react';
import { API_BASE } from '../../services/api';
import type { GameSession } from '../../types';
import { StrahdDeathHousePanel } from './StrahdDeathHousePanel';
import { StrahdChildrenPanel } from './StrahdChildrenPanel';
import '../sidebar/D6.css';

type Actor = { id: string; name: string; sheet_level: number; registered: boolean; baseline_xp: number | null; awarded_xp: number | null; total_xp: number | null; xp_level: number | null; level_up_pending: boolean };
type Milestone = { id: string; title: string; arcs: string[]; xp_per_pc: number | null; variants: Record<string, number>; trigger: string; source_path: string; prerequisite_ids: string[]; notes: string[]; claimed: boolean; prerequisites_met: boolean };
type Review = { actor_id: string; eligible: boolean; reason: string };
type Award = { id: string; milestone_id: string; title: string; variant: string | null; xp_per_pc: number; reason: string; trigger: string; source_path: string; reviews: Review[]; allocations: { actor_id: string; name: string; xp: number; total_xp: number; sheet_level: number; xp_level: number; level_up_pending: boolean }[] };
type State = { updated_at: number; actors: Actor[]; catalog: Milestone[]; arcs: { id: string; title: string; act: string; status: string; reason: string | null }[]; progress: { awards: Award[]; arc_reviews: { id: string; arc: string; status: string; reason: string }[]; death_house: { status: string } }; rules: { notes: string[]; xp_source: string } };
type Request = { milestone_id: string; variant: string | null; completion_confirmed: boolean; reason: string; reviews: Review[]; expected_updated_at: number | null };
const words = (value: string) => value.replaceAll('_', ' ');

async function request<T>(action: string, body?: unknown, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`${API_BASE}/strahd/progress/${action}`, body === undefined ? { signal } : { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body), signal });
  if (!response.ok) {
    const data = await response.json().catch(() => null) as { detail?: string | { msg: string }[] } | null;
    throw new Error(typeof data?.detail === 'string' ? data.detail : Array.isArray(data?.detail) ? data.detail.map(item => item.msg).join('; ') : `Campaign progress request failed (${response.status})`);
  }
  return response.json();
}

export function StrahdProgressPanel({ session, onSessionChanged }: { session: GameSession; onSessionChanged: (session: GameSession) => void }) {
  const [data, setData] = useState<State | null>(null);
  const [loadedSignature, setLoadedSignature] = useState('');
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [enrollId, setEnrollId] = useState('');
  const [baseline, setBaseline] = useState(0);
  const [pcConfirmed, setPCConfirmed] = useState(false);
  const [baselineReason, setBaselineReason] = useState('');
  const [milestoneId, setMilestoneId] = useState('');
  const [variant, setVariant] = useState('');
  const [confirmed, setConfirmed] = useState(false);
  const [reason, setReason] = useState('');
  const [reviews, setReviews] = useState<Record<string, { eligible: boolean; reason: string }>>({});
  const [review, setReview] = useState<{ signature: string; payload: Request; quote: Award } | null>(null);
  const [arcId, setArcId] = useState('A');
  const [arcStatus, setArcStatus] = useState('active');
  const [arcReason, setArcReason] = useState('');
  const lastMutationRevision = useRef<number | null>(null);
  const actorSignature = JSON.stringify(session.character);
  const querySignature = JSON.stringify({ id: session.id, revision: session.updated_at, actorSignature });
  const loading = loadedSignature !== querySignature;
  useEffect(() => {
    const controller = new AbortController();
    request<State>('state', undefined, controller.signal).then(value => { setData(value); if (lastMutationRevision.current !== value.updated_at) { setNotice(''); setReview(null); } }).catch(err => { if (!controller.signal.aborted) setError(String(err)); }).finally(() => { if (!controller.signal.aborted) setLoadedSignature(querySignature); });
    return () => controller.abort();
  }, [querySignature]);
  const unregistered = data?.actors.filter(actor => !actor.registered) ?? [];
  const actor = unregistered.find(person => person.id === enrollId) ?? unregistered[0];
  const registered = data?.actors.filter(person => person.registered) ?? [];
  const available = data?.catalog.filter(item => !item.claimed) ?? [];
  const milestone = available.find(item => item.id === milestoneId) ?? available[0];
  const variants = Object.entries(milestone?.variants ?? {});
  const revision = Math.max(data?.updated_at ?? 0, session.updated_at ?? 0);
  const payload: Request = { milestone_id: milestone?.id ?? '', variant: variants.length ? variant || null : null, completion_confirmed: confirmed, reason, reviews: registered.map(person => ({ actor_id: person.id, eligible: reviews[person.id]?.eligible ?? false, reason: reviews[person.id]?.reason ?? '' })), expected_updated_at: revision ?? null };
  const signature = JSON.stringify({ session: session.id, actorSignature, payload });
  const quote = review?.signature === signature ? review : null;
  const combat = Boolean(session.encounter?.active || session.vehicle_encounter);
  const unresolvedHouse = Boolean(milestone?.id === 'a_escape_rest' && data?.progress.death_house && !['unstarted', 'escaped'].includes(data.progress.death_house.status));
  const canReview = Boolean(!unresolvedHouse && milestone && milestone.prerequisites_met && confirmed && reason.trim() && registered.length && payload.reviews.every(item => item.reason.trim()) && payload.reviews.some(item => item.eligible) && (!variants.length || variants.some(([key]) => key === variant)));
  async function mutate(action: string, body: unknown) {
    setPending(true); setError(''); setNotice('');
    try {
      const result = await request<{ session: GameSession; eval_result?: { summary: string } }>(action, body);
      lastMutationRevision.current = result.session.updated_at ?? null;
      onSessionChanged(result.session);
      setReview(null);
      setNotice(result.eval_result?.summary ?? 'Campaign progress saved.');
      return true;
    } catch (err) { setReview(null); setError(err instanceof Error ? err.message : String(err)); await request<State>('state').then(setData).catch(() => {}); return false; }
    finally { setPending(false); }
  }
  return <details name="campaign-tools" className="native-force-panel" style={{ maxHeight: 'min(58vh, calc(100dvh - 290px))' }}>
    <summary>Strahd campaign progress & milestone XP</summary>
    <StrahdDeathHousePanel session={session} onSessionChanged={onSessionChanged} />
    <StrahdChildrenPanel session={session} onSessionChanged={onSessionChanged} />
    <p className="native-help">Reloaded awards XP at specific story milestones. Confirm actual completion and review every enrolled player character. Monster kills and narration grant no automatic XP. Saved XP guidance leaves class, HP and spell changes for the separate level-up review.</p>
    {error && <p className="native-error" role="alert">{error}</p>}{notice && <p role="status">{notice}</p>}{loading && <p>Loading campaign progress…</p>}
    <fieldset disabled={pending || loading || combat} style={{ border: 0, padding: 0, margin: 0, minWidth: 0 }}>
      {combat && <p className="native-help">Finish the current encounter before reviewing campaign awards.</p>}
      {!!data?.actors.length && <section className="native-training-card" aria-label="Strahd party experience"><h4>Actual player characters</h4>{data.actors.map(person => <p key={person.id}>{person.name} · sheet level {person.sheet_level} · {person.registered ? `${person.total_xp?.toLocaleString()} XP (${person.baseline_xp?.toLocaleString()} recorded baseline + ${person.awarded_xp?.toLocaleString()} awarded here)` : 'XP baseline not recorded'}{person.level_up_pending ? ` · level ${person.xp_level} sheet review pending` : ''}</p>)}</section>}
      {actor && <details><summary>Register an actual player character and existing XP</summary><p className="native-help">Legacy saves have unknown prior XP and milestones. Enter an actual absolute XP baseline and its source; NPC companions are enrolled only when the GM explicitly confirms that a player controls them.</p><label>Player character<select aria-label="Strahd XP character" value={actor.id} onChange={event => { setEnrollId(event.target.value); setPCConfirmed(false); }}>{unregistered.map(person => <option key={person.id} value={person.id}>{person.name} · sheet level {person.sheet_level}</option>)}</select></label><label>Actual existing XP<input aria-label="Strahd baseline XP" type="number" min={0} max={1000000000} step={1} value={baseline} onChange={event => setBaseline(Number(event.target.value))} /></label><label className="native-checkbox"><input type="checkbox" checked={pcConfirmed} onChange={event => setPCConfirmed(event.target.checked)} />GM confirms this is an actual player-controlled character</label><label>XP baseline evidence and GM reason<textarea aria-label="Strahd XP baseline reason" rows={2} maxLength={1000} value={baselineReason} onChange={event => setBaselineReason(event.target.value)} /></label><button className="hp-btn" disabled={!pcConfirmed || !baselineReason.trim() || !Number.isInteger(baseline) || baseline < 0 || baseline > 1000000000} onClick={async () => { if (await mutate('register', { actors: [{ actor_id: actor.id, baseline_xp: baseline, reason: baselineReason, pc_confirmed: true }], expected_updated_at: revision })) { setPCConfirmed(false); setBaselineReason(''); } }}>Save actual XP baseline</button></details>}
      {milestone && <section aria-label="Strahd milestone review"><h4>Review an unclaimed source milestone</h4><label>Source milestone<select aria-label="Strahd milestone" value={milestone.id} onChange={event => { setMilestoneId(event.target.value); setVariant(''); setConfirmed(false); setReview(null); }}>{available.map(item => <option key={item.id} value={item.id}>Arc {item.arcs.join('/')} · {item.title} · {item.xp_per_pc == null ? 'conditional XP' : `${item.xp_per_pc} XP each`}</option>)}</select></label><p><strong>Actual trigger:</strong> {milestone.trigger}</p>{milestone.notes.map(note => <p className="native-help" key={note}>{note}</p>)}<p className="native-help">{milestone.source_path}</p>{!milestone.prerequisites_met && <p className="native-error">Required earlier awards must be recorded before this bonus can be claimed.</p>}
        {unresolvedHouse && <p className="native-error">The saved Death House clock still records the party inside. Confirm the actual exit in its GM clock before reviewing the first post-escape long-rest award.</p>}
        {!!variants.length && <label>Actual source outcome<select aria-label="Strahd milestone outcome" value={variant} onChange={event => setVariant(event.target.value)}><option value="">Choose the actual outcome</option>{variants.map(([key, xp]) => <option key={key} value={key}>{words(key)} · {xp} XP per eligible PC</option>)}</select></label>}
        <label className="native-checkbox"><input type="checkbox" checked={confirmed} onChange={event => setConfirmed(event.target.checked)} />GM confirms the exact source trigger actually occurred and this award has not already been included in existing XP</label><label>Actual completion evidence and award reason<textarea aria-label="Strahd milestone reason" rows={2} maxLength={2000} value={reason} onChange={event => setReason(event.target.value)} /></label>
        {registered.map(person => <section className="native-training-card" key={person.id}><label className="native-checkbox"><input type="checkbox" checked={reviews[person.id]?.eligible ?? false} onChange={event => setReviews(previous => ({ ...previous, [person.id]: { reason: previous[person.id]?.reason ?? '', eligible: event.target.checked } }))} />{person.name} is eligible for this milestone</label><label>Eligibility / exclusion reason<input aria-label={`Strahd eligibility reason for ${person.id}`} maxLength={1000} value={reviews[person.id]?.reason ?? ''} onChange={event => { const text = event.target.value; setReviews(previous => ({ ...previous, [person.id]: { eligible: previous[person.id]?.eligible ?? false, reason: text } })); }} /></label></section>)}
        {!registered.length && <p className="native-help">Record actual PC XP baselines before reviewing an award.</p>}
        <button className="hp-btn" disabled={!canReview} onClick={async () => { setPending(true); setError(''); setReview(null); try { const response = await request<{ quote: Award }>('quote', payload); setReview({ signature, payload, quote: response.quote }); } catch (err) { setError(err instanceof Error ? err.message : String(err)); } finally { setPending(false); } }}>Review milestone XP</button>
        {quote && <section className="native-training-card" aria-label="Reviewed Strahd milestone award"><strong>{quote.quote.title} · {quote.quote.xp_per_pc} XP to each eligible PC</strong>{quote.quote.allocations.map(item => <p key={item.actor_id}>{item.name}: +{item.xp} XP → {item.total_xp.toLocaleString()} XP{item.level_up_pending ? ` · level ${item.xp_level} sheet review pending` : ''}</p>)}<p className="native-help">The source amount is awarded to each eligible PC. It is not divided by party size. This source milestone is claimed once.</p><button className="hp-btn" onClick={async () => { if (await mutate('award', quote.payload)) { setConfirmed(false); setReason(''); setReviews({}); } }}>Commit reviewed milestone award</button></section>}
      </section>}
      <details><summary>GM arc progress review</summary><p className="native-help">Arc status records actual campaign progress. It does not grant milestone XP or mark other arcs complete.</p><label>Adventure arc<select aria-label="Strahd progress arc" value={arcId} onChange={event => setArcId(event.target.value)}>{data?.arcs.map(arc => <option key={arc.id} value={arc.id}>{arc.id} · {arc.title} · {arc.status}</option>)}</select></label><label>Actual arc status<select aria-label="Strahd arc status" value={arcStatus} onChange={event => setArcStatus(event.target.value)}>{['unreviewed', 'active', 'completed', 'failed'].map(status => <option key={status} value={status}>{status}</option>)}</select></label><label>Arc status evidence<input aria-label="Strahd arc status reason" maxLength={1000} value={arcReason} onChange={event => setArcReason(event.target.value)} /></label><button className="hp-btn" disabled={!arcReason.trim()} onClick={async () => { if (await mutate('arc', { arc: arcId, status: arcStatus, reason: arcReason, expected_updated_at: revision })) setArcReason(''); }}>Save GM arc review</button></details>
    </fieldset>
    {!!data?.progress.awards.length && <details><summary>Saved milestone awards ({data.progress.awards.length})</summary>{[...data.progress.awards].reverse().map(award => <section className="native-training-card" key={award.id}><strong>{award.title} · {award.xp_per_pc} XP per eligible PC</strong><p>{award.reason}</p>{award.allocations.map(item => <p key={item.actor_id}>{item.name}: +{item.xp} → {item.total_xp.toLocaleString()} XP</p>)}<p className="native-help">{award.trigger} · {award.source_path}</p></section>)}</details>}
    {!!data?.progress.arc_reviews.length && <details><summary>Saved arc reviews ({data.progress.arc_reviews.length})</summary>{[...data.progress.arc_reviews].reverse().map(item => <p key={item.id}>Arc {item.arc} · {item.status} · {item.reason}</p>)}</details>}
    {data?.rules.notes.map(note => <p className="native-help" key={note}>{note}</p>)}
  </details>;
}
