import { useEffect, useState, type FormEvent } from 'react';
import { API_BASE } from '../../services/api';
import type { D6Character, GameSession } from '../../types';
import '../sidebar/D6.css';

type Person = { id: string; name: string; d6: D6Character };
type Mode = 'normal' | 'prepared' | 'rushed';
type TimeUnit = 'rounds' | 'minutes' | 'hours' | 'days';
type SavedRoll = { total: number; expression?: string; breakdown?: string };
type StepRequest = { skill: string; difficulty: number; rounds: number; mode: Mode; reason: string; rush_rounding?: 'down' | 'up' | null; rounding_reason?: string };
type StepDraft = StepRequest & { id: string; time: number; unit: TimeUnit };
type TaskRequest = {
  actor_id: string | null; label: string; reason: string; exclusive: boolean; steps: StepRequest[];
  participant_ids: string[]; commander_id: string | null; commander_participates: boolean;
  contact_confirmed: boolean; target_visible: boolean; same_range: boolean; participant_limit: number | null;
  command_difficulty: number | null; command_character_points: number; command_force_point: boolean; expected_updated_at: number | null;
};
type StepQuote = { skill: string; difficulty: number; base_rounds: number; preparation_rounds: number; work_rounds: number; total_rounds: number; mode: Mode };
type TaskQuote = { steps: StepQuote[]; combined: boolean; average_skill: number | null; command_band: string | null; command_difficulty: number | null; declared_count: number; table_count: number; participants: { actor_id: string; name: string; skills: Record<string, string>; declared_actions: number }[]; notes: string[]; source: string };
type CommandOutcome = { actor_id: string; name: string; difficulty: number; band: string; average_skill: number; declared_count: number; table_count: number; coordinated_count: number; coordinated_ids: string[]; bonus_dice: number; success: boolean; roll: SavedRoll; cp: number; fp: boolean; participates: boolean };
type TaskOutcome = { step: number; skill: string; mode: Mode; difficulty: number; rounds: number; success: boolean; roll: SavedRoll; pool_dice: number; pool_pips: number; cp: number; fp: boolean; actor_id?: string; name?: string; actor_ids?: string[]; average_skill?: number; bonus_dice?: number };
type WorkEntry = { step: number; rounds: number; reason: string; interrupted_actor_ids?: string[] };
type Declaration = { actor_id: string; name: string; role: string; declared_actions: number; exclusive?: boolean; skills?: Record<string, string>; skill?: string; skill_code?: string; cp?: number; fp?: boolean };
type TaskProject = { id: string; label: string; request: TaskRequest; quote: TaskQuote; status: string; current_step: number; work_rounds: number; elapsed_rounds: number; declarations: Declaration[]; command: CommandOutcome | null; results: TaskOutcome[]; work_log: WorkEntry[]; reason: string };
type TaskState = { actors: Person[]; tasks: { projects: TaskProject[] }; rules: { source: string; notes: string[]; preparation_banned: string[]; combining_banned: string[] } };
type MutationResponse = { session: GameSession; eval_result?: { summary: string } };
type Mutation = (action: 'begin' | 'advance' | 'resolve' | 'cancel', payload: unknown) => Promise<boolean>;
const units: Record<TimeUnit, number> = { rounds: 1, minutes: 12, hours: 720, days: 17280 };
const words = (value: string) => value.replaceAll('_', ' ');
const skillKey = (value: string) => value.trim().toLowerCase().replace(/[\s/-]+/g, '_');
const roundsText = (rounds: number) => {
  const unit = rounds >= 720 ? 'hour' : 'minute';
  const amount = Number((rounds / (rounds >= 720 ? 720 : 12)).toFixed(3));
  return `${rounds.toLocaleString()} ${rounds === 1 ? 'round' : 'rounds'} (${amount} ${unit}${amount === 1 ? '' : 's'})`;
};
const newStep = (): StepDraft => ({ id: crypto.randomUUID(), skill: 'search', difficulty: 10, rounds: 12, mode: 'normal', reason: '', time: 1, unit: 'minutes', rush_rounding: null, rounding_reason: '' });
const pointLimit = (person: Person | undefined, skill: string) => person?.d6.specializations.some(item => skillKey(item) === skillKey(skill)) ? 5 : 2;
const rating = (person: Person | undefined, skill: string) => {
  if (!person) return 'no native sheet';
  const key = skillKey(skill);
  const native = person.d6;
  return native.skills[key] ?? native.attributes[key as keyof typeof native.attributes] ?? (native.skill_attributes[key] ? native.attributes[native.skill_attributes[key]] : 'untrained pool assessed by engine');
};

