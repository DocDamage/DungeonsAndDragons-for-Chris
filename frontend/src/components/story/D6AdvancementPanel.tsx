import { useEffect, useState } from 'react';
import { api } from '../../services/api';
import D6RewardsPanel from './D6RewardsPanel';
import type { D6AdvancementView, D6Instructor, D6TrainingKind, D6TrainingQuote, D6TrainingRequest, ForcePower, GameSession } from '../../types';
import '../sidebar/D6.css';

const attributes = ['dexterity', 'knowledge', 'mechanical', 'perception', 'strength', 'technical'];
const title = (value: string) => value.replaceAll('_', ' ');
const names: Record<D6TrainingKind, string> = { skill: 'Basic skill / new skill', specialization: 'Specialization', advanced: 'Advanced Medicine', attribute: 'Attribute', force_skill: 'Force skill', force_power: 'Force power only', sensitivity: 'Become Force sensitive', move: 'Move +1 meter' };
const blankInstructor = (): D6Instructor => ({ name: '', attributes: {}, skills: {}, skill_attributes: {}, specialization_parents: {}, force_skills: { control: '0D', sense: '0D', alter: '0D' }, known_powers: [], full_time: false, studying_with_master: false, notes: '' });
function entries(value: string) {
  const result: Record<string, string> = {};
  for (const line of value.split(/[\n;]+/).map(line => line.trim()).filter(Boolean)) {
    const parts = line.split('=');
    if (parts.length !== 2 || !parts[0].trim() || !parts[1].trim()) throw new Error('Use one name=rating entry per line, such as blaster=6D.');
    result[parts[0].trim().toLowerCase().replace(/[\s/-]+/g, '_')] = parts[1].trim();
  }
  return result;
}
const lines = (value: Record<string, string>) => Object.entries(value).map(([key, value]) => `${key}=${value}`).join('\n');

