import { useEffect, useState } from 'react';
import type { D6Arc, D6Vehicle, GameSession } from '../../types';
import { api } from '../../services/api';
import { D6VehicleModal } from '../modals/D6VehicleModal';
import '../sidebar/D6.css';

const arcs: D6Arc[] = ['front', 'back', 'left', 'right'];
const words = (text: string) => text.replaceAll('_', ' ');

export function D6VehiclePanel({ session, onSessionChanged }: { session: GameSession; onSessionChanged: (session: GameSession) => void }) {
  const [catalog, setCatalog] = useState<D6Vehicle[]>([]);
  const [preset, setPreset] = useState('ghtroc');
  const [selectedId, setSelectedId] = useState('');
  const [enemyPreset, setEnemyPreset] = useState('tie_fighter');
  const [enemyCount, setEnemyCount] = useState(1);
  const [environment, setEnvironment] = useState<'space' | 'atmosphere'>('space');
  const [editing, setEditing] = useState<D6Vehicle | null>(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [declarer, setDeclarer] = useState('');
  const [actions, setActions] = useState(1);
  const [moves, setMoves] = useState(0);
  const [half, setHalf] = useState(false);
  const [force, setForce] = useState(false);
  const [defenseCp, setDefenseCp] = useState(0);
  const [full, setFull] = useState(false);
  const [shieldArc, setShieldArc] = useState<Record<D6Arc, string>>({ front: '1D', back: '0D', left: '0D', right: '0D' });
  const [shieldDifficulty, setShieldDifficulty] = useState('');
  const [targetId, setTargetId] = useState('');
  const [weaponId, setWeaponId] = useState('');
  const [distance, setDistance] = useState(3);
  const [fireArc, setFireArc] = useState<D6Arc>('front');
  const [incomingArc, setIncomingArc] = useState<D6Arc>('front');
  const [difficulty, setDifficulty] = useState('');
  const [actionCp, setActionCp] = useState(0);
  const [mishap, setMishap] = useState<'penalty' | 'complication'>('penalty');
  const [passengers, setPassengers] = useState(true);
  const [terrain, setTerrain] = useState(10);
  const [maneuver, setManeuver] = useState(0);
  const [ram, setRam] = useState(false);
  const [sideswipe, setSideswipe] = useState(false);
  const [collisionAngle, setCollisionAngle] = useState('obstacle');

  useEffect(() => {
    const controller = new AbortController();
    api.nativeVehicleCatalog(controller.signal).then(result => setCatalog(result.presets)).catch(err => {
      if (!controller.signal.aborted) setError(err instanceof Error ? err.message : 'Could not load craft catalog');
    });
    return () => controller.abort();
  }, []);

  const encounter = session.vehicle_encounter;
  const fleet = session.vehicles ?? [];
  const selected = fleet.find(craft => craft.id === selectedId) ?? fleet[0];
  const allCrew = encounter?.craft.flatMap(craft => craft.crew.map(crew => ({ craft, crew }))) ?? [];
  const declaration = allCrew.find(pair => pair.crew.id === declarer) ?? allCrew.find(pair => pair.crew.character_id === session.character.id) ?? allCrew[0];
  const current = allCrew.find(pair => pair.crew.id === encounter?.actor_order[encounter.current_turn_index]);
  const weapons = current?.craft.weapons.filter(weapon => (weapon.operator_id ?? current.craft.crew.find(crew => crew.stations.includes('pilot'))?.id) === current.crew.id) ?? [];
  const weapon = weapons.find(item => item.id === weaponId) ?? weapons[0];
  const targets = encounter?.craft.filter(craft => craft.id !== current?.craft.id && craft.damage !== 'destroyed') ?? [];
  const target = targets.find(craft => craft.id === targetId) ?? targets.find(craft => craft.is_player !== current?.craft.is_player) ?? targets[0];
  const active = Boolean(encounter?.active);
  const actionReady = active && !encounter?.turn_acted && current && current.crew.d6.unconscious_rounds === 0 && !current.crew.d6.round_state.blocked && !current.crew.evacuated;
  const declarationReady = active && !encounter?.actions_started;
  const actionAvailable = actionReady && current && !current.crew.d6.round_state.full_defense && current.crew.d6.round_state.actions_taken < current.crew.d6.round_state.declared_actions;
  const freeHalfAvailable = actionReady && current?.craft.half_speed && current.craft.moves_taken === 0 && terrain <= 15 && maneuver === 0 && current.craft.speed_losses < 4 && !current.craft.frozen_rounds;
  const canFire = actionAvailable && weapon?.status === 'operational' && weapon.ammo !== 0 && !current?.craft.frozen_rounds && !current?.craft.weapons_disabled && !current?.craft.generator_shutdown && !current?.craft.controls_dead;
  const occupied = fleet.some(craft => craft.occupied);

  async function run(action: string, payload: unknown = {}) {
    if (pending) return;
    setPending(true); setError(null);
    try {
      const response = await api.nativeVehicleAction(action, payload);
      onSessionChanged(response.session);
      return response;
    } catch (err) { setError(err instanceof Error ? err.message : 'Craft action failed'); }
    finally { setPending(false); }
  }

  const actionOptions = { actor_id: current?.crew.id, character_points: actionCp, mishap, passenger_damage: passengers };

  return <section className="native-vehicle-panel" aria-label="Native D6 vehicles and starships">
    <details name="native-tools" open={Boolean(encounter)}>
      <summary>{encounter ? `Vehicle / starship encounter · round ${encounter.round}${active ? '' : ' · complete'}` : `Vehicles & starships · ${fleet.length} in fleet`}</summary>
      <div className="native-vehicle-scroll">
        {error && <p role="alert" className="native-error">{error}</p>}
        {!encounter ? <>
          <p className="native-help">Add a craft, assign its crew, then start a space or ground encounter. Source: WEG Second Edition (1992), with scale die caps and persistent system damage.</p>
          <div className="native-form-row"><label>Craft preset<select value={preset} onChange={event => setPreset(event.target.value)}>{catalog.map(craft => <option key={craft.id} value={craft.id}>{craft.name} · {craft.scale}</option>)}</select></label>
            <button className="hp-btn" disabled={pending || Boolean(session.encounter?.active) || !catalog.length} onClick={async () => {
              const response = await run('add', { preset });
              if (response) {
                const added = response.session.vehicles!.at(-1)!;
                setSelectedId(added.id);
                setEnvironment(added.kind === 'vehicle' ? 'atmosphere' : 'space');
                setEnemyPreset(added.kind === 'vehicle' ? 'atst' : 'tie_fighter');
                setDistance(added.kind === 'vehicle' ? 100 : 3);
              }
            }}>Add craft</button></div>
          {selected && <>
            <label>Party craft<select value={selected.id} onChange={event => {
              const craft = fleet.find(craft => craft.id === event.target.value)!;
              setSelectedId(craft.id); setEnvironment(craft.kind === 'vehicle' ? 'atmosphere' : 'space');
              setEnemyPreset(craft.kind === 'vehicle' ? 'atst' : 'tie_fighter'); setDistance(craft.kind === 'vehicle' ? 100 : 3);
            }}>{fleet.map(craft => <option key={craft.id} value={craft.id}>{craft.name} · {words(craft.damage)}</option>)}</select></label>
            <p>{selected.hull} hull/body · {selected.maneuverability} maneuverability · {selected.shields} shields · {words(selected.damage)}</p>
            <p className="native-help">{selected.crew.map(crew => `${crew.name}: ${crew.stations.join(', ')}`).join(' · ')}</p>
            {(selected.shields_lost > 0 || selected.maneuverability_lost > 0 || selected.speed_losses > 0) && <p className="native-error">Damage: shields −{selected.shields_lost}D · maneuverability −{selected.maneuverability_lost}D · {selected.speed_losses} speed reductions</p>}
            {selected.destruction_countdown !== null && <p role="alert" className="native-error">{selected.destruction_cause} failure: {selected.destruction_countdown} rounds until destruction. End combat does not stop the clock.</p>}
            <div className="native-button-row"><button className="hp-btn" disabled={pending || Boolean(session.encounter?.active)} onClick={() => setEditing(selected)}>Edit craft & crew</button>
              {selected.occupied && <button className="hp-btn" disabled={pending} onClick={() => run(`disembark/${encodeURIComponent(selected.id)}`)}>Disembark (safe location)</button>}
              <button className="hp-btn" disabled={pending || Boolean(session.encounter?.active)} onClick={() => run('advance')}>Advance fleet time 1 round</button></div>
            <div className="native-form-row">
              <label>Battle environment<select value={environment} onChange={event => setEnvironment(event.target.value as 'space' | 'atmosphere')}><option value="space">Space · units</option><option value="atmosphere">Ground / atmosphere · meters</option></select></label>
              <label>Enemy craft<select value={enemyPreset} onChange={event => setEnemyPreset(event.target.value)}>{catalog.filter(craft => environment !== 'space' || craft.kind === 'starship').map(craft => <option key={craft.id} value={craft.id}>{craft.name}</option>)}</select></label>
              <label>Enemy count<input type="number" min={1} max={8} value={enemyCount} onChange={event => setEnemyCount(Number(event.target.value))} /></label>
            </div>
            <button className="send-btn" disabled={pending || Boolean(session.encounter?.active)} onClick={() => run('start', { vehicle_id: selected.id, enemies: Array.from({ length: Math.min(8, Math.max(1, enemyCount)) }, () => enemyPreset), environment })}>Start vehicle / starship encounter</button>
            <p className="native-help">{selected.source}</p>
          </>}
          {occupied && <p className="native-help">Crew remain aboard after an encounter. Disembark at a safe location before a damaged craft is left behind. Rest advances pending generator/structural failures.</p>}
        </> : <>
          <div className="native-button-row"><strong>{encounter.environment === 'space' ? 'Space units' : 'Ground / atmosphere meters'} · {encounter.initiative_winner ? 'Party' : 'Enemy'} won initiative ({encounter.initiative.party}–{encounter.initiative.enemy})</strong><button className="hp-btn" disabled={pending} onClick={() => run('end')}>End craft encounter</button></div>
          <div className="native-flight-toolbar"><span>{encounter.actions_started ? 'Action phase' : 'Declaration phase'} · Acting: <strong>{current?.crew.name ?? 'Encounter complete'}</strong></span><button className="hp-btn" disabled={pending || !active} onClick={() => run('next')}>Advance crew turn</button></div>
          <div className="native-craft-grid">{encounter.craft.map(craft => <button type="button" className={`native-craft-card ${craft.id === target?.id ? 'native-craft-target' : ''}`} key={craft.id} aria-pressed={craft.id === target?.id} aria-label={`Target craft ${craft.name}`} disabled={craft.id === current?.craft.id || craft.damage === 'destroyed'} onClick={() => setTargetId(craft.id)}>
            <strong>{craft.is_player ? 'Party' : 'Enemy'} · {craft.name}</strong><span>{craft.scale} · hull {craft.hull} · {words(craft.damage)}</span>
            <span>Maneuver −{craft.maneuverability_lost}D · shields −{craft.shields_lost}D</span><span>Ionized {craft.ion_durations.length} · {craft.frozen_rounds ? `frozen now + ${Math.max(0, craft.frozen_rounds - 1)} more rounds` : 'controls responsive'} · moves {craft.moves_taken}/{craft.declared_moves}</span>
            <span>Shields: {Object.entries(craft.shield_allocation).map(([arc, code]) => `${arc} ${code}`).join(', ') || 'none deployed'}</span>
            <span>{craft.distance_moved} moved this round{craft.particle_shields ? '' : ' · particle shields down'}</span>
            {craft.captured_by && <span>Tractor locked · {craft.tractor_distance} separation</span>}
            {craft.destruction_countdown !== null && <strong className="native-error">{craft.destruction_cause}: {craft.destruction_countdown} rounds</strong>}
            {(craft.controls_dead || craft.generator_shutdown || craft.drives_disabled || craft.weapons_disabled || craft.hyperdrive_disabled) && <span>{[craft.controls_dead && 'controls dead', craft.generator_shutdown && 'power off', craft.drives_disabled && 'drives offline', craft.weapons_disabled && 'weapons offline', craft.hyperdrive_disabled && 'hyperdrive offline'].filter(Boolean).join(' · ')}</span>}
          </button>)}</div>
          <details open={declarationReady}><summary>Crew declarations & defensive phase</summary>
            <label>Declaration station<select value={declaration?.crew.id ?? ''} onChange={event => { setDeclarer(event.target.value); setForce(false); setDefenseCp(0); setMoves(0); setHalf(false); }}>{allCrew.map(({ craft, crew }) => <option key={crew.id} value={crew.id}>{craft.name} · {crew.name}</option>)}</select></label>
            {declaration && <>
              <p className="native-help">{declaration.crew.stations.join(' / ')} · {words(declaration.crew.d6.wound)} · {declaration.crew.d6.round_state.actions_taken}/{declaration.crew.d6.round_state.declared_actions} actions used · CP {declaration.crew.d6.character_points} · FP {declaration.crew.d6.force_points}{declaration.crew.d6.round_state.force_active ? ' · Force active' : ''}</p>
              <div className="native-form-row"><label>Crew actions<input type="number" min={1} max={10} value={actions} onChange={event => setActions(Number(event.target.value))} /></label>
                {declaration.crew.stations.includes('pilot') && <label>Declared moves<input type="number" min={0} max={4} value={moves} onChange={event => setMoves(Number(event.target.value))} /></label>}
                <label>Defensive Character Points<input type="number" min={0} max={5} value={defenseCp} onChange={event => setDefenseCp(Number(event.target.value))} /></label></div>
              <div className="native-button-row"><label className="native-checkbox"><input type="checkbox" checked={force} onChange={event => setForce(event.target.checked)} />Spend one Force Point this round</label>
                {declaration.crew.stations.includes('pilot') && <label className="native-checkbox"><input type="checkbox" checked={half} onChange={event => { setHalf(event.target.checked); if (event.target.checked) setMoves(1); }} />One half-speed move</label>}
                <button className="hp-btn" disabled={pending || !declarationReady} onClick={async () => {
                  if (await run('declare', { actor_id: declaration.crew.id, actions, moves: declaration.crew.stations.includes('pilot') ? moves : 0, half_speed: declaration.crew.stations.includes('pilot') && half, force_point: force })) setForce(false);
                }}>Declare crew actions</button></div>
              <div className="native-button-row"><label className="native-checkbox"><input type="checkbox" checked={full} onChange={event => setFull(event.target.checked)} />Full vehicle dodge</label><button className="hp-btn" disabled={pending || !declarationReady || !declaration.crew.stations.includes('pilot')} onClick={() => run('dodge', { actor_id: declaration.crew.id, full, character_points: defenseCp, mishap })}>Roll vehicle dodge</button></div>
              <div className="native-shield-grid">{arcs.map(arc => <label key={arc}>Shield {arc}<input aria-label={`Shield allocation ${arc}`} value={shieldArc[arc]} onChange={event => setShieldArc({ ...shieldArc, [arc]: event.target.value })} /></label>)}</div>
              <div className="native-form-row"><label>Shield difficulty override<input type="number" min={1} max={1000} placeholder="10 / 15 / 20 / 30" value={shieldDifficulty} onChange={event => setShieldDifficulty(event.target.value)} /></label><button className="hp-btn" disabled={pending || !declarationReady || !declaration.crew.stations.includes('shields')} onClick={() => run('shields', { actor_id: declaration.crew.id, allocation: shieldArc, difficulty: shieldDifficulty ? Number(shieldDifficulty) : null, character_points: defenseCp, mishap })}>Deploy shields</button></div>
              <p className="native-help">Declare every crew member's actions first. Dodges/shields consume their operator's actions. A normal vehicle dodge uses the higher of range difficulty and the capped dodge; full dodge adds both. Shields must be redeployed each round.</p>
              <div className="native-button-row"><button className="hp-btn" disabled={pending || !declarationReady} onClick={() => run(`initiative?winner_first=true`)}>Winning side first</button><button className="hp-btn" disabled={pending || !declarationReady} onClick={() => run(`initiative?winner_first=false`)}>Winning side last</button></div>
            </>}
          </details>
          {encounter.boost && <div className="native-button-row"><span>Last {encounter.boost.kind}: {encounter.boost.points_spent}/5 CP · {allCrew.find(pair => pair.crew.id === encounter.boost?.actor_id)?.crew.name}</span>
            <button className="hp-btn" disabled={pending || encounter.boost.force_used || encounter.boost.points_spent >= 5} onClick={() => run('boost', { points: 1 })}>Add 1 CP to last craft defense</button><span className="native-help">Before another roll or action; original dice stay unchanged.</span>
          </div>}
          {current && <div className="native-crew-turn">
            <h3>Current station: {current.crew.name}</h3><p className="native-help">{current.craft.name} · {current.crew.stations.join(' / ')} · {current.crew.d6.round_state.actions_taken}/{current.crew.d6.round_state.declared_actions} actions used · CP {current.crew.d6.character_points} · FP {current.crew.d6.force_points}</p>
            <div className="native-form-row"><label>Target craft<select value={target?.id ?? ''} onChange={event => setTargetId(event.target.value)}>{targets.map(craft => <option key={craft.id} value={craft.id}>{craft.name}</option>)}</select></label><label>Action Character Points<input type="number" min={0} max={2} value={actionCp} onChange={event => setActionCp(Number(event.target.value))} /></label></div>
            <div className="native-form-row"><label>Mounted weapon<select value={weapon?.id ?? ''} onChange={event => setWeaponId(event.target.value)}>{weapons.length ? weapons.map(weapon => <option key={weapon.id} value={weapon.id}>{weapon.name} · {weapon.damage} · {weapon.status}{weapon.ammo !== null ? ` · ammo ${weapon.ammo}` : ''}</option>) : <option value="">No assigned weapon</option>}</select></label><label>Distance ({encounter.environment === 'space' ? 'units' : 'meters'})<input type="number" min={0} step="any" value={distance} onChange={event => setDistance(Number(event.target.value))} /></label></div>
            <div className="native-form-row"><label>Target in my fire arc<select value={fireArc} onChange={event => setFireArc(event.target.value as D6Arc)}>{arcs.map(arc => <option key={arc}>{arc}</option>)}</select></label><label>Target's incoming arc<select value={incomingArc} onChange={event => setIncomingArc(event.target.value as D6Arc)}>{arcs.map(arc => <option key={arc}>{arc}</option>)}</select></label><label>Gunnery base difficulty<input type="number" min={1} max={1000} placeholder="From weapon range" value={difficulty} onChange={event => setDifficulty(event.target.value)} /></label></div>
            <div className="native-form-row"><label>Wild 1 handling<select value={mishap} onChange={event => setMishap(event.target.value as 'penalty' | 'complication')}><option value="penalty">Discard Wild + highest</option><option value="complication">GM complication</option></select></label><label className="native-checkbox"><input type="checkbox" checked={passengers} onChange={event => setPassengers(event.target.checked)} />Apply exposed crew damage</label></div>
            <button className="send-btn" disabled={pending || !canFire || !target || !weapon || !current.crew.stations.includes('gunner')} onClick={() => run('attack', { ...actionOptions, target_id: target?.id, weapon_id: weapon?.id, distance, fire_arc: fireArc, incoming_arc: incomingArc, difficulty: difficulty ? Number(difficulty) : null })}>Fire mounted weapon</button>
            <p className="native-help">GM sets distance and relative arcs; no automatic tactical map. Missiles add target-speed difficulty and drop the launcher's particle shields. Ion fire bypasses energy shields. Crew CP/FP affect skills, not hull or weapon damage.</p>
            {current.crew.stations.includes('pilot') && <>
              <div className="native-form-row"><label>Terrain difficulty<input type="number" min={1} max={1000} value={terrain} onChange={event => setTerrain(Number(event.target.value))} /></label><label>Maneuver difficulty modifier<input type="number" min={0} value={maneuver} onChange={event => setManeuver(Number(event.target.value))} /></label><label>Accidental collision angle<select value={collisionAngle} onChange={event => setCollisionAngle(event.target.value)}><option value="obstacle">Obstacle / default</option><option value="head_on">Head on · +3D</option><option value="rear_ender">Rear / sideswipe · −3D</option><option value="t_bone">T-bone · normal</option></select></label></div>
              <div className="native-button-row"><label className="native-checkbox"><input type="checkbox" checked={ram} onChange={event => setRam(event.target.checked)} />Ram selected target</label><label className="native-checkbox"><input type="checkbox" checked={sideswipe} onChange={event => setSideswipe(event.target.checked)} />Sideswipe</label><button className="hp-btn" disabled={pending || !(actionAvailable || freeHalfAvailable) || current.craft.moves_taken >= current.craft.declared_moves || Boolean(current.craft.spin_rounds || current.craft.drives_disabled || current.craft.captured_by)} onClick={() => run('move', { ...actionOptions, terrain_difficulty: terrain, maneuver_modifier: maneuver, ram_target_id: ram ? target?.id : null, sideswipe, collision_angle: collisionAngle })}>Resolve declared move</button></div>
            </>}
            <div className="native-button-row">
              {current.craft.captured_by && current.crew.stations.includes('pilot') && <button className="hp-btn" disabled={pending || !actionReady} onClick={() => run('system', { actor_id: current.crew.id, action: 'escape_tractor' })}>Attempt tractor escape</button>}
              {target?.captured_by === current.craft.id && <><button className="hp-btn" disabled={pending || !actionReady} onClick={() => run('system', { actor_id: current.crew.id, action: 'pull_tractor', target_id: target.id })}>Tractor pull 1 unit</button><button className="hp-btn" disabled={pending || !actionReady} onClick={() => run('system', { actor_id: current.crew.id, action: 'release_tractor', target_id: target.id })}>Release tractor</button></>}
              {current.craft.destruction_cause === 'generator' && current.crew.stations.includes('engineer') && <button className="hp-btn" disabled={pending || !actionReady} onClick={() => run('system', { actor_id: current.crew.id, action: 'shutdown_generator' })}>Shut down overloaded generator</button>}
              <button className="hp-btn" disabled={pending || !actionReady} onClick={() => run('system', { actor_id: current.crew.id, action: 'evacuate' })}>Evacuate station (GM confirms safe exit)</button>
              <button className="send-btn" disabled={pending || !active} onClick={() => run('next')}>Next crew action</button>
            </div>
          </div>}
          <details><summary>Craft combat log ({encounter.combat_log.length})</summary><ol className="native-flight-log">{encounter.combat_log.map((line, index) => <li key={index}>{line}</li>)}</ol></details>
          <p className="native-help">{encounter.combat_log.at(-1)}</p>
        </>}
      </div>
    </details>
    {editing && <D6VehicleModal initial={editing} character={session.character} onClose={() => setEditing(null)} onSave={async craft => {
      const response = await api.nativeVehicleAction('update', craft);
      onSessionChanged(response.session); setEditing(null);
    }} />}
  </section>;
}
