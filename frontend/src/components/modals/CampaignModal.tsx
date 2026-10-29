import React, { useState } from 'react';
import { Layers, X } from 'lucide-react';
import type { CampaignSummary } from '../../types';
import { LibraryBrowser } from './LibraryBrowser';

interface CampaignModalProps {
  campaignList: CampaignSummary[];
  activeSessionId: string;
  onSwitchCampaign: (id: string) => void;
  onClose: () => void;
  onRefreshCampaigns: () => void;
  busy: boolean;
  error: string | null;
}

export const CampaignModal: React.FC<CampaignModalProps> = ({
  campaignList,
  activeSessionId,
  onSwitchCampaign,
  onClose,
  onRefreshCampaigns,
  busy,
  error
}) => {
  const [view, setView] = useState<'campaigns' | 'library'>('campaigns');
  return (
    <div role="dialog" aria-modal="true" aria-labelledby="campaign-modal-title" style={{
      position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
      background: 'rgba(0,0,0,0.85)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000
    }}>
      <div style={{
        background: 'var(--bg-secondary)', border: '1px solid var(--border)', borderRadius: 8,
        width: 900, maxWidth: '95vw', maxHeight: '90vh', display: 'flex', flexDirection: 'column', overflow: 'hidden'
      }}>
        <div style={{ padding: '16px 20px', borderBottom: '1px solid var(--border)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--gold)', fontWeight: 700, fontSize: '1.1rem' }}>
            <Layers size={18} />
            <span id="campaign-modal-title">CAMPAIGNS & SOURCE LIBRARY</span>
          </div>
          <button onClick={onClose} className="hp-btn" aria-label="Close campaigns"><X size={16} /></button>
        </div>

        <nav aria-label="Campaigns and sources" style={{ display: 'flex', gap: 8, padding: '12px 20px', borderBottom: '1px solid var(--border)' }}>
          <button className="hp-btn" aria-pressed={view === 'campaigns'} onClick={() => setView('campaigns')}>Play campaigns</button>
          <button className="hp-btn" aria-pressed={view === 'library'} onClick={() => setView('library')}>Source folders & rules</button>
        </nav>

        <div style={{ padding: 20, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 14 }}>
          {view === 'library' ? <LibraryBrowser onLibraryUpdated={onRefreshCampaigns} /> : <>
          {error && <p role="alert" style={{ color: '#ff6b6b' }}>{error}</p>}
          {campaignList.length === 0 && <button className="hp-btn" onClick={onRefreshCampaigns}>Reload campaigns</button>}
          {campaignList.map((c) => (
            <div
              key={c.id}
              style={{
                background: 'var(--bg-card)', border: activeSessionId === `session_${c.id}` ? '1px solid var(--gold)' : '1px solid var(--border)',
                borderRadius: 6, padding: 14, display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 14, flexWrap: 'wrap'
              }}
            >
              <div style={{ flex: 1 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                  <span style={{ fontWeight: 700, color: '#fff', fontSize: '1rem' }}>{c.title}</span>
                  <span className="compendium-badge">{c.edition === 'weg_d6' ? 'WEG D6' : c.edition}</span>
                  <span style={{ fontSize: '0.7rem', color: '#2a9d8f' }}>{c.genre}</span>
                </div>
                <p style={{ fontSize: '0.8rem', color: '#a0a6b8', marginTop: 6, lineHeight: 1.4 }}>{c.description}</p>
                <p style={{ fontSize: '0.75rem', color: '#8b92a5', marginTop: 6 }}>{c.source_count || 0} local {c.source_count === 1 ? 'source' : 'sources'} · {(c.source_passages || 0).toLocaleString()} searchable passages</p>
                {c.rules_note && <p style={{ fontSize: '0.75rem', color: '#d4af37', marginTop: 6, lineHeight: 1.4 }}>{c.rules_note}</p>}
              </div>

              <button
                onClick={() => onSwitchCampaign(c.id)}
                disabled={busy}
                className="send-btn"
                style={{ padding: '8px 16px', fontSize: '0.8rem', whiteSpace: 'nowrap' }}
              >
                Play Campaign
              </button>
            </div>
          ))}
          </>}
        </div>
      </div>
    </div>
  );
};
