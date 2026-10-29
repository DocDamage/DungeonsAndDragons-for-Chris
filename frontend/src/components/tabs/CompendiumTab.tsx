import React, { useState } from 'react';
import { Search, Eye, Sword } from 'lucide-react';
import type { CompendiumEntry } from '../../types';

interface CompendiumTabProps {
  results: CompendiumEntry[];
  onSearch: (q: string, cat: string, ed: string) => void;
  onSpawnMonster: (entry: CompendiumEntry) => void;
}

export const CompendiumTab: React.FC<CompendiumTabProps> = ({
  results,
  onSearch,
  onSpawnMonster
}) => {
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("all");
  const [edition, setEdition] = useState("all");
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const handleSearchSubmit = () => {
    onSearch(query, category, edition);
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <div className="compendium-search-bar">
        <div style={{ display: 'flex', gap: 6 }}>
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleSearchSubmit()}
            placeholder="Search spells, monsters, items..."
            className="action-input"
            style={{ padding: '8px 10px', fontSize: '0.85rem' }}
          />
          <button onClick={handleSearchSubmit} className="send-btn" style={{ padding: '8px 12px' }}>
            <Search size={14} />
          </button>
        </div>

        <div className="compendium-filters">
          <select
            value={category}
            onChange={(e) => setCategory(e.target.value)}
            style={{ background: '#181b24', border: '1px solid #282d3d', color: '#fff', fontSize: '0.75rem', padding: 4, borderRadius: 4, flex: 1 }}
          >
            <option value="all">All Categories</option>
            <option value="spell">Spells</option>
            <option value="monster">Monsters</option>
            <option value="item">Items</option>
          </select>

          <select
            value={edition}
            onChange={(e) => setEdition(e.target.value)}
            style={{ background: '#181b24', border: '1px solid #282d3d', color: '#fff', fontSize: '0.75rem', padding: 4, borderRadius: 4, flex: 1 }}
          >
            <option value="all">All Editions</option>
            <option value="2e">AD&D 2e</option>
            <option value="3.5e">D&D 3.5e</option>
            <option value="5e">D&D 5e</option>
          </select>
        </div>
      </div>

      <div className="compendium-list">
        {results.map((item) => {
          const isExpanded = expandedId === item.id;
          const isMonster = item.category === "monster";

          return (
            <div key={item.id} className="compendium-item">
              <div className="compendium-item-header">
                <div className="compendium-item-name">{item.name}</div>
                <div style={{ display: 'flex', gap: 4 }}>
                  <span className="compendium-badge">{item.edition}</span>
                  <span className="compendium-badge">{item.category}</span>
                </div>
              </div>

              {item.level_or_cr && (
                <div style={{ fontSize: '0.75rem', color: '#d4af37' }}>
                  {item.school_or_type} • {item.level_or_cr}
                </div>
              )}

              <div style={{ fontSize: '0.78rem', color: '#8b92a5' }}>
                {item.summary}
              </div>

              {isExpanded && (
                <div className="compendium-desc" style={{ marginTop: 6, borderTop: '1px solid #282d3d', paddingTop: 6 }}>
                  {item.description}
                </div>
              )}

              <div style={{ display: 'flex', gap: 6, marginTop: 4, alignItems: 'center' }}>
                <button
                  onClick={() => setExpandedId(isExpanded ? null : item.id)}
                  className="hp-btn"
                  style={{ fontSize: '0.7rem' }}
                >
                  <Eye size={10} style={{ display: 'inline', marginRight: 3 }} />
                  {isExpanded ? "Collapse" : "Full Statblock"}
                </button>

                {isMonster && (
                  <button
                    onClick={() => onSpawnMonster(item)}
                    className="hp-btn"
                    style={{ color: '#ff6b6b', borderColor: '#e63946', fontSize: '0.7rem' }}
                  >
                    <Sword size={10} style={{ display: 'inline', marginRight: 3 }} />
                    Fight Monster
                  </button>
                )}

                <span style={{ marginLeft: 'auto', fontSize: '0.65rem', color: '#8b92a5' }}>
                  {item.source}
                </span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
