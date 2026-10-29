import React, { useState } from 'react';
import type { RollResult } from '../../types';

interface DiceRollerTabProps {
  native?: boolean;
  diceHistory: RollResult[];
  error: string | null;
  onRollDice: (expression: string) => void;
}

export const DiceRollerTab: React.FC<DiceRollerTabProps> = ({
  native = false,
  diceHistory,
  error,
  onRollDice
}) => {
  const [customDice, setCustomDice] = useState(native ? '3D+2' : '1d20');

  const handleCustomRoll = () => {
    if (!customDice.trim()) return;
    onRollDice(customDice.trim());
  };

  return (
    <div className="dice-tray">
      <div style={{ fontSize: '0.8rem', color: '#8b92a5' }}>Click a die to roll immediately:</div>
      <div className="dice-grid">
        {(native ? ['1D', '2D', '3D', '3D+2', '4D', '5D', '6D'] : ['1d4', '1d6', '1d8', '1d10', '1d12', '1d20', '1d100', '4d6kh3']).map((d) => (
          <button key={d} onClick={() => onRollDice(d)} className="die-btn">
            {d}
          </button>
        ))}
      </div>

      <div style={{ display: 'flex', gap: 6, marginTop: 8 }}>
        <input
          type="text"
          value={customDice}
          onChange={(e) => setCustomDice(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleCustomRoll()}
          placeholder={native ? 'e.g. 3D+2 (includes Wild Die)' : 'e.g. 2d6+3 or 1d20+5 adv'}
          aria-label="Dice expression"
          aria-invalid={Boolean(error)}
          aria-describedby={error ? 'dice-error' : 'dice-help'}
          className="action-input"
          style={{ padding: '8px 10px', fontSize: '0.85rem' }}
        />
        <button onClick={handleCustomRoll} className="send-btn" style={{ padding: '8px 12px' }}>
          Roll
        </button>
      </div>

      <div id="dice-help" style={{ marginTop: 8, fontSize: '0.75rem', color: '#8b92a5' }}>
        {native ? 'Native WEG pools include one Wild Die. Six explodes; an initial one discards the Wild Die and highest normal die. Use the character sheet for skills and resource spending.' : 'Try 4d6kh3, 2d20kl1+5, 1d20+5 dis, or 2d6+1d4+3.'}
      </div>
      {error && <div id="dice-error" role="alert" style={{ marginTop: 8, color: '#ff6b6b', fontSize: '0.85rem' }}>{error}</div>}

      <div style={{ marginTop: 12 }}>
        <div style={{ fontSize: '0.75rem', fontWeight: 700, color: '#8b92a5', marginBottom: 6, textTransform: 'uppercase' }}>
          Recent Roll History
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          {diceHistory.map((r, idx) => (
            <div
              key={idx}
              style={{
                background: '#181b24',
                border: r.is_crit ? '1px solid #ff6b6b' : '1px solid #282d3d',
                padding: '6px 10px',
                borderRadius: 4,
                fontSize: '0.8rem',
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center'
              }}
            >
              <span>{r.expression}: {r.breakdown}</span>
              <strong style={{ color: r.is_crit ? '#ff6b6b' : '#d4af37', fontSize: '0.95rem' }}>
                {r.total}
              </strong>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};
