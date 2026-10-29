import React from 'react';

interface QuestsTabProps {
  activeQuests: Record<string, string[]>;
}

export const QuestsTab: React.FC<QuestsTabProps> = ({ activeQuests }) => {
  return (
    <div style={{ padding: 14, display: 'flex', flexDirection: 'column', gap: 14 }}>
      {Object.keys(activeQuests).length === 0 ? (
        <div style={{ color: '#8b92a5', fontSize: '0.85rem', textAlign: 'center', marginTop: 20 }}>
          No active quests found. Select a campaign from the Campaigns menu above.
        </div>
      ) : (
        Object.entries(activeQuests).map(([act, arcs]) => (
          <div key={act} style={{ background: '#181b24', border: '1px solid #282d3d', borderRadius: 6, padding: 10 }}>
            <div style={{ fontWeight: 700, color: '#d4af37', fontSize: '0.85rem', marginBottom: 6 }}>
              {act}
            </div>
            <ul style={{ listStyle: 'none', paddingLeft: 0, fontSize: '0.8rem', display: 'flex', flexDirection: 'column', gap: 4 }}>
              {arcs.map((arc, idx) => (
                <li key={idx} style={{ color: '#e2e4ec', display: 'flex', alignItems: 'center', gap: 6 }}>
                  <span style={{ color: '#2a9d8f' }}>✦</span> {arc}
                </li>
              ))}
            </ul>
          </div>
        ))
      )}
    </div>
  );
};
