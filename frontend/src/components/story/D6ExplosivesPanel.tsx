import { useEffect, useState } from 'react';
import { API_BASE } from '../../services/api';
import type { D6Character, GameSession, Item, RollResult } from '../../types';
import '../sidebar/D6.css';

type Point = { x: number; y: number };
type Position = { actor_id: string; point: Point; hit_location: string | null; side: string; resistance_character_points: number };
type Actor = { id: string; name: string; is_player: boolean; d6: D6Character; weapon: Item | null; armor: Item[] };
type Intent = { actor_id: string; declared_round: number; stage: 'declared' | 'approached' | 'grabbed' | 'thrown'; grenade_id: string | null; actions: { operation: string; round: number; reason: string }[]; reason: string };
type Throw = { actor_id: string; name: string; round: number; origin: Point; target: Point; landing: Point; distance: number; range_band: string; difficulty: number; roll: RollResult; success: boolean; character_points: number; force_point_active: boolean; scatter_direction: RollResult | null; scatter_distance: RollResult | null; rethrow: boolean; reason: string };
type Victim = { actor_id: string; name: string; distance: number; blast_distance: number; affected: boolean; damage_code: string | null; damage_roll: RollResult | null; resistance_roll: RollResult | null; character_points: number; point_note: string; hit_location: string | null; side: string; before: string; after: string; armor_damage: { name: string; before: string; after: string } | null };
type Grenade = { id: string; item_id: string; name: string; catalog_id: string; status: 'armed' | 'resolved'; trigger: string; timer_seconds: number | null; due_round: number; created_round: number; resolved_round: number | null; position: Point; holder_id: string | null; throws: Throw[]; victims: Victim[]; reason: string };
type Explosives = { positions: Record<string, Position>; position_round: number; position_reason: string; distance_rounding: 'up' | 'down'; grenades: Grenade[]; intents: Intent[] };
type View = { encounter_id: string | null; active: boolean; round: number | null; current_actor_id: string | null; actions_started: boolean; turn_acted: boolean; round_closing: boolean; actors: Actor[]; explosives: Explosives | null; catalog: { id: string; name: string; ranges: number[]; blast_radius: number[]; blast_damage: string[] }[]; notes: string[]; source: string };
type PositionDraft = { x: string; y: string; side: string; hit: string; cp: number };
const locations = ['head', 'torso', 'left_arm', 'right_arm', 'left_leg', 'right_leg'];
const pointText = (point: Point) => `(${Number(point.x.toFixed(3))}, ${Number(point.y.toFixed(3))})m`;
const words = (text: string) => text.replaceAll('_', ' ');
async function request<T>(action: string, payload?: unknown, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`${API_BASE}/weg-d6/explosives/${action}`, payload === undefined ? { signal } : { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload), signal });
  if (!response.ok) {
    const data = await response.json().catch(() => null) as { detail?: string | { msg: string }[] } | null;
    throw new Error(typeof data?.detail === 'string' ? data.detail : Array.isArray(data?.detail) ? data.detail.map(error => error.msg).join('; ') : `Grenade request failed (${response.status})`);
  }
  return response.json();
}
function number(value: string, label: string) {
  if (!value.trim() || !Number.isFinite(Number(value))) throw new Error(`Record the actual ${label}; empty coordinates are not positions.`);
  return Number(value);
}

