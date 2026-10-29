import { useState } from 'react';
import { api } from '../../services/api';
import type { D6AdvancementView, D6RewardRecord, ForceRuling, GameSession } from '../../types';

const rulings: Record<ForceRuling, string> = {
  unheroic: 'Unheroic / personal benefit · lost',
  heroic: 'Heroic · return 1 FP',
  heroic_climax: 'Heroic at decisive moment · return 2 FP',
  evil: 'Evil · lost',
  evil_climax: 'Evil at decisive moment · 2 FP for consumed characters only',
};
interface Review { ruling: ForceRuling | ''; reason: string; corruption_event_id?: string }
interface Award { character_points: number; zero_point_heroism: boolean; reason: string }

export default function D6RewardsPanel({ view, session, onSessionChanged }: { view: D6AdvancementView; session: GameSession; onSessionChanged: (session: GameSession) => void }) {
  const [reviews, setReviews] = useState<Record<string, Review>>({});
  const [awards, setAwards] = useState<Record<string, Award>>({});
  const [label, setLabel] = useState('');
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');
  const [preview, setPreview] = useState<{ signature: string; quote: D6RewardRecord } | null>(null);
  const combat = Boolean(session.encounter?.active || session.vehicle_encounter);
  const uses = (id: string) => view.actors.find(actor => actor.id === id)?.d6.rewards?.expenditures.filter(item => item.adventure === view.campaign.adventure && !item.ruling && !item.forfeited) ?? [];
  const award = (id: string): Award => awards[id] ?? { character_points: 0, zero_point_heroism: false, reason: '' };
  const review = (id: string, heroic: boolean): Review => reviews[id] ?? { ruling: heroic ? 'heroic' : '', reason: '' };
  const request = { adventure: view.campaign.adventure, expected_updated_at: session.updated_at, next_label: label, actors: view.actors.map(actor => ({ actor_id: actor.id, ...award(actor.id), reviews: uses(actor.id).map(item => ({ expenditure_id: item.id, ...review(item.id, item.guaranteed_heroic) })) })) };
  const signature = JSON.stringify({ request, revision: session.updated_at });
  const quote = preview?.signature === signature ? preview.quote : null;
  const complete = label.trim() && request.actors.every(actor => actor.reason.trim() && actor.reviews.every(item => item.ruling && item.reason.trim()));
  async function run(finish: boolean) {
    setPending(true); setError('');
    try {
      if (finish) {
        const response = await api.nativeAdvancementAction('finish-adventure', request);
        onSessionChanged(response.session);
      } else {
        const response = await api.nativeRewardQuote(request);
        setPreview({ signature, quote: response.quote });
      }
    } catch (err) { setError(err instanceof Error ? err.message : String(err)); }
    finally { setPending(false); }
  }
  return <details className="native-rewards-panel">
    <summary>Finish adventure & rewards</summary>
    <p className="native-help">Review adventure {view.campaign.adventure}: {view.campaign.label}. Heroic use returns one FP; a decisive heroic moment returns two. A consumed character receives two only for evil at a decisive moment. Non-sensitive characters keep at most five FP; each excess FP becomes three CP.</p>
    <p className="native-help">Evil uses require the existing moral ruling from Dark Side & atonement. Select that event below; corruption is never rolled twice. Temporary points from successful Dark Side calls are reviewed as spent points too.</p>
    {error && <p className="native-error" role="alert">{error}</p>}
    {view.actors.map(actor => {
      const draft = award(actor.id);
      const consumed = actor.d6.force?.dark_side_consumed;
      const events = actor.d6.corruption?.events.filter(event => event.adventure === view.campaign.adventure && ['evil_force_point', 'evil_act', 'temptation', 'injure_kill', 'telekinetic_attack'].includes(event.source)) ?? [];
      return <section className="native-training-card" key={actor.id} aria-label={`Rewards for ${actor.name}`}>
        <h4>{actor.name} · {actor.d6.force_points} FP · {actor.d6.character_points} CP</h4>
        <p className="native-help">Adventure starting FP: {actor.d6.rewards?.baseline_known ? actor.d6.rewards.starting_force_points : 'unknown in this older save; tracked from next boundary'}{consumed ? ' · Consumed: no adventuring CP or zero-start award' : ''}</p>
        <label>Adventure CP award<input aria-label={`Adventure CP for ${actor.name}`} type="number" min={0} max={100000} disabled={pending || !!consumed} value={draft.character_points} onChange={event => setAwards({ ...awards, [actor.id]: { ...draft, character_points: Number(event.target.value) } })} /></label>
        <label className="native-checkbox"><input type="checkbox" aria-label={`Zero-start heroism for ${actor.name}`} disabled={pending || !!consumed || !actor.d6.rewards?.baseline_known || actor.d6.rewards.starting_force_points !== 0} checked={draft.zero_point_heroism} onChange={event => setAwards({ ...awards, [actor.id]: { ...draft, zero_point_heroism: event.target.checked } })} />Began with zero FP and acted heroically at a decisive moment, regardless of risk (+1 FP)</label>
        <label>GM reward reason<input aria-label={`Reward reason for ${actor.name}`} maxLength={500} value={draft.reason} onChange={event => setAwards({ ...awards, [actor.id]: { ...draft, reason: event.target.value } })} /></label>
        {uses(actor.id).map((item, index) => {
          const current = review(item.id, item.guaranteed_heroic);
          return <div className="native-training-card" key={item.id}>
            <strong>Force use {index + 1}: {item.source.replaceAll('_', ' ')}{item.consumed ? ' · already consumed when spent' : ''}</strong>
            <label>GM classification<select aria-label={`Force use ${index + 1} ruling for ${actor.name}`} value={current.ruling} onChange={event => setReviews({ ...reviews, [item.id]: { ...current, ruling: event.target.value as ForceRuling } })}><option value="">Choose a ruling</option>{Object.entries(rulings).filter(([id]) => !item.guaranteed_heroic || ['heroic', 'heroic_climax'].includes(id)).map(([id, text]) => <option key={id} value={id}>{text}</option>)}</select></label>
            <label>Actual use and GM reason<input aria-label={`Force use ${index + 1} reason for ${actor.name}`} maxLength={500} value={current.reason} onChange={event => setReviews({ ...reviews, [item.id]: { ...current, reason: event.target.value } })} /></label>
            {current.ruling.startsWith('evil') && <label>Existing Dark Side ruling<select aria-label={`Force use ${index + 1} corruption for ${actor.name}`} value={current.corruption_event_id ?? ''} onChange={event => setReviews({ ...reviews, [item.id]: { ...current, corruption_event_id: event.target.value } })}><option value="">Record / select the evil use's DSP first</option>{events.map(event => <option key={event.id} value={event.id}>{event.source.replaceAll('_', ' ')}: {event.reason}</option>)}</select></label>}
          </div>;
        })}
        {!uses(actor.id).length && <p className="native-help">No pending Force Point uses.</p>}
      </section>;
    })}
    <label>Next adventure name<input aria-label="Reward next adventure name" value={label} maxLength={120} onChange={event => setLabel(event.target.value)} /></label>
    <button className="hp-btn" disabled={pending || combat || !complete} onClick={() => run(false)}>Preview adventure rewards</button>
    {quote && <section className="native-training-card" aria-label="Adventure reward preview"><strong>Reward preview · adventure {quote.adventure}</strong>{quote.actors.map(item => <p key={item.actor_id}>{view.actors.find(actor => actor.id === item.actor_id)?.name}: +{item.force_returned} returned FP, +{item.zero_point_award} zero-start FP, +{item.character_points_awarded} adventure CP; {item.force_converted} excess FP → {item.conversion_cp} CP. Final: {item.force_points} FP / {item.character_points} CP.</p>)}<p className="native-help">Finishing awards these points and opens the next adventure for the whole party. Time and wounds stay as recorded. This adventure cannot be claimed again.</p><button className="hp-btn" disabled={pending || combat} onClick={() => run(true)}>Finish adventure & award rewards</button></section>}
    {!!view.campaign.rewards?.length && <details><summary>Adventure reward history ({view.campaign.rewards.length})</summary>{[...view.campaign.rewards].reverse().map(record => <div className="native-training-card" key={record.adventure}><strong>Adventure {record.adventure}: {record.label}</strong>{record.actors.map(item => <p key={item.actor_id}>{view.actors.find(actor => actor.id === item.actor_id)?.name ?? item.actor_id}: {item.force_returned} returned FP, {item.zero_point_award} zero-start FP, {item.character_points_awarded} adventure CP, {item.conversion_cp} conversion CP. {item.reason}</p>)}</div>)}</details>}
  </details>;
}