async function taskRequest<T>(action: string, payload?: unknown, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`${API_BASE}/weg-d6/tasks/${action}`, payload === undefined ? { signal } : {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload), signal,
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { detail?: string | { msg: string }[] } | null;
    throw new Error(typeof body?.detail === 'string' ? body.detail : Array.isArray(body?.detail) ? body.detail.map(item => item.msg).join('; ') : `Task request failed (${response.status})`);
  }
  return response.json();
}

function PointControls({ person, skill, scope, cp, fp, setCP, setFP, disabled }: {
  person: Person | undefined; skill: string; scope: string; cp: number; fp: boolean;
  setCP: (value: number) => void; setFP: (value: boolean) => void; disabled: boolean;
}) {
  return <div className="native-form-row"><label>{scope} Character Points<input aria-label={`${scope} Character Points`} type="number" min={0} max={Math.min(pointLimit(person, skill), person?.d6.character_points ?? 0)} value={cp} disabled={disabled || fp} onChange={event => setCP(Number(event.target.value))} /></label><label className="native-checkbox"><input type="checkbox" checked={fp} disabled={disabled || !person?.d6.force_points} onChange={event => { setFP(event.target.checked); setCP(0); }} />Spend {scope.toLowerCase()} Force Point</label><span>{person?.d6.character_points ?? 0} CP · {person?.d6.force_points ?? 0} FP available</span></div>;
}

