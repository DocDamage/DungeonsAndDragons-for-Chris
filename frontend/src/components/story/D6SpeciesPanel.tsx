import { useState } from 'react';
import { api } from '../../services/api';
import type { D6SpeciesContext, GameSession } from '../../types';

export function D6SpeciesPanel({ session, onSessionChanged }: { session: GameSession; onSessionChanged: (session: GameSession) => void }) {
  const actors = [session.character, ...(session.character.companions ?? [])].filter(actor => actor.d6);
  const [actorId, setActorId] = useState(session.character.id);
  const actor = actors.find(item => item.id === actorId) ?? actors[0];
  const [draft, setDraft] = useState<{ source: string; context: D6SpeciesContext } | null>(null);
  const saved = actor.d6!.species_context ?? { environment: 'neutral', scent_tracking: false, climbing_claws: false, enhanced_senses: false, familiar_destination: false, berserk: false, heavy_grasper: false, long_range_sensor: false, moving_target_sensor: false, target_distance_m: 0, visited_locations: [] } as D6SpeciesContext;
  const sourceKey = JSON.stringify({ id: actor.id, saved });
  const context = draft?.source === sourceKey ? draft.context : saved;
  const [reason, setReason] = useState('');
  const [danger, setDanger] = useState(false);
  const [controlled, setControlled] = useState(false);
  const [calmForce, setCalmForce] = useState(false);
  const [coordination, setCoordination] = useState(0);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');
  const identity = actor.d6!.species_id || actor.race.toLowerCase().replaceAll(' ', '_').replaceAll("'", '');
  function update(changes: Partial<D6SpeciesContext>) { setDraft({ source: sourceKey, context: { ...context, ...changes } }); }
  async function run(action: string) {
    setPending(true); setError('');
    try {
      const response = await api.nativeSpeciesAction(action, action === 'species-context' ? { actor_id: actor.id, context, reason, deadly_danger: danger } : action === 'calm' ? { actor_id: actor.id, enemies_controlled: controlled, force_point: calmForce, coordination_dice: coordination, coordination_reason: reason } : {});
      onSessionChanged(response.session);
    } catch (err) { setError(err instanceof Error ? err.message : String(err)); }
    finally { setPending(false); }
  }
  return <details name="native-tools" className="native-force-panel">
    <summary>Species abilities & scene conditions</summary>
    {error && <p className="native-error" role="alert">{error}</p>}
    <label>Party member<select aria-label="Species ability actor" value={actor.id} onChange={event => setActorId(event.target.value)}>{actors.map(item => <option key={item.id} value={item.id}>{item.name} · {item.race}</option>)}</select></label>
    <p className="native-help">Record actual scene conditions with a GM reason. Applicable bonuses affect native checks, defenses, crew skills and Strength resistance. Equipment dice keep their own values.</p>
    {identity === 'mon_calamari' && <label>Environment<select aria-label="Mon Calamari environment" value={context?.environment ?? 'neutral'} onChange={event => update({ environment: event.target.value as D6SpeciesContext['environment'] })}><option value="neutral">Neutral</option><option value="moist">Moist (+1D Dex / Per / Str)</option><option value="dry">Very dry (−1D Dex / Per / Str)</option></select></label>}
    {identity === 'ewok' && <label className="native-checkbox"><input type="checkbox" checked={context?.scent_tracking ?? false} onChange={event => update({ scent_tracking: event.target.checked })} />Tracking by scent (+1D search)</label>}
    {identity === 'sullustan' && <><label className="native-checkbox"><input type="checkbox" checked={context?.enhanced_senses ?? false} onChange={event => update({ enhanced_senses: event.target.checked })} />Hearing / low-light search or Perception (+2D)</label><label className="native-checkbox"><input type="checkbox" checked={context?.familiar_destination ?? false} onChange={event => update({ familiar_destination: event.target.checked })} />Astrogating to an already visited place (+1D)</label><p className="native-help">A Sullustan remembers the return route in a visited area automatically.</p></>}
    {identity === 'wookiee' && <><label className="native-checkbox"><input type="checkbox" checked={context?.climbing_claws ?? false} onChange={event => update({ climbing_claws: event.target.checked })} />Using climbing claws (+2D climbing; never a weapon bonus)</label><label className="native-checkbox"><input type="checkbox" checked={context?.berserk ?? false} disabled={actor.d6?.species_context?.berserk} onChange={event => update({ berserk: event.target.checked })} />Berserker rage (+2D brawling damage; −2D non-Strength checks)</label><label className="native-checkbox"><input type="checkbox" checked={danger} onChange={event => setDanger(event.target.checked)} />Self or life-debt companion faces immediate deadly danger</label>{actor.d6?.species_context?.berserk && <><label className="native-checkbox"><input type="checkbox" checked={controlled} onChange={event => setControlled(event.target.checked)} />GM confirms all enemies are controlled</label><button className="hp-btn" disabled={pending || !controlled} onClick={() => run('calm')}>Roll Moderate Perception to calm down</button></>}</>}
    {identity === 'gamorrean' && <><p className="native-help">A failed stamina check permits one immediate retry without another action. This button applies to the player character’s latest native stamina check.</p><button className="hp-btn" disabled={pending || actor.id !== session.character.id} onClick={() => run('stamina-retry')}>Retry failed Gamorrean stamina check</button></>}
    {actor.d6?.droid && <><p className="native-help">Built-in tools use their equipment ratings; they do not grant the NPC example skills.</p>{['r2', '9g'].includes(actor.d6.droid.model) && <label className="native-checkbox"><input type="checkbox" checked={context?.heavy_grasper ?? false} onChange={event => update({ heavy_grasper: event.target.checked })} />Using heavy grasper (lifting {actor.d6.droid.model === 'r2' ? '2D' : '4D'})</label>}{actor.d6.droid.model === '9g' && <><label className="native-checkbox"><input type="checkbox" checked={context?.long_range_sensor ?? false} onChange={event => update({ long_range_sensor: event.target.checked })} />Long-range sensor (+2D search at 25–50m)</label><label>Sensor target distance (meters)<input type="number" min={0} value={context?.target_distance_m ?? 0} onChange={event => update({ target_distance_m: Number(event.target.value) })} /></label><label className="native-checkbox"><input type="checkbox" checked={context?.moving_target_sensor ?? false} onChange={event => update({ moving_target_sensor: event.target.checked })} />Movement sensor on an actually moving target (+2D search)</label></>}</>}
    {identity === 'wookiee' && actor.d6?.species_context?.berserk && <div className="native-form-row"><label className="native-checkbox"><input type="checkbox" checked={calmForce} onChange={event => setCalmForce(event.target.checked)} />Spend one FP on the calm-down check</label><label>Actual close-friend coordination bonus (dice)<input aria-label="Wookiee calm coordination dice" type="number" min={0} max={30} value={coordination} onChange={event => setCoordination(Number(event.target.value))} /></label><p className="native-help">Use the scene reason below to record earned coordination. A small Perception pool may need assistance or an FP to overcome the rage penalty.</p></div>}
    <label>GM scene reason<input aria-label="Species scene reason" value={reason} maxLength={1000} onChange={event => setReason(event.target.value)} /></label><button className="hp-btn" disabled={pending || !reason.trim()} onClick={() => run('species-context')}>Record species scene conditions</button>
  </details>;
}
