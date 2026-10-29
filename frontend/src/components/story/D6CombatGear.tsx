import { useState } from 'react';
import { API_BASE } from '../../services/api';
import type { GameSession } from '../../types';

export function D6CombatGear({ session, selectedTargetId, onSessionChanged }: { session: GameSession; selectedTargetId: string | null; onSessionChanged: (session: GameSession) => void }) {
  const [weaponId, setWeaponId] = useState('');
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');
  const [factTarget, setFactTarget] = useState('');
  const [visibility, setVisibility] = useState(0);
  const [fraction, setFraction] = useState('none');
  const [coverId, setCoverId] = useState('');
  const [name, setName] = useState('');
  const [body, setBody] = useState('2D');
  const [reason, setReason] = useState('');
  const encounter = session.encounter;
  const actor = encounter?.combatants[encounter.current_turn_index];
  if (!encounter?.active || !actor) return null;
  const inventory = actor.is_player ? session.character.inventory : actor.inventory ?? [];
  const available = inventory.filter(item => item.id && item.item_type === 'weapon' && item.quantity >= 1 && (!item.equipped_by || item.equipped_by === actor.id));
  const selected = available.find(item => item.id === weaponId) ?? available.find(item => item.id === actor.weapon?.id) ?? available[0];
  const used = actor.weapon;
  const blocked = pending || !!encounter.d6_turn_acted || actor.is_defeated || !!actor.d6?.round_state.blocked;
  const target = encounter.combatants.find(item => item.id === factTarget) ?? encounter.combatants.find(item => item.id === selectedTargetId) ?? actor;
  async function run(action: string, payload: Record<string, unknown>) {
    setPending(true); setError('');
    try {
      const response = await fetch(`${API_BASE}/weg-d6/tactics/${action}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ...payload, expected_updated_at: session.updated_at }) });
      const data = await response.json();
      if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Review this combat action.');
      onSessionChanged(data.session);
    } catch (err) { setError(err instanceof Error ? err.message : 'Combat action failed.'); }
    finally { setPending(false); }
  }
  const gear = (action: string, payload: Record<string, unknown> = {}) => run('gear', { actor_id: actor.id, item_id: used?.id, action, ...payload });
  return <details className="native-combat-gear"><summary>Combat equipment and cover</summary>
    <p className="native-help">Current actor: {actor.name}. Drawing, changing setting and reloading each use one declared action. Preparation uses a whole round, followed by one exclusive attack round with the same weapon and target.</p>
    <p>{used?.name ?? 'Unarmed'}{used?.ammo != null ? ` · ammunition ${used.ammo}/${used.ammo_capacity ?? '?'}` : ''}{used?.power_ammo != null ? ` · power ${used.power_ammo}/${used.power_ammo_capacity ?? '?'}` : ''}{used?.d6_can_stun ? ` · ${used.stun_mode ? 'stun' : 'normal'} setting` : ''}{used?.weapon_damage_state && used.weapon_damage_state !== 'intact' ? ` · ${used.weapon_damage_state.replaceAll('_', ' ')}` : ''}</p>
    <div className="native-form-row"><label>Actual weapon<select aria-label="Combat actual weapon" value={selected?.id ?? ''} onChange={event => setWeaponId(event.target.value)}>{available.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label><button className="hp-btn" disabled={blocked || !selected || selected.id === used?.id} onClick={() => gear('draw', { item_id: selected?.id })}>Draw weapon</button>
    {used?.d6_can_stun && <button className="hp-btn" disabled={blocked} onClick={() => gear('setting', { stun: !used.stun_mode })}>Set {used.stun_mode ? 'normal' : 'stun'}</button>}
    <button className="hp-btn" disabled={blocked || !used?.id || used.ammo == null || used.ammo === used.ammo_capacity} onClick={() => gear('reload')}>Reload ammunition</button>
    {used?.power_ammo != null && <button className="hp-btn" disabled={blocked || used.power_ammo === used.power_ammo_capacity} onClick={() => gear('reload', { primary: false, power: true })}>Reload power feed</button>}
    <button className="hp-btn" disabled={blocked || !used?.id || !selectedTargetId || actor.d6?.round_state.declared_actions !== 1} onClick={() => gear('prepare', { target_id: selectedTargetId })}>Prepare aimed attack</button></div>
    <details><summary>GM battlefield facts</summary><p className="native-help">Record actual visibility and physical cover. Full cover requires an attack on its protection. Saved objects retain damage; reusing one cannot restore it. These facts do not grant movement or another action.</p><div className="native-form-row">
      <label>Protected actor<select aria-label="Cover protected actor" value={target.id} onChange={event => setFactTarget(event.target.value)}>{encounter.combatants.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
      <label>Visibility<select aria-label="Cover visibility" value={visibility} onChange={event => setVisibility(Number(event.target.value))}><option value={0}>Clear · +0D</option><option value={1}>Light smoke / poor light · +1D</option><option value={2}>Thick smoke / moonlight · +2D</option><option value={4}>Very thick smoke / darkness · +4D</option></select></label>
      <label>Physical cover<select aria-label="Cover fraction" value={fraction} onChange={event => setFraction(event.target.value)}><option value="none">None</option><option value="quarter">Quarter · +1D</option><option value="half">Half · +2D</option><option value="three_quarters">Three quarters · +3D</option><option value="full">Full · attack protection</option></select></label>
      {fraction !== 'none' && <><label>Actual object<select aria-label="Cover actual object" value={coverId} onChange={event => setCoverId(event.target.value)}><option value="">Record a new object</option>{encounter.cover_objects?.map(item => <option key={item.id} value={item.id} disabled={item.damage_state === 'destroyed'}>{item.name} · {item.body} · {item.damage_state.replaceAll('_', ' ')}</option>)}</select></label>{!coverId && <><label>Object name<input aria-label="Cover object name" value={name} onChange={event => setName(event.target.value)} /></label><label>Actual object Strength<input aria-label="Cover object Strength" value={body} onChange={event => setBody(event.target.value)} /></label></>}</>}
      <label>GM scene evidence<input aria-label="Cover GM reason" value={reason} onChange={event => setReason(event.target.value)} /></label></div><button className="hp-btn" disabled={pending || !reason.trim() || fraction !== 'none' && !coverId && !name.trim()} onClick={() => run('cover', { target_id: target.id, concealment_dice: visibility, fraction, object_id: fraction === 'none' ? null : coverId || null, new_name: fraction !== 'none' && !coverId ? name : null, new_body: fraction !== 'none' && !coverId ? body : null, reason })}>Record battlefield facts</button>
      <p className="native-help">Object examples: flimsy wood 1D, standard wood 2D, metal 3D, reinforced 4D, blast door 6D. Each impact rolls its own source damage result; no cumulative object wound penalty is invented.</p>
    </details>{error && <p className="native-error" role="alert">{error}</p>}
  </details>;
}
