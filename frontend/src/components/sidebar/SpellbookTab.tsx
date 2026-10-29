import React, { useState } from 'react';
import { Wand2, X } from 'lucide-react';
import type { SpellSlot } from '../../types';

interface SpellbookTabProps {
  spellSlots?: Record<string, SpellSlot>;
  knownSpells?: string[];
  onCastSpell: (spellName: string, slotLevel?: number) => void;
  onRestoreSlots: (level?: number) => void;
  onLearnSpell: (spellName: string) => void;
  onUnlearnSpell: (spellName: string) => void;
}

export const SpellbookTab: React.FC<SpellbookTabProps> = ({
  spellSlots,
  knownSpells = [],
  onCastSpell,
  onRestoreSlots,
  onLearnSpell,
  onUnlearnSpell
}) => {
  const [newSpellInput, setNewSpellInput] = useState("");

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!newSpellInput.trim()) return;
    onLearnSpell(newSpellInput.trim());
    setNewSpellInput("");
  };

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflowY: 'auto' }}>
      {/* Spell Slots */}
      <div style={{ padding: '12px 16px', borderBottom: '1px solid #282d3d' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
          <span style={{ fontSize: '0.8rem', fontWeight: 700, color: '#8b92a5', textTransform: 'uppercase' }}>Spell Slots</span>
          <button onClick={() => onRestoreSlots()} className="hp-btn" style={{ fontSize: '0.65rem', padding: '2px 6px' }}>Restore All</button>
        </div>
        {spellSlots && Object.entries(spellSlots).map(([lvl, slot]) => (
          <div key={lvl} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
            <span style={{ fontSize: '0.8rem', color: '#e2e4ec' }}>Level {lvl}:</span>
            <div className="slot-track">
              {Array.from({ length: slot.max_slots }).map((_, i) => (
                <div
                  key={i}
                  className={`slot-bubble ${i < slot.current ? 'filled' : ''}`}
                  title={`Level ${lvl} Slot ${i + 1} (${i < slot.current ? 'Ready' : 'Expended'})`}
                />
              ))}
              <span style={{ fontSize: '0.75rem', color: '#8b92a5', marginLeft: 4 }}>{slot.current}/{slot.max_slots}</span>
            </div>
          </div>
        ))}
      </div>

      {/* Prepared Spells */}
      <div style={{ padding: '12px 16px', flex: 1, overflowY: 'auto' }}>
        <div style={{ fontSize: '0.8rem', fontWeight: 700, color: '#8b92a5', marginBottom: 8, textTransform: 'uppercase' }}>
          Prepared Spells
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginBottom: 12 }}>
          {knownSpells.map((spell, idx) => (
            <div
              key={idx}
              style={{
                background: '#181b24',
                border: '1px solid #282d3d',
                padding: '8px 10px',
                borderRadius: 4,
                fontSize: '0.85rem',
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center'
              }}
            >
              <div>
                <span style={{ color: '#a8dadc', fontWeight: 600 }}>{spell}</span>
              </div>
              <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                <button
                  onClick={() => onCastSpell(spell, 1)}
                  className="hp-btn"
                  style={{ color: '#d4af37', borderColor: '#d4af37', fontSize: '0.65rem', padding: '2px 6px', display: 'flex', alignItems: 'center', gap: 3 }}
                >
                  <Wand2 size={10} /> Cast
                </button>
                <button
                  onClick={() => onUnlearnSpell(spell)}
                  className="hp-btn"
                  style={{ color: '#8b92a5', fontSize: '0.65rem', padding: '2px 4px' }}
                  title="Remove from prepared spells"
                >
                  <X size={10} />
                </button>
              </div>
            </div>
          ))}
        </div>

        {/* Learn Spell Input */}
        <form onSubmit={handleSubmit} style={{ display: 'flex', gap: 6 }}>
          <input
            type="text"
            value={newSpellInput}
            onChange={(e) => setNewSpellInput(e.target.value)}
            placeholder="New spell name..."
            className="input-field"
            style={{ flex: 1, padding: '6px 8px', fontSize: '0.75rem' }}
          />
          <button type="submit" className="send-btn" style={{ padding: '6px 10px', fontSize: '0.75rem' }}>
            Learn
          </button>
        </form>
      </div>
    </div>
  );
};
