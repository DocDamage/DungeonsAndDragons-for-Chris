import { useState, type FormEvent } from 'react';
import { API_BASE } from '../../services/api';
import type { Character, Companion, D6Vehicle, D6VehicleWeapon, GameSession, RollResult } from '../../types';
import '../sidebar/D6.css';

type RepairSystem = 'maneuverability' | 'moves' | 'shields' | 'drives' | 'hyperdrive' | 'generator' | 'controls' | 'weapon' | 'weapons' | 'nav_computer' | 'escape_pods';
type Damage = 'lightly_damaged' | 'heavily_damaged' | 'severely_damaged' | 'destroyed';
type RepairRequest = {
  craft_id: string; system: RepairSystem; weapon_id: string | null; asset_value: number;
  assessed_damage: Damage; replacement: boolean; gm_difficulty: number | null; gm_cost: number | null;
  parts_item: string | null; reason: string; expected_updated_at: number | undefined;
};
type RepairQuote = { craft_id: string; key: string; skill: string; difficulty: number; parts_cost: number; percent: number | null; fingerprint: string; notes: string[]; source: string };
type RepairAttempt = { actor_id?: string; minutes: number; success: boolean; interrupted?: boolean; reason?: string; timing_reason?: string; roll?: RollResult; cp?: number; fp?: boolean };
type RepairProject = { id: string; request: RepairRequest; quote: RepairQuote; paid_credits: number; parts_source: string; status: 'pending' | 'completed' | 'cancelled'; attempts: RepairAttempt[] };
type EngineeringWeapon = D6VehicleWeapon & { purchase_value?: number; repair_damage?: Damage | 'intact' };
type EngineeringCraft = Omit<D6Vehicle, 'weapons' | 'repair_projects'> & {
  purchase_value?: number; hull_breached?: boolean; nav_computer_disabled?: boolean; escape_pods_disabled?: boolean;
  weapons: EngineeringWeapon[]; repair_projects?: RepairProject[];
};
type WorkResponse = { session: GameSession; eval_result?: { summary: string } };
type Person = Character | Companion;
const words = (value: string) => value.replaceAll('_', ' ');
const systems: Record<RepairSystem, string> = {
  maneuverability: 'Maneuverability', moves: 'Lost Moves', shields: 'Shields', drives: 'Drives', hyperdrive: 'Hyperdrive',
  generator: 'Power generator', controls: 'Controls', weapon: 'One mounted weapon', weapons: 'Whole weapons system',
  nav_computer: 'Navigation computer', escape_pods: 'Escape pods',
};
function standardMinutes(skill: string, attempts: number) {
  const schedule = skill === 'blaster_repair' ? [15, 60, 120] : skill === 'walker_repair' ? [15, 360, 1440, 2880] : [15, 60, 1440, 2880];
  return schedule[Math.min(attempts, schedule.length - 1)];
}
const duration = (minutes: number) => minutes === 1440 ? '1 day' : minutes === 2880 ? '2 days' : minutes >= 60 && minutes % 60 === 0 ? `${minutes / 60} ${minutes === 60 ? 'hour' : 'hours'}` : `${minutes} minutes`;

function damageSummary(craft: EngineeringCraft, system: RepairSystem) {
  if (system === 'maneuverability') return `${craft.maneuverability_lost}D lost`;
  if (system === 'moves') return `${craft.speed_losses} Moves lost`;
  if (system === 'shields') return `${craft.shields_lost}D lost`;
  if (system === 'weapon') return `${craft.weapons.filter(weapon => weapon.status !== 'operational' || weapon.repair_damage && weapon.repair_damage !== 'intact').length} damaged weapons`;
  const fields = { drives: 'drives_disabled', hyperdrive: 'hyperdrive_disabled', generator: 'generator_shutdown', controls: 'controls_dead', weapons: 'weapons_disabled', nav_computer: 'nav_computer_disabled', escape_pods: 'escape_pods_disabled' } as const;
  return craft[fields[system]] ? 'damaged / disabled' : 'no recorded damage';
}

async function engineeringRequest<T>(action: string, payload: unknown): Promise<T> {
  const response = await fetch(`${API_BASE}/weg-d6/engineering/${action}`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : Array.isArray(data.detail) ? data.detail.map((item: { msg: string }) => item.msg).join('; ') : 'Craft repair request failed');
  return data as T;
}

