import React, { useState } from 'react';
import { Save, X, Trash2 } from 'lucide-react';
import type { SaveSlot } from '../../types';

interface SaveSlotsModalProps {
  saveSlots: SaveSlot[];
  onSaveSession: (slotName?: string) => void;
  onLoadSession: (slotId: string) => void;
  onDeleteSave: (slotId: string) => void;
  onClose: () => void;
}

export const SaveSlotsModal: React.FC<SaveSlotsModalProps> = ({
  saveSlots,
  onSaveSession,
  onLoadSession,
  onDeleteSave,
  onClose
}) => {
  const [saveSlotInput, setSaveSlotInput] = useState("");

  const handleSave = () => {
    onSaveSession(saveSlotInput.trim() || undefined);
    setSaveSlotInput("");
  };

  return (
    <div style={{
      position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
      background: 'rgba(0,0,0,0.85)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000
    }}>
      <div style={{
        background: 'var(--bg-secondary)', border: '1px solid var(--border)', borderRadius: 8,
        width: 640, maxWidth: '90vw', maxHeight: '85vh', display: 'flex', flexDirection: 'column', overflow: 'hidden'
      }}>
        <div style={{ padding: '16px 20px', borderBottom: '1px solid var(--border)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--gold)', fontWeight: 700, fontSize: '1.1rem' }}>
            <Save size={18} />
            <span>ADVENTURE SAVES & CHRONICLE</span>
          </div>
          <button onClick={onClose} className="hp-btn"><X size={16} /></button>
        </div>

        <div style={{ padding: 20, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 16 }}>
          {/* Save New Slot Box */}
          <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: 6, padding: 14 }}>
            <div style={{ fontSize: '0.85rem', fontWeight: 700, color: '#fff', marginBottom: 8 }}>Save Active Adventure</div>
            <div style={{ display: 'flex', gap: 8 }}>
              <input
                type="text"
                value={saveSlotInput}
                onChange={(e) => setSaveSlotInput(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleSave()}
                placeholder="Slot name (e.g. death_house_ritual)"
                className="action-input"
                style={{ padding: '8px 10px', fontSize: '0.85rem' }}
              />
              <button onClick={handleSave} className="send-btn" style={{ padding: '8px 14px', fontSize: '0.8rem' }}>
                <Save size={14} /> Save Slot
              </button>
            </div>
          </div>

          {/* Saved Slots List */}
          <div>
            <div style={{ fontSize: '0.85rem', fontWeight: 700, color: '#8b92a5', marginBottom: 8, textTransform: 'uppercase' }}>
              Saved Adventures ({saveSlots.length})
            </div>
            {saveSlots.length === 0 ? (
              <div style={{ color: '#8b92a5', fontSize: '0.85rem', textAlign: 'center', padding: 20 }}>
                No saved adventures found. Save your current progress above.
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {saveSlots.map((s) => (
                  <div
                    key={s.slot_id}
                    style={{
                      background: 'var(--bg-card)', border: '1px solid var(--border)',
                      borderRadius: 6, padding: 12, display: 'flex', justifyContent: 'space-between', alignItems: 'center'
                    }}
                  >
                    <div>
                      <div style={{ fontWeight: 700, color: '#fff', fontSize: '0.9rem' }}>{s.title}</div>
                      <div style={{ fontSize: '0.75rem', color: '#8b92a5', marginTop: 2 }}>
                        Hero: <strong style={{ color: '#d4af37' }}>{s.character_name}</strong> • {s.edition.toUpperCase()} • {s.turns_count} turns
                      </div>
                    </div>

                    <div style={{ display: 'flex', gap: 6 }}>
                      <button
                        onClick={() => onLoadSession(s.slot_id)}
                        className="send-btn"
                        style={{ padding: '6px 12px', fontSize: '0.75rem' }}
                      >
                        Load
                      </button>
                      <button
                        onClick={() => onDeleteSave(s.slot_id)}
                        className="hp-btn"
                        style={{ color: '#ff6b6b' }}
                        title="Delete Save"
                      >
                        <Trash2 size={12} />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
