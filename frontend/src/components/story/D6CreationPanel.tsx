import { useEffect, useState } from 'react';
import { api } from '../../services/api';
import type { Character, D6Attribute, D6CreationCatalog, D6CreationRequest, D6Species, ForcePower, GameSession } from '../../types';

const attributes: D6Attribute[] = ['dexterity', 'knowledge', 'mechanical', 'perception', 'strength', 'technical'];
const defaultSkills = 'blaster=2\ndodge=2\nsearch=1\nfirst_aid=1\nspace_transports=1';
type CustomSpecies = {
  id: string; name: string; average_attribute_dice: number; minimums: Record<D6Attribute, string>; maximums: Record<D6Attribute, string>;
  move: number; move_maximum: number; concept: string; biology: string; breathing_needs: string; culture: string;
  special_abilities: string; disadvantages: string; story_factors: string; gm_rationale: string; source: string;
};
type CreationDraft = D6CreationRequest & { custom_species?: CustomSpecies | null };
const speciesText: { key: 'concept' | 'biology' | 'breathing_needs' | 'culture' | 'special_abilities' | 'disadvantages' | 'story_factors' | 'gm_rationale' | 'source'; label: string }[] = [
  { key: 'concept', label: 'Species concept' }, { key: 'biology', label: 'Biology & physical characteristics' },
  { key: 'breathing_needs', label: 'Breathing & environmental needs' }, { key: 'culture', label: 'Culture, society & technology' },
  { key: 'special_abilities', label: 'Special abilities & actual GM procedures' }, { key: 'disadvantages', label: 'Balancing disadvantages' },
  { key: 'story_factors', label: 'Story factors' }, { key: 'gm_rationale', label: 'GM balance rationale & approval' },
  { key: 'source', label: 'Species write-up source / GM record' },
];
function newSpecies(): CustomSpecies {
  return { id: `custom_${crypto.randomUUID().replaceAll('-', '').slice(0, 12)}`, name: '', average_attribute_dice: 12,
    minimums: Object.fromEntries(attributes.map(key => [key, '2D'])) as Record<D6Attribute, string>,
    maximums: Object.fromEntries(attributes.map(key => [key, '4D'])) as Record<D6Attribute, string>, move: 10, move_maximum: 12,
    concept: '', biology: '', breathing_needs: '', culture: '', special_abilities: '', disadvantages: '', story_factors: '', gm_rationale: '', source: '' };
}
function parseSkills(text: string) {
  const result: Record<string, number> = {};
  for (const line of text.split('\n').filter(line => line.trim())) {
    const match = line.trim().match(/^([a-z_ ]+)\s*=\s*([12])$/i);
    if (!match) throw new Error('Use one skill per line, such as blaster=2. Allocate 1D or 2D per skill.');
    const key = match[1].trim().toLowerCase().replaceAll(' ', '_');
    if (key in result) throw new Error(`Allocate ${key} once.`);
    result[key] = Number(match[2]);
  }
  return result;
}
function pips(value: string) { const match = value.match(/^(\d+)D(?:\+([12]))?$/i); return match ? Number(match[1]) * 3 + Number(match[2] ?? 0) : 0; }
function code(value: number) { return `${Math.floor(value / 3)}D${value % 3 ? `+${value % 3}` : ''}`; }