function SavedProject({ project, craft, people, disabled, onWork }: {
  project: RepairProject; craft: EngineeringCraft; people: Person[]; disabled: boolean;
  onWork: (action: 'attempt' | 'cancel', payload: unknown) => Promise<WorkResponse | undefined>;
}) {
  const [actorId, setActorId] = useState('');
  const [cp, setCP] = useState(0);
  const [fp, setFP] = useState(false);
  const [customTime, setCustomTime] = useState(false);
  const [minutes, setMinutes] = useState(15);
  const [timingReason, setTimingReason] = useState('');
  const [cancelReason, setCancelReason] = useState('');
  const technician = people.find(person => person.id === actorId) ?? people[0];
  const native = technician?.d6;
  const standard = standardMinutes(project.quote.skill, project.attempts.length);
  const elapsed = customTime ? minutes : standard;
  const weapon = craft.weapons.find(item => item.id === project.request.weapon_id);
  const validTime = Number.isInteger(elapsed) && elapsed >= 1 && elapsed <= 525600 && (elapsed === standard || Boolean(timingReason.trim()));
  const availablePoints = cp <= (native?.character_points ?? 0) && (!fp || (native?.force_points ?? 0) > 0);

  return <section className="native-training-card" aria-label={`${systems[project.request.system]} repair project`}>
    <strong>{systems[project.request.system]}{weapon ? ` · ${weapon.name}` : ''} · {project.status}</strong>
    <p>{words(project.quote.skill)} · difficulty {project.quote.difficulty} · {project.paid_credits.toLocaleString()} credits paid · parts: {project.parts_source}</p>
    <p className="native-help">{project.request.reason}</p>
    {project.status === 'pending' && <>
      <p className="native-help">Parts are reserved and paid once. Another attempt uses this project without charging again. Attempt {project.attempts.length + 1}: standard time {duration(standard)}.</p>
      <label>Repair technician<select aria-label={`Technician for ${project.id}`} value={technician?.id ?? ''} disabled={disabled} onChange={event => { setActorId(event.target.value); setCP(0); setFP(false); }}>{people.map(person => <option key={person.id} value={person.id}>{person.name} · {person.d6?.character_points ?? 0} CP · {person.d6?.force_points ?? 0} FP</option>)}</select></label>
      {native && <p className="native-help">{words(project.quote.skill)}: {native.skills[project.quote.skill] ?? native.attributes.technical} · {words(native.wound)}. The technician must be conscious and free of a pending Force activation.</p>}
      <div className="native-form-row">
        <label>Technician Character Points<input aria-label={`Repair CP for ${project.id}`} type="number" min={0} max={Math.min(2, native?.character_points ?? 0)} value={cp} disabled={disabled || fp} onChange={event => setCP(Number(event.target.value))} /></label>
        <label className="native-checkbox"><input type="checkbox" checked={fp} disabled={disabled || !native?.force_points} onChange={event => { setFP(event.target.checked); setCP(0); }} />Spend technician Force Point</label>
      </div>
      <label className="native-checkbox"><input type="checkbox" checked={customTime} disabled={disabled} onChange={event => { setCustomTime(event.target.checked); setMinutes(standard); }} />Use GM-customized attempt time</label>
      {customTime && <div className="native-form-row"><label>Actual work minutes<input aria-label={`Repair minutes for ${project.id}`} type="number" min={1} max={525600} value={minutes} disabled={disabled} onChange={event => setMinutes(Number(event.target.value))} /></label><label>GM reason for changing the standard time<input aria-label={`Repair timing reason for ${project.id}`} maxLength={1000} value={timingReason} disabled={disabled} onChange={event => setTimingReason(event.target.value)} /></label></div>}
      <button className="hp-btn" disabled={disabled || !technician || !!native?.force?.attempt || !validTime || !availablePoints || !Number.isInteger(cp) || cp < 0 || cp > 2 || craft.damage === 'destroyed'} onClick={async () => {
        const response = await onWork('attempt', { project_id: project.id, actor_id: technician?.id, character_points: cp, force_point: fp, minutes: customTime ? minutes : null, timing_reason: customTime ? timingReason : '' });
        if (response) { setCP(0); setFP(false); setCustomTime(false); setTimingReason(''); }
      }}>Attempt repair · advance {duration(elapsed)}</button>
      <details><summary>Abandon this paid project</summary><p className="native-help">Cancellation gives no automatic refund of purchased or reserved materials.</p><label>Reason for abandoning the work<input aria-label={`Cancel repair reason for ${project.id}`} maxLength={1000} value={cancelReason} disabled={disabled} onChange={event => setCancelReason(event.target.value)} /></label><button className="hp-btn" disabled={disabled || !cancelReason.trim()} onClick={() => onWork('cancel', { project_id: project.id, reason: cancelReason })}>Abandon project · no refund</button></details>
    </>}
    {!!project.attempts.length && <details><summary>Saved attempts ({project.attempts.length})</summary>{project.attempts.map((attempt, index) => <p className="native-help" key={index}>
      Attempt {index + 1}: {duration(attempt.minutes)} · {attempt.interrupted ? 'interrupted' : attempt.success ? 'success' : 'failed'}{attempt.actor_id ? ` · ${people.find(person => person.id === attempt.actor_id)?.name ?? attempt.actor_id}` : ''}{attempt.roll ? ` · ${attempt.roll.total} vs ${project.quote.difficulty} (${attempt.roll.breakdown})` : ''}{attempt.cp ? ` · ${attempt.cp} CP` : ''}{attempt.fp ? ' · 1 FP' : ''}{attempt.timing_reason ? ` · ${attempt.timing_reason}` : ''}{attempt.reason ? ` · ${attempt.reason}` : ''}
    </p>)}</details>}
  </section>;
}

