import React, { useState } from 'react';
import { User, Heart, Shield, Scroll, Wand2, Users } from 'lucide-react';
import type { Character, CombatEncounter, D6BoostWindow, GameSession, LeftSidebarTab } from '../../types';
import { D6Sidebar } from './D6Sidebar';
import { getMod } from '../../utils/helpers';
import { InventoryTab } from './InventoryTab';
import { SpellbookTab } from './SpellbookTab';
import { CompanionsTab } from './CompanionsTab';

interface CharacterSidebarProps {
  character: Character;
  edition: string;
  isCombatActive: boolean;
  selectedTargetId: string | null;
  onOpenCharModal: () => void;
  onQuickHp: (delta: number) => void;
  onUseItem: (itemName: string) => void;
  onCastSpell: (spellName: string, slotLevel?: number) => void;
  onRestoreSlots: (level?: number) => void;
  onLearnSpell: (spellName: string) => void;
  onUnlearnSpell: (spellName: string) => void;
  onOpenRecruitModal: () => void;
  onDeleteCompanion: (companionId: string) => void;
  onAdjustCompanionHp: (companionId: string, delta: number) => void;
  onCompanionAttack: (companionId: string) => void;
  encounter?: CombatEncounter | null;
  onSessionChanged: (session: GameSession) => void;
  nativeBoost?: D6BoostWindow | null;
  vehicleCombatActive?: boolean;
}

export const CharacterSidebar: React.FC<CharacterSidebarProps> = ({
  character,
  edition,
  isCombatActive,
  selectedTargetId,
  onOpenCharModal,
  onQuickHp,
  onUseItem,
  onCastSpell,
  onRestoreSlots,
  onLearnSpell,
  onUnlearnSpell,
  onOpenRecruitModal,
  onDeleteCompanion,
  onAdjustCompanionHp,
  onCompanionAttack,
  encounter,
  onSessionChanged,
  nativeBoost,
  vehicleCombatActive
}) => {
  const [leftTab, setLeftTab] = useState<LeftSidebarTab>("inventory");
  const hpPercent = Math.max(0, Math.min(100, (character.current_hp / character.max_hp) * 100));

  if (edition === 'weg_d6' && character.d6) return <D6Sidebar character={character} encounter={encounter} selectedTargetId={selectedTargetId} onEdit={onOpenCharModal} onSessionChanged={onSessionChanged} boost={nativeBoost} vehicleCombatActive={vehicleCombatActive} />;

  return (
    <aside className="panel-sidebar">
      {/* Character Identity */}
      <div className="char-header">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div className="char-name">{character.name}</div>
          <button
            onClick={onOpenCharModal}
            className="hp-btn"
            style={{ fontSize: '0.7rem', display: 'flex', alignItems: 'center', gap: 4 }}
            title="Edit Character Sheet & Roll Stats"
          >
            <User size={12} /> Edit
          </button>
        </div>
        <div className="char-sub">
          Level {character.level} {character.race} {character.class_name} • {character.alignment}
        </div>

        {/* HP Bar */}
        <div className="hp-container">
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.8rem' }}>
            <span style={{ color: '#8b92a5', display: 'flex', alignItems: 'center', gap: 4 }}>
              <Heart size={14} color="#e63946" /> HP
            </span>
            <span style={{ fontWeight: 700, color: '#fff' }}>
              {character.current_hp} / {character.max_hp}
            </span>
          </div>
          <div className="hp-bar-bg">
            <div className="hp-bar-fill" style={{ width: `${hpPercent}%` }} />
          </div>
          <div className="hp-controls">
            <button className="hp-btn" onClick={() => onQuickHp(-5)}>-5</button>
            <button className="hp-btn" onClick={() => onQuickHp(-1)}>-1</button>
            <button className="hp-btn" onClick={() => onQuickHp(1)}>+1</button>
            <button className="hp-btn" onClick={() => onQuickHp(5)}>+5</button>
            <button className="hp-btn" onClick={() => onQuickHp(character.max_hp)}>Full</button>
          </div>
        </div>
      </div>

      {/* Core Defense & Wealth */}
      <div style={{ display: 'flex', borderBottom: '1px solid #282d3d', padding: '10px 16px', justifyContent: 'space-between' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <Shield size={16} color="#d4af37" />
          <span style={{ fontSize: '0.85rem' }}>
            {edition === '2e' ? 'Descending AC: ' : 'AC: '}
            <strong>{character.ac}</strong>
          </span>
        </div>
        <div style={{ fontSize: '0.85rem' }}>
          Gold: <strong style={{ color: '#d4af37' }}>{character.gold} gp</strong>
        </div>
      </div>

      {/* Ability Scores Grid */}
      <div className="stat-grid">
        {(['str', 'dex', 'con', 'int', 'wis', 'cha'] as const).map((stat) => (
          <div key={stat} className="stat-box">
            <div className="stat-label">{stat.toUpperCase()}</div>
            <div className="stat-score">{character.abilities[stat]}</div>
            <div className="stat-mod">{getMod(character.abilities[stat])}</div>
          </div>
        ))}
      </div>

      {/* Sub-Tabs: Inventory / Spellbook / Party */}
      <div className="sidebar-tabs">
        <button
          onClick={() => setLeftTab("inventory")}
          className={`sidebar-tab-btn ${leftTab === "inventory" ? "active" : ""}`}
        >
          <Scroll size={12} /> Items ({character.inventory.length})
        </button>
        <button
          onClick={() => setLeftTab("spells")}
          className={`sidebar-tab-btn ${leftTab === "spells" ? "active" : ""}`}
        >
          <Wand2 size={12} /> Spells ({(character.known_spells || []).length})
        </button>
        <button
          onClick={() => setLeftTab("companions")}
          className={`sidebar-tab-btn ${leftTab === "companions" ? "active" : ""}`}
        >
          <Users size={12} /> Party ({(character.companions || []).length})
        </button>
      </div>

      {/* Active Tab View */}
      {leftTab === "inventory" && (
        <InventoryTab inventory={character.inventory} onUseItem={onUseItem} />
      )}
      {leftTab === "spells" && (
        <SpellbookTab
          spellSlots={character.spell_slots}
          knownSpells={character.known_spells}
          onCastSpell={onCastSpell}
          onRestoreSlots={onRestoreSlots}
          onLearnSpell={onLearnSpell}
          onUnlearnSpell={onUnlearnSpell}
        />
      )}
      {leftTab === "companions" && (
        <CompanionsTab
          companions={character.companions}
          isCombatActive={isCombatActive}
          selectedTargetId={selectedTargetId}
          onOpenRecruitModal={onOpenRecruitModal}
          onDeleteCompanion={onDeleteCompanion}
          onAdjustCompanionHp={onAdjustCompanionHp}
          onCompanionAttack={onCompanionAttack}
        />
      )}
    </aside>
  );
};