export function D6ExplosivesPanel({ session, onSessionChanged }: { session: GameSession; onSessionChanged: (session: GameSession) => void }) {
  const [loaded, setLoaded] = useState<{ revision: number | undefined; sessionId: string; data: View } | null>(null);
  const [drafts, setDrafts] = useState<Record<string, PositionDraft>>({});
  const [actorId, setActorId] = useState('');
  const [reason, setReason] = useState('');
  const [exhaustive, setExhaustive] = useState(false);
  const [unobstructed, setUnobstructed] = useState(false);
  const [independent, setIndependent] = useState(false);
  const [rounding, setRounding] = useState<'up' | 'down'>('up');
  const [x, setX] = useState(''); const [y, setY] = useState('');
  const [headingX, setHeadingX] = useState(''); const [headingY, setHeadingY] = useState('');
  const [trigger, setTrigger] = useState<'contact' | 'timer'>('timer'); const [seconds, setSeconds] = useState('4');
  const [timerConfirmed, setTimerConfirmed] = useState(false);
  const [visible, setVisible] = useState(true); const [unseen, setUnseen] = useState('');
  const [cp, setCp] = useState(0); const [mishap, setMishap] = useState<'penalty' | 'complication'>('penalty');
  const [clearPath, setClearPath] = useState(false);
  const [far, setFar] = useState(false); const [lowered, setLowered] = useState(''); const [farReason, setFarReason] = useState('');
  const [pending, setPending] = useState(false); const [error, setError] = useState(''); const [message, setMessage] = useState('');
  useEffect(() => {
    const controller = new AbortController();
    request<View>('state', undefined, controller.signal).then(data => setLoaded({ revision: session.updated_at, sessionId: session.id, data })).catch(err => { if (!controller.signal.aborted) setError(String(err)); });
    return () => controller.abort();
  }, [session.id, session.updated_at]);
  const view = loaded?.sessionId === session.id && loaded.revision === session.updated_at ? loaded.data : null;
  const actor = view?.actors.find(actor => actor.id === actorId) ?? view?.actors.find(actor => actor.id === view.current_actor_id) ?? view?.actors[0];
  const live = view?.explosives?.grenades.filter(grenade => grenade.status === 'armed') ?? [];
  const ready = !!view?.active && !view.round_closing && !pending && !!reason.trim() && session.updated_at != null;
  const turn = ready && actor?.id === view?.current_actor_id && !view?.turn_acted;
  const grenadeWeapon = actor?.weapon && ['fragmentation_grenade', 'thermal_detonator'].includes(actor.weapon.catalog_id ?? '') ? actor.weapon : null;
  const drawn = !!grenadeWeapon && grenadeWeapon.quantity === 1 && grenadeWeapon.ammo === 1 && grenadeWeapon.equipped && grenadeWeapon.equipped_by === actor?.id;
  function row(person: Actor): PositionDraft {
    const saved = view?.explosives?.positions[person.id];
    return drafts[person.id] ?? { x: saved ? String(saved.point.x) : '', y: saved ? String(saved.point.y) : '', side: saved?.side ?? '', hit: saved?.hit_location ?? '', cp: saved?.resistance_character_points ?? 0 };
  }
  function changeRow(person: Actor, change: Partial<PositionDraft>) { setDrafts(previous => ({ ...previous, [person.id]: { ...row(person), ...change } })); }
  async function run(action: string, data: Record<string, unknown>) {
    if (!ready) return;
    setPending(true); setError(''); setMessage('');
    try {
      const response = await request<{ session: GameSession; eval_result?: { summary: string } }>(action, { ...data, reason, expected_updated_at: session.updated_at });
      onSessionChanged(response.session); setMessage(response.eval_result?.summary ?? 'Actual grenade state saved.');
    } catch (err) { setError(err instanceof Error ? err.message : String(err)); }
    finally { setPending(false); }
  }
  function reviewPositions() {
    try {
      const positions = view!.actors.map(person => {
        const value = row(person);
        if (!value.side) throw new Error(`Record ${person.name}'s actual exposure side.`);
        return { actor_id: person.id, point: { x: number(value.x, `${person.name} x coordinate`), y: number(value.y, `${person.name} y coordinate`) }, side: value.side, hit_location: value.hit || null, resistance_character_points: value.cp };
      });
      void run('positions', { positions, all_scene_actors_confirmed: exhaustive, same_plane_unobstructed_confirmed: unobstructed, independent_damage_rolls_confirmed: independent, distance_rounding: rounding });
    } catch (err) { setError(err instanceof Error ? err.message : String(err)); }
  }
  function throwData() {
    return { actor_id: actor!.id, target: { x: number(x, 'landing x coordinate'), y: number(y, 'landing y coordinate') },
      heading: headingX.trim() || headingY.trim() ? { x: number(headingX, 'heading x coordinate'), y: number(headingY, 'heading y coordinate') } : null,
      visible_landing: visible, unseen_modifier: visible ? null : number(unseen, 'unseen landing modifier'), character_points: cp, mishap };
  }
  function toss(action: 'throw' | 'rethrow', grenade?: Grenade) {
    try {
      const data = throwData();
      void run(action, action === 'throw' ? { ...data, item_id: actor!.weapon!.id, trigger, timer_seconds: trigger === 'timer' ? number(seconds, 'timer seconds') : null, timer_rounding_confirmed: timerConfirmed } : { ...data, grenade_id: grenade!.id, throw_as_far: far, lowered_difficulty: far ? number(lowered, 'lowered GM difficulty') : null, far_throw_ruling: far ? farReason : '' });
    } catch (err) { setError(err instanceof Error ? err.message : String(err)); }
  }
  return <details name="native-tools" className="native-force-panel native-explosives-panel">
    <summary>Grenades, scatter & live fuses · {live.length} pending</summary>
    {error && <p role="alert" className="native-error">{error}</p>}{message && <p role="status">{message}</p>}
    <p className="native-help">{view?.source}</p>
    {!view ? <p>Loading actual grenade state…</p> : !view.active && !view.explosives?.grenades.length ? <p>Start an actual native personal encounter to review positions and use a drawn grenade.</p> : <>
      <p>Round {view.round}{!view.active ? ' · encounter ended; saved grenade history' : ''} · actual actor: {view.actors.find(actor => actor.id === view.current_actor_id)?.name ?? 'none'}{view.round_closing ? ' · resolve immediate injury reactions, then advance the native round' : view.turn_acted ? ' · this action pass is complete' : ''}.</p>
      <label>Actual grenade actor<select aria-label="Grenade actor" value={actor?.id ?? ''} disabled={pending} onChange={event => setActorId(event.target.value)}>{view.actors.map(actor => <option key={actor.id} value={actor.id}>{actor.name}{actor.is_player ? ' · party' : ''}</option>)}</select></label>
      <label>Actual GM scene facts / reason<input aria-label="Grenade GM reason" value={reason} maxLength={1500} disabled={pending} onChange={event => setReason(event.target.value)} /></label>
      <details><summary>Exhaustive actual positions · {view.actors.length} registered actors</summary>
        <p className="native-help">Register every actual affected person in the encounter first. Enter actual meter coordinates for all actors, including the party. This procedure requires unobstructed geometry on one plane. Saved positions cannot be rewritten to escape a live grenade.</p>
        {view.actors.map(person => { const value = row(person); return <section className="native-training-card" key={person.id}><strong>{person.name}{person.is_player ? ' · party' : ''}</strong><div className="native-form-row"><label>x meters<input aria-label={`Blast x ${person.id}`} type="number" value={value.x} disabled={pending || !!live.length} onChange={event => changeRow(person, { x: event.target.value })} /></label><label>y meters<input aria-label={`Blast y ${person.id}`} type="number" value={value.y} disabled={pending || !!live.length} onChange={event => changeRow(person, { y: event.target.value })} /></label><label>Actual exposure side<select aria-label={`Blast side ${person.id}`} value={value.side} disabled={pending || !!live.length} onChange={event => changeRow(person, { side: event.target.value })}><option value="">Choose actual side</option><option value="front">Front</option><option value="back">Back</option></select></label><label>Armor hit location<select aria-label={`Blast location ${person.id}`} value={value.hit} disabled={pending || !!live.length} onChange={event => changeRow(person, { hit: event.target.value })}><option value="">No partial armor location needed</option>{locations.map(location => <option key={location} value={location}>{words(location)}</option>)}</select></label><label>Resistance CP per blast<input aria-label={`Blast resistance CP ${person.id}`} type="number" min={0} max={5} value={value.cp} disabled={pending || !!live.length} onChange={event => changeRow(person, { cp: Number(event.target.value) })} /></label></div></section>; })}
        <label className="native-checkbox"><input type="checkbox" checked={exhaustive} disabled={pending || !!live.length} onChange={event => setExhaustive(event.target.checked)} />GM confirms all actual scene occupants are represented, including every party member</label>
        <label className="native-checkbox"><input type="checkbox" checked={unobstructed} disabled={pending || !!live.length} onChange={event => setUnobstructed(event.target.checked)} />Actual same-plane blast geometry is unobstructed; physical cover is resolved first</label>
        <label className="native-checkbox"><input type="checkbox" checked={independent} disabled={pending || !!live.length} onChange={event => setIndependent(event.target.checked)} />GM confirms independent damage rolls per affected actor</label>
        <label>GM ruling for fractional blast meters<select aria-label="Blast distance rounding" value={rounding} disabled={pending || !!live.length} onChange={event => setRounding(event.target.value as 'up' | 'down')}><option value="up">Round up</option><option value="down">Round down</option></select></label>
        <button className="hp-btn" disabled={!ready || !!live.length || !exhaustive || !unobstructed || !independent} onClick={reviewPositions}>Save reviewed actual blast positions</button>
      </details>
      {actor && <p>{actor.name}: {actor.d6.round_state.actions_taken}/{actor.d6.round_state.declared_actions} actions used · {actor.d6.character_points} CP · drawn weapon {actor.weapon?.name ?? 'none'}{grenadeWeapon ? `, quantity ${grenadeWeapon.quantity}, charge ${grenadeWeapon.ammo ?? 'unknown'}` : ''}.</p>}
      <button className="hp-btn" disabled={!ready || view.actions_started || !actor || actor.d6.round_state.declared_actions < 3 || actor.d6.round_state.actions_taken > 0} onClick={() => run('declare-rethrow', { actor_id: actor!.id })}>Save intent before landing: move, grab, throw · 3 actions</button>
      <p className="native-help">Declare at least three native actions before the action phase. The saved intent must exist before the grenade lands; each stage then uses its own actual action pass. Approaching only moves to the grenade.</p>
      <fieldset disabled={pending} style={{ border: 0, padding: 0, margin: 0, minWidth: 0 }}>
        <div className="native-form-row"><label>Actual landing x<input aria-label="Grenade target x" type="number" value={x} onChange={event => setX(event.target.value)} /></label><label>Actual landing y<input aria-label="Grenade target y" type="number" value={y} onChange={event => setY(event.target.value)} /></label><label>CP for actual Grenade roll<input aria-label="Grenade roll CP" type="number" min={0} max={2} value={cp} onChange={event => setCp(Number(event.target.value))} /></label></div>
        <label className="native-checkbox"><input type="checkbox" checked={visible} onChange={event => setVisible(event.target.checked)} />Landing point is actually visible</label>{!visible && <label>Actual unseen-landing modifier (+5 to +10)<input aria-label="Grenade unseen modifier" type="number" min={5} max={10} value={unseen} onChange={event => setUnseen(event.target.value)} /></label>}
        <details><summary>Explicit heading for a coincident landing point</summary><p className="native-help">A target at the thrower's own position needs a distinct heading point so a miss can use the source scatter diagram.</p><div className="native-form-row"><label>Heading x<input aria-label="Grenade heading x" type="number" value={headingX} onChange={event => setHeadingX(event.target.value)} /></label><label>Heading y<input aria-label="Grenade heading y" type="number" value={headingY} onChange={event => setHeadingY(event.target.value)} /></label></div></details>
        <label>Wild-1 handling<select aria-label="Grenade Wild-1 handling" value={mishap} onChange={event => setMishap(event.target.value as 'penalty' | 'complication')}><option value="penalty">Penalty</option><option value="complication">Complication</option></select></label>
        <div className="native-form-row"><label>Actual activator<select aria-label="Grenade activator" value={trigger} onChange={event => setTrigger(event.target.value as 'contact' | 'timer')}><option value="timer">Timer</option><option value="contact">Contact · immediate detonation</option></select></label>{trigger === 'timer' && <label>Actual timer seconds<input aria-label="Grenade timer seconds" type="number" min={0.001} step="any" value={seconds} onChange={event => setSeconds(event.target.value)} /></label>}</div>
        {trigger === 'timer' && <label className="native-checkbox"><input type="checkbox" checked={timerConfirmed} onChange={event => setTimerConfirmed(event.target.checked)} />Confirm ceil(seconds/5) round-end timing; under five seconds detonates at end of this round</label>}
        {!drawn && <p className="native-help">Equip and draw one actual fragmentation grenade or thermal detonator first. Stacks, unknown charges and another actor's weapon cannot be thrown.</p>}
        <button className="hp-btn" disabled={!turn || !drawn || !view.explosives?.position_round || trigger === 'timer' && !timerConfirmed} onClick={() => toss('throw')}>Throw actual grenade at saved point</button>
        <label className="native-checkbox"><input type="checkbox" checked={clearPath} onChange={event => setClearPath(event.target.checked)} />Actual clear approach to the live grenade is within one native Move</label>
        <label className="native-checkbox"><input type="checkbox" checked={far} onChange={event => setFar(event.target.checked)} />Toss-away as far as possible · GM supplies actual landing point and lower difficulty</label>{far && <div className="native-form-row"><label>Lower GM difficulty<input aria-label="Grenade far difficulty" type="number" min={1} value={lowered} onChange={event => setLowered(event.target.value)} /></label><label>Actual lower-difficulty ruling<input aria-label="Grenade far ruling" value={farReason} maxLength={1000} onChange={event => setFarReason(event.target.value)} /></label></div>}
      </fieldset>
      {view.explosives?.grenades.map(grenade => {
        const intent = [...view.explosives!.intents].reverse().find(intent => intent.actor_id === actor?.id && (intent.grenade_id === grenade.id || !intent.grenade_id && intent.declared_round === grenade.created_round));
        return <section className="native-training-card" key={grenade.id} aria-label={`Saved grenade ${grenade.id}`}><h4>{grenade.name} · {grenade.status === 'armed' ? `LIVE · end of round ${grenade.due_round}` : `detonated round ${grenade.resolved_round}`}</h4><p>Actual position {pointText(grenade.position)} · {grenade.trigger}{grenade.timer_seconds != null ? ` ${grenade.timer_seconds}s` : ''}{grenade.holder_id ? ` · held by ${view.actors.find(actor => actor.id === grenade.holder_id)?.name ?? grenade.holder_id}` : ''}. {grenade.reason}</p>
          {grenade.throws.map((saved, index) => <p className="native-help" key={index}>{saved.rethrow ? 'Actual toss-away' : 'Initial throw'}: {saved.name}, round {saved.round}; {pointText(saved.origin)} → {pointText(saved.target)}, {saved.distance.toFixed(3)}m {words(saved.range_band)}; {saved.roll.total} vs {saved.difficulty} → {saved.success ? 'hit point' : 'miss'}; {saved.character_points} CP paid; FP active {String(saved.force_point_active)}. Landing {pointText(saved.landing)}.{saved.scatter_direction && ` Plain scatter direction ${saved.scatter_direction.total}, distance ${saved.scatter_distance?.total}m.`} {saved.roll.breakdown}</p>)}
          {grenade.status === 'armed' && <><p className="native-help">The original fuse continues through action passes. Advance native combat turns for round-end detonation; ending combat or resting cannot clear it.</p><div className="native-button-row"><button className="hp-btn" disabled={!turn || intent?.stage !== 'declared' || !clearPath || !!grenade.holder_id} onClick={() => run('move', { actor_id: actor!.id, grenade_id: grenade.id, clear_path_confirmed: clearPath })}>1/3 · Move to grenade</button><button className="hp-btn" disabled={!turn || intent?.stage !== 'approached' || !!grenade.holder_id} onClick={() => run('grab', { actor_id: actor!.id, grenade_id: grenade.id })}>2/3 · Grab grenade</button><button className="hp-btn" disabled={!turn || intent?.stage !== 'grabbed' || grenade.holder_id !== actor?.id} onClick={() => toss('rethrow', grenade)}>3/3 · Roll toss-away</button></div></>}
          {grenade.victims.map(victim => <p key={victim.actor_id}>{victim.name}: actual {victim.distance.toFixed(3)}m → GM blast distance {victim.blast_distance}m · {victim.damage_code ?? 'outside blast'}{victim.affected ? `; damage ${victim.damage_roll?.total ?? 'no new roll'}, free Strength ${victim.resistance_roll?.total ?? 'no new roll'}; ${victim.character_points} CP; ${words(victim.before)} → ${words(victim.after)}` : ''}.{victim.armor_damage && ` ${victim.armor_damage.name}: ${words(victim.armor_damage.before)} → ${words(victim.armor_damage.after)}.`} {victim.point_note}</p>)}
          {view.explosives!.intents.filter(intent => intent.grenade_id === grenade.id).map(intent => <p className="native-help" key={`${intent.actor_id}-${intent.declared_round}`}>Saved toss-away: {view.actors.find(actor => actor.id === intent.actor_id)?.name ?? intent.actor_id}; declared round {intent.declared_round}; {intent.actions.map(action => `${action.operation} in round ${action.round}`).join(' → ') || 'no actions taken'}; stage {intent.stage}.</p>)}
        </section>;
      })}
    </>}
    <details><summary>Printed scope & GM rulings</summary>{view?.notes.map(note => <p className="native-help" key={note}>{note}</p>)}{view?.catalog.map(entry => <p key={entry.id}>{entry.name}: {entry.blast_radius.slice(1).map((high, index) => `${index ? entry.blast_radius[index] + 1 : 0}–${high}m ${entry.blast_damage[index]}`).join(' · ')}.</p>)}</details>
  </details>;
}
