import React from 'react';
import { Dices, Volume1, Edit2, Sparkles } from 'lucide-react';
import type { ActionTurn } from '../../types';

interface TurnCardProps {
  turn: ActionTurn;
  isEditing: boolean;
  editTurnText: string;
  illustratingTurnId: string | null;
  onEditChange: (text: string) => void;
  onSaveAlteration: (turnId: string) => void;
  onCancelAlteration: () => void;
  onStartEditing: (turn: ActionTurn) => void;
  onSpeakTurn: (text: string) => void;
  onIllustrateTurn: (turnId: string, text: string) => void;
  onViewImage: (url: string) => void;
}

export const TurnCard: React.FC<TurnCardProps> = ({
  turn,
  isEditing,
  editTurnText,
  illustratingTurnId,
  onEditChange,
  onSaveAlteration,
  onCancelAlteration,
  onStartEditing,
  onSpeakTurn,
  onIllustrateTurn,
  onViewImage
}) => {
  return (
    <div className="turn-card">
      {/* Player Action */}
      <div className="player-bubble">
        <div className="player-mode-tag">{turn.mode}</div>
        <div>
          {turn.mode === 'do' && `> You ${turn.player_input}`}
          {turn.mode === 'say' && `> You say, "${turn.player_input}"`}
          {turn.mode === 'story' && turn.player_input}
          {turn.mode === 'attack' && `> Attack: ${turn.player_input}`}
          {turn.mode === 'check' && `> Check: ${turn.player_input}`}
          {turn.mode === 'cast' && `> Cast: ${turn.player_input}`}
          {turn.mode === 'see' && `> See: ${turn.player_input}`}
          {turn.mode === 'rest' && `> Rest: ${turn.player_input}`}
        </div>
      </div>

      {/* Deterministic Rule Check Output */}
      {turn.rule_result && (
        <div className={`rule-check-box ${turn.rule_result.is_crit ? 'rule-crit' : ''}`}>
          <Dices size={16} />
          <span>{turn.rule_result.summary}</span>
        </div>
      )}

      {!!turn.rule_result?.force_rolls?.length && <details className="native-help"><summary>Force skill rolls</summary>{turn.rule_result.force_rolls.map((component, index) => <p key={`${component.skill}-${index}`}>{component.skill}: {component.roll.breakdown} vs {component.difficulty} · {component.success ? 'SUCCESS' : 'FAILED'}{component.opposition ? ` · Resistance: ${component.opposition.breakdown}` : ''}</p>)}</details>}

      {/* DM Narrative */}
      {isEditing ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          <textarea
            value={editTurnText}
            onChange={(e) => onEditChange(e.target.value)}
            rows={4}
            style={{
              background: '#181b24',
              border: '1px solid #d4af37',
              color: '#fff',
              padding: 10,
              borderRadius: 6
            }}
          />
          <div style={{ display: 'flex', gap: 6 }}>
            <button onClick={() => onSaveAlteration(turn.id)} className="send-btn" style={{ padding: '6px 12px' }}>
              Save Alteration
            </button>
            <button onClick={onCancelAlteration} className="hp-btn">
              Cancel
            </button>
          </div>
        </div>
      ) : turn.dm_output !== turn.rule_result?.summary && (
        <div className="dm-bubble">{turn.dm_output}</div>
      )}

      {Boolean(turn.source_references?.length) && <details style={{ fontSize: '0.75rem', color: '#8b92a5' }}>
        <summary style={{ cursor: 'pointer' }}>Sources consulted</summary>
        <ul>{turn.source_references?.map((source, index) => <li key={`${source.source_id}-${index}`}>
          <a style={{ color: '#d4af37' }} href={source.file_url + (/^Page (\d+)$/.test(source.section) ? `#page=${source.section.slice(5)}` : '')} target="_blank" rel="noopener noreferrer">{source.title} · {source.section}</a>
        </li>)}</ul>
      </details>}

      {/* Illustrated Scene Image Banner */}
      {turn.image_url && (
        <div className="turn-scene-container">
          <img
            src={turn.image_url}
            alt="Illustrated Scene"
            className="turn-scene-img"
            onClick={() => onViewImage(turn.image_url!)}
          />
          <div className="turn-scene-badge">
            <Sparkles size={11} /> Scene Illustrated • Click to Enlarge
          </div>
        </div>
      )}

      {/* Turn Actions */}
      <div className="turn-actions">
        <button
          onClick={() => onSpeakTurn(turn.dm_output)}
          className="hp-btn"
          style={{ display: 'flex', alignItems: 'center', gap: 4 }}
          title="Narrate turn with Text-to-Speech"
        >
          <Volume1 size={11} /> Read Aloud
        </button>

        <button
          onClick={() => onIllustrateTurn(turn.id, turn.dm_output)}
          disabled={illustratingTurnId === turn.id}
          className="hp-btn"
          style={{ display: 'flex', alignItems: 'center', gap: 4, color: '#d4af37', borderColor: '#d4af37' }}
          title="Generate visual scene illustration"
        >
          <Sparkles size={11} />
          {illustratingTurnId === turn.id ? "Illustrating..." : (turn.image_url ? "Regenerate Art" : "Illustrate Scene")}
        </button>

        <button
          onClick={() => onStartEditing(turn)}
          className="hp-btn"
          style={{ display: 'flex', alignItems: 'center', gap: 4 }}
        >
          <Edit2 size={10} /> Alter
        </button>
      </div>
    </div>
  );
};
