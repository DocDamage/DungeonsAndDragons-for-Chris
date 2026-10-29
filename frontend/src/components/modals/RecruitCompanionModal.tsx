import React, { useState } from 'react';
import { UserPlus, X } from 'lucide-react';

interface RecruitCompanionModalProps {
  onAddCompanion: (payload: {
    name: string;
    race?: string;
    class_name?: string;
    level?: number;
    current_hp?: number;
    max_hp?: number;
    ac?: number;
    attack_name?: string;
    damage?: string;
    notes?: string;
  }) => void;
  onClose: () => void;
}

export const RecruitCompanionModal: React.FC<RecruitCompanionModalProps> = ({
  onAddCompanion,
  onClose
}) => {
  const [name, setName] = useState("");
  const [className, setClassName] = useState("Fighter");
  const [race, setRace] = useState("Human");
  const [level, setLevel] = useState(2);
  const [hp, setHp] = useState(18);
  const [ac, setAc] = useState(14);
  const [attackName, setAttackName] = useState("Shortsword");
  const [damage, setDamage] = useState("1d6+2");
  const [notes, setNotes] = useState("");

  const handleSubmit = () => {
    if (!name.trim()) return;
    onAddCompanion({
      name: name.trim(),
      race: race.trim() || "Human",
      class_name: className.trim() || "Fighter",
      level: level || 2,
      current_hp: hp || 18,
      max_hp: hp || 18,
      ac: ac || 14,
      attack_name: attackName.trim() || "Weapon Strike",
      damage: damage.trim() || "1d6+2",
      notes: notes.trim()
    });
  };

  return (
    <div style={{
      position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
      background: 'rgba(0,0,0,0.85)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000
    }}>
      <div style={{
        background: 'var(--bg-secondary)', border: '1px solid var(--gold)', borderRadius: 8,
        width: 480, maxWidth: '90vw', overflow: 'hidden'
      }}>
        <div style={{
          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
          padding: '14px 20px', borderBottom: '1px solid var(--border)'
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--gold)', fontWeight: 700 }}>
            <UserPlus size={18} />
            <span>RECRUIT PARTY COMPANION</span>
          </div>
          <button onClick={onClose} className="hp-btn"><X size={16} /></button>
        </div>

        <div style={{ padding: 20, display: 'flex', flexDirection: 'column', gap: 12 }}>
          <div style={{ display: 'grid', gridTemplateColumns: '1.5fr 1fr 1fr', gap: 10 }}>
            <div>
              <label style={{ fontSize: '0.75rem', color: '#8b92a5' }}>Name</label>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. Ezmerelda"
                className="input-field"
                style={{ width: '100%', marginTop: 4 }}
              />
            </div>
            <div>
              <label style={{ fontSize: '0.75rem', color: '#8b92a5' }}>Race</label>
              <input
                type="text"
                value={race}
                onChange={(e) => setRace(e.target.value)}
                placeholder="Human, Elf..."
                className="input-field"
                style={{ width: '100%', marginTop: 4 }}
              />
            </div>
            <div>
              <label style={{ fontSize: '0.75rem', color: '#8b92a5' }}>Class</label>
              <input
                type="text"
                value={className}
                onChange={(e) => setClassName(e.target.value)}
                placeholder="Fighter, Rogue..."
                className="input-field"
                style={{ width: '100%', marginTop: 4 }}
              />
            </div>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 10 }}>
            <div>
              <label style={{ fontSize: '0.75rem', color: '#8b92a5' }}>Level</label>
              <input
                type="number"
                value={level}
                onChange={(e) => setLevel(parseInt(e.target.value) || 1)}
                className="input-field"
                style={{ width: '100%', marginTop: 4 }}
              />
            </div>
            <div>
              <label style={{ fontSize: '0.75rem', color: '#8b92a5' }}>Max HP</label>
              <input
                type="number"
                value={hp}
                onChange={(e) => setHp(parseInt(e.target.value) || 1)}
                className="input-field"
                style={{ width: '100%', marginTop: 4 }}
              />
            </div>
            <div>
              <label style={{ fontSize: '0.75rem', color: '#8b92a5' }}>AC</label>
              <input
                type="number"
                value={ac}
                onChange={(e) => setAc(parseInt(e.target.value) || 10)}
                className="input-field"
                style={{ width: '100%', marginTop: 4 }}
              />
            </div>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
            <div>
              <label style={{ fontSize: '0.75rem', color: '#8b92a5' }}>Attack Name</label>
              <input
                type="text"
                value={attackName}
                onChange={(e) => setAttackName(e.target.value)}
                placeholder="e.g. Silvered Rapier"
                className="input-field"
                style={{ width: '100%', marginTop: 4 }}
              />
            </div>
            <div>
              <label style={{ fontSize: '0.75rem', color: '#8b92a5' }}>Damage Dice</label>
              <input
                type="text"
                value={damage}
                onChange={(e) => setDamage(e.target.value)}
                placeholder="e.g. 1d8+3"
                className="input-field"
                style={{ width: '100%', marginTop: 4 }}
              />
            </div>
          </div>

          <div>
            <label style={{ fontSize: '0.75rem', color: '#8b92a5' }}>Companion Notes / Backstory</label>
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="Notes, motivations, loyalty or relationship to party..."
              rows={2}
              className="input-field"
              style={{ width: '100%', marginTop: 4 }}
            />
          </div>

          <div style={{ display: 'flex', gap: 10, marginTop: 10 }}>
            <button onClick={handleSubmit} className="send-btn" style={{ flex: 1 }}>
              Add Companion to Party
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