function SavedTask({ project, people, disabled, run }: { project: TaskProject; people: Person[]; disabled: boolean; run: Mutation }) {
  const [time, setTime] = useState(1);
  const [unit, setUnit] = useState<TimeUnit>('minutes');
  const [workReason, setWorkReason] = useState('');
  const [cancelReason, setCancelReason] = useState('');
  const [cp, setCP] = useState(0);
  const [fp, setFP] = useState(false);
  const step = project.quote.steps[project.current_step];
  const actor = people.find(person => person.id === project.request.actor_id);
  const remaining = Math.max(0, (step?.total_rounds ?? 0) - project.work_rounds);
  const requested = Math.ceil(time * units[unit]);
  const advance = Math.min(remaining, requested);
  const ready = !!step && remaining === 0;
  const validPoints = !!actor && Number.isInteger(cp) && cp >= 0 && cp <= Math.min(pointLimit(actor, step?.skill ?? ''), actor.d6.character_points) && (!fp || actor.d6.force_points > 0);
  const pending = project.status === 'pending';
  const command = project.command;
  const names = (ids: string[]) => ids.map(id => people.find(person => person.id === id)?.name ?? id).join(', ') || 'none';
  return <section className="native-training-card" aria-label={`Saved task ${project.label}`}>
    <h4>{project.label} · {words(project.status)}</h4>
    <p className="native-help">{project.request.reason}</p>
    <p>{project.quote.combined ? `Combined effort: ${project.request.participant_ids.map(id => people.find(person => person.id === id)?.name ?? id).join(', ')}` : `Performer: ${actor?.name ?? project.request.actor_id ?? 'not recorded'}`}</p>
    <p className="native-help">Total scene time recorded for this project: {roundsText(project.elapsed_rounds)}.</p>
    <details><summary>Saved work plan ({project.quote.steps.length} steps)</summary>{project.quote.steps.map((planned, index) => <p className="native-help" key={index}>Step {index + 1}: {words(planned.skill)} · difficulty {planned.difficulty} · {planned.mode} · preparation {roundsText(planned.preparation_rounds)} + work {roundsText(planned.work_rounds)}{project.request.steps[index]?.reason ? ` · ${project.request.steps[index].reason}` : ''}</p>)}</details>
    {command && <details open={pending}><summary>Saved Command outcome · {command.coordinated_count}/{command.declared_count} coordinated · +{command.bonus_dice}D</summary><p>{command.name}: {command.roll.total} vs Command difficulty {command.difficulty} ({words(command.band)}) · {command.success ? 'full coordination' : command.coordinated_count ? 'partial coordination' : 'no workers coordinated'}.</p><p>Actual coordinated workers: {names(command.coordinated_ids)}. Saved bonus +{command.bonus_dice}D applies only to this project’s aggregate task roll.</p><p className="native-help">Declared average skill {command.average_skill}D · source table row {command.table_count} · {command.participates ? 'commander also works (−1D)' : 'commander directs only'} · {command.cp} CP / {command.fp ? '1' : '0'} FP spent once.</p><p className="native-help">{command.roll.breakdown}</p></details>}
    {pending && step && <>
      <p><strong>Step {project.current_step + 1}: {words(step.skill)}</strong> · {project.work_rounds.toLocaleString()}/{step.total_rounds.toLocaleString()} focused rounds recorded</p>
      {step.preparation_rounds > 0 && <p className="native-help">Preparation: {Math.min(project.work_rounds, step.preparation_rounds)}/{step.preparation_rounds} rounds · work: {Math.max(0, project.work_rounds - step.preparation_rounds)}/{step.work_rounds} rounds. The preparation bonus requires exclusive preparation and work.</p>}
      {!ready ? <>
        <div className="native-form-row"><label>Focused work to record<input aria-label={`Work time for ${project.id}`} type="number" min={0.001} max={6307200} step="any" value={time} disabled={disabled} onChange={event => setTime(Number(event.target.value))} /></label><label>Work time units<select aria-label={`Work units for ${project.id}`} value={unit} disabled={disabled} onChange={event => setUnit(event.target.value as TimeUnit)}>{Object.keys(units).map(key => <option key={key} value={key}>{key}</option>)}</select></label></div>
        <p className="native-help">Remaining in this step: {roundsText(remaining)}. This action records at most the remaining time and advances the shared scene clock once. Ordinary passage of time does not credit focused work.</p>
        <label>Actual focused work & interruption facts<input aria-label={`Work reason for ${project.id}`} maxLength={1000} value={workReason} disabled={disabled} onChange={event => setWorkReason(event.target.value)} /></label>
        <button className="hp-btn" disabled={disabled || !workReason.trim() || !Number.isFinite(advance) || advance < 1 || advance > 6307200} onClick={async () => { if (await run('advance', { project_id: project.id, rounds: advance, reason: workReason })) setWorkReason(''); }}>Record {roundsText(advance)} of focused work</button>
      </> : <>
        <p className="native-help">The required time is recorded. Resolve this step once against difficulty {project.request.steps[project.current_step]?.difficulty}. A failed required step ends the project; a saved result cannot be rerolled.</p>
        {project.quote.combined ? <p className="native-help">The aggregate roll uses the saved Command benefit and group pool. Individual CP or FP cannot boost this aggregate roll.</p> : <PointControls person={actor} skill={step.skill} scope={`Task ${project.label}`} cp={cp} fp={fp} setCP={setCP} setFP={setFP} disabled={disabled} />}
        <button className="hp-btn" disabled={disabled || !project.quote.combined && !validPoints} onClick={async () => { if (await run('resolve', { project_id: project.id, character_points: project.quote.combined ? 0 : cp, force_point: !project.quote.combined && fp })) { setCP(0); setFP(false); } }}>Resolve required step {project.current_step + 1}</button>
      </>}
      <details><summary>Cancel this unfinished task</summary><label>Actual reason for stopping<input aria-label={`Cancel task reason for ${project.id}`} maxLength={1000} value={cancelReason} disabled={disabled} onChange={event => setCancelReason(event.target.value)} /></label><p className="native-help">Recorded work and Command expenditure remain in the saved history. Cancellation does not undo time or spent points.</p><button className="hp-btn" disabled={disabled || !cancelReason.trim()} onClick={() => run('cancel', { project_id: project.id, reason: cancelReason })}>Cancel unfinished task</button></details>
    </>}
    {!!project.results.length && <details open={!pending}><summary>Saved required-step results ({project.results.length})</summary>{project.results.map((result, index) => <section className="native-training-card" key={index}><strong>Step {result.step + 1}: {words(result.skill)} · {result.success ? 'success' : 'failed'}</strong><p>{result.name ?? names(result.actor_ids ?? [])} · {result.mode} · {result.pool_dice}D{result.pool_pips ? `+${result.pool_pips}` : ''} · roll {result.roll.total} vs {result.difficulty} · {result.cp} CP / {result.fp ? '1' : '0'} FP spent.</p>{result.bonus_dice != null && <p className="native-help">Actual coordinated group average {result.average_skill}D +{result.bonus_dice}D Command bonus.</p>}<p className="native-help">{roundsText(result.rounds)} recorded · {result.roll.breakdown}</p></section>)}</details>}
    {!!project.work_log.length && <details><summary>Recorded focused work ({project.work_log.length})</summary>{project.work_log.map((entry, index) => <p className="native-help" key={index}>Step {entry.step + 1}: {roundsText(entry.rounds)} · {entry.reason}{entry.interrupted_actor_ids?.length ? ` · Interrupted: ${names(entry.interrupted_actor_ids)}` : ''}</p>)}</details>}
    {!!project.declarations.length && <details><summary>Saved declarations ({project.declarations.length})</summary>{project.declarations.map((entry, index) => <p className="native-help" key={index}>{entry.name} · {words(entry.role)} · {entry.declared_actions} declared {entry.declared_actions === 1 ? 'action' : 'actions'}{entry.exclusive ? ' · exclusive work' : ''}{entry.skills ? ` · ${Object.entries(entry.skills).map(([skill, code]) => `${words(skill)} ${code}`).join(', ')}` : ''}{entry.skill ? ` · ${words(entry.skill)} ${entry.skill_code}` : ''}{entry.cp != null ? ` · ${entry.cp} CP / ${entry.fp ? '1' : '0'} FP spent` : ''}</p>)}</details>}
  </section>;
}