export function D6AdvancementPanel({ session, onSessionChanged }: { session: GameSession; onSessionChanged: (session: GameSession) => void }) {
  const [view, setView] = useState<D6AdvancementView | null>(null);
  const [powers, setPowers] = useState<ForcePower[]>([]);
  const [actorId, setActorId] = useState('');
  const [kind, setKind] = useState<D6TrainingKind>('skill');
  const [skill, setSkill] = useState('blaster');
  const [attribute, setAttribute] = useState('dexterity');
  const [forceSkill, setForceSkill] = useState('control');
  const [powerId, setPowerId] = useState('');
  const [parent, setParent] = useState('blaster');
  const [teacherId, setTeacherId] = useState('');
  const [savedDays, setSavedDays] = useState(0);
  const [powerSavedDays, setPowerSavedDays] = useState(0);
  const [studyDays, setStudyDays] = useState(1);
  const [powerDays, setPowerDays] = useState(7);
  const [selectedPowers, setSelectedPowers] = useState<string[]>([]);
  const [review, setReview] = useState<{ signature: string; quote: D6TrainingQuote; affordable: boolean } | null>(null);
  const [claimChoices, setClaimChoices] = useState<Record<string, string>>({});
  const [award, setAward] = useState(5);
  const [reason, setReason] = useState('');
  const [adventure, setAdventure] = useState('');
  const [instructor, setInstructor] = useState<D6Instructor>(blankInstructor);
  const [ratings, setRatings] = useState('');
  const [teacherAttributes, setTeacherAttributes] = useState('');
  const [teacherParents, setTeacherParents] = useState('');
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    api.nativeAdvancementState(controller.signal).then(setView).catch(err => { if (!controller.signal.aborted) setError(String(err)); });
    return () => controller.abort();
  }, [session]);
  useEffect(() => {
    const controller = new AbortController();
    api.nativeForceCatalog(controller.signal).then(data => setPowers(data.powers)).catch(err => { if (!controller.signal.aborted) setError(String(err)); });
    return () => controller.abort();
  }, []);
  const source = view?.actors.find(actor => actor.id === actorId) ?? view?.actors.find(actor => actor.id === session.character.id);
  const native = source?.d6;
  const training = native?.advancement;
  const project = training?.project;
  const availablePowers = powers.filter(power => !native?.force?.known_powers.includes(power.id));
  const standalonePower = availablePowers.find(power => power.id === powerId) ?? availablePowers[0];
  const combat = Boolean(session.encounter?.active || session.vehicle_encounter);
  const key = kind === 'attribute' ? attribute : kind === 'force_skill' ? forceSkill : kind === 'force_power' ? standalonePower?.id ?? '' : kind === 'advanced' ? 'medicine' : skill;
  const request: D6TrainingRequest = { actor_id: source?.id, kind, key, attribute, parent_skill: kind === 'specialization' ? parent : undefined, teacher_id: ['move', 'sensitivity'].includes(kind) ? null : teacherId || null, days_saved: savedDays, power_days_saved: kind === 'force_skill' ? powerSavedDays : 0, powers: kind === 'force_skill' ? selectedPowers : [], gm_study_days: powerDays };
  const signature = JSON.stringify({ request, revision: session.updated_at, native, teachers: view?.campaign.instructors });
  const quote = review?.signature === signature ? review : null;
  const initialForce = parseInt(native?.force_skills[forceSkill as 'control'] ?? '0') === 0;
  const maxPowers = initialForce ? 3 : 1;
  async function run(action: string, payload: unknown) {
    setPending(true); setError(null);
    try { const response = await api.nativeAdvancementAction(action, payload); onSessionChanged(response.session); return response; }
    catch (err) { setError(err instanceof Error ? err.message : String(err)); }
    finally { setPending(false); }
  }
  async function preview() {
    setPending(true); setError(null);
    try { const data = await api.nativeAdvancementQuote(request); setReview({ ...data, signature }); }
    catch (err) { setError(err instanceof Error ? err.message : String(err)); }
    finally { setPending(false); }
  }
  function editInstructor(id: string) {
    const record = view?.campaign.instructors.find(item => item.id === id) ?? blankInstructor();
    setInstructor(structuredClone(record)); setRatings(lines(record.skills)); setTeacherAttributes(lines(record.attributes)); setTeacherParents(lines(record.specialization_parents));
  }
  async function saveInstructor() {
    try {
      const result = await run('instructor', { ...instructor, skills: entries(ratings), attributes: entries(teacherAttributes), specialization_parents: entries(teacherParents) });
      if (result) { setInstructor(blankInstructor()); setRatings(''); setTeacherAttributes(''); setTeacherParents(''); }
    } catch (err) { setError(err instanceof Error ? err.message : String(err)); }
  }
  return <details name="native-tools" className="native-force-panel native-advancement-panel">
    <summary>Advancement & Force training</summary>
    <p className="native-help">Spend earned Character Points during downtime. Review the cost first; payment happens when study begins, and the rank changes only when intensive study finishes. Ordinary rest does not count as study. Recording study days advances scene time, Force durations, mortality, and craft countdowns.</p>
    {error && <p className="native-error" role="alert">{error}</p>}
    {combat && <p className="native-help">End the character or craft encounter to use advancement controls.</p>}
    {view && <D6RewardsPanel key={`${session.id}-${view.campaign.adventure}`} view={view} session={session} onSessionChanged={onSessionChanged} />}
    <div className="native-form-row"><label>Student<select aria-label="Advancement student" value={source?.id ?? ''} onChange={event => { setActorId(event.target.value); setSelectedPowers([]); setStudyDays(1); }}>{view?.actors.map(actor => <option key={actor.id} value={actor.id}>{actor.name}</option>)}</select></label><span>{native?.character_points ?? 0} CP · Adventure window {view?.campaign.adventure ?? 1}: {view?.campaign.label}</span></div>
    {project ? <section className="native-training-card"><h4>Current study · {title(project.quote.key)}</h4><p>{project.quote.old_code} → {project.quote.new_code} · {project.quote.cp_cost} CP paid · {project.quote.teacher_name ?? 'Self-study'}</p><progress aria-label="Training progress" max={project.quote.days} value={project.days_completed} /><p>{project.days_completed}/{project.quote.days} intensive days completed</p><div className="native-form-row"><label>Intensive study days<input aria-label="Intensive study days" type="number" min={1} max={project.quote.days - project.days_completed} value={studyDays} onChange={event => setStudyDays(Number(event.target.value))} /></label><button className="hp-btn" disabled={pending || combat} onClick={() => run('study', { actor_ids: [source?.id], days: studyDays })}>Record intensive study</button><button className="hp-btn" disabled={pending || combat} onClick={() => run('cancel', { actor_id: source?.id })}>Abandon study (no CP refund)</button></div></section> : <>
      <div className="native-form-row"><label>Advancement type<select aria-label="Advancement type" value={kind} onChange={event => { setKind(event.target.value as D6TrainingKind); setSelectedPowers([]); setSavedDays(0); setPowerSavedDays(0); }}>{Object.entries(names).map(([id, name]) => <option key={id} value={id}>{name}</option>)}</select></label>
        {['skill', 'specialization'].includes(kind) && <label>Skill name<input aria-label="Advancement skill" list="native-training-skills" value={skill} onChange={event => setSkill(event.target.value)} /><datalist id="native-training-skills">{Object.keys(native?.skills ?? {}).map(skill => <option key={skill} value={skill} />)}</datalist></label>}
        {(kind === 'attribute' || kind === 'skill') && <label>{kind === 'attribute' ? 'Attribute' : 'New custom skill attribute'}<select aria-label="Advancement attribute" value={attribute} onChange={event => setAttribute(event.target.value)}>{attributes.map(attribute => <option key={attribute} value={attribute}>{title(attribute)}</option>)}</select></label>}
        {kind === 'force_skill' && <label>Force skill<select aria-label="Training Force skill" value={forceSkill} onChange={event => { setForceSkill(event.target.value); setSelectedPowers([]); }}>{['control', 'sense', 'alter'].map(skill => <option key={skill} value={skill}>{title(skill)} · {native?.force_skills[skill as 'control']}</option>)}</select></label>}
        {kind === 'force_power' && <label>New Force power<select aria-label="Training Force power" value={standalonePower?.id ?? ''} onChange={event => setPowerId(event.target.value)}>{availablePowers.map(power => <option key={power.id} value={power.id}>{power.name}</option>)}</select></label>}
      </div>
      {kind === 'specialization' && <label>Basic parent skill<input aria-label="Specialization parent" value={parent} onChange={event => setParent(event.target.value)} placeholder="blaster" /></label>}
      {!['sensitivity', 'move'].includes(kind) && <div className="native-form-row"><label>Instructor<select aria-label="Training instructor" value={teacherId} onChange={event => setTeacherId(event.target.value)}><option value="">Self-study</option>{view?.actors.filter(actor => actor.id !== source?.id).map(actor => <option key={actor.id} value={actor.id}>{actor.name} (party sheet)</option>)}{view?.campaign.instructors.map(teacher => <option key={teacher.id} value={teacher.id}>{teacher.name}</option>)}</select></label><label>Extra CP to save study days<input aria-label="Training days saved" type="number" min={0} max={1000} disabled={kind === 'attribute'} value={savedDays} onChange={event => setSavedDays(Number(event.target.value))} /></label></div>}
      {kind === 'force_power' && <label>GM-set power study days<input aria-label="Standalone power study days" type="number" min={1} max={3650} value={powerDays} onChange={event => setPowerDays(Number(event.target.value))} /></label>}
      {kind === 'force_skill' && <details><summary>Included / accompanying powers ({selectedPowers.length}/{maxPowers})</summary><p className="native-help">New skills include three instructor-known choices. A pip increase may include one power known by the instructor; independent research adds CP and time. All required skills and prerequisite powers must be learned. Unselected included choices remain saved with the course’s instructor.</p><div className="native-editor-grid">{availablePowers.filter(power => power.skills.includes(forceSkill as 'control')).map(power => <label key={power.id} className="native-checkbox"><input type="checkbox" checked={selectedPowers.includes(power.id)} onChange={event => setSelectedPowers(previous => event.target.checked ? [...previous, power.id] : previous.filter(id => id !== power.id))} />{power.name}</label>)}</div><label>Extra CP to save additional power-study days<input type="number" min={0} max={6} value={powerSavedDays} onChange={event => setPowerSavedDays(Number(event.target.value))} /></label></details>}
      <button className="hp-btn" disabled={pending || combat || !source} onClick={preview}>Review training cost</button>
      {quote && <section className="native-training-card" aria-label="Training cost review"><strong>{title(quote.quote.key)} · {quote.quote.old_code} → {quote.quote.new_code}</strong><p>{quote.quote.cp_cost} CP · {quote.quote.days} intensive day(s) · {quote.quote.teacher_name ?? 'Self-study'}</p>{quote.quote.notes.map((note, index) => <p key={index} className="native-help">{note}</p>)}<p className="native-help">{quote.quote.source}</p>{!quote.affordable && <p className="native-error">Not enough Character Points.</p>}<button className="hp-btn" disabled={pending || combat || !quote.affordable} onClick={() => run('start', request)}>Pay {quote.quote.cp_cost} CP & {quote.quote.days ? 'begin study' : 'apply advancement'}</button></section>}
    </>}
    {!!training?.power_grants.some(grant => grant.remaining > 0) && <section><h4>Included Force power choices</h4>{training.power_grants.filter(grant => grant.remaining > 0).map(grant => {
      const choices = availablePowers.filter(power => grant.allowed_powers.includes(power.id));
      const selected = choices.find(power => power.id === claimChoices[grant.id]) ?? choices[0];
      return <div className="native-training-card" key={grant.id}><p>{title(grant.skill)} · {grant.remaining} included choice(s) remaining · instructor must still qualify</p>{choices.length ? <><label>Included power<select aria-label={`Included ${grant.skill} power`} value={selected?.id ?? ''} onChange={event => setClaimChoices({ ...claimChoices, [grant.id]: event.target.value })}>{choices.map(power => <option key={power.id} value={power.id}>{power.name}</option>)}</select></label><button className="hp-btn" disabled={pending || combat} onClick={() => run('claim-power', { actor_id: source?.id, grant_id: grant.id, power_id: selected?.id })}>Select included power (prerequisites required)</button></> : <p className="native-help">No remaining unlearned power from this course’s instructor is available in the current catalog.</p>}</div>;
    })}</section>}
    <details><summary>Training history & suspended CP</summary>{training?.history.length ? [...training.history].reverse().map(item => <div key={item.id} className="native-training-card"><strong>{title(item.quote.key)} · {item.status}</strong><p>{item.quote.old_code} → {item.quote.new_code} · {item.quote.cp_cost} CP · {item.days_completed}/{item.quote.days} days</p>{item.student_roll && <p className="native-help">Attribute {item.student_roll.total} vs species maximum {item.maximum_roll?.total} · no Force/CP or injury modifiers</p>}{item.status === 'suspended' && <button className="hp-btn" disabled={pending || combat || (view?.campaign.adventure ?? 1) <= (item.finished_adventure ?? item.started_adventure)} onClick={() => run('release-suspended', { actor_id: source?.id, project_id: item.id })}>GM: release held CP after next adventure</button>}</div>) : <p className="native-help">No recorded courses.</p>}</details>
    <details><summary>GM: instructors</summary><p className="native-help">Record a teacher already found in the story. Party instructors use live sheets. Ordinary teachers must match the target rank; Force instructors also need at least 3D. Only full-time NPC instructors may take multiple Force pupils.</p>
      <label>Edit instructor<select aria-label="Edit instructor" value={instructor.id ?? ''} onChange={event => editInstructor(event.target.value)}><option value="">New instructor</option>{view?.campaign.instructors.map(teacher => <option key={teacher.id} value={teacher.id}>{teacher.name} · DSP {teacher.dark_side_points ?? 0}</option>)}</select></label>
      <label>Instructor name<input aria-label="Instructor name" maxLength={120} value={instructor.name} onChange={event => setInstructor({ ...instructor, name: event.target.value })} /></label>
      <div className="native-form-row"><label>Skill ratings (name=code)<textarea aria-label="Instructor skill ratings" rows={3} value={ratings} onChange={event => setRatings(event.target.value)} placeholder={'blaster=6D\nmedicine=2D'} /></label><label>Attribute ratings (name=code)<textarea aria-label="Instructor attribute ratings" rows={3} value={teacherAttributes} onChange={event => setTeacherAttributes(event.target.value)} placeholder="dexterity=4D" /></label></div>
      <div className="native-form-row">{['control', 'sense', 'alter'].map(skill => <label key={skill}>Instructor {skill}<input aria-label={`Instructor ${skill}`} value={instructor.force_skills[skill] ?? '0D'} onChange={event => setInstructor({ ...instructor, force_skills: { ...instructor.force_skills, [skill]: event.target.value } })} /></label>)}</div>
      <label className="native-checkbox"><input type="checkbox" checked={instructor.full_time} onChange={event => setInstructor({ ...instructor, full_time: event.target.checked })} />Full-time Force instructor (small group)</label><label className="native-checkbox"><input type="checkbox" checked={instructor.studying_with_master} onChange={event => setInstructor({ ...instructor, studying_with_master: event.target.checked })} />Currently studying with a master (cannot teach Force)</label>
      <details><summary>Instructor’s known Force powers ({instructor.known_powers.length})</summary><div className="native-editor-grid">{powers.map(power => <label key={power.id} className="native-checkbox"><input type="checkbox" checked={instructor.known_powers.includes(power.id)} onChange={event => {
        const known = new Set(instructor.known_powers);
        function learn(id: string) { powers.find(power => power.id === id)?.prerequisites.forEach(learn); known.add(id); }
        if (event.target.checked) learn(power.id); else { known.delete(power.id); let changed = true; while (changed) { changed = false; for (const item of powers) if (known.has(item.id) && item.prerequisites.some(id => !known.has(id))) { known.delete(item.id); changed = true; } } }
        setInstructor({ ...instructor, known_powers: [...known] });
      }} />{power.name}</label>)}</div></details>
      <details><summary>Instructor specialization metadata</summary><label>Specialization=basic parent<textarea rows={3} value={teacherParents} onChange={event => setTeacherParents(event.target.value)} placeholder="blaster_pistol=blaster" /></label></details>
      <label>Teacher / facility notes<input value={instructor.notes} maxLength={1000} onChange={event => setInstructor({ ...instructor, notes: event.target.value })} /></label>
      <button className="hp-btn" disabled={pending || combat || !instructor.name.trim()} onClick={saveInstructor}>Record instructor</button>
    </details>
    <details><summary>GM: awards & adventure boundary</summary><p className="native-help">Awards are explicit GM decisions. Record a boundary after an adventure before increasing the same skill another pip. It grants no CP and advances no time.</p><div className="native-form-row"><label>CP award<input aria-label="CP award" type="number" min={0} max={100000} value={award} onChange={event => setAward(Number(event.target.value))} /></label><label>Award reason<input aria-label="CP award reason" value={reason} maxLength={500} onChange={event => setReason(event.target.value)} /></label></div><button className="hp-btn" disabled={pending || combat || !reason.trim()} onClick={() => run('award', { actor_id: source?.id, points: award, reason })}>Award CP to {source?.name ?? 'student'}</button><label>Next adventure / training window<input aria-label="Next adventure label" value={adventure} maxLength={120} onChange={event => setAdventure(event.target.value)} /></label><button className="hp-btn" disabled={pending || combat || !adventure.trim()} onClick={() => run('adventure', { label: adventure })}>Record next adventure boundary</button></details>
    <details><summary>Rules conventions & scope</summary>{view?.rules.notes.map((note, index) => <p className="native-help" key={index}>{note}</p>)}<p className="native-help">Species-specific exceptions, special-ability advancement, instructor fees and facilities, and moral awards are resolved by the GM. The character editor remains available for explicit GM corrections.</p></details>
  </details>;
}
