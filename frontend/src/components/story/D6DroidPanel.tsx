import { useState } from 'react';
import { api } from '../../services/api';
import type { GameSession } from '../../types';

type Operation = 'refine' | 'learn' | 'task' | 'wipe' | 'cartridge' | 'repair' | 'attachment';
const operations: Record<Operation, string> = { refine: 'Refine known skill (+1 pip, CP)', learn: 'Install a new skill (software + CP)', task: 'Program a specific task', wipe: 'Memory wipe', cartridge: 'Install a skill cartridge', repair: 'Repair chassis', attachment: 'Install hardware attachment' };
export function D6DroidPanel({ session, onSessionChanged }: { session: GameSession; onSessionChanged: (session: GameSession) => void }) {
  const people = [session.character, ...(session.character.companions ?? [])].filter(actor => actor.d6);
  const droids = people.filter(actor => actor.d6?.droid);
  const [actorId, setActorId] = useState('');
  const actor = droids.find(item => item.id === actorId) ?? droids[0];
  const [programmerId, setProgrammerId] = useState('');
  const technician = people.find(item => item.id === programmerId && item.id !== actor?.id) ?? people.find(item => item.id !== actor?.id);
  const [operation, setOperation] = useState<Operation>('refine');
  const [skill, setSkill] = useState('search');
  const [parent, setParent] = useState('');
  const [attribute, setAttribute] = useState('perception');
  const [minutes, setMinutes] = useState(15);
  const [difficulty, setDifficulty] = useState(20);
  const [difficultyModifier, setDifficultyModifier] = useState(0);
  const [rollBonus, setRollBonus] = useState(0);
  const [technicianCP, setTechnicianCP] = useState(0);
  const [technicianFP, setTechnicianFP] = useState(false);
  const [credits, setCredits] = useState(0);
  const [connected, setConnected] = useState(false);
  const [software, setSoftware] = useState(false);
  const [hardwire, setHardwire] = useState(false);
  const [reason, setReason] = useState('');
  const [task, setTask] = useState('');
  const [rating, setRating] = useState('4D');
  const [parts, setParts] = useState('');
  const [attachment, setAttachment] = useState('');
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');
  const combat = Boolean(session.encounter?.active || session.vehicle_encounter);
  async function work() {
    setPending(true); setError('');
    try {
      const response = await api.nativeDroidWork({ actor_id: actor?.id, programmer_id: technician?.id, operation, skill, parent_skill: parent || null, attribute, minutes, reason, difficulty, difficulty_modifier: difficultyModifier, roll_bonus: rollBonus, character_points: operation === 'refine' ? 0 : technicianCP, force_point: operation === 'refine' ? false : technicianFP, credits, computer_connected: connected, software_available: software, hardwire: hardwire && ['learn', 'cartridge'].includes(operation), cartridge_rating: rating, task, parts_item: parts, attachment });
      onSessionChanged(response.session);
    } catch (err) { setError(err instanceof Error ? err.message : String(err)); }
    finally { setPending(false); }
  }
  if (!actor) return null;
  const state = actor.d6!.droid!;
  return <details name="native-tools" className="native-force-panel native-droid-panel">
    <summary>Droid programming & repairs</summary>
    <p className="native-help">Software refinement spends the Droid’s CP. New skills need software and a programmer rated at least 2D above the initial skill. Droid skills stop at 13D. GM supplies work duration, actual commercial costs and situational modifiers. Work advances scene and fleet time.</p>
    {error && <p className="native-error" role="alert">{error}</p>}
    <label>Droid<select aria-label="Engineering Droid" value={actor.id} onChange={event => setActorId(event.target.value)}>{droids.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
    <p>{actor.d6!.character_points} CP · Owner: {state.owner} · Memory wipes: {state.memory_wipes} · Damage: {actor.d6!.wound}</p>
    <details><summary>Installed equipment & tasks</summary>{state.equipment.map((item, i) => <p className="native-help" key={i}>{item}</p>)}{state.tasks.map((item, i) => <p key={i}>Task: {item}</p>)}</details>
    <label>Work type<select aria-label="Droid work operation" value={operation} onChange={event => { const choice = event.target.value as Operation; setOperation(choice); if (choice === 'wipe') setDifficulty(10); if (choice === 'learn') setDifficulty(20); if (choice === 'repair') setDifficulty(({ healthy: 10, wounded: 10, incapacitated: 20, mortally_wounded: 30, dead: 31 })[actor.d6!.wound]); }}>{Object.entries(operations).map(([key, title]) => <option key={key} value={key}>{title}</option>)}</select></label>
    {['refine', 'learn', 'cartridge'].includes(operation) && <><div className="native-form-row"><label>Skill<input aria-label="Droid work skill" value={skill} onChange={event => setSkill(event.target.value)} /></label><label>Governing attribute<select value={attribute} onChange={event => setAttribute(event.target.value)}>{Object.keys(actor.d6!.attributes).map(key => <option key={key}>{key}</option>)}</select></label></div><label>Parent skill (only for a specialization)<input value={parent} onChange={event => setParent(event.target.value)} /></label></>}
    {operation !== 'refine' && <><label>Programmer / technician<select aria-label="Droid technician" value={technician?.id ?? ''} onChange={event => setProgrammerId(event.target.value)}>{people.filter(item => item.id !== actor.id).map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label><div className="native-form-row"><label>GM base difficulty<input aria-label="Droid work difficulty" type="number" min={1} max={1000} value={difficulty} onChange={event => setDifficulty(Number(event.target.value))} /></label><label>Difficulty modifier<input type="number" min={0} max={1000} value={difficultyModifier} onChange={event => setDifficultyModifier(Number(event.target.value))} /></label><label>Programmer roll bonus<input type="number" min={0} max={1000} value={rollBonus} onChange={event => setRollBonus(Number(event.target.value))} /></label></div>{operation !== 'repair' && <label className="native-checkbox"><input type="checkbox" checked={connected} onChange={event => setConnected(event.target.checked)} />Computer/datapad connected directly to memory</label>}</>}
    {['learn', 'cartridge'].includes(operation) && <><label className="native-checkbox"><input type="checkbox" checked={software} onChange={event => setSoftware(event.target.checked)} />Compatible software / cartridge is actually available</label><label className="native-checkbox"><input type="checkbox" checked={hardwire} onChange={event => setHardwire(event.target.checked)} />Hardwire permanently (+30 difficulty; survives wipes)</label></>}
    {operation !== 'refine' && <div className="native-form-row"><label>Technician roll CP<input aria-label="Droid technician roll CP" type="number" min={0} max={2} disabled={technicianFP} value={technicianCP} onChange={event => setTechnicianCP(Number(event.target.value))} /></label><label className="native-checkbox"><input type="checkbox" checked={technicianFP} onChange={event => { setTechnicianFP(event.target.checked); if (event.target.checked) setTechnicianCP(0); }} />Spend technician FP on this dedicated task</label></div>}
    {operation === 'cartridge' && <label>Purchased cartridge rating<input value={rating} onChange={event => setRating(event.target.value)} /></label>}
    {operation === 'task' && <label>Specific task<textarea rows={2} value={task} onChange={event => setTask(event.target.value)} /></label>}
    {['repair', 'attachment'].includes(operation) && <label>Appropriate parts / attachment in inventory<select aria-label="Droid replacement parts" value={parts} onChange={event => setParts(event.target.value)}><option value="">Choose installed replacement material</option>{session.character.inventory.filter(item => item.quantity > 0).map((item, i) => <option key={i} value={item.name}>{item.name} ×{item.quantity}</option>)}</select></label>}
    {operation === 'attachment' && <label>Attachment and included software<input value={attachment} onChange={event => setAttachment(event.target.value)} /></label>}
    {operation === 'repair' && <p className="native-help">Repair attempts take at least 15 minutes, then 1 hour, then 2 hours. A successful repair consumes the selected parts and restores the salvageable chassis; rest and medpacs do not.</p>}
    {operation === 'wipe' && <p className="native-help">A successful wipe permanently removes learned skills, tasks and memories. Hardwired skills and equipment remain. Save the adventure first if you want a restore point.</p>}
    <div className="native-form-row"><label>GM work minutes<input aria-label="Droid work minutes" type="number" min={15} max={525600} value={minutes} onChange={event => setMinutes(Number(event.target.value))} /></label><label>Actual credits charged<input aria-label="Droid work credits" type="number" min={0} max={1000000} value={credits} onChange={event => setCredits(Number(event.target.value))} /></label></div>
    <label>GM work reason & facilities<input aria-label="Droid work reason" maxLength={1000} value={reason} onChange={event => setReason(event.target.value)} /></label><button className="hp-btn" disabled={pending || combat || !reason.trim() || operation !== 'refine' && !technician} onClick={work}>Resolve Droid work</button>
    {!!state.work_history.length && <details><summary>Droid work history ({state.work_history.length})</summary>{[...state.work_history].reverse().map((item, i) => <p className="native-training-card" key={i}>{item.operation}: {item.success ? 'completed' : 'failed'} · {item.skill} · {item.minutes} minutes · {item.cp_spent} CP · {item.credits} credits. {item.reason}</p>)}</details>}
  </details>;
}
