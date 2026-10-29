import { useEffect, useState } from 'react';
import { API_BASE } from '../../services/api';
import type { Character, D6Vehicle, ForcePower, GameSession, Item } from '../../types';
import '../sidebar/D6.css';

type Template = {
  id: string; name: string; pdf_page: number; source: string; species_id: string; species_name: string;
  attributes: Record<string, string>; attribute_budget: number; skill_budget: number; skills: Record<string, string>;
  suggested_skill_dice: Record<string, number>; force_skills: string[]; force_policy: 'yes' | 'no' | 'choice';
  force_tradition: 'standard' | 'tyia'; automatic_powers: string[]; move: number; credits: number; gear: Item[];
  notes: string[]; craft: string | null; debt: number; droid_model: string | null; dark_side_points: number;
};
type Catalog = { templates: Template[]; powers: ForcePower[]; notes: string[]; source: string };
type Grant = { id: string; skill: string; remaining: number; eligible_powers: string[] };
type StartingActor = { id: string; name: string; template_id: string; force_tradition: string; force_skills: Record<string, string>; known_powers: string[]; grants: Grant[] };
type State = { actors: StartingActor[]; source: string };
type Request = { template_id: string; name: string; skill_dice: Record<string, number>; specializations: { name: string; parent: string }[]; powers: string[]; force_sensitive: boolean; owner: string; background: string; gm_approval: string; survival_gear: string[]; pet_alive: boolean; include_medic: boolean; expected_updated_at: number | null };
type Preview = { character: Character; craft: D6Vehicle[]; notes: string[]; source: string };
type Mutation = (action: 'start' | 'recruit' | 'power-choice', payload: unknown) => Promise<boolean>;
const words = (value: string) => value.replaceAll('_', ' ');
const lines = (values: Record<string, number>) => Object.entries(values).map(([key, value]) => `${key}=${value}`).join('\n');
function allocation(text: string) {
  const value: Record<string, number> = {};
  for (const line of text.split(/[\n;]+/).map(item => item.trim()).filter(Boolean)) {
    const parts = line.split('=');
    const key = parts[0]?.trim().toLowerCase().replace(/[\s/-]+/g, '_');
    if (parts.length !== 2 || !key || !/^[12]$/.test(parts[1].trim()) || key in value) return { value, error: 'Use distinct listed skills: skill_name=1 or skill_name=2, one per line.' };
    value[key] = Number(parts[1]);
  }
  return { value, error: '' };
}
async function templateRequest<T>(action: string, payload?: unknown, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`${API_BASE}/weg-d6/templates/${action}`, payload === undefined ? { signal } : {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload), signal,
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { detail?: string | { msg: string }[] } | null;
    throw new Error(typeof body?.detail === 'string' ? body.detail : Array.isArray(body?.detail) ? body.detail.map(item => item.msg).join('; ') : `Template request failed (${response.status})`);
  }
  return response.json();
}

function StartingSlot({ actor, grant, powers, revision, disabled, run }: { actor: StartingActor; grant: Grant; powers: ForcePower[]; revision: number | undefined; disabled: boolean; run: Mutation }) {
  const [powerId, setPowerId] = useState('');
  const [reason, setReason] = useState('');
  const selected = grant.eligible_powers.includes(powerId) ? powerId : grant.eligible_powers[0];
  return <section className="native-training-card" aria-label={`${actor.name} earned ${grant.skill} starting powers`}>
    <strong>{words(grant.skill)} · {grant.remaining} earned starting choices remain</strong>
    {selected ? <><label>Eligible power with trained skills & known prerequisites<select aria-label={`Starting power ${grant.id}`} value={selected} disabled={disabled} onChange={event => setPowerId(event.target.value)}>{grant.eligible_powers.map(id => <option key={id} value={id}>{powers.find(power => power.id === id)?.name ?? words(id)}</option>)}</select></label><label>Actual starting-power selection<input aria-label={`Starting power reason ${grant.id}`} maxLength={1000} value={reason} disabled={disabled} onChange={event => setReason(event.target.value)} /></label><button className="hp-btn" disabled={disabled || !reason.trim() || revision == null} onClick={async () => { if (await run('power-choice', { actor_id: actor.id, grant_id: grant.id, power_id: selected, reason, expected_updated_at: revision })) setReason(''); }}>Use one earned starting choice</button></> : <p className="native-help">No currently eligible unlearned power fits this saved slot. Required skills and prerequisites must actually be known; the slot remains saved.</p>}
  </section>;
}

