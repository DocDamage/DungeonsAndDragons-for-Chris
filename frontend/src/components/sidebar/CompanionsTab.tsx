import React from 'react';
import { User, UserPlus, Trash2 } from 'lucide-react';
import type { Companion } from '../../types';

interface CompanionsTabProps {
  companions?: Companion[];
  isCombatActive: boolean;
  selectedTargetId: string | null;
  onOpenRecruitModal: () => void;
  onDeleteCompanion: (companionId: string) => void;
  onAdjustCompanionHp: (companionId: string, delta: number) => void;
  onCompanionAttack: (companionId: string) => void;
}

export const CompanionsTab: React.FC<CompanionsTabProps> = ({
  companions = [],
  isCombatActive,
  selectedTargetId,
  onOpenRecruitModal,
  onDeleteCompanion,
  onAdjustCompanionHp,
  onCompanionAttack
}) => {
  return (
    <div style={{ padding: '12px 16px', flex: 1, overflowY: 'auto' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
        <span style={{ fontSize: '0.8rem', fontWeight: 700, color: '#8b92a5', textTransform: 'uppercase' }}>Party Allies</span>
        <button
          onClick={onOpenRecruitModal}
          className="hp-btn"
          style={{ fontSize: '0.7rem', padding: '2px 8px', display: 'flex', alignItems: 'center', gap: 4 }}
        >
          <UserPlus size={11} /> Recruit
        </button>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        {companions.length === 0 ? (
          <div style={{ fontSize: '0.75rem', color: '#8b92a5', fontStyle: 'italic', textAlign: 'center', padding: '20px 0' }}>
            No companion allies currently traveling in the party.
          </div>
        ) : (
          companions.map((comp) => {
            const compHpPct = Math.max(0, Math.min(100, (comp.current_hp / comp.max_hp) * 100));
            return (
              <div key={comp.id} className="companion-card">
                <div className="companion-header">
                  {comp.avatar_url ? (
                    <img src={comp.avatar_url} alt={comp.name} className="companion-avatar" />
                  ) : (
                    <div className="companion-avatar" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                      <User size={20} color="#d4af37" />
                    </div>
                  )}
                  <div className="companion-info">
                    <div className="companion-name">{comp.name}</div>
                    <div className="companion-class">Level {comp.level} {comp.race} {comp.class_name} • AC {comp.ac}</div>
                    <div style={{ fontSize: '0.7rem', color: '#ff6b6b', marginTop: 2 }}>
                      {comp.attack_name} ({comp.damage})
                    </div>
                  </div>
                  <button
                    onClick={() => onDeleteCompanion(comp.id)}
                    className="hp-btn"
                    style={{ color: '#8b92a5', padding: '2px 4px' }}
                    title="Dismiss companion"
                  >
                    <Trash2 size={11} />
                  </button>
                </div>

                {/* HP Bar */}
                <div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.7rem', marginBottom: 2 }}>
                    <span style={{ color: '#8b92a5' }}>HP</span>
                    <span style={{ color: comp.current_hp === 0 ? '#ff6b6b' : '#fff', fontWeight: 600 }}>
                      {comp.current_hp} / {comp.max_hp}
                    </span>
                  </div>
                  <div className="hp-bar-bg" style={{ height: 4 }}>
                    <div className="hp-bar-fill" style={{ width: `${compHpPct}%` }} />
                  </div>
                  <div style={{ display: 'flex', gap: 4, marginTop: 4 }}>
                    <button className="hp-btn" style={{ fontSize: '0.65rem', padding: '1px 5px' }} onClick={() => onAdjustCompanionHp(comp.id, -2)}>-2</button>
                    <button className="hp-btn" style={{ fontSize: '0.65rem', padding: '1px 5px' }} onClick={() => onAdjustCompanionHp(comp.id, 2)}>+2</button>
                    <button className="hp-btn" style={{ fontSize: '0.65rem', padding: '1px 5px' }} onClick={() => onAdjustCompanionHp(comp.id, comp.max_hp)}>Full</button>
                    {isCombatActive && selectedTargetId && (
                      <button
                        className="hp-btn"
                        style={{ fontSize: '0.65rem', padding: '1px 7px', color: '#d4af37', borderColor: '#d4af37', marginLeft: 'auto' }}
                        onClick={() => onCompanionAttack(comp.id)}
                      >
                        ⚔️ Strike Target
                      </button>
                    )}
                  </div>
                </div>

                {comp.notes && (
                  <div style={{ fontSize: '0.7rem', color: '#8b92a5', borderTop: '1px solid #282d3d', paddingTop: 4 }}>
                    {comp.notes}
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
};
