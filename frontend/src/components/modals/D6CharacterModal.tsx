import { type FormEvent, useState, useEffect } from 'react';
import type { Character, D6Attribute, D6Character, D6Wound, ForcePower } from '../../types';
import { api } from '../../services/api';
import '../sidebar/D6.css';

const codePattern = '(?:0|[1-9]|[1-4][0-9]|50)[dD](?:\\+[12])?';
const woundLevels: D6Wound[] = ['healthy', 'wounded', 'incapacitated', 'mortally_wounded', 'dead'];

export function D6CharacterModal({ initialCharacter, onSave, onClose }: { initialCharacter: Character; onSave: (character: Character) => Promise<void> | void; onClose: () => void }) {
  const [draft, setDraft] = useState(() => structuredClone(initialCharacter));
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [newSkill, setNewSkill] = useState('');
  const [newCode, setNewCode] = useState('3D');
  const [newAttribute, setNewAttribute] = useState<D6Attribute>('perception');
  const [powers, setPowers] = useState<ForcePower[]>([]);
  useEffect(() => {
    const controller = new AbortController();
    api.nativeForceCatalog(controller.signal).then(data => setPowers(data.powers)).catch(err => { if (!controller.signal.aborted) setError(String(err)); });
    return () => controller.abort();
  }, []);
  const native = draft.d6!;
  const update = (changes: Partial<D6Character>) => setDraft(previous => ({ ...previous, d6: { ...previous.d6!, ...changes } }));

  async function save(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setPending(true);
    try { await onSave(draft); }
    catch (err) { setError(err instanceof Error ? err.message : 'Unable to save D6 sheet'); }
    finally { setPending(false); }
  }

  return <div role="dialog" aria-modal="true" aria-labelledby="native-editor-title" style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,.85)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000 }}>
    <form className="native-editor" onSubmit={save}>
      <h2 id="native-editor-title">Native WEG D6 character</h2><p className="native-help">Die codes are absolute pools, such as 3D+2. This sheet uses wounds, credits, and Force/Character Points.</p>
      {error && <p className="native-error" role="alert">{error}</p>}
      <div className="native-editor-grid">
        <label>Name<input value={draft.name} onChange={event => setDraft({ ...draft, name: event.target.value })} required /></label>
        <label>Species<input value={draft.race} onChange={event => setDraft({ ...draft, race: event.target.value })} required /></label>
        <label>Template<input value={draft.class_name} onChange={event => setDraft({ ...draft, class_name: event.target.value })} required /></label>
      </div>
      <h3>Six attributes</h3><div className="native-editor-grid">{Object.entries(native.attributes).map(([name, code]) => <label key={name}>{name}<input aria-label={`Attribute ${name}`} value={code} pattern="(?:[1-9]|[1-4][0-9]|50)[dD](?:\+[12])?" onChange={event => update({ attributes: { ...native.attributes, [name]: event.target.value } })} required /></label>)}</div>
      <h3>Skills</h3><div className="native-editor-grid">{Object.entries(native.skills).map(([name, code]) => <label key={name}>{name.replaceAll('_', ' ')}<input aria-label={`Skill ${name}`} value={code} pattern={codePattern} onChange={event => update({ skills: { ...native.skills, [name]: event.target.value } })} required /></label>)}</div>
      <div className="native-form-row"><label>New skill name<input value={newSkill} onChange={event => setNewSkill(event.target.value)} placeholder="e.g. computer_programming_repair" /></label><label>New skill pool<input value={newCode} onChange={event => setNewCode(event.target.value)} /></label><label>New skill attribute<select value={newAttribute} onChange={event => setNewAttribute(event.target.value as D6Attribute)}>{Object.keys(native.attributes).map(name => <option key={name}>{name}</option>)}</select></label></div>
      <button type="button" className="hp-btn" onClick={() => {
        const name = newSkill.trim().toLowerCase().replace(/[\s/-]+/g, '_');
        if (!name || !new RegExp(`^${codePattern}$`).test(newCode)) { setError('Enter a skill name and a pool such as 3D+2.'); return; }
        update({ skills: { ...native.skills, [name]: newCode }, skill_attributes: { ...native.skill_attributes, [name]: newAttribute } });
        setNewSkill(''); setError(null);
      }}>Add trained skill</button>
      <h3>Resources & injury (GM adjustments)</h3><div className="native-editor-grid">
        {(['character_points', 'force_points', 'credits'] as const).map(name => <label key={name}>{name.replaceAll('_', ' ')}<input type="number" min={0} value={native[name]} onChange={event => update({ [name]: Number(event.target.value) })} required /></label>)}
        <label>Dark Side Points<input type="number" value={native.dark_side_points} readOnly /><span>Use Dark Side & atonement for rulings or GM corrections.</span></label>
        <label>Wound<select value={native.wound} onChange={event => update({ wound: event.target.value as D6Wound })}>{woundLevels.map(wound => <option key={wound} value={wound}>{wound.replaceAll('_', ' ')}</option>)}</select></label>
        <label>Unconscious rounds<input type="number" min={0} value={native.unconscious_rounds} onChange={event => update({ unconscious_rounds: Number(event.target.value) })} /></label>
      </div>
      <h3>Armor & Force training</h3><div className="native-editor-grid">
        <label>Energy armor<input pattern={codePattern} value={native.armor_energy} onChange={event => update({ armor_energy: event.target.value })} required /></label>
        <label>Physical armor<input pattern={codePattern} value={native.armor_physical} onChange={event => update({ armor_physical: event.target.value })} required /></label>
        <label>Dexterity penalty (dice)<input type="number" min={0} max={50} value={native.dexterity_penalty} onChange={event => update({ dexterity_penalty: Number(event.target.value) })} /></label>
      </div>
      <h3>Move & species limits (GM records)</h3><p className="native-help">Human defaults are 4D maximum attributes and Move 10/12. Record other species’ limits from their source before training. Use Advancement & Force training for paid improvements; these fields are GM corrections.</p><div className="native-editor-grid">
        <label>Native Move (meters)<input type="number" min={1} max={1000} value={native.move ?? 10} onChange={event => update({ move: Number(event.target.value) })} /></label>
        <label>Species maximum Move<input type="number" min={1} max={1000} placeholder={draft.race.toLowerCase() === 'human' ? '12' : 'Required for advancement'} value={native.move_maximum ?? ''} onChange={event => update({ move_maximum: event.target.value ? Number(event.target.value) : null })} /></label>
        {Object.keys(native.attributes).map(name => <label key={name}>Species maximum {name}<input aria-label={`Species maximum ${name}`} pattern="(?:[1-9]|[1-4][0-9]|50)[dD](?:\+[12])?" placeholder={draft.race.toLowerCase() === 'human' ? '4D' : 'Required for advancement'} value={native.species_attribute_maximums?.[name as D6Attribute] ?? ''} onChange={event => {
          const maximums = { ...native.species_attribute_maximums };
          if (event.target.value) maximums[name as D6Attribute] = event.target.value; else delete maximums[name as D6Attribute];
          update({ species_attribute_maximums: maximums });
        }} /></label>)}
      </div>
      <label className="native-checkbox"><input type="checkbox" disabled={!!native.droid} checked={native.force_sensitive} onChange={event => update({ force_sensitive: event.target.checked })} />Force sensitive (Droids cannot train in the Force)</label>
      <div className="native-editor-grid">{(['control', 'sense', 'alter'] as const).map(name => <label key={name}>{name}<input disabled={!!native.droid} pattern={codePattern} value={native.force_skills[name]} onChange={event => update({ force_skills: { ...native.force_skills, [name]: event.target.value } })} required /></label>)}</div>
      <h3>Learned Force powers (GM corrections)</h3><p className="native-help">These adjustments spend no CP or study time. Use Advancement & Force training for paid learning. Required powers are selected together; their Force skills still need training above 0D.</p>
      {native.force && <label className="native-checkbox"><input type="checkbox" checked={native.force.dark_side_consumed} disabled />Consumed by the Dark Side (managed by Dark Side & atonement)</label>}
      <div className="native-editor-grid">{powers.map(power => <label className="native-checkbox" key={power.id} title={power.difficulty_notes}><input type="checkbox" checked={native.force?.known_powers.includes(power.id) ?? false} onChange={event => {
        if (!native.force) return;
        const known = new Set(native.force.known_powers);
        function learn(id: string) { powers.find(item => item.id === id)?.prerequisites.forEach(learn); known.add(id); }
        if (event.target.checked) learn(power.id);
        else { known.delete(power.id); let changed = true; while (changed) { changed = false; for (const item of powers) if (known.has(item.id) && item.prerequisites.some(id => !known.has(id))) { known.delete(item.id); changed = true; } } }
        update({ force: { ...native.force, known_powers: [...known] } });
      }} />{power.name} ({power.skills.join(' / ')})</label>)}</div>
      <h3>Weapon pools</h3>{draft.inventory.map((item, index) => item.item_type !== 'weapon' ? null : <div className="native-form-row" key={`${item.name}-${index}`}>
        <label>{item.name}<input value={item.damage || ''} aria-label={`${item.name} damage`} onChange={event => setDraft({ ...draft, inventory: draft.inventory.map((other, i) => i === index ? { ...other, damage: event.target.value } : other) })} placeholder="5D or STR+1D" required /></label>
        <label>Attack skill<input value={item.d6_skill || 'blaster'} onChange={event => setDraft({ ...draft, inventory: draft.inventory.map((other, i) => i === index ? { ...other, d6_skill: event.target.value } : other) })} /></label>
        <label>Damage type<select value={item.damage_type || 'energy'} onChange={event => setDraft({ ...draft, inventory: draft.inventory.map((other, i) => i === index ? { ...other, damage_type: event.target.value as 'energy' | 'physical' } : other) })}><option value="energy">Energy</option><option value="physical">Physical</option></select></label>
      </div>)}
      <button type="button" className="hp-btn" onClick={() => setDraft({ ...draft, inventory: [...draft.inventory.map(item => ({ ...item, equipped: item.item_type === 'weapon' ? false : item.equipped })), { name: 'Lightsaber', quantity: 1, item_type: 'weapon', equipped: true, damage: '5D', d6_skill: 'lightsaber', damage_type: 'energy' }] })}>Equip lightsaber (5D, base difficulty 20)</button>
      <div className="native-editor-actions"><button className="send-btn" disabled={pending}>Save D6 character</button><button type="button" className="hp-btn" onClick={onClose}>Cancel</button></div>
    </form>
  </div>;
}