export function D6TemplatePanel({ session, onSessionChanged }: { session: GameSession; onSessionChanged: (session: GameSession) => void }) {
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [view, setView] = useState<{ revision: number | undefined; sessionId: string; data: State } | null>(null);
  const [templateId, setTemplateId] = useState('brash_pilot');
  const [name, setName] = useState('');
  const [skillText, setSkillText] = useState<string | null>(null);
  const [specializations, setSpecializations] = useState<{ name: string; parent: string }[]>([]);
  const [selectedPowers, setSelectedPowers] = useState<string[]>([]);
  const [sensitive, setSensitive] = useState(false);
  const [owner, setOwner] = useState('');
  const [background, setBackground] = useState('');
  const [approval, setApproval] = useState('');
  const [survivalGear, setSurvivalGear] = useState('');
  const [petAlive, setPetAlive] = useState(true);
  const [medic, setMedic] = useState(false);
  const [actorId, setActorId] = useState('');
  const [slotsOpen, setSlotsOpen] = useState(false);
  const [review, setReview] = useState<{ signature: string; request: Request; preview: Preview } | null>(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  useEffect(() => {
    const controller = new AbortController();
    templateRequest<Catalog>('catalog', undefined, controller.signal).then(setCatalog).catch(err => { if (!controller.signal.aborted) setError(String(err)); });
    return () => controller.abort();
  }, []);
  useEffect(() => {
    const controller = new AbortController();
    templateRequest<State>('state', undefined, controller.signal).then(data => setView({ revision: session.updated_at, sessionId: session.id, data })).catch(err => { if (!controller.signal.aborted) setError(String(err)); });
    return () => controller.abort();
  }, [session.id, session.updated_at]);
  const profile = catalog?.templates.find(item => item.id === templateId) ?? catalog?.templates[0];
  const parsed = allocation(skillText ?? (profile ? lines(profile.suggested_skill_dice) : ''));
  const spent = Object.values(parsed.value).reduce((sum, amount) => sum + amount, 0) + (specializations.length ? 1 : 0);
  const known = [...(profile?.automatic_powers ?? []), ...selectedPowers];
  const powers = catalog?.powers ?? [];
  const initialSkills = profile?.force_skills ?? [];
  const validPowers = selectedPowers.every(id => {
    const power = powers.find(item => item.id === id);
    return power && power.skills.every(skill => initialSkills.includes(skill)) && power.prerequisites.every(required => known.includes(required));
  });
  const request: Request = { template_id: profile?.id ?? '', name, skill_dice: parsed.value, specializations, powers: selectedPowers,
    force_sensitive: profile?.force_policy === 'yes' || profile?.force_policy === 'choice' && sensitive, owner, background, gm_approval: approval,
    survival_gear: profile?.id === 'cynical_scout' ? survivalGear.split('\n').map(item => item.trim()).filter(Boolean) : [], pet_alive: petAlive,
    include_medic: medic, expected_updated_at: session.updated_at ?? null };
  const signature = JSON.stringify({ request, session: session.id, revision: session.updated_at });
  const preview = review?.signature === signature ? review : null;
  const canReview = !!profile && !!name.trim() && !!approval.trim() && !parsed.error && spent === profile.skill_budget && validPowers && (!profile.droid_model || !!owner.trim()) && specializations.every(item => item.name.trim());
  const combat = Boolean(session.encounter?.active || session.vehicle_encounter);
  const nativeSession = session as GameSession & { d6_navigation?: { journeys: { status: string }[] }; d6_tasks?: { projects: { status: string }[] } };
  const navigation = nativeSession.d6_navigation?.journeys.some(journey => !['arrived', 'aborted', 'interrupted', 'off_course', 'abandoned'].includes(journey.status));
  const tasks = nativeSession.d6_tasks?.projects.some(project => project.status === 'pending');
  const drowning = [session.character, ...(session.character.companions ?? [])].some(person => (person.d6 as (NonNullable<Character['d6']> & { hazards?: { drowning?: unknown } }) | null)?.hazards?.drowning && person.d6?.wound !== 'dead');
  const blocked = combat || navigation || tasks || drowning;
  const current = view?.sessionId === session.id && view.revision === session.updated_at ? view.data : null;
  const slotActors = current?.actors.filter(actor => actor.grants.some(grant => grant.remaining > 0)) ?? [];
  const actor = slotActors.find(person => person.id === actorId) ?? slotActors[0];

  function choose(id: string) {
    const selected = catalog?.templates.find(item => item.id === id);
    if (!selected) return;
    setTemplateId(id); setSkillText(lines(selected.suggested_skill_dice)); setSpecializations([]); setSelectedPowers([]); setSensitive(false); setOwner(''); setReview(null);
  }
  async function run(action: 'start' | 'recruit' | 'power-choice', payload: unknown) {
    if (pending) return false;
    setPending(true); setError(''); setMessage('');
    try {
      const response = await templateRequest<{ session: GameSession; backup_slot?: string; eval_result?: { summary: string } }>(action, payload);
      onSessionChanged(response.session); setReview(null);
      setMessage(response.eval_result?.summary ?? (response.backup_slot ? `New template adventure started. Previous adventure saved as ${response.backup_slot}.` : 'Printed template saved.'));
      return true;
    } catch (err) { setError(err instanceof Error ? err.message : String(err)); return false; }
    finally { setPending(false); }
  }
  async function inspect() {
    if (!canReview || pending) return;
    setPending(true); setError(''); setMessage(''); setReview(null);
    try { const response = await templateRequest<Preview>('preview', request); setReview({ signature, request, preview: response }); }
    catch (err) { setError(err instanceof Error ? err.message : String(err)); }
    finally { setPending(false); }
  }

  return <details name="native-tools" className="native-force-panel native-template-panel">
    <summary>Printed character templates · 16 corebook choices</summary>
    <p className="native-help">Choose a printed template, allocate its actual starting skill dice, and review the character and equipment before starting or recruiting. Printed exceptions remain intact. Custom creation keeps its existing budgets.</p>
    {error && <p role="alert" className="native-error">{error}</p>}
    {message && <p role="status">{message}</p>}
    {blocked && <p className="native-help">Finish encounters, journeys, drowning emergencies and pending exclusive tasks before changing the roster or selecting starting powers. Character previews remain available.</p>}
    {profile && <>
      <fieldset disabled={pending} style={{ border: 0, padding: 0, margin: 0, minWidth: 0 }}>
        <div className="native-form-row"><label>Printed template<select aria-label="Stock character template" value={profile.id} onChange={event => choose(event.target.value)}>{catalog?.templates.map(item => <option key={item.id} value={item.id}>{item.name} · {item.species_name}</option>)}</select></label><label>Character name<input aria-label="Stock template character name" maxLength={120} value={name} onChange={event => setName(event.target.value)} /></label></div>
        <p>{profile.species_name} · printed attributes + initial Force skills: {profile.attribute_budget}D · {profile.skill_budget}D starting skills · Move {profile.move} · {profile.credits.toLocaleString()} credits</p>
        <div className="native-form-row">{Object.entries(profile.attributes).map(([key, value]) => <span key={key}>{words(key)} {value}</span>)}</div>
        <p className="native-help">{profile.source}</p>
        {profile.notes.map(note => <p className="native-help" key={note}>{note}</p>)}
        <label className="native-checkbox"><input type="checkbox" checked={request.force_sensitive} disabled={profile.force_policy !== 'choice'} onChange={event => setSensitive(event.target.checked)} />Force sensitive · {request.force_sensitive ? '2' : '1'} starting FP{profile.force_policy !== 'choice' ? ` · printed ${profile.force_policy}` : ' · player choice on the blank template line'}</label>
        {!!initialSkills.length && <><p>Initial Force skills: {initialSkills.map(skill => `${words(skill)} 1D`).join(' · ')}. Starting skill dice may improve these.</p><details><summary>Choose starting powers now, or keep earned choices for later</summary>{!!profile.automatic_powers.length && <p className="native-help">Automatic Tyia powers: {profile.automatic_powers.map(id => powers.find(power => power.id === id)?.name ?? words(id)).join(', ')}. These do not consume the three additional Control choices.</p>}<p className="native-help">Each printed initial Force skill earns three choices. Unselected choices are saved as actual starting slots. Select prerequisites too; all required Force skills must be trained. No CP, training or extra skill rank is granted by a later slot selection.</p>{powers.filter(power => !profile.automatic_powers.includes(power.id) && power.skills.every(skill => initialSkills.includes(skill))).map(power => <label key={power.id} className="native-checkbox"><input type="checkbox" checked={selectedPowers.includes(power.id)} onChange={event => setSelectedPowers(previous => event.target.checked ? [...previous, power.id] : previous.filter(id => id !== power.id))} />{power.name}{power.prerequisites.length ? ` · requires ${power.prerequisites.map(id => powers.find(item => item.id === id)?.name ?? words(id)).join(', ')}` : ''}</label>)}{!validPowers && <p className="native-error">Select the required known prerequisites before reviewing these powers.</p>}</details></>}
        {profile.droid_model && <label>Droid owner / companion<input aria-label="Stock Droid owner" value={owner} maxLength={120} onChange={event => setOwner(event.target.value)} /></label>}
        <details><summary>Printed skill list</summary>{['dexterity', 'knowledge', 'mechanical', 'perception', 'strength', 'technical'].map(attribute => <p className="native-help" key={attribute}><strong>{words(attribute)}:</strong> {Object.entries(profile.skills).filter(([, parent]) => parent === attribute).map(([skill]) => words(skill)).join(', ')}</p>)}</details>
        <label>Starting skill allocation · {spent}/{profile.skill_budget}D<textarea aria-label="Stock template skill dice" rows={6} value={skillText ?? lines(profile.suggested_skill_dice)} onChange={event => setSkillText(event.target.value)} /></label>
        <p className="native-help">One listed skill per line: skill_name=1 or skill_name=2. These are added dice, before printed species bonuses. All starting dice must be allocated.</p>
        {parsed.error && <p className="native-error">{parsed.error}</p>}
        <label className="native-checkbox"><input type="checkbox" checked={!!specializations.length} onChange={event => setSpecializations(event.target.checked ? Object.keys(profile.skills).slice(0, 3).map(parent => ({ parent, name: '' })) : [])} />Use 1D of this budget for three +1D specializations</label>
        {specializations.map((choice, index) => <div className="native-form-row" key={index}><label>Specialization {index + 1}<input aria-label={`Stock specialization ${index + 1}`} value={choice.name} maxLength={100} onChange={event => setSpecializations(previous => previous.map((entry, i) => i === index ? { ...entry, name: event.target.value } : entry))} /></label><label>Printed parent skill<select value={choice.parent} onChange={event => setSpecializations(previous => previous.map((entry, i) => i === index ? { ...entry, parent: event.target.value } : entry))}>{Object.keys(profile.skills).map(skill => <option key={skill} value={skill}>{words(skill)}</option>)}</select></label></div>)}
        <details><summary>Printed equipment & obligations</summary>{profile.gear.map((gear, index) => <p className="native-help" key={index}>{gear.name} ×{gear.quantity}{gear.damage ? ` · ${gear.damage}` : ''}{gear.description ? ` · ${gear.description}` : ''}</p>)}{profile.craft && <p>Starting craft: {words(profile.craft)} · actual fleet statistics are included in the preview.</p>}{profile.debt > 0 && <p>Starting debt: {profile.debt.toLocaleString()} credits · recorded obligation, separate from starting cash.</p>}{profile.id === 'young_jedi' && <p>Printed R2 astromech equipment companion, with source NPC skills.</p>}</details>
        {profile.id === 'cynical_scout' && <label>Actual reasonable survival gear approved by the GM<textarea aria-label="Stock scout survival gear" rows={3} maxLength={2400} value={survivalGear} onChange={event => setSurvivalGear(event.target.value)} placeholder="One actual item per line" /></label>}
        {profile.id === 'kid' && <label>Printed small pet<select aria-label="Stock Kid pet" value={petAlive ? 'alive' : 'dead'} onChange={event => setPetAlive(event.target.value === 'alive')}><option value="alive">Alive</option><option value="dead">Dead</option></select></label>}
        <label>Your character's background<textarea aria-label="Stock character background" rows={3} value={background} maxLength={4000} onChange={event => setBackground(event.target.value)} /></label>
        <label>GM approval of the printed template, gear & starting choices<input aria-label="Stock template GM approval" maxLength={2000} value={approval} onChange={event => setApproval(event.target.value)} /></label>
        <label className="native-checkbox"><input type="checkbox" checked={medic} onChange={event => setMedic(event.target.checked)} />New-adventure campaign option: include Rebel Field Medic</label>
        <button className="hp-btn" disabled={!canReview || pending} onClick={inspect}>Review printed-template character</button>
      </fieldset>
      {preview && <section className="native-training-card" aria-label="Reviewed printed-template character"><h4>{preview.preview.character.name} · {preview.preview.character.class_name}</h4><p>{Object.entries(preview.preview.character.d6!.attributes).map(([key, code]) => `${words(key)} ${code}`).join(' · ')}</p><p>Skills: {Object.entries(preview.preview.character.d6!.skills).map(([key, code]) => `${words(key)} ${code}`).join(' · ')}</p><p>5 CP · {preview.preview.character.d6!.force_points} FP · {preview.preview.character.d6!.dark_side_points} DSP · {preview.preview.character.d6!.credits} credits · Move {preview.preview.character.d6!.move}</p><p>Known powers: {preview.preview.character.d6!.force?.known_powers.map(id => powers.find(power => power.id === id)?.name ?? words(id)).join(', ') || 'none'} · earned choices remaining: {preview.preview.character.d6!.advancement?.power_grants.reduce((sum, grant) => sum + grant.remaining, 0) ?? 0}</p>{preview.preview.craft.map(craft => <p key={craft.id}>Craft: {craft.name} · hull {craft.hull} · maneuverability {craft.maneuverability} · shields {craft.shields} · Move {craft.space_move || craft.atmosphere_move}</p>)}{!!preview.preview.character.companions?.length && <p>Companions: {preview.preview.character.companions.map(person => person.name).join(', ')}</p>}<p className="native-help">Printed gear: {preview.preview.character.inventory.map(gear => `${gear.name} ×${gear.quantity}`).join(', ')}</p><div className="native-button-row"><button className="hp-btn" disabled={pending || blocked || session.updated_at == null} onClick={() => run('start', preview.request)}>Save current adventure & start this template</button><button className="hp-btn" disabled={pending || blocked || medic || session.updated_at == null} onClick={() => run('recruit', preview.request)}>Recruit this reviewed template</button></div></section>}
    </>}
    {actor && <details open={slotsOpen} onToggle={event => setSlotsOpen(event.currentTarget.open)}><summary>Use earned starting Force power choices · {slotActors.reduce((sum, person) => sum + person.grants.reduce((total, grant) => total + grant.remaining, 0), 0)} saved slots</summary><label>Character with earned starting choices<select aria-label="Starting Force power actor" value={actor.id} disabled={pending} onChange={event => setActorId(event.target.value)}>{slotActors.map(person => <option key={person.id} value={person.id}>{person.name} · {words(person.force_tradition)}</option>)}</select></label><p className="native-help">Known: {actor.known_powers.map(id => powers.find(power => power.id === id)?.name ?? words(id)).join(', ') || 'none'}. These choices were earned at creation; ordinary training continues through Advancement & Force training.</p>{actor.grants.filter(grant => grant.remaining > 0).map(grant => <StartingSlot key={grant.id} actor={actor} grant={grant} powers={powers} revision={session.updated_at} disabled={pending || blocked} run={run} />)}</details>}
  </details>;
}
