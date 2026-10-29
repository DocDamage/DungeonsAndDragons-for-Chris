import React, { useState } from 'react';
import { User, X, Sparkles } from 'lucide-react';
import type { Character } from '../../types';
import { getMod } from '../../utils/helpers';
import { D6CharacterModal } from './D6CharacterModal';

interface CharacterModalProps {
  initialCharacter: Character;
  onSaveCharacter: (char: Character) => Promise<void> | void;
  onRollStats: () => Promise<{ stats: Record<string, number> }>;
  onClose: () => void;
}

export const CharacterModal: React.FC<CharacterModalProps> = ({
  initialCharacter,
  onSaveCharacter,
  onRollStats,
  onClose
}) => {
  const [char, setChar] = useState<Character>({ ...initialCharacter });
  const [rolling, setRolling] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  const handleRoll = async () => {
    setRolling(true);
    try {
      const res = await onRollStats();
      if (res && res.stats) {
        setChar(prev => ({
          ...prev,
          abilities: {
            str: res.stats.str || prev.abilities.str,
            dex: res.stats.dex || prev.abilities.dex,
            con: res.stats.con || prev.abilities.con,
            int: res.stats.int || prev.abilities.int,
            wis: res.stats.wis || prev.abilities.wis,
            cha: res.stats.cha || prev.abilities.cha
          }
        }));
      }
    } finally {
      setRolling(false);
    }
  };

  if (initialCharacter.edition === 'weg_d6' && initialCharacter.d6) return <D6CharacterModal initialCharacter={initialCharacter} onSave={onSaveCharacter} onClose={onClose} />;

  return (
    <div style={{
      position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
      background: 'rgba(0,0,0,0.85)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000
    }}>
      <div style={{
        background: 'var(--bg-secondary)', border: '1px solid var(--border)', borderRadius: 8,
        width: 600, maxWidth: '90vw', maxHeight: '85vh', display: 'flex', flexDirection: 'column', overflow: 'hidden'
      }}>
        <div style={{ padding: '16px 20px', borderBottom: '1px solid var(--border)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--gold)', fontWeight: 700, fontSize: '1.1rem' }}>
            <User size={18} />
            <span>CHARACTER CREATION & STAT WIZARD</span>
          </div>
          <button onClick={onClose} className="hp-btn"><X size={16} /></button>
        </div>

        <div style={{ padding: 20, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 14 }}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 10 }}>
            <div>
              <label style={{ fontSize: '0.75rem', color: '#8b92a5' }}>Character Name</label>
              <input
                type="text"
                value={char.name}
                onChange={(e) => setChar({ ...char, name: e.target.value })}
                className="action-input"
                style={{ width: '100%', marginTop: 4, padding: 8 }}
              />
            </div>
            <div>
              <label style={{ fontSize: '0.75rem', color: '#8b92a5' }}>Class & Level</label>
              <div style={{ display: 'flex', gap: 6, marginTop: 4 }}>
                <input
                  type="text"
                  value={char.class_name}
                  onChange={(e) => setChar({ ...char, class_name: e.target.value })}
                  className="action-input"
                  style={{ flex: 1, padding: 8 }}
                />
                <input
                  type="number"
                  value={char.level}
                  onChange={(e) => setChar({ ...char, level: parseInt(e.target.value) || 1 })}
                  className="action-input"
                  style={{ width: 60, padding: 8 }}
                />
              </div>
            </div>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 10 }}>
            <div>
              <label style={{ fontSize: '0.75rem', color: '#8b92a5' }}>Race / Lineage</label>
              <input
                type="text"
                value={char.race}
                onChange={(e) => setChar({ ...char, race: e.target.value })}
                className="action-input"
                style={{ width: '100%', marginTop: 4, padding: 8 }}
              />
            </div>
            <div>
              <label style={{ fontSize: '0.75rem', color: '#8b92a5' }}>Alignment</label>
              <input
                type="text"
                value={char.alignment}
                onChange={(e) => setChar({ ...char, alignment: e.target.value })}
                className="action-input"
                style={{ width: '100%', marginTop: 4, padding: 8 }}
              />
            </div>
          </div>

          {/* Ability Scores with 4d6 Roll Button */}
          <div style={{ borderTop: '1px solid var(--border)', paddingTop: 12 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
              <span style={{ fontSize: '0.85rem', fontWeight: 700, color: '#fff' }}>Ability Scores</span>
              <button
                onClick={handleRoll}
                disabled={rolling}
                className="send-btn"
                style={{ padding: '6px 12px', fontSize: '0.75rem' }}
              >
                <Sparkles size={12} /> Roll 4d6 Drop Lowest
              </button>
            </div>

            <div className="stat-grid" style={{ padding: 0 }}>
              {(['str', 'dex', 'con', 'int', 'wis', 'cha'] as const).map((stat) => (
                <div key={stat} className="stat-box">
                  <div className="stat-label">{stat.toUpperCase()}</div>
                  <input
                    type="number"
                    value={char.abilities[stat]}
                    onChange={(e) => setChar({
                      ...char,
                      abilities: { ...char.abilities, [stat]: parseInt(e.target.value) || 10 }
                    })}
                    style={{
                      width: '100%', background: 'transparent', border: 'none',
                      color: '#fff', fontSize: '1.2rem', fontWeight: 700, textAlign: 'center', outline: 'none'
                    }}
                  />
                  <div className="stat-mod">{getMod(char.abilities[stat])}</div>
                </div>
              ))}
            </div>
          </div>

          {saveError && <p role="alert" style={{ color: '#ff6b6b' }}>{saveError}</p>}
          <div style={{ display: 'flex', gap: 10, marginTop: 10 }}>
            <button onClick={async () => { try { await onSaveCharacter(char); } catch (err) { setSaveError(err instanceof Error ? err.message : 'Unable to save character'); } }} className="send-btn" style={{ flex: 1 }}>
              Save Character Changes
            </button>
            <button onClick={onClose} className="hp-btn">
              Cancel
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