export function D6TaskPanel({ session, onSessionChanged }: { session: GameSession; onSessionChanged: (session: GameSession) => void }) {
  const [loaded, setLoaded] = useState<{ key: string; data: TaskState } | null>(null);
  const [refresh, setRefresh] = useState(0);
  const [failedLoad, setFailedLoad] = useState('');
  const [actorId, setActorId] = useState('');
  const [label, setLabel] = useState('');
  const [reason, setReason] = useState('');
  const [exclusive, setExclusive] = useState(false);
  const [steps, setSteps] = useState<StepDraft[]>(() => [newStep()]);
  const [combined, setCombined] = useState(false);
  const [participants, setParticipants] = useState<string[]>([]);
  const [commanderId, setCommanderId] = useState('');
  const [contact, setContact] = useState(false);
  const [visible, setVisible] = useState(false);
  const [sameRange, setSameRange] = useState(false);
  const [participantLimit, setParticipantLimit] = useState('');
  const [commandDifficulty, setCommandDifficulty] = useState('');
  const [commandCP, setCommandCP] = useState(0);
  const [commandFP, setCommandFP] = useState(false);
  const [review, setReview] = useState<{ signature: string; request: TaskRequest; quote: TaskQuote } | null>(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const loadKey = JSON.stringify([session.id, session.updated_at, refresh]);
  useEffect(() => {
    const controller = new AbortController();
    taskRequest<TaskState>('state', undefined, controller.signal).then(data => setLoaded({ key: loadKey, data })).catch(err => {
      if (!controller.signal.aborted) { setFailedLoad(loadKey); setError(err instanceof Error ? err.message : String(err)); }
    });
    return () => controller.abort();
  }, [loadKey]);
  const view = loaded?.key === loadKey ? loaded.data : null;
  const loading = !view && failedLoad !== loadKey;
  const people = view?.actors ?? [];
  const selectedPeople = participants.flatMap(id => { const person = people.find(item => item.id === id); return person ? [person] : []; });
  const actorChoices = combined ? selectedPeople : people;
  const actor = actorChoices.find(person => person.id === actorId) ?? actorChoices[0];
  const commander = people.find(person => person.id === commanderId) ?? people[0];
  const commanderParticipates = !!commander && participants.includes(commander.id);
  const commanderLongTask = combined && commanderParticipates && Math.ceil(steps[0].time * units[steps[0].unit]) > 1;
  const combat = Boolean(session.encounter?.active || session.vehicle_encounter);
  const navigation = (session as GameSession & { d6_navigation?: { journeys: { status: string }[] } }).d6_navigation;
  const currentJourney = navigation?.journeys.findLast(journey => !['arrived', 'aborted', 'interrupted', 'off_course', 'abandoned'].includes(journey.status));
  const navigationBlocked = !!currentJourney && currentJourney.status !== 'travelling';
  const sceneBlocked = combat || navigationBlocked;
  const projects = view?.tasks.projects ?? [];
  const activeProjects = projects.filter(project => project.status === 'pending');
  const history = projects.filter(project => project.status !== 'pending');
  const busyIds = new Set(activeProjects.flatMap(project => [...(project.request.participant_ids.length ? project.request.participant_ids : [project.request.actor_id ?? '']), ...(project.request.commander_id ? [project.request.commander_id] : [])]));
  const selectedBusyPeople = people.filter(person => busyIds.has(person.id) && (person.id === actor?.id || combined && (participants.includes(person.id) || person.id === commander?.id)));
  const request: TaskRequest = {
    actor_id: actor?.id ?? null, label, reason, exclusive,
    steps: steps.map(step => ({ skill: skillKey(step.skill), difficulty: step.difficulty, rounds: Math.ceil(step.time * units[step.unit]), mode: step.mode, reason: step.reason, rush_rounding: step.mode === 'rushed' ? step.rush_rounding : null, rounding_reason: step.mode === 'rushed' ? step.rounding_reason : '' })),
    participant_ids: combined ? selectedPeople.map(person => person.id) : [], commander_id: combined ? commander?.id ?? null : null,
    commander_participates: combined && commanderParticipates, contact_confirmed: combined && contact, target_visible: combined && visible, same_range: combined && sameRange,
    participant_limit: combined && participantLimit ? Number(participantLimit) : null, command_difficulty: combined && commandDifficulty ? Number(commandDifficulty) : null,
    command_character_points: combined && !commanderLongTask ? commandCP : 0, command_force_point: combined && !commanderLongTask && commandFP, expected_updated_at: session.updated_at ?? null,
  };
  const signature = JSON.stringify({ request, sessionId: session.id, actors: people, revision: session.updated_at });
  const quote = review?.signature === signature ? review : null;
  const validSteps = request.steps.every(step => step.skill && step.reason.trim() && Number.isInteger(step.difficulty) && step.difficulty >= 1 && step.difficulty <= 1000 && Number.isFinite(step.rounds) && step.rounds >= 1 && step.rounds <= 6307200 && (step.mode !== 'rushed' || step.rounds >= 2));
  const validCommand = !combined || !!commander && selectedPeople.length >= 2 && contact && visible && sameRange && Number.isInteger(request.participant_limit) && (request.participant_limit ?? 0) >= selectedPeople.length && Number.isInteger(request.command_character_points) && request.command_character_points >= 0 && request.command_character_points <= Math.min(pointLimit(commander, 'command'), commander.d6.character_points) && (!request.command_force_point || commander.d6.force_points > 0) && (!commandDifficulty || Number.isInteger(Number(commandDifficulty)) && Number(commandDifficulty) >= 1 && Number(commandDifficulty) <= 1000);
  const canReview = !!view && !!actor && !!label.trim() && !!reason.trim() && exclusive && validSteps && validCommand && !selectedBusyPeople.length && session.updated_at != null;
  const skills = [...new Set(people.flatMap(person => [...Object.keys(person.d6.attributes), ...Object.keys(person.d6.skills), ...Object.keys(person.d6.skill_attributes)]))].sort();
  const toggleParticipant = (id: string) => setParticipants(previous => previous.includes(id) ? previous.filter(item => item !== id) : [...previous, id]);
  const moveParticipant = (index: number, offset: number) => setParticipants(previous => {
    const next = [...previous]; [next[index], next[index + offset]] = [next[index + offset], next[index]]; return next;
  });
  const updateStep = (id: string, changes: Partial<StepDraft>) => setSteps(previous => previous.map(step => step.id === id ? { ...step, ...changes } : step));

  async function run(action: 'begin' | 'advance' | 'resolve' | 'cancel', payload: unknown) {
    if (pending) return false;
    setPending(true); setError(''); setMessage('');
    try {
      const response = await taskRequest<MutationResponse>(action, payload);
      onSessionChanged(response.session); setReview(null); setCommandCP(0); setCommandFP(false);
      setMessage(response.eval_result?.summary ?? 'Task state saved.');
      return true;
    } catch (err) { setError(err instanceof Error ? err.message : String(err)); return false; }
    finally { setPending(false); }
  }

  async function preview(event: FormEvent) {
    event.preventDefault();
    if (pending || !canReview) return;
    setPending(true); setError(''); setMessage(''); setReview(null);
    try { const response = await taskRequest<{ quote: TaskQuote }>('quote', request); setReview({ signature, request, quote: response.quote }); }
    catch (err) { setError(err instanceof Error ? err.message : String(err)); }
    finally { setPending(false); }
  }

  return <details name="native-tools" className="native-force-panel native-task-panel">
    <summary>Combined actions, preparation & focused tasks · {activeProjects.length} pending</summary>
    <p className="native-help">WEG Second Edition (1992), printed pp.55, 58, 65, 68–70. Review an actual task and its required checks before beginning. Preparation adds 1D after equal exclusive preparation and work time; rushing halves eligible work time and dice. Source exclusions and GM rounding rulings apply.</p>
    {error && <p className="native-error" role="alert">{error}</p>}
    {message && <p role="status">{message}</p>}
    {loading && <p className="native-help">Loading saved tasks and native party sheets…</p>}
    {combat && <p className="native-help">These controls resolve focused scene tasks. End the character or craft encounter before using them.</p>}
    {navigationBlocked && <p className="native-help">Resolve the saved navigation ruling or crew emergency ({words(currentJourney.status)}) before focused scene work.</p>}
    <button className="hp-btn" disabled={pending || loading} onClick={() => { setError(''); setRefresh(value => value + 1); }}>Refresh task state</button>
    {view && <>
      <form onSubmit={preview}>
        <fieldset disabled={pending} style={{ border: 0, padding: 0, margin: 0, minWidth: 0 }}>
          <label>Task name<input aria-label="Focused task name" maxLength={120} value={label} onChange={event => setLabel(event.target.value)} required /></label>
          <label>Actual task, goal, tools & GM ruling<textarea aria-label="Focused task reason" rows={2} maxLength={1000} value={reason} onChange={event => setReason(event.target.value)} required /></label>
          <label className="native-checkbox"><input type="checkbox" checked={exclusive} onChange={event => setExclusive(event.target.checked)} />The participants devote the stated preparation and work periods to this task alone</label>
          <label className="native-checkbox"><input type="checkbox" checked={combined} disabled={!combined && (steps.length !== 1 || steps[0].mode !== 'normal')} onChange={event => setCombined(event.target.checked)} />Resolve a combined effort with an actual Command roll</label>
          <p className="native-help">Combined projects support one normal-mode step. The aggregate task roll uses the coordinated group; personal CP/FP apply to the commander’s own Command roll. Use combat controls for attacks and dedicated repair, navigation or training controls to change those saved systems.</p>
          {!!selectedBusyPeople.length && <p className="native-help">Already committed to pending exclusive work: {selectedBusyPeople.map(person => person.name).join(', ')}. Finish or cancel their saved task before declaring another.</p>}
          {combined && <section className="native-training-card" aria-label="Combined action participants">
            <label>Commander<select aria-label="Combined task commander" value={commander?.id ?? ''} onChange={event => { setCommanderId(event.target.value); setCommandCP(0); setCommandFP(false); }}>{people.map(person => <option key={person.id} value={person.id}>{person.name} · Command {rating(person, 'command')}</option>)}</select></label>
            <p className="native-help">Select each person actually doing hands-on work. Commanding alone does not count as participating. A commander who also works takes −1D on both Command and the task contribution.</p>
            <div className="native-button-row">{people.map(person => <label className="native-checkbox" key={person.id}><input type="checkbox" checked={participants.includes(person.id)} onChange={() => toggleParticipant(person.id)} />{person.name}{person.id === commander?.id ? ' · commander also participates' : ''} · {rating(person, steps[0]?.skill ?? '')}</label>)}</div>
            {!!selectedPeople.length && <><p className="native-help">Declared worker priority: a partial Command result coordinates the first eligible workers in this order.</p>{selectedPeople.map((person, index) => <div className="native-button-row" key={person.id}><span>{index + 1}. {person.name}</span><button type="button" className="hp-btn" disabled={index === 0} onClick={() => moveParticipant(index, -1)}>Earlier priority</button><button type="button" className="hp-btn" disabled={index === selectedPeople.length - 1} onClick={() => moveParticipant(index, 1)}>Later priority</button></div>)}</>}
            <div className="native-form-row"><label>GM hands-on participant limit<input aria-label="Combined task participant limit" type="number" min={2} max={1500} step={1} value={participantLimit} onChange={event => setParticipantLimit(event.target.value)} required /></label><label>GM Command difficulty within source band (optional)<input aria-label="Combined task command difficulty" type="number" min={1} max={1000} value={commandDifficulty} placeholder="Source band maximum" onChange={event => setCommandDifficulty(event.target.value)} /></label></div>
            <label className="native-checkbox"><input type="checkbox" checked={contact} onChange={event => setContact(event.target.checked)} />All participants are in direct voice / comlink contact with the commander</label>
            <label className="native-checkbox"><input type="checkbox" checked={visible} onChange={event => setVisible(event.target.checked)} />All participants can see the actual target of the action</label>
            <label className="native-checkbox"><input type="checkbox" checked={sameRange} onChange={event => setSameRange(event.target.checked)} />The target is in the same range band for every participant</label>
            {commanderLongTask && <p className="native-help">A participating commander both commands and works. Long-task CP/FP require one exclusive action, so no Command CP/FP are spent for this declaration.</p>}
            <PointControls person={commander} skill="command" scope="Command" cp={request.command_character_points} fp={request.command_force_point} setCP={setCommandCP} setFP={setCommandFP} disabled={pending || commanderLongTask} />
          </section>}
          <label>{combined ? 'Participant representing the group roll' : 'Task performer'}<select aria-label="Focused task performer" value={actor?.id ?? ''} onChange={event => setActorId(event.target.value)}>{actorChoices.map(person => <option key={person.id} value={person.id}>{person.name} · {words(person.d6.wound)}</option>)}</select></label>
          <datalist id={`native-task-skills-${session.id}`}>{skills.map(skill => <option key={skill} value={skill} />)}</datalist>
          {steps.map((step, index) => <section className="native-training-card" key={step.id} aria-label={`Required task step ${index + 1}`}>
            <h4>Required step {index + 1}</h4>
            <div className="native-form-row"><label>Skill or attribute<input aria-label={`Task step ${index + 1} skill`} list={`native-task-skills-${session.id}`} value={step.skill} maxLength={120} onChange={event => updateStep(step.id, { skill: event.target.value })} required /></label><label>GM difficulty<input aria-label={`Task step ${index + 1} difficulty`} type="number" min={1} max={1000} value={step.difficulty} onChange={event => updateStep(step.id, { difficulty: Number(event.target.value) })} required /></label></div>
            <div className="native-form-row"><label>Normal work duration<input aria-label={`Task step ${index + 1} duration`} type="number" min={0.001} max={6307200} step="any" value={step.time} onChange={event => updateStep(step.id, { time: Number(event.target.value) })} required /></label><label>Duration units<select aria-label={`Task step ${index + 1} units`} value={step.unit} onChange={event => updateStep(step.id, { unit: event.target.value as TimeUnit })}>{Object.keys(units).map(key => <option key={key} value={key}>{key}</option>)}</select></label><label>Work method<select aria-label={`Task step ${index + 1} mode`} value={step.mode} disabled={combined} onChange={event => updateStep(step.id, { mode: event.target.value as Mode })}><option value="normal">Normal</option><option value="prepared">Prepare exclusively · +1D</option><option value="rushed">Rush · half time & dice</option></select></label></div>
            <p className="native-help">Normal duration: {roundsText(Math.ceil(step.time * units[step.unit]))}. Time is recorded in full five-second rounds.{!combined && ` ${actor?.name ?? 'Performer'}: ${rating(actor, step.skill)}.`}{step.mode === 'prepared' ? ' Less-than-round skills still require one round preparing and one round working. Reactions and listed skills cannot prepare.' : step.mode === 'rushed' ? ' Only tasks normally taking at least two rounds can rush.' : ''}</p>
            {step.mode === 'rushed' && <div className="native-form-row"><label>GM ruling for fractional dice / time<select aria-label={`Task step ${index + 1} rush rounding`} value={step.rush_rounding ?? ''} onChange={event => updateStep(step.id, { rush_rounding: event.target.value as 'up' | 'down' || null })}><option value="">Exact halves only</option><option value="down">Round down</option><option value="up">Round up</option></select></label><label>Reason for rounding ruling<input aria-label={`Task step ${index + 1} rounding reason`} maxLength={1000} value={step.rounding_reason ?? ''} onChange={event => updateStep(step.id, { rounding_reason: event.target.value })} /></label></div>}
            <label>What this required check accomplishes<input aria-label={`Task step ${index + 1} reason`} maxLength={1000} value={step.reason} onChange={event => updateStep(step.id, { reason: event.target.value })} required /></label>
            <div className="native-button-row"><button type="button" className="hp-btn" disabled={steps.length === 1} onClick={() => setSteps(previous => previous.filter(item => item.id !== step.id))}>Remove required step</button>{index > 0 && <button type="button" className="hp-btn" onClick={() => setSteps(previous => { const next = [...previous]; [next[index - 1], next[index]] = [next[index], next[index - 1]]; return next; })}>Move earlier</button>}</div>
          </section>)}
          <div className="native-button-row"><button type="button" className="hp-btn" disabled={combined || steps.length >= 20} onClick={() => setSteps(previous => [...previous, newStep()])}>Add another required step</button><button className="hp-btn" disabled={pending || loading || sceneBlocked || !canReview}>Review task plan</button></div>
        </fieldset>
      </form>
      {quote && <section className="native-training-card" aria-label="Reviewed task plan"><h4>{quote.request.label} · reviewed plan</h4>{quote.quote.steps.map((step, index) => <p key={index}>Step {index + 1}: {words(step.skill)} · difficulty {step.difficulty} · {step.mode} · preparation {roundsText(step.preparation_rounds)} + work {roundsText(step.work_rounds)} = {roundsText(step.total_rounds)}</p>)}{quote.quote.combined && <><p>Actual participants: {quote.quote.declared_count} · source table row: {quote.quote.table_count} · average skill: {quote.quote.average_skill}D · Command difficulty {quote.quote.command_difficulty} ({words(quote.quote.command_band ?? '')})</p><p>Commander: {commander?.name} · {quote.request.commander_participates ? 'also participates' : 'commands only'} · spend {quote.request.command_character_points} CP / {quote.request.command_force_point ? '1' : '0'} FP when Command is rolled.</p><p className="native-help">Beginning rolls Command once and saves the actual coordinated count and bonus. A partial Command result can leave some selected participants ineffectual.</p></>}{quote.quote.participants.map((person, index) => <p className="native-help" key={person.actor_id}>{index + 1}. {person.name} · {Object.entries(person.skills).map(([skill, code]) => `${words(skill)} ${code}`).join(', ')} · {person.declared_actions} declared {person.declared_actions === 1 ? 'action' : 'actions'}</p>)}{quote.quote.notes.map(note => <p className="native-help" key={note}>{note}</p>)}<p className="native-help">{quote.quote.source}</p><button className="hp-btn" disabled={pending || loading || sceneBlocked || !canReview} onClick={() => run('begin', quote.request)}>{quote.quote.combined ? 'Roll Command & save combined task' : 'Save task & begin focused work'}</button></section>}
      {!!activeProjects.length && <h4>Saved focused work</h4>}
      {activeProjects.map(project => <SavedTask key={project.id} project={project} people={people} disabled={pending || loading || sceneBlocked} run={run} />)}
      {!!history.length && <details><summary>Completed, failed & cancelled tasks ({history.length})</summary>{[...history].reverse().map(project => <SavedTask key={project.id} project={project} people={people} disabled={pending || loading || sceneBlocked} run={run} />)}</details>}
    </>}
  </details>;
}
