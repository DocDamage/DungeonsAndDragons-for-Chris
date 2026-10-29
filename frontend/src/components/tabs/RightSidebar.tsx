import React, { useState } from 'react';
import { BookOpen, MapPin, Map as MapIcon, Search, Dices, Settings } from 'lucide-react';
import type { StoryCard, CompendiumEntry, RollResult, RightSidebarTab } from '../../types';
import { CardsTab } from './CardsTab';
import { QuestsTab } from './QuestsTab';
import DungeonMap from '../../DungeonMap';
import { CompendiumTab } from './CompendiumTab';
import { DiceRollerTab } from './DiceRollerTab';
import { LLMSettingsTab } from './LLMSettingsTab';

interface RightSidebarProps {
  edition: string;
  cards: StoryCard[];
  activeQuests: Record<string, string[]>;
  compendiumResults: CompendiumEntry[];
  diceHistory: RollResult[];
  diceError: string | null;
  onTravelToRoom: (roomName: string) => void;
  onSearchCompendium: (q: string, cat: string, ed: string) => void;
  onSpawnMonster: (entry: CompendiumEntry) => void;
  onRollDice: (expr: string) => void;
  onSaveLLMConfig: (payload: { provider: string; api_key?: string; base_url?: string; model?: string }) => void;
}

export const RightSidebar: React.FC<RightSidebarProps> = ({
  edition,
  cards,
  activeQuests,
  compendiumResults,
  diceHistory,
  diceError,
  onTravelToRoom,
  onSearchCompendium,
  onSpawnMonster,
  onRollDice,
  onSaveLLMConfig
}) => {
  const [rightTab, setRightTab] = useState<RightSidebarTab>("cards");

  return (
    <aside className="panel-right">
      <div className="tabs-header">
        <button
          onClick={() => setRightTab("cards")}
          className={`tab-btn ${rightTab === "cards" ? "active" : ""}`}
        >
          <BookOpen size={14} /> Cards ({cards.length})
        </button>
        <button
          onClick={() => setRightTab("quests")}
          className={`tab-btn ${rightTab === "quests" ? "active" : ""}`}
        >
          <MapPin size={14} /> Quests
        </button>
        <button
          onClick={() => setRightTab("map")}
          className={`tab-btn ${rightTab === "map" ? "active" : ""}`}
        >
          <MapIcon size={14} /> Map
        </button>
        <button
          onClick={() => {
            setRightTab("compendium");
            if (compendiumResults.length === 0) onSearchCompendium("", "all", "all");
          }}
          className={`tab-btn ${rightTab === "compendium" ? "active" : ""}`}
        >
          <Search size={14} /> Lore
        </button>
        <button
          onClick={() => setRightTab("dice")}
          className={`tab-btn ${rightTab === "dice" ? "active" : ""}`}
        >
          <Dices size={14} /> Dice
        </button>
        <button
          onClick={() => setRightTab("settings")}
          className={`tab-btn ${rightTab === "settings" ? "active" : ""}`}
        >
          <Settings size={14} /> LLM
        </button>
      </div>

      {rightTab === "cards" && <CardsTab cards={cards} />}
      {rightTab === "quests" && <QuestsTab activeQuests={activeQuests} />}
      {rightTab === "map" && (
        <div style={{ height: '100%' }}>
          <DungeonMap onTravelToRoom={onTravelToRoom} />
        </div>
      )}
      {rightTab === "compendium" && (
        <CompendiumTab
          results={compendiumResults}
          onSearch={onSearchCompendium}
          onSpawnMonster={onSpawnMonster}
        />
      )}
      {rightTab === "dice" && (
        <DiceRollerTab
          key={edition}
          native={edition === 'weg_d6'}
          diceHistory={diceHistory}
          error={diceError}
          onRollDice={onRollDice}
        />
      )}
      {rightTab === "settings" && (
        <LLMSettingsTab onSaveConfig={onSaveLLMConfig} />
      )}
    </aside>
  );
};
