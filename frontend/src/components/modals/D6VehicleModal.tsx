import { useState, type FormEvent } from 'react';
import type { Character, D6Arc, D6Crew, D6Scale, D6Station, D6Vehicle, D6VehicleWeapon } from '../../types';
import '../sidebar/D6.css';

const scales: D6Scale[] = ['character', 'speeder', 'walker', 'starfighter', 'capital', 'death_star'];
const arcs: D6Arc[] = ['front', 'back', 'left', 'right'];
const codePattern = '(?:0|[1-9]|[1-4][0-9]|50)[dD](?:\\+[12])?';
type EngineeringWeapon = D6VehicleWeapon & { purchase_value?: number; repair_damage?: D6Vehicle['damage'] };
type EngineeringCraft = Omit<D6Vehicle, 'weapons'> & {
  purchase_value?: number; hyperdrive_multiplier?: number | null; backup_hyperdrive?: number | null;
  nav_computer?: boolean; nav_computer_disabled?: boolean; escape_pods_disabled?: boolean;
  hull_breached?: boolean; location?: string; weapons: EngineeringWeapon[];
};

export function D6VehicleModal({ initial, character, onSave, onClose }: {
  initial: D6Vehicle; character: Character; onSave: (craft: D6Vehicle) => Promise<void>; onClose: () => void;
}) {
  const [draft, setDraft] = useState<EngineeringCraft>(() => structuredClone(initial));
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const people = [character, ...(character.companions ?? [])].filter(person => person.d6);
  const update = (changes: Partial<EngineeringCraft>) => setDraft(previous => ({ ...previous, ...changes }));
  const weaponUpdate = (index: number, changes: Partial<EngineeringWeapon>) => update({ weapons: draft.weapons.map((weapon, i) => i === index ? { ...weapon, ...changes } : weapon) });
  const crewUpdate = (id: string, changes: Partial<D6Crew>) => update({ crew: draft.crew.map(crew => crew.id === id ? { ...crew, ...changes } : crew) });

  async function save(event: FormEvent) {
    event.preventDefault();
    setPending(true); setError(null);
    try { await onSave(draft); }
    catch (err) { setError(err instanceof Error ? err.message : 'Unable to save craft'); }
    finally { setPending(false); }
  }

  return <div role="dialog" aria-modal="true" aria-label="Edit native D6 craft" className="native-vehicle-overlay">
    <form className="native-editor" onSubmit={save}>
      <h2>Edit vehicle or starship</h2>
      <p className="native-help">Equipment pools stay separate from crew skills. Record actual values and explicit GM corrections here. Craft repair projects handle paid parts, repair rolls and work time; resting does not repair a craft.</p>
      {error && <p role="alert" className="native-error">{error}</p>}
      <div className="native-editor-grid">
        <label>Craft name<input value={draft.name} onChange={event => update({ name: event.target.value })} required /></label>
        <label>Craft type<select value={draft.kind} onChange={event => update({ kind: event.target.value as D6Vehicle['kind'] })}><option value="starship">Starship</option><option value="vehicle">Surface vehicle</option></select></label>
        <label>Craft scale<select value={draft.scale} onChange={event => update({ scale: event.target.value as D6Scale })}>{scales.map(scale => <option key={scale}>{scale}</option>)}</select></label>
        <label>Piloting skill<input value={draft.piloting_skill} onChange={event => update({ piloting_skill: event.target.value })} required /></label>
        <label>Craft purchase value (credits)<input aria-label="Craft purchase value" type="number" min={0} max={1000000000000} step={1} value={draft.purchase_value ?? 0} onChange={event => update({ purchase_value: Number(event.target.value) })} /></label>
        <label>Current location<input aria-label="Craft location" maxLength={120} value={draft.location ?? ''} onChange={event => update({ location: event.target.value })} /></label>
        <label>Hyperdrive multiplier (blank = none)<input aria-label="Craft hyperdrive multiplier" type="number" min={0.001} max={1000} step="any" value={draft.hyperdrive_multiplier ?? ''} onChange={event => update({ hyperdrive_multiplier: event.target.value === '' ? null : Number(event.target.value) })} /></label>
        <label>Backup hyperdrive multiplier (blank = none)<input aria-label="Craft backup hyperdrive" type="number" min={0.001} max={1000} step="any" value={draft.backup_hyperdrive ?? ''} onChange={event => update({ backup_hyperdrive: event.target.value === '' ? null : Number(event.target.value) })} /></label>
        {(['hull', 'maneuverability', 'shields'] as const).map(field => <label key={field}>{field}<input aria-label={`Craft ${field}`} value={draft[field]} pattern={codePattern} onChange={event => update({ [field]: event.target.value })} required /></label>)}
        <label>Space Move (units)<input type="number" min={0} step="any" value={draft.space_move} onChange={event => update({ space_move: Number(event.target.value) })} required /></label>
        <label>Ground/atmosphere Move (meters)<input type="number" min={0} step="any" value={draft.atmosphere_move} onChange={event => update({ atmosphere_move: Number(event.target.value) })} required /></label>
        <label>Altitude (meters)<input type="number" min={0} step="any" value={draft.altitude} onChange={event => update({ altitude: Number(event.target.value) })} required /></label>
      </div>
      <label className="native-checkbox"><input type="checkbox" checked={draft.nav_computer ?? false} onChange={event => update({ nav_computer: event.target.checked })} />Navigation computer installed</label>
      <label className="native-checkbox"><input type="checkbox" checked={draft.airborne} onChange={event => update({ airborne: event.target.checked })} />Airborne in gravity (destroyed drives cause a crash/fall)</label>
      <h3>Crew assignments</h3>
      <label>Pilot station<select value={draft.crew.find(crew => crew.stations.includes('pilot'))?.id ?? ''} onChange={event => update({ crew: draft.crew.map(crew => ({ ...crew, stations: [...crew.stations.filter(station => station !== 'pilot'), ...(crew.id === event.target.value ? ['pilot' as const] : [])] })) })}>{draft.crew.map(crew => <option key={crew.id} value={crew.id}>{crew.name}</option>)}</select></label>
      {people.map(person => {
        const crew = draft.crew.find(member => member.character_id === person.id);
        return <div key={person.id} className="native-crew-assignment">
          <label className="native-checkbox"><input type="checkbox" checked={Boolean(crew)} disabled={crew?.stations.includes('pilot')} onChange={event => {
            if (event.target.checked) update({ crew: [...draft.crew, { id: person.id, name: person.name, character_id: person.id, stations: ['gunner', 'shields', 'engineer'], d6: person.d6!, control_penalty: 0, next_control_penalty: 0, evacuated: false }] });
            else update({ crew: draft.crew.filter(member => member.id !== person.id), weapons: draft.weapons.map(weapon => weapon.operator_id === person.id ? { ...weapon, operator_id: null } : weapon) });
          }} />{person.name} aboard</label>
          {crew && <div className="native-button-row">{(['gunner', 'shields', 'engineer'] as D6Station[]).map(station => <label className="native-checkbox" key={station}><input type="checkbox" checked={crew.stations.includes(station)} onChange={event => crewUpdate(crew.id, { stations: event.target.checked ? [...crew.stations, station] : crew.stations.filter(value => value !== station) })} />{station}</label>)}</div>}
        </div>;
      })}
      <h3>Weapons</h3>
      {draft.weapons.map((weapon, index) => <fieldset key={weapon.id} className="native-weapon-editor">
        <legend>{weapon.name}</legend>
        <div className="native-editor-grid">
          <label>Weapon name<input value={weapon.name} onChange={event => weaponUpdate(index, { name: event.target.value })} required /></label>
          <label>Weapon purchase value (credits)<input aria-label={`${weapon.name} purchase value`} type="number" min={0} max={1000000000000} step={1} value={weapon.purchase_value ?? 0} onChange={event => weaponUpdate(index, { purchase_value: Number(event.target.value) })} /></label>
          <label>Weapon skill<input value={weapon.skill} onChange={event => weaponUpdate(index, { skill: event.target.value })} required /></label>
          <label>Weapon kind<select value={weapon.kind} onChange={event => weaponUpdate(index, { kind: event.target.value as D6VehicleWeapon['kind'] })}>{['energy', 'ion', 'missile', 'tractor'].map(kind => <option key={kind}>{kind}</option>)}</select></label>
          <label>Weapon scale<select value={weapon.scale ?? ''} onChange={event => weaponUpdate(index, { scale: event.target.value as D6Scale || null })}><option value="">Same as craft</option>{scales.map(scale => <option key={scale}>{scale}</option>)}</select></label>
          <label>Fire control<input pattern={codePattern} value={weapon.fire_control} onChange={event => weaponUpdate(index, { fire_control: event.target.value })} required /></label>
          <label>Damage / tractor strength<input pattern={codePattern} value={weapon.damage} onChange={event => weaponUpdate(index, { damage: event.target.value })} required /></label>
          <label>Weapon operator<select value={weapon.operator_id ?? ''} onChange={event => weaponUpdate(index, { operator_id: event.target.value || null })}><option value="">Pilot operated</option>{draft.crew.filter(crew => crew.stations.includes('gunner')).map(crew => <option key={crew.id} value={crew.id}>{crew.name}</option>)}</select></label>
          <label>Ammunition (blank = unlimited)<input type="number" min={0} value={weapon.ammo ?? ''} onChange={event => weaponUpdate(index, { ammo: event.target.value === '' ? null : Number(event.target.value) })} /></label>
          <label>Weapon status<select value={weapon.status} onChange={event => weaponUpdate(index, { status: event.target.value as D6VehicleWeapon['status'] })}>{['operational', 'disabled', 'destroyed'].map(status => <option key={status}>{status}</option>)}</select></label>
          <label>Recorded weapon repair damage<select aria-label={`${weapon.name} repair damage`} value={weapon.repair_damage ?? 'intact'} onChange={event => weaponUpdate(index, { repair_damage: event.target.value as D6Vehicle['damage'] })}>{['intact', 'lightly_damaged', 'heavily_damaged', 'severely_damaged', 'destroyed'].map(level => <option key={level} value={level}>{level.replaceAll('_', ' ')}</option>)}</select></label>
          <label>Weapons system group<input value={weapon.system} onChange={event => weaponUpdate(index, { system: event.target.value })} required /></label>
        </div>
        <div className="native-button-row">{arcs.map(arc => <label key={arc} className="native-checkbox"><input type="checkbox" checked={weapon.arcs.includes(arc)} onChange={event => weaponUpdate(index, { arcs: event.target.checked ? [...weapon.arcs, arc] : weapon.arcs.filter(value => value !== arc) })} />{arc} arc</label>)}</div>
        <label className="native-checkbox"><input type="checkbox" checked={weapon.pilot_operated} onChange={event => weaponUpdate(index, { pilot_operated: event.target.checked })} />Pilot may operate this weapon</label>
        {(['space_ranges', 'atmosphere_ranges'] as const).map(field => <div key={field}><p className="native-help">{field === 'space_ranges' ? 'Space ranges (units)' : 'Ground/atmosphere ranges (meters)'}</p><div className="native-range-editor">{['Minimum', 'Short maximum', 'Medium maximum', 'Long maximum'].map((label, i) => <label key={label}>{label}<input aria-label={`${weapon.name} ${field} ${label}`} type="number" min={0} step="any" value={weapon[field][i]} onChange={event => {
          const range = [...weapon[field]] as [number, number, number, number]; range[i] = Number(event.target.value); weaponUpdate(index, { [field]: range });
        }} required /></label>)}</div></div>)}
        <button type="button" className="hp-btn" onClick={() => update({ weapons: draft.weapons.filter((_, i) => i !== index) })}>Remove this weapon</button>
      </fieldset>)}
      <button type="button" className="hp-btn" onClick={() => update({ weapons: [...draft.weapons, {
        id: crypto.randomUUID(), name: 'Mounted cannon', system: 'laser', skill: draft.kind === 'vehicle' ? 'vehicle_blasters' : 'starship_gunnery', scale: null, arcs: ['front'], fire_control: '1D', damage: '4D', kind: 'energy', space_ranges: [1, 3, 12, 25], atmosphere_ranges: [50, 300, 1000, 2500], operator_id: null, pilot_operated: true, ammo: null, status: 'operational', repair_damage: 'intact', purchase_value: 0,
      }] })}>Add weapon</button>
      <details><summary>GM damage and completed repairs</summary>
        <div className="native-editor-grid">
          <label>Craft damage<select value={draft.damage} onChange={event => update({ damage: event.target.value as D6Vehicle['damage'] })}>{['intact', 'lightly_damaged', 'heavily_damaged', 'severely_damaged', 'destroyed'].map(level => <option key={level}>{level}</option>)}</select></label>
          {(['maneuverability_lost', 'shields_lost', 'speed_losses'] as const).map(field => <label key={field}>{field.replaceAll('_', ' ')}<input type="number" min={0} max={field === 'speed_losses' ? 6 : 50} value={draft[field]} onChange={event => update({ [field]: Number(event.target.value) })} required /></label>)}
        </div>
        {(['controls_dead', 'drives_disabled', 'weapons_disabled', 'hyperdrive_disabled', 'generator_shutdown', 'nav_computer_disabled', 'escape_pods_disabled', 'hull_breached'] as const).map(field => <label key={field} className="native-checkbox"><input type="checkbox" checked={draft[field] ?? false} onChange={event => update({ [field]: event.target.checked })} />{field.replaceAll('_', ' ')}</label>)}
        <button type="button" className="hp-btn" onClick={() => update({ damage: 'intact', maneuverability_lost: 0, shields_lost: 0, speed_losses: 0, ion_durations: [], frozen_rounds: 0, spin_rounds: 0, controls_dead: false, drives_disabled: false, weapons_disabled: false, hyperdrive_disabled: false, generator_shutdown: false, nav_computer_disabled: false, escape_pods_disabled: false, hull_breached: false, destruction_countdown: null, destruction_cause: null, captured_by: null, captured_weapon: null, shield_allocation: {}, weapons: draft.weapons.map(weapon => ({ ...weapon, status: 'operational', repair_damage: 'intact' })) })}>Record GM-approved complete repairs</button>
        <p className="native-help">Use only after the GM resolves repair rolls, time, and cost. Ammunition and character injuries remain as recorded.</p>
      </details>
      <p className="native-help">Based on: {initial.source} Edited values are GM statistics.</p>
      <div className="native-editor-actions"><button className="send-btn" disabled={pending}>Save craft</button><button type="button" className="hp-btn" onClick={onClose} disabled={pending}>Cancel</button></div>
    </form>
  </div>;
}
