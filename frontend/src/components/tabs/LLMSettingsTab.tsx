import React, { useState } from 'react';

interface LLMSettingsTabProps {
  onSaveConfig: (payload: { provider: string; api_key?: string; base_url?: string; model?: string }) => void;
}

export const LLMSettingsTab: React.FC<LLMSettingsTabProps> = ({ onSaveConfig }) => {
  const [provider, setProvider] = useState("mock");
  const [apiKey, setApiKey] = useState("");
  const [modelName, setModelName] = useState("llama3");
  const [baseUrl, setBaseUrl] = useState("");

  const handleSave = () => {
    onSaveConfig({
      provider,
      api_key: apiKey || undefined,
      base_url: baseUrl || undefined,
      model: modelName || undefined
    });
  };

  return (
    <div style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div style={{ fontSize: '0.9rem', fontWeight: 700, color: '#d4af37' }}>
        AI Model Provider
      </div>

      <div>
        <label style={{ fontSize: '0.75rem', color: '#8b92a5' }}>Provider</label>
        <select
          value={provider}
          onChange={(e) => setProvider(e.target.value)}
          style={{
            width: '100%',
            background: '#181b24',
            border: '1px solid #282d3d',
            color: '#fff',
            padding: 8,
            borderRadius: 4,
            marginTop: 4
          }}
        >
          <option value="mock">Offline Mock Engine (Instant / Zero-Cost)</option>
          <option value="ollama">Ollama (Local Llama 3 / Mistral)</option>
          <option value="gemini">Google Gemini API</option>
          <option value="openai">OpenAI / OpenRouter API</option>
        </select>
      </div>

      {provider !== 'mock' && (
        <>
          <div>
            <label style={{ fontSize: '0.75rem', color: '#8b92a5' }}>API Key</label>
            <input
              type="password"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder="sk-..."
              className="action-input"
              style={{ width: '100%', marginTop: 4, padding: 8 }}
            />
          </div>

          <div>
            <label style={{ fontSize: '0.75rem', color: '#8b92a5' }}>Model Name</label>
            <input
              type="text"
              value={modelName}
              onChange={(e) => setModelName(e.target.value)}
              placeholder="llama3, gpt-4o, gemini-1.5-pro"
              className="action-input"
              style={{ width: '100%', marginTop: 4, padding: 8 }}
            />
          </div>

          {provider === 'ollama' && (
            <div>
              <label style={{ fontSize: '0.75rem', color: '#8b92a5' }}>Base URL</label>
              <input
                type="text"
                value={baseUrl}
                onChange={(e) => setBaseUrl(e.target.value)}
                placeholder="http://localhost:11434/v1"
                className="action-input"
                style={{ width: '100%', marginTop: 4, padding: 8 }}
              />
            </div>
          )}
        </>
      )}

      <button onClick={handleSave} className="send-btn" style={{ marginTop: 8 }}>
        Save Configuration
      </button>
    </div>
  );
};
