import React from 'react';
import { Dices, Volume2, VolumeX, Layers, Save, Download } from 'lucide-react';

interface HeaderProps {
  edition: string;
  ambianceOn: boolean;
  onToggleAmbiance: () => void;
  onOpenCampaignModal: () => void;
  onOpenSavesModal: () => void;
  onDownloadChronicle: () => void;
  onSwitchEdition: (edition: string) => void;
  hasNativeSheet?: boolean;
}

export const Header: React.FC<HeaderProps> = ({
  edition,
  ambianceOn,
  onToggleAmbiance,
  onOpenCampaignModal,
  onOpenSavesModal,
  onDownloadChronicle,
  onSwitchEdition,
  hasNativeSheet = false
}) => {
  return (
    <header className="top-nav">
      <div className="brand">
        <Dices className="brand-icon" size={24} />
        <span>DUNGEONFORGE</span>
        <span className="edition-badge">{edition === 'weg_d6' ? 'WEG D6' : edition.toUpperCase()}</span>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        {/* Ambiance Audio Toggle */}
        <button
          onClick={onToggleAmbiance}
          style={{
            background: ambianceOn ? 'rgba(42, 157, 143, 0.2)' : 'var(--bg-card)',
            border: `1px solid ${ambianceOn ? '#2a9d8f' : 'var(--border)'}`,
            color: ambianceOn ? '#2a9d8f' : 'var(--text-muted)',
            padding: '4px 8px',
            borderRadius: 4,
            fontSize: '0.75rem',
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            gap: 5
          }}
          title="Toggle procedural gothic rain & wind ambiance"
        >
          {ambianceOn ? <Volume2 size={14} /> : <VolumeX size={14} />}
          <span>Rain: {ambianceOn ? "ON" : "OFF"}</span>
        </button>

        {/* Campaign Selector Modal Button */}
        <button
          onClick={onOpenCampaignModal}
          style={{
            background: 'rgba(212, 175, 55, 0.12)',
            border: '1px solid #d4af37',
            color: '#d4af37',
            padding: '4px 10px',
            borderRadius: 4,
            fontSize: '0.75rem',
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            gap: 5
          }}
        >
          <Layers size={14} />
          <span>Campaigns</span>
        </button>

        {/* Saves & Chronicle Modal Button */}
        <button
          onClick={onOpenSavesModal}
          style={{
            background: 'var(--bg-card)',
            border: '1px solid var(--border)',
            color: 'var(--text-main)',
            padding: '4px 10px',
            borderRadius: 4,
            fontSize: '0.75rem',
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            gap: 5
          }}
        >
          <Save size={14} />
          <span>Saves</span>
        </button>

        {/* Download Chronicle Markdown */}
        <button
          onClick={onDownloadChronicle}
          style={{
            background: 'var(--bg-card)',
            border: '1px solid var(--border)',
            color: 'var(--text-main)',
            padding: '4px 8px',
            borderRadius: 4,
            fontSize: '0.75rem',
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            gap: 5
          }}
          title="Download formatted adventure chronicle (.md)"
        >
          <Download size={14} />
          <span>Export Book</span>
        </button>

        {/* Edition Badges */}
        <div style={{ display: 'flex', gap: 4, marginLeft: 6 }}>
          {['2e', '3.5e', '5e', 'weg_d6'].map((ed) => (
            <button
              key={ed}
              onClick={() => onSwitchEdition(ed)}
              disabled={edition === 'weg_d6' ? ed !== 'weg_d6' : ed === 'weg_d6' && !hasNativeSheet}
              title={ed === 'weg_d6' && !hasNativeSheet ? 'Choose the Star Wars campaign for a native D6 sheet' : edition === 'weg_d6' && ed !== 'weg_d6' ? 'Choose a D&D campaign to change character systems' : undefined}
              className={`mode-btn ${edition === ed ? 'active' : ''}`}
            >
              {ed === 'weg_d6' ? 'D6' : ed.toUpperCase()}
            </button>
          ))}
        </div>
      </div>
    </header>
  );
};
