import { useEffect, useState } from 'react';
import { api } from '../../services/api';
import type { ForceActor, ForceCatalog, ForceSkill, GameSession } from '../../types';
import '../sidebar/D6.css';

const title = (value: string) => value.replaceAll('_', ' ');
const proximityLabels: Record<string, string> = { touching: 'Touching', line_of_sight: 'In sight', hidden_nearby: 'Hidden · 1–100m', nearby_km: '101m–10km', regional: '11–1000km', same_planet: 'Same planet · >1000km', same_system: 'Same system', different_system: 'Different system' };

export function D6ForcePanel({ session, onSessionChanged }: { session: GameSession; onSessionChanged: (session: GameSession) => void }) {
  const [catalog, setCatalog] = useState<ForceCatalog | null>(null);
  const [actors, setActors] = useState<ForceActor[]>([]);
  const [actorId, setActorId] = useState('');
  const [powerId, setPowerId] = useState('');
  const [targetId, setTargetId] = useState('');
  const [objectTarget, setObjectTarget] = useState(false);
  const [shooterId, setShooterId] = useState('');
  const [reflectionRange, setReflectionRange] = useState('short');
  const [keep, setKeep] = useState(true);
  const [sameRound, setSameRound] = useState(true);
  const [actions, setActions] = useState(1);
  const [fp, setFp] = useState(false);
  const [cp, setCp] = useState(0);
  const [relationship, setRelationship] = useState('stranger');
  const [proximity, setProximity] = useState('line_of_sight');
  const [willing, setWilling] = useState(true);
  const [profile, setProfile] = useState('');
  const [description, setDescription] = useState('');
  const [mass, setMass] = useState(1);
  const [speed, setSpeed] = useState(10);
  const [maneuver, setManeuver] = useState(0);
  const [visible, setVisible] = useState(true);
  const [quiet, setQuiet] = useState(false);
  const [duration, setDuration] = useState(12);
  const [rounds, setRounds] = useState(1);
  const [stimulus, setStimulus] = useState(false);
  const [permanent, setPermanent] = useState('');
  const [bases, setBases] = useState<Partial<Record<ForceSkill, number>>>({});
  const [opposition, setOpposition] = useState('');
  const [tyiaAlter, setTyiaAlter] = useState('');
  const [mishap, setMishap] = useState('penalty');
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    api.nativeForceCatalog(controller.signal).then(setCatalog).catch(err => { if (!controller.signal.aborted) setError(String(err)); });
    return () => controller.abort();
  }, []);
  useEffect(() => {
    const controller = new AbortController();
    api.nativeForceActors(controller.signal).then(data => setActors(data.actors)).catch(err => { if (!controller.signal.aborted) setError(String(err)); });
    return () => controller.abort();
  }, [session]);
  const source = actors.find(actor => actor.id === actorId) ?? actors.find(actor => actor.id === session.character.id) ?? actors[0];
  const force = source?.d6.force;
  const learned = catalog?.powers.filter(power => force?.known_powers.includes(power.id)) ?? [];
  const power = learned.find(power => power.id === powerId) ?? learned[0];
  const attempt = force?.attempt;
  const tyia = source?.d6.origin?.force_tradition === 'tyia';
  const prepRounds = power ? Math.max(power.preparation_rounds, tyia ? 12 : 1) : 1;
  const combat = Boolean(session.encounter?.active || session.vehicle_encounter);
  const currentId = session.vehicle_encounter ? session.vehicle_encounter.actor_order[session.vehicle_encounter.current_turn_index] : session.encounter?.combatants[session.encounter.current_turn_index]?.id;
  const acted = session.vehicle_encounter?.turn_acted ?? session.encounter?.d6_turn_acted;
  const turn = !combat || (source?.id === currentId && !acted);
  const reduce = power?.id === 'reduce_injury' && force?.reduce_injury_available;
  const targets = actors.filter(actor => actor.id !== source?.id);
  const target = targets.find(actor => actor.id === targetId) ?? targets[0];
  const shooter = targets.find(actor => actor.id === shooterId) ?? targets[0];
  const boost = session.force_boost?.actor_id === source?.id ? session.force_boost : null;
  const upkeep = force?.effects.filter(effect => effect.maintained && !effect.recipient && !effect.activation_round).reduce((sum, effect) => sum + effect.skills.length, 0) ?? 0;
  async function run(action: string, payload: Record<string, unknown>) {
    if (!source) return;
    setPending(true); setError(null);
    try { const response = await api.nativeForceAction(action, { actor_id: source.id, ...payload }); onSessionChanged(response.session); setFp(false); }
    catch (err) { setError(err instanceof Error ? err.message : String(err)); }
    finally { setPending(false); }
  }
  const manage = (action: string, extra: Record<string, unknown> = {}) => run('manage', { action, stimulus, character_points: cp, ...extra });
  return <details name="native-tools" className="native-force-panel">
    <summary>Force powers · WEG Second Edition (1992)</summary>
    <p className="native-help">Learn skills and powers with Advancement & Force training. Each required skill takes one action; every component must pass. Combat uses the current actor and declared actions. Edit D6 sheet supports explicit GM corrections.</p>
    {error && <p role="alert" className="native-error">{error}</p>}
    <div className="native-form-row">
      <label>Force actor<select aria-label="Force actor" value={source?.id ?? ''} onChange={event => { setActorId(event.target.value); setProfile(''); setBases({}); }}>{actors.map(actor => <option key={actor.id} value={actor.id}>{actor.name}</option>)}</select></label>
      <span>{source?.d6.force_skills.control} Control · {source?.d6.force_skills.sense} Sense · {source?.d6.force_skills.alter} Alter · upkeep −{upkeep}D</span>
    </div>
    {!!force?.remain_pending && <p className="native-help">Remain Conscious is available as the next round’s first action. Declare at least two actions to attempt one further action.</p>}
    {!!force?.permanent_injuries.length && <p>Permanent injuries: {force.permanent_injuries.join('; ')}</p>}
    {!!force?.heroic_force_returns && <p>Heroic Force Points owed at adventure end: {force.heroic_force_returns}</p>}
    {!learned.length && <p>No learned Force powers for this actor. Force sensitivity alone grants no powers.</p>}
    {power && <>
      <label>Learned power<select aria-label="Learned Force power" value={power.id} onChange={event => { setPowerId(event.target.value); setProfile(''); setBases({}); }}>{learned.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
      <p>{power.description}</p><p className="native-help">{power.difficulty_notes} · {power.source}</p>
      {tyia && <p className="native-help">Tyia: every activation takes at least one minute (12 rounds); Emptiness entry is Easy. Alter difficulties increase one band after other modifiers. Above Heroic requires a GM harder target. Immediate injury/energy reactions cannot meet this timing.</p>}
      {prepRounds > 1 && <p className="native-help">Complete the {prepRounds}-round preparation before declaring a Force Point for the actual skill rolls.</p>}
      {tyia && power.skills.includes('alter') && <label>GM harder Alter difficulty (required above Heroic)<input aria-label="Tyia Alter difficulty" type="number" min={1} max={1000} value={tyiaAlter} onChange={event => setTyiaAlter(event.target.value)} /></label>}
      <div className="native-form-row">
        {!['self', 'reaction', 'scene'].includes(power.target) && <label>Power target<select aria-label="Force target" value={power.target === 'object' && !objectTarget ? 'scene_object' : target?.id ?? ''} onChange={event => { setObjectTarget(event.target.value !== 'scene_object'); setTargetId(event.target.value); }}>{power.target === 'object' && <option value="scene_object">Scene object (describe below)</option>}{targets.map(actor => <option key={actor.id} value={actor.id}>{actor.name}</option>)}</select></label>}
        {!!Object.keys(power.profiles).length && <label>Use<select aria-label="Force power use" value={profile || Object.keys(power.profiles)[0]} onChange={event => setProfile(event.target.value)}>{Object.entries(power.profiles).map(([id, label]) => <option key={id} value={id}>{label}</option>)}</select></label>}
        {power.can_keep_up && <label className="native-checkbox"><input type="checkbox" checked={keep} onChange={event => setKeep(event.target.checked)} />Keep power up</label>}
      </div>
      {!['self', 'reaction'].includes(power.target) && <div className="native-form-row">
        <label>Relationship<select value={relationship} onChange={event => setRelationship(event.target.value)}>{Object.entries(catalog?.relationship ?? {}).map(([id, value]) => <option key={id} value={id}>{title(id)} +{value}</option>)}</select></label>
        <label>Proximity<select value={proximity} onChange={event => setProximity(event.target.value)}>{Object.entries(catalog?.proximity ?? {}).map(([id, value]) => <option key={id} value={id}>{proximityLabels[id]} +{value}</option>)}</select></label>
        <label className="native-checkbox"><input type="checkbox" checked={willing} onChange={event => setWilling(event.target.checked)} />Willing target</label>
      </div>}
      {power.id === 'telekinesis' && <div className="native-form-row"><label>Object mass (kg)<input type="number" min={0.01} max={100000} value={mass} onChange={event => setMass(Number(event.target.value))} /></label><label>Speed (m/round)<input type="number" min={0} value={speed} onChange={event => setSpeed(Number(event.target.value))} /></label><label>Maneuver modifier<input type="number" min={0} value={maneuver} onChange={event => setManeuver(Number(event.target.value))} /></label><label><input type="checkbox" checked={visible} onChange={event => setVisible(event.target.checked)} />Object in sight</label></div>}
      {power.id === 'projective_telepathy' && <label className="native-checkbox"><input type="checkbox" checked={quiet} onChange={event => setQuiet(event.target.checked)} />Silent communication (+5 Control; GM may increase base)</label>}
      {['emptiness', 'hibernation_trance'].includes(power.id) && <label>Declared duration (5-second rounds)<input type="number" min={1} max={725760} value={duration} onChange={event => setDuration(Number(event.target.value))} /></label>}
      {power.id === 'reduce_injury' && <label>Permanent sacrifice if killed<input value={permanent} onChange={event => setPermanent(event.target.value)} placeholder="GM-agreed permanent injury" /></label>}
      <label>Declared effect / object / waking stimulus<input aria-label="Declared Force effect" value={description} maxLength={2000} onChange={event => setDescription(event.target.value)} /></label>
      {power.id === 'injure_kill' && session.encounter?.active && <button className="hp-btn" disabled={pending || !turn || !target} onClick={() => run('touch', { target_id: target?.id, character_points: cp, mishap })}>Roll brawling touch (one action; GM confirms reach)</button>}
      <details><summary>GM difficulty choices</summary><p className="native-help">Choose a value within the book’s difficulty band, before relationship/proximity. Opposed rolls use actual resistance. Affect Mind’s Alter base sets complexity (5–30).</p><div className="native-form-row">{power.skills.map(skill => <label key={skill}>{title(skill)} base<input type="number" min={1} max={1000} placeholder="Book default" value={bases[skill] ?? ''} onChange={event => setBases({ ...bases, [skill]: event.target.value ? Number(event.target.value) : undefined })} /></label>)}<label>Target resistance total<input type="number" min={0} max={10000} placeholder="Roll automatically" value={opposition} onChange={event => setOpposition(event.target.value)} /></label></div></details>
      <div className="native-form-row">
        <label>CP per component<input aria-label="Force Character Points" type="number" min={0} max={2} value={cp} onChange={event => setCp(Number(event.target.value))} /></label>
        <label>Wild 1<select value={mishap} onChange={event => setMishap(event.target.value)}><option value="penalty">Penalty</option><option value="complication">GM complication</option></select></label>
        {!combat && <><label>Declared actions<input type="number" min={1} max={10} value={actions} onChange={event => setActions(Number(event.target.value))} /></label><label className="native-checkbox"><input type="checkbox" checked={sameRound} onChange={event => setSameRound(event.target.checked)} />All skills this round (MAP)</label><label className="native-checkbox"><input type="checkbox" checked={fp} onChange={event => setFp(event.target.checked)} />Spend Force Point to double this round</label></>}
      </div>
      <button className="hp-btn" disabled={pending || !!attempt || (!turn && !reduce) || (fp && prepRounds > 1) || (tyia && ['reduce_injury', 'remain_conscious'].includes(power.id))} onClick={() => run('begin', { power_id: power.id, target_id: power.target === 'person' || (power.target === 'object' && objectTarget) ? target?.id : null, keep_up: power.can_keep_up && keep, same_round: sameRound, actions, force_point: fp, character_points: cp, mishap, relationship, proximity, willing, profile: profile || Object.keys(power.profiles)[0] || '', description, mass_kg: mass, speed_m_per_round: speed, maneuver_modifier: maneuver, in_sight: visible, quiet, duration_rounds: duration, permanent_injury: permanent, base_difficulties: Object.fromEntries(Object.entries(bases).filter(([, value]) => value !== undefined)), tyia_alter_difficulty: tyiaAlter === '' ? null : Number(tyiaAlter), resistance_total: opposition === '' ? null : Number(opposition) })}>Begin {power.name}</button>
    </>}
    {attempt && <section><h4>Activation in progress · {catalog?.powers.find(item => item.id === attempt.power_id)?.name}</h4>
      <p>{attempt.preparation_remaining ? `${attempt.preparation_remaining} round boundaries of preparation remain` : `${attempt.rolls.length}/${attempt.skills.length} skill actions resolved`}{attempt.failed ? ' · FAILED: add CP now or cancel' : ''}</p>
      {attempt.rolls.map((roll, index) => <p key={`${roll.skill}-${index}`} className="native-help">{title(roll.skill)} {roll.roll.expression}: {roll.roll.total} vs {roll.difficulty} · {roll.success ? 'passed' : 'failed'}</p>)}
      <div className="native-button-row"><button className="hp-btn" disabled={pending || !turn || attempt.failed} onClick={() => run('continue', { character_points: cp, mishap, actions, force_point: fp })}>Continue activation / preparation</button><button className="hp-btn" disabled={pending} onClick={() => manage('cancel')}>Cancel activation</button>
      {boost && <button className="hp-btn" disabled={pending || boost.force_used || boost.points_spent >= boost.limit} onClick={() => run('boost', { points: 1 })}>Add 1 CP to latest component ({boost.points_spent}/{boost.limit})</button>}</div>
    </section>}
    {!!force?.effects.length && <section><h4>Ongoing powers</h4><label>Ongoing effect target<select aria-label="Ongoing Force target" value={target?.id ?? ''} onChange={event => setTargetId(event.target.value)}>{targets.map(actor => <option key={actor.id} value={actor.id}>{actor.name}</option>)}</select></label>{force.effects.map(effect => <div key={effect.id} className="native-force-effect"><span>{catalog?.powers.find(item => item.id === effect.power_id)?.name ?? title(effect.power_id)}{effect.recipient ? ' · recipient' : effect.maintained ? ` · upkeep ${effect.skills.length}D${effect.activation_round ? ' next round' : ''}` : ''}{effect.ready_in_rounds ? ' · begins next round' : ''}{effect.rounds_remaining != null ? ` · ${effect.rounds_remaining} rounds left` : ''}</span>
      {!effect.recipient && <button className="hp-btn" disabled={pending} onClick={() => manage(effect.power_id === 'emptiness' ? 'leave_emptiness' : effect.power_id === 'hibernation_trance' ? 'wake' : 'drop', { effect_id: effect.id })}>{effect.power_id === 'emptiness' ? 'Roll exit' : effect.power_id === 'hibernation_trance' ? 'Wake on stimulus' : 'Drop'}</button>}
      {effect.power_id === 'telekinesis' && <button className="hp-btn" disabled={pending || !turn || !target} onClick={() => run('telekinetic-attack', { target_id: target?.id, effect_id: effect.id, character_points: cp, mishap })}>Attack selected target (+1 DSP)</button>}
      {effect.power_id === 'life_detection' && <button className="hp-btn" disabled={pending || !target} onClick={() => run('detect-life', { target_id: target?.id, character_points: cp, mishap })}>Detect selected approaching creature (≤10m)</button>}
    </div>)}</section>}
    <div className="native-form-row"><label className="native-checkbox"><input type="checkbox" checked={stimulus} onChange={event => setStimulus(event.target.checked)} />GM confirms waking stimulus / healing contact</label>{!!force?.healing_rolls_remaining && <button className="hp-btn" disabled={pending || combat} onClick={() => manage('heal')}>Roll accelerated healing (+2) · {force.healing_rolls_remaining} left today</button>}</div>
    {!combat && <div className="native-form-row"><label>Quiet time (5-second rounds)<input aria-label="Force time rounds" type="number" min={1} max={725760} value={rounds} onChange={event => setRounds(Number(event.target.value))} /></label><button className="hp-btn" disabled={pending} onClick={() => manage('advance', { rounds })}>Advance Force time</button></div>}
    {session.encounter?.active && <details><summary>Prepare personal energy reaction</summary><p className="native-help">Reserve a declared Control action. Absorption uses 15 + actual bolt damage; a redirect requires active Lightsaber Combat and a rolled lightsaber parry. Triggered reactions use the CP choice above.</p><div className="native-form-row"><label>Specific shooter<select value={shooter?.id ?? ''} onChange={event => setShooterId(event.target.value)}>{targets.map(actor => <option key={actor.id} value={actor.id}>{actor.name}</option>)}</select></label><label>Reflected bolt target<select value={target?.id ?? ''} onChange={event => setTargetId(event.target.value)}>{targets.map(actor => <option key={actor.id} value={actor.id}>{actor.name}</option>)}</select></label><label>Reflected bolt range<select value={reflectionRange} onChange={event => setReflectionRange(event.target.value)}><option value="point_blank">Point blank · 5</option><option value="short">Short · 10</option><option value="medium">Medium · 15</option><option value="long">Long · 20</option></select></label></div><div className="native-button-row"><button className="hp-btn" disabled={pending} onClick={() => run('prepare-reaction', { action: 'absorb_energy', character_points: cp, mishap })}>Prepare energy absorption</button><button className="hp-btn" disabled={pending || !shooter || !target} onClick={() => run('prepare-reaction', { action: 'redirect_blaster', attacker_id: shooter?.id, target_id: target?.id, range_band: reflectionRange, character_points: cp, mishap })}>Prepare bolt redirect</button></div></details>}
    <details><summary>Corebook catalog · {catalog?.powers.length ?? 0} powers</summary>{catalog?.powers.map(item => <p key={item.id}><strong>{item.name}</strong> · {item.skills.join(' / ')}<br /><span className="native-help">{item.difficulty_notes} {item.source}</span></p>)}</details>
  </details>;
}
