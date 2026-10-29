import React, { type RefObject } from 'react';
import { Scroll } from 'lucide-react';
import type { ActionTurn } from '../../types';
import { TurnCard } from './TurnCard';

interface NarrativeStreamProps {
  history: ActionTurn[];
  editingTurnId: string | null;
  editTurnText: string;
  illustratingTurnId: string | null;
  storyEndRef: RefObject<HTMLDivElement | null>;
  onEditChange: (text: string) => void;
  onSaveAlteration: (turnId: string) => void;
  onCancelAlteration: () => void;
  onStartEditing: (turn: ActionTurn) => void;
  onSpeakTurn: (text: string) => void;
  onIllustrateTurn: (turnId: string, text: string) => void;
  onViewImage: (url: string) => void;
}

export const NarrativeStream: React.FC<NarrativeStreamProps> = ({
  history,
  editingTurnId,
  editTurnText,
  illustratingTurnId,
  storyEndRef,
  onEditChange,
  onSaveAlteration,
  onCancelAlteration,
  onStartEditing,
  onSpeakTurn,
  onIllustrateTurn,
  onViewImage
}) => {
  return (
    <div className="story-stream">
      {history.length === 0 && (
        <div style={{ textAlign: 'center', color: '#8b92a5', margin: 'auto', maxWidth: 460 }}>
          <Scroll size={40} color="#d4af37" style={{ margin: '0 auto 12px' }} />
          <h3 style={{ color: '#e2e4ec', marginBottom: 8 }}>The Adventure Begins</h3>
          <p style={{ fontSize: '0.9rem', lineHeight: 1.5 }}>
            The realm unfolds before you. What would you like to do?
            Use <strong>Do</strong> to act, <strong>Say</strong> to speak, <strong>Attack</strong> to fight, or <strong>See</strong> to illustrate!
          </p>
        </div>
      )}

      {history.map((turn) => (
        <TurnCard
          key={turn.id}
          turn={turn}
          isEditing={editingTurnId === turn.id}
          editTurnText={editTurnText}
          illustratingTurnId={illustratingTurnId}
          onEditChange={onEditChange}
          onSaveAlteration={onSaveAlteration}
          onCancelAlteration={onCancelAlteration}
          onStartEditing={onStartEditing}
          onSpeakTurn={onSpeakTurn}
          onIllustrateTurn={onIllustrateTurn}
          onViewImage={onViewImage}
        />
      ))}
      <div ref={storyEndRef} />
    </div>
  );
};
