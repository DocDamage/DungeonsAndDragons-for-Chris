import React, { useState } from 'react';
import { Sword, Crosshair } from 'lucide-react';
import type { CombatEncounter, Companion, D6Options, GameSession } from '../../types';
import { D6CombatGear } from './D6CombatGear';

interface TacticalCombatBannerProps {
  session: GameSession;
  onSessionChanged: (session: GameSession) => void;
  encounter: CombatEncounter;
  companions?: Companion[];
  knownSpells?: string[];
  selectedTargetId: string | null;
  onSelectTarget: (id: string) => void;
  onAttackTarget: (options?: D6Options) => void;
  playerId: string;
  onEnemyAttack: (actorId: string, options: D6Options) => void;
  onCompanionAttack: (companionId: string) => void;
  onCastCombatSpell: (spellName: string) => void;
  onNextTurn: () => void;
}

export const TacticalCombatBanner: React.FC<TacticalCombatBannerProps> = ({
  session,
  onSessionChanged,
  encounter,
  companions = [],
  knownSpells = [],
  selectedTargetId,
  onSelectTarget,
  onAttackTarget,
  playerId,
  onEnemyAttack,
  onCompanionAttack,
  onCastCombatSpell,
  onNextTurn
}) => {
  const [nativeOptions, setNativeOptions] = useState<D6Options>({ range_band: 'short', character_points: 0, stun: false });
  const native = encounter.system === 'weg_d6';
  const current = encounter.combatants[encounter.current_turn_index];
  return (
    <div className="combat-banner">
      <div className="combat-header">
        <div className="combat-title">
          <Sword size={18} />
          <span>{native ? 'WEG D6 • CHARACTER SCALE' : 'TACTICAL ENCOUNTER'} • ROUND {encounter.round}</span>
        </div>
        <div style={{ fontSize: '0.8rem', color: '#8b92a5' }}>
          Turn: <strong>{encounter.combatants[encounter.current_turn_index]?.name}</strong>
        </div>
      </div>

      {/* Combatants Initiative Line */}
      <div className="combatants-row">
        {encounter.combatants.map((c, idx) => {
          const isTurn = idx === encounter.current_turn_index;
          const isSelected = selectedTargetId === c.id;
          const canTarget = !c.is_player && !c.is_defeated && (native || c.current_hp > 0);
          const cHpPct = Math.max(0, Math.min(100, (c.current_hp / c.max_hp) * 100));

          return (
            <div
              key={c.id}
              role={canTarget ? 'button' : undefined}
              tabIndex={canTarget ? 0 : undefined}
              aria-label={canTarget ? `Target ${c.name}` : undefined}
              aria-pressed={canTarget ? isSelected : undefined}
              onClick={() => canTarget && onSelectTarget(c.id)}
              onKeyDown={(event) => {
                if (canTarget && (event.key === 'Enter' || event.key === ' ')) {
                  event.preventDefault();
                  onSelectTarget(c.id);
                }
              }}
              style={{ cursor: canTarget ? 'pointer' : 'default' }}
              className={`combatant-card ${isTurn ? 'active-turn' : ''} ${isSelected ? 'selected-target' : ''} ${c.is_defeated ? 'defeated' : ''}`}
            >
              <div className="combatant-name">
                {c.is_player ? "👤 " : "🐺 "}
                {c.name}
              </div>
              <div className="combatant-meta">
                <span>Init: {c.initiative}</span>
                <span>{native ? `Strength: ${c.d6?.attributes.strength}` : `AC: ${c.ac}`}</span>
              </div>
              {!native && <div className="hp-bar-bg" style={{ height: 4 }}>
                <div className="hp-bar-fill" style={{ width: `${cHpPct}%` }} />
              </div>}
              <div style={{ fontSize: '0.7rem', textAlign: 'right', color: c.current_hp === 0 ? '#ff6b6b' : '#fff' }}>
                {native ? `${c.d6?.wound.replaceAll('_', ' ')}${c.d6?.unconscious_rounds ? ' · unconscious' : ''} · stuns ${c.d6?.stun_count}` : c.is_defeated ? "DEAD" : `${c.current_hp}/${c.max_hp} HP`}
              </div>
            </div>
          );
        })}
      </div>

      {native && <div className="native-combat-options">
        <span>{encounter.d6_initiative_winner ? 'Party' : 'Enemy'} won side initiative · {encounter.d6_actions_started ? 'Action phase' : 'Declaration phase'}</span>
        <label>Range<select aria-label="D6 attack range" value={nativeOptions.range_band} onChange={event => setNativeOptions({ ...nativeOptions, range_band: event.target.value as D6Options['range_band'] })}><option value="point_blank">Point blank · 5</option><option value="short">Short · 10</option><option value="medium">Medium · 15</option><option value="long">Long · 20</option></select></label>
        <label>Actual distance (m)<input aria-label="D6 actual target distance" type="number" min={0} placeholder="Use chosen range" value={nativeOptions.distance_m ?? ''} onChange={event => setNativeOptions({ ...nativeOptions, distance_m: event.target.value ? Number(event.target.value) : undefined })} /></label>
        <label>CP<input aria-label="D6 attack Character Points" type="number" min={0} max={2} value={nativeOptions.character_points} onChange={event => setNativeOptions({ ...nativeOptions, character_points: Number(event.target.value) })} /></label>
        <label>Base difficulty<input aria-label="D6 base difficulty override" type="number" min={1} max={1000} placeholder="Auto" value={nativeOptions.difficulty ?? ''} onChange={event => setNativeOptions({ ...nativeOptions, difficulty: event.target.value ? Number(event.target.value) : undefined })} /></label>
        {current?.weapon?.d6_skill === 'lightsaber' && <label>Saber Control damage dice<input aria-label="Lightsaber Control damage dice" type="number" min={-100} max={100} placeholder="All Control" value={nativeOptions.lightsaber_control_dice ?? ''} onChange={event => setNativeOptions({ ...nativeOptions, lightsaber_control_dice: event.target.value ? Number(event.target.value) : undefined })} /></label>}
        <label>Wild 1<select aria-label="D6 Wild Die mishap" value={nativeOptions.mishap ?? 'penalty'} onChange={event => setNativeOptions({ ...nativeOptions, mishap: event.target.value as D6Options['mishap'] })}><option value="penalty">Penalty</option><option value="complication">Complication</option></select></label>
        <label>Resist CP<input aria-label="D6 player resistance Character Points" type="number" min={0} max={5} value={nativeOptions.resistance_character_points ?? 0} onChange={event => setNativeOptions({ ...nativeOptions, resistance_character_points: Number(event.target.value) })} /></label>
        {current?.weapon?.catalog_id ? <span>Actual setting: {current.weapon.stun_mode ? 'stun' : 'normal'}</span> : <label><input type="checkbox" checked={nativeOptions.stun} onChange={event => setNativeOptions({ ...nativeOptions, stun: event.target.checked })} />GM weapon stun setting</label>}
        {current?.weapon?.catalog_id === 'bowcaster' && <label>Extra-shot Strength CP<input aria-label="Bowcaster Strength Character Points" type="number" min={0} max={2} value={nativeOptions.bowcaster_strength_character_points ?? 0} onChange={event => setNativeOptions({ ...nativeOptions, bowcaster_strength_character_points: Number(event.target.value) })} /></label>}
        <label>Hit location<select aria-label="D6 hit location" value={nativeOptions.hit_location ?? ''} onChange={event => setNativeOptions({ ...nativeOptions, hit_location: (event.target.value || undefined) as D6Options['hit_location'], called_shot: false })}><option value="">Normal / roll for partial armor</option><option value="random">Optional random location</option>{['head', 'torso', 'left_arm', 'right_arm', 'left_leg', 'right_leg'].map(item => <option key={item} value={item}>{item.replaceAll('_', ' ')}</option>)}</select></label>
        <label><input type="checkbox" checked={nativeOptions.called_shot ?? false} disabled={!nativeOptions.hit_location || nativeOptions.hit_location === 'random'} onChange={event => setNativeOptions({ ...nativeOptions, called_shot: event.target.checked })} />Called shot · −1D attack</label>
        <label><input type="checkbox" checked={nativeOptions.location_damage ?? false} onChange={event => setNativeOptions({ ...nativeOptions, location_damage: event.target.checked })} />Optional head +1D / torso −1D damage</label>
        <label>Attack side<select aria-label="D6 attack side" value={nativeOptions.attack_side ?? 'front'} onChange={event => setNativeOptions({ ...nativeOptions, attack_side: event.target.value as D6Options['attack_side'] })}><option value="front">Front</option><option value="back">Back</option></select></label>
        <label><input type="checkbox" checked={nativeOptions.attack_cover ?? false} onChange={event => setNativeOptions({ ...nativeOptions, attack_cover: event.target.checked })} />Attack physical protection</label>
        <label><input type="checkbox" checked={nativeOptions.target_weapon ?? false} onChange={event => setNativeOptions({ ...nativeOptions, target_weapon: event.target.checked, called_shot: false, hit_location: undefined, location_damage: false })} />Target held weapon · −1D attack</label>
      </div>}

      {/* Combat Controls */}
      <div className="combat-actions-bar" style={{ flexWrap: 'wrap', gap: 8 }}>
        <span style={{ fontSize: '0.8rem', color: '#8b92a5' }}>Target:</span>
        <span style={{ fontSize: '0.85rem', fontWeight: 700, color: '#ff6b6b' }}>
          {encounter.combatants.find(c => c.id === selectedTargetId)?.name || "Select Enemy"}
        </span>

        <div style={{ display: 'flex', gap: 6, marginLeft: 'auto', flexWrap: 'wrap', alignItems: 'center' }}>
          <button
            onClick={() => onAttackTarget(native ? { ...nativeOptions, stun: current?.weapon?.catalog_id ? !!current.weapon.stun_mode : nativeOptions.stun, resistance_character_points: 0 } : undefined)}
            disabled={!selectedTargetId || (native && (current?.id !== playerId || encounter.d6_turn_acted || current.d6?.round_state.blocked))}
            className="send-btn"
            style={{ padding: '6px 14px', fontSize: '0.8rem' }}
          >
            <Crosshair size={14} /> Attack Target
          </button>

          {/* Ally Companion Strikes */}
          {companions.map((comp) => (
            <button
              key={comp.id}
              onClick={() => onCompanionAttack(comp.id)}
              disabled={!selectedTargetId || (native ? current?.id !== comp.id || encounter.d6_turn_acted || comp.d6?.round_state.blocked : comp.current_hp === 0)}
              className="hp-btn"
              style={{ padding: '5px 10px', fontSize: '0.75rem', borderColor: '#d4af37', color: '#d4af37', display: 'flex', alignItems: 'center', gap: 4 }}
              title={`Command ${comp.name} to strike target`}
            >
              <Sword size={11} /> {comp.name}
            </button>
          ))}

          {/* Quick Spell Strike */}
          {!native && knownSpells.length > 0 && (
            <select
              onChange={(e) => {
                if (e.target.value) {
                  onCastCombatSpell(e.target.value);
                  e.target.value = "";
                }
              }}
              defaultValue=""
              className="input-field"
              style={{ width: 'auto', padding: '5px 8px', fontSize: '0.75rem', borderColor: '#457b9d', color: '#a8dadc' }}
              title="Cast a spell against target"
            >
              <option value="" disabled>✨ Cast Spell...</option>
              {knownSpells.map((s) => (
                <option key={s} value={s}>{s}</option>
              ))}
            </select>
          )}

          {native && current && !current.is_player && <button className="send-btn" disabled={encounter.d6_turn_acted || current.d6?.round_state.blocked} onClick={() => onEnemyAttack(current.id, { ...nativeOptions, stun: current.weapon?.catalog_id ? !!current.weapon.stun_mode : nativeOptions.stun, character_points: 0 })}>Resolve enemy attack</button>}

          <button
            onClick={onNextTurn}
            className="hp-btn"
            style={{ padding: '6px 12px' }}
            title={native ? 'Advance to the next combatant; an unused current action is skipped' : undefined}
          >
            {native && encounter.d6_round_closing ? 'Finish round ➔' : 'Next Turn ➔'}
          </button>
        </div>
      </div>

      {native && <D6CombatGear session={session} selectedTargetId={selectedTargetId} onSessionChanged={onSessionChanged} />}

      {/* Combat Log Ticker */}
      {encounter.combat_log.length > 0 && (
        <div style={{ fontSize: '0.75rem', color: '#a8dadc', background: 'rgba(0,0,0,0.3)', padding: '6px 8px', borderRadius: 4 }}>
          {encounter.combat_log[encounter.combat_log.length - 1]}
        </div>
      )}
    </div>
  );
};