export function D6CreationPanel({ session, onSessionChanged }: { session: GameSession; onSessionChanged: (session: GameSession) => void }) {
  const [catalog, setCatalog] = useState<D6CreationCatalog | null>(null);
  const [powers, setPowers] = useState<ForcePower[]>([]);
  const [draft, setDraft] = useState<CreationDraft>({ name: '', occupation: 'Rebel operative', species_id: 'human', droid_model: null, owner: '', attributes: {}, skill_dice: {}, skill_attributes: {}, specializations: [], force_skills: [], force_sensitive: false, powers: [], force_background: '', background: '', gm_approval: '', equipment: ['blaster_pistol', 'comlink', 'medpac'], credits: 250, include_medic: true, expected_updated_at: session.updated_at ?? 0 });
  const [skillText, setSkillText] = useState(defaultSkills);
  const [error, setError] = useState('');
  const [pending, setPending] = useState(false);
  const [preview, setPreview] = useState<{ signature: string; character: Character; notes: string[]; request: CreationDraft } | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    Promise.all([api.nativeCreationCatalog(controller.signal), api.nativeForceCatalog(controller.signal)]).then(([data, force]) => {
      setCatalog(data); setPowers(force.powers);
      setDraft(previous => ({ ...previous, attributes: data.species.find(item => item.id === 'human')!.suggested_attributes }));
    }).catch(err => { if (!controller.signal.aborted) setError(String(err)); });
    return () => controller.abort();
  }, []);
  const custom = draft.species_id === 'custom' ? draft.custom_species : null;
  const spec: D6Species | undefined = custom ? { ...custom, attribute_dice: custom.average_attribute_dice + 6,
    suggested_attributes: draft.attributes as Record<D6Attribute, string>, creation_bonus_skills: [],
    notes: ['GM-defined species: abilities, needs and story factors are saved rulings; prose grants no automatic bonuses or equipment.'] } : catalog?.species.find(item => item.id === draft.species_id);
  const chassis = catalog?.droids.find(item => item.id === draft.droid_model);
  const signature = JSON.stringify({ draft, skillText, revision: session.updated_at });
  const reviewed = preview?.signature === signature ? preview : null;
  const combat = Boolean(session.encounter?.active || session.vehicle_encounter);
  function update(changes: Partial<CreationDraft>) { setDraft(previous => ({ ...previous, ...changes })); }
  function chooseSpecies(id: string) {
    const droid = id === 'droid';
    const choice = catalog?.species.find(item => item.id === id);
    const model = catalog?.droids[0];
    update({ species_id: id, custom_species: id === 'custom' ? draft.custom_species ?? newSpecies() : null,
      droid_model: droid ? model?.id ?? 'r2' : null, attributes: droid ? model?.pc_attributes ?? {} : id === 'custom' ? Object.fromEntries(attributes.map(key => [key, '3D'])) : choice?.suggested_attributes ?? {},
      force_skills: [], force_sensitive: false, powers: [], specializations: [] });
    setSkillText(droid ? 'blaster=2\ndodge=2\nsearch=2\nfirst_aid=2\ncomputer_programming_repair=2' : id === 'ewok' ? 'hide=2\nsneak=2\nsearch=1\nglider=1\nfirst_aid=1' : id === 'gamorrean' ? 'melee_combat=2\nbrawling=2\nthrown_weapons=1\ndodge=1\nsearch=1' : defaultSkills);
  }
  function updateSpecies(changes: Partial<CustomSpecies>) {
    if (custom) update({ custom_species: { ...custom, ...changes } });
  }
  function fitCustomAttributes() {
    if (!custom) return;
    const pools = Object.fromEntries(attributes.map(key => [key, pips(custom.minimums[key])])) as Record<D6Attribute, number>;
    let remaining = (custom.average_attribute_dice + 6 - draft.force_skills.length) * 3 - Object.values(pools).reduce((sum, value) => sum + value, 0);
    if (remaining < 0 || attributes.some(key => pools[key] > pips(custom.maximums[key]))) { setError('These species bounds cannot fit this attribute budget and initial Force skills.'); return; }
    while (remaining > 0) {
      const key = attributes.find(key => pools[key] < pips(custom.maximums[key]));
      if (!key) { setError('The six maximums cannot fit the exact average + 6D budget.'); return; }
      pools[key] += 1; remaining -= 1;
    }
    update({ attributes: Object.fromEntries(attributes.map(key => [key, code(pools[key])])) }); setError('');
  }
  function toggleForce(key: string) {
    const remove = draft.force_skills.includes(key);
    const pools = { ...draft.attributes };
    const attribute = attributes.find(item => remove ? pips(pools[item]) + 3 <= pips(spec?.maximums[item] ?? '4D') : pips(pools[item]) - 3 >= pips(spec?.minimums[item] ?? '2D'));
    if (attribute) pools[attribute] = code(pips(pools[attribute]) + (remove ? 3 : -3));
    update({ attributes: pools, force_skills: remove ? draft.force_skills.filter(item => item !== key) : [...draft.force_skills, key], force_sensitive: true, powers: [] });
  }
  async function review() {
    setPending(true); setError('');
    try {
      const request = { ...draft, expected_updated_at: session.updated_at ?? 0, skill_dice: parseSkills(skillText) };
      const response = await api.nativeCreationPreview(request);
      setPreview({ signature, character: response.character, notes: response.notes, request });
    } catch (err) { setError(err instanceof Error ? err.message : String(err)); }
    finally { setPending(false); }
  }
  async function start(recruit = false) {
    if (!reviewed) return;
    setPending(true); setError('');
    try {
      const response = recruit ? await api.nativeCreationRecruit(reviewed.request) : await api.nativeCreationStart(reviewed.request);
      onSessionChanged(response.session);
      if (recruit) { setPreview(null); update({ name: '' }); }
    }
    catch (err) { setError(err instanceof Error ? err.message : String(err)); }
    finally { setPending(false); }
  }
  return <details name="native-tools" className="native-force-panel native-creation-panel">
    <summary>Create a native D6 character</summary>
    <p className="native-help">Build a new custom template or a corebook Droid PC. Review all rules and starting equipment with the GM. Starting creates a new adventure and saves the current one in a “before_character_creation” slot.</p>
    {error && <p className="native-error" role="alert">{error}</p>}
    {catalog && <>
      <div className="native-form-row"><label>Character name<input aria-label="New D6 character name" maxLength={120} value={draft.name} onChange={event => update({ name: event.target.value })} /></label><label>Occupation<input aria-label="New D6 occupation" value={draft.occupation} maxLength={120} onChange={event => update({ occupation: event.target.value })} /></label></div>
      <label>Species<select aria-label="New D6 species" value={draft.species_id} onChange={event => chooseSpecies(event.target.value)}>{catalog.species.map(item => <option key={item.id} value={item.id}>{item.name} · {item.attribute_dice}D</option>)}<option value="droid">Droid · chassis attributes +1D each</option><option value="custom">New alien species · explicit GM record</option></select></label>
      {custom && <section className="native-training-card" aria-label="GM-defined species record">
        <h4>New alien species · GM review</h4>
        <p className="native-help">WEG40055 (1992), printed pp.15–17. Set the average dice and all six bounds explicitly. The PC receives exactly average + 6D; each initial Force skill costs 1D of that total. The usual 12D average and 1D–5D limits are guidelines. Record the GM's balancing reasons for the actual design.</p>
        <div className="native-form-row"><label>Species name<input aria-label="Custom species name" value={custom.name} maxLength={120} onChange={event => updateSpecies({ name: event.target.value })} /></label><label>Average attribute dice<input aria-label="Custom species average dice" type="number" min={0} step={1} value={custom.average_attribute_dice} onChange={event => updateSpecies({ average_attribute_dice: Number(event.target.value) })} /></label><label>Starting Move<input aria-label="Custom species starting Move" type="number" min={1} max={1000} step={1} value={custom.move} onChange={event => updateSpecies({ move: Number(event.target.value) })} /></label><label>Maximum Move<input aria-label="Custom species maximum Move" type="number" min={1} max={1000} step={1} value={custom.move_maximum} onChange={event => updateSpecies({ move_maximum: Number(event.target.value) })} /></label></div>
        <div className="native-editor-grid">{attributes.map(key => <div key={key}><strong>{key}</strong><label>Minimum<input aria-label={`Custom species ${key} minimum`} value={custom.minimums[key]} onChange={event => updateSpecies({ minimums: { ...custom.minimums, [key]: event.target.value } })} /></label><label>Maximum<input aria-label={`Custom species ${key} maximum`} value={custom.maximums[key]} onChange={event => updateSpecies({ maximums: { ...custom.maximums, [key]: event.target.value } })} /></label></div>)}</div>
        <button className="hp-btn" disabled={pending} onClick={fitCustomAttributes}>Fit attributes to this species & current Force choices</button>
        {speciesText.map(field => <label key={field.key}>{field.label}<textarea aria-label={`Custom species ${field.key}`} rows={2} maxLength={field.key === 'source' ? 1000 : 2000} value={custom[field.key]} onChange={event => updateSpecies({ [field.key]: event.target.value })} /></label>)}
        <p className="native-help">State “none” where appropriate. Species powers and special needs remain explicit GM procedures. This form grants no automatic bonus dice, breathing equipment, immunity or known power. The complete record and numerical advancement limits are saved with the character.</p>
      </section>}
      {draft.species_id === 'droid' && <div className="native-form-row"><label>Droid chassis<select aria-label="New Droid chassis" value={draft.droid_model ?? 'r2'} onChange={event => { const model = catalog.droids.find(item => item.id === event.target.value)!; update({ droid_model: model.id, attributes: model.pc_attributes }); }}>{catalog.droids.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label><label>Owner / companion<input aria-label="New Droid owner" value={draft.owner} maxLength={120} onChange={event => update({ owner: event.target.value })} /></label></div>}
      <p className="native-help">{(spec?.notes ?? chassis?.notes)?.join(' ')} Move {spec?.move ?? chassis?.move}m.</p>
      <div className="native-editor-grid">{attributes.map(key => <label key={key}>{key}<input aria-label={`Creation ${key}`} value={draft.attributes[key] ?? ''} disabled={!!draft.droid_model} onChange={event => update({ attributes: { ...draft.attributes, [key]: event.target.value } })} />{spec && <span className="native-help">{spec.minimums[key]}–{spec.maximums[key]}</span>}</label>)}</div>
      <p className="native-help">Allocated attributes + initial Force skills: {Object.values(draft.attributes).reduce((sum, value) => sum + pips(value), 0) + 3 * draft.force_skills.length} pips / {(spec?.attribute_dice ?? Object.values(draft.attributes).reduce((sum, value) => sum + pips(value), 0) / 3) * 3} pips. Three pips = one die.</p>
      {!draft.droid_model && <details><summary>Starting Force training</summary><label className="native-checkbox"><input type="checkbox" checked={draft.force_sensitive} disabled={!!draft.force_skills.length} onChange={event => update({ force_sensitive: event.target.checked })} />Force sensitive (2 starting FP; otherwise 1)</label>{['control', 'sense', 'alter'].map(key => <label className="native-checkbox" key={key}><input type="checkbox" checked={draft.force_skills.includes(key)} onChange={() => toggleForce(key)} />{key} · costs 1D from attributes, begins at 1D</label>)}<label>Previous Force teacher / training<input aria-label="Creation Force background" value={draft.force_background} maxLength={2000} onChange={event => update({ force_background: event.target.value })} /></label><p className="native-help">Each initial Force skill earns three starting power choices. Select prerequisites too; all required Force skills must be trained. Unselected choices stay saved. Use Printed character templates → Use earned starting Force power choices to select them later.</p><div className="native-editor-grid">{powers.map(power => <label className="native-checkbox" key={power.id}><input type="checkbox" checked={draft.powers.includes(power.id)} onChange={event => update({ powers: event.target.checked ? [...draft.powers, power.id] : draft.powers.filter(id => id !== power.id) })} />{power.name}</label>)}</div></details>}
      <label>Starting skill dice · {draft.droid_model ? '10D' : '7D'}<textarea aria-label="Creation skill dice" rows={7} value={skillText} onChange={event => setSkillText(event.target.value)} /></label><p className="native-help">One skill per line: skill_name=1 or skill_name=2. These are dice added to the attribute, before species bonuses. Force skills may receive dice only after buying their initial 1D. Droids receive no example NPC skills.</p>
      <label className="native-checkbox"><input type="checkbox" checked={!!draft.specializations.length} onChange={event => update({ specializations: event.target.checked ? [{ name: '', parent: 'blaster' }, { name: '', parent: 'search' }, { name: '', parent: 'space_transports' }] : [] })} />Spend 1D of this budget on three +1D specializations</label>
      {draft.specializations.map((choice, index) => <div className="native-form-row" key={index}><label>Specialization {index + 1}<input aria-label={`Creation specialization ${index + 1}`} value={choice.name} onChange={event => update({ specializations: draft.specializations.map((item, i) => i === index ? { ...item, name: event.target.value } : item) })} /></label><label>Parent skill<select value={choice.parent} onChange={event => update({ specializations: draft.specializations.map((item, i) => i === index ? { ...item, parent: event.target.value } : item) })}>{Object.keys(catalog.skills).map(key => <option key={key}>{key}</option>)}</select></label></div>)}
      <details><summary>GM-approved starting equipment</summary><p className="native-help">Starting equipment is approved as part of the template. These selections do not charge shopping prices. Droid chassis equipment is added automatically.</p><div className="native-editor-grid">{catalog.equipment.map(item => <label className="native-checkbox" key={item.id}><input type="checkbox" checked={draft.equipment.includes(item.id)} onChange={event => update({ equipment: event.target.checked ? [...draft.equipment, item.id] : draft.equipment.filter(id => id !== item.id) })} />{item.name}</label>)}</div><label>Starting credits<input aria-label="Creation credits" type="number" min={0} max={1000000} value={draft.credits} onChange={event => update({ credits: Number(event.target.value) })} /></label></details>
      <label>Background<textarea aria-label="Creation background" rows={3} value={draft.background} maxLength={4000} onChange={event => update({ background: event.target.value })} /></label><label>GM approval of template and equipment<input aria-label="Creation GM approval" value={draft.gm_approval} maxLength={2000} onChange={event => update({ gm_approval: event.target.value })} /></label>
      <label className="native-checkbox"><input type="checkbox" checked={draft.include_medic} onChange={event => update({ include_medic: event.target.checked })} />Include the Rebel Field Medic companion</label>
      <button className="hp-btn" disabled={pending || !draft.name.trim() || !draft.gm_approval.trim()} onClick={review}>Review new D6 character</button>
      {reviewed && <section className="native-training-card" aria-label="New D6 character preview"><h4>{reviewed.character.name} · {reviewed.character.race}</h4><p>{Object.entries(reviewed.character.d6!.attributes).map(([key, value]) => `${key} ${value}`).join(' · ')}</p><p>{Object.entries(reviewed.character.d6!.skills).map(([key, value]) => `${key} ${value}`).join(' · ')}</p><p>5 CP · {reviewed.character.d6!.force_points} FP · {reviewed.character.d6!.credits} credits · healthy · Move {reviewed.character.d6!.move}m</p><p>Known starting powers: {reviewed.character.d6!.force?.known_powers.length ?? 0} · saved earned choices: {reviewed.character.d6!.advancement?.power_grants.reduce((sum, grant) => sum + grant.remaining, 0) ?? 0}</p>{reviewed.notes.map(note => <p className="native-help" key={note}>{note}</p>)}<div className="native-button-row"><button className="hp-btn" disabled={pending || combat} onClick={() => start()}>Save current adventure & start this character</button><button className="hp-btn" disabled={pending || combat} onClick={() => start(true)}>Recruit this character to the party</button></div></section>}
    </>}
  </details>;
}