export function D6EngineeringPanel({ session, onSessionChanged }: { session: GameSession; onSessionChanged: (session: GameSession) => void }) {
  const fleet = (session.vehicles ?? []) as EngineeringCraft[];
  const people = [session.character, ...(session.character.companions ?? [])].filter(person => person.d6);
  const [craftId, setCraftId] = useState('');
  const [system, setSystem] = useState<RepairSystem>('maneuverability');
  const [weaponId, setWeaponId] = useState('');
  const [assetValue, setAssetValue] = useState('');
  const [assessedDamage, setAssessedDamage] = useState<Damage>('lightly_damaged');
  const [replacement, setReplacement] = useState(false);
  const [gmDifficulty, setGMDifficulty] = useState('');
  const [gmCost, setGMCost] = useState('');
  const [parts, setParts] = useState('');
  const [reason, setReason] = useState('');
  const [review, setReview] = useState<{ signature: string; quote: RepairQuote; request: RepairRequest } | null>(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const craft = fleet.find(item => item.id === craftId) ?? fleet[0];
  const weapon = craft?.weapons.find(item => item.id === weaponId) ?? craft?.weapons[0];
  const combat = Boolean(session.encounter?.active || session.vehicle_encounter);
  const destroyedWeapon = system === 'weapon' && (weapon?.status === 'destroyed' || (weapon?.repair_damage && weapon.repair_damage !== 'intact' ? weapon.repair_damage : assessedDamage) === 'destroyed');
  const unlistedProcedure = ['controls', 'weapons', 'nav_computer', 'escape_pods'].includes(system);
  const needsGMCost = unlistedProcedure || system === 'hyperdrive';
  const needsGMDifficulty = unlistedProcedure || destroyedWeapon;
  const value = system === 'weapon' ? weapon?.purchase_value ?? 0 : craft?.purchase_value ?? 0;
  const request: RepairRequest = { craft_id: craft?.id ?? '', system, weapon_id: system === 'weapon' ? weapon?.id ?? null : null, asset_value: assetValue ? Number(assetValue) : 0, assessed_damage: assessedDamage, replacement: Boolean(destroyedWeapon && replacement), gm_difficulty: gmDifficulty ? Number(gmDifficulty) : null, gm_cost: needsGMCost && gmCost !== '' ? Number(gmCost) : null, parts_item: parts || null, reason, expected_updated_at: session.updated_at };
  const signature = JSON.stringify({ request, session: session.id, revision: session.updated_at, craft });
  const quote = review?.signature === signature ? review : null;
  const inventory = session.character.inventory.filter(item => item.quantity > 0);
  const projects = craft?.repair_projects ?? [];
  const pendingProjects = projects.filter(project => project.status === 'pending');
  const history = projects.filter(project => project.status !== 'pending');
  const validParts = !parts || inventory.some(item => item.name === parts);
  const affordable = !!parts || (quote?.quote.parts_cost ?? 0) <= (session.character.d6?.credits ?? 0);
  const validRequest = Boolean(craft && craft.damage !== 'destroyed' && reason.trim() && validParts && session.updated_at != null && (system !== 'weapon' || weapon) && (!destroyedWeapon || replacement) && (!needsGMCost || gmCost !== '') && (!needsGMDifficulty || gmDifficulty));

  async function work(action: 'begin' | 'attempt' | 'cancel', payload: unknown) {
    if (pending) return;
    setPending(true); setError(''); setMessage('');
    try {
      const response = await engineeringRequest<WorkResponse>(action, payload);
      onSessionChanged(response.session); setReview(null);
      setMessage(response.eval_result?.summary ?? (action === 'begin' ? 'Parts reserved; the paid repair project is saved.' : action === 'cancel' ? 'Repair project abandoned without an automatic refund.' : 'Repair attempt saved.'));
      return response;
    } catch (err) { setError(err instanceof Error ? err.message : String(err)); }
    finally { setPending(false); }
  }

  async function preview(event: FormEvent) {
    event.preventDefault();
    if (pending || !validRequest) return;
    setPending(true); setError(''); setMessage(''); setReview(null);
    try {
      const response = await engineeringRequest<{ quote: RepairQuote }>('quote', request);
      setReview({ signature, quote: response.quote, request });
    } catch (err) { setError(err instanceof Error ? err.message : String(err)); }
    finally { setPending(false); }
  }

  return <details name="native-tools" className="native-force-panel native-engineering-panel">
    <summary>Craft repair projects · {fleet.reduce((count, item) => count + (item.repair_projects?.filter(project => project.status === 'pending').length ?? 0), 0)} pending</summary>
    <p className="native-help">WEG Second Edition (1992), printed pp.87–91. Review parts and difficulty, reserve materials once, then resolve saved repair attempts. Standard attempt times: 15 minutes, 1 hour, 1 day, then 2 days for further retries. Walker repair uses 6 hours for the second attempt; vehicle blaster repair uses 2 hours from the third attempt onward. Work advances scene and fleet time.</p>
    {error && <p className="native-error" role="alert">{error}</p>}
    {message && <p role="status">{message}</p>}
    {combat && <p className="native-help">End the character or craft encounter before beginning, attempting, or cancelling repair work.</p>}
    {!craft ? <p className="native-help">Add a saved party craft in Vehicles & starships to start a repair project.</p> : <>
      <label>Craft to repair<select aria-label="Repair craft" value={craft.id} disabled={pending} onChange={event => { setCraftId(event.target.value); setWeaponId(''); setAssetValue(''); setReplacement(false); setParts(''); }}>{fleet.map(item => <option key={item.id} value={item.id}>{item.name} · {words(item.damage)}</option>)}</select></label>
      {craft.hull_breached && <p className="native-help">Hull breach remains recorded. This repair table does not resolve structural breaches; record the GM's separate ruling in Edit craft.</p>}
      {craft.destruction_countdown != null && <p className="native-error">Active destruction countdown: {craft.destruction_countdown} rounds. Shut down an overloaded generator before lengthy repair work; an attempt advances all countdowns.</p>}
      {craft.damage === 'destroyed' && <p className="native-help">A destroyed craft cannot be restored with a standard repair project.</p>}
      <form onSubmit={preview}>
        <div className="native-form-row"><label>Damaged system<select aria-label="Craft repair system" value={system} disabled={pending} onChange={event => { setSystem(event.target.value as RepairSystem); setAssetValue(''); setGMDifficulty(''); setGMCost(''); setReplacement(false); }}>{Object.entries(systems).map(([key, label]) => <option key={key} value={key}>{label} · {damageSummary(craft, key as RepairSystem)}</option>)}</select></label>
          {system === 'weapon' && <label>Mounted weapon<select aria-label="Weapon to repair" value={weapon?.id ?? ''} disabled={pending} onChange={event => { setWeaponId(event.target.value); setAssetValue(''); setReplacement(false); }}>{craft.weapons.map(item => <option key={item.id} value={item.id}>{item.name} · {words(item.repair_damage && item.repair_damage !== 'intact' ? item.repair_damage : item.status)}</option>)}</select></label>}
        </div>
        {system === 'weapon' && weapon && (!weapon.repair_damage || weapon.repair_damage === 'intact') && weapon.status !== 'destroyed' && <label>GM-assessed weapon damage<select aria-label="Assessed weapon damage" value={assessedDamage} disabled={pending} onChange={event => setAssessedDamage(event.target.value as Damage)}>{(['lightly_damaged', 'heavily_damaged', 'severely_damaged', 'destroyed'] as const).map(item => <option key={item} value={item}>{words(item)}</option>)}</select></label>}
        {destroyedWeapon && <label className="native-checkbox"><input type="checkbox" checked={replacement} disabled={pending} onChange={event => setReplacement(event.target.checked)} />Install a purchased replacement for this destroyed weapon (100% weapon value; GM installation difficulty)</label>}
        <div className="native-form-row">
          {!needsGMCost && <label>Actual {system === 'weapon' ? 'weapon' : 'craft'} value (credits)<input aria-label="Repair asset value" type="number" min={0} max={1000000000000} step={1} placeholder={value ? `Saved value: ${value}` : 'Required: actual purchase value'} value={assetValue} disabled={pending} onChange={event => setAssetValue(event.target.value)} required={!value} /></label>}
          <label>{needsGMDifficulty ? 'Required GM repair / installation difficulty' : 'GM difficulty within source band (optional)'}<input aria-label="Craft repair difficulty" type="number" min={1} max={1000} step={1} placeholder={needsGMDifficulty ? 'GM ruling required' : 'Source band maximum'} value={gmDifficulty} disabled={pending} onChange={event => setGMDifficulty(event.target.value)} required={Boolean(needsGMDifficulty)} /></label>
          {needsGMCost && <label>GM-approved parts cost (credits)<input aria-label="Craft repair GM cost" type="number" min={0} max={1000000000000} step={1} value={gmCost} disabled={pending} onChange={event => setGMCost(event.target.value)} required /></label>}
        </div>
        {needsGMCost && <p className="native-help">{system === 'hyperdrive' ? 'The source gives Moderate difficulty for hyperdrive repair, with no listed parts price. Record the actual GM-approved cost.' : 'This system has no specific repair cost or difficulty table. The GM must supply both for the actual procedure.'}</p>}
        <label>Parts source<select aria-label="Craft repair parts source" value={parts} disabled={pending} onChange={event => setParts(event.target.value)}><option value="">Buy parts with party credits</option>{[...new Set(inventory.map(item => item.name))].map(name => <option key={name} value={name}>Inventory: {name} (consume 1)</option>)}</select></label>
        {parts && <p className="native-help">Selecting inventory declares that the GM has approved this item as appropriate replacement parts. Beginning consumes one item and charges no credits. The quoted parts value is still recorded.</p>}
        <label>Actual damage, appropriate parts, facilities & GM ruling<input aria-label="Craft repair reason" maxLength={1000} value={reason} disabled={pending} onChange={event => setReason(event.target.value)} required /></label>
        <button className="hp-btn" disabled={pending || combat || !validRequest}>Review repair quote</button>
      </form>
      {quote && <section className="native-training-card" aria-label="Craft repair quote"><strong>{systems[system]} · {words(quote.quote.skill)} · difficulty {quote.quote.difficulty}</strong><p>Parts value: {quote.quote.parts_cost.toLocaleString()} credits{quote.quote.percent != null ? ` (${quote.quote.percent}% of asset value)` : ''} · pay now: {parts ? '1 inventory item' : `${quote.quote.parts_cost.toLocaleString()} credits`}</p><p className="native-help">Starting saves the paid project. Retries use the reserved parts; cancelling gives no automatic refund.</p>{quote.quote.notes.map(note => <p className="native-help" key={note}>{note}</p>)}<p className="native-help">{quote.quote.source}</p>{!affordable && <p className="native-error">Party credits are insufficient for this parts purchase.</p>}<button className="hp-btn" disabled={pending || combat || !validRequest || !affordable} onClick={() => work('begin', quote.request)}>Reserve parts & begin saved repair</button></section>}
      {!!pendingProjects.length && <h4>Paid projects awaiting repair</h4>}
      {pendingProjects.map(project => <SavedProject key={project.id} project={project} craft={craft} people={people} disabled={pending || combat} onWork={work} />)}
      {!!history.length && <details><summary>Completed & abandoned projects ({history.length})</summary>{[...history].reverse().map(project => <SavedProject key={project.id} project={project} craft={craft} people={people} disabled={pending || combat} onWork={work} />)}</details>}
    </>}
  </details>;
}
