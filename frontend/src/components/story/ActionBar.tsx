import React from 'react';
import { Sword, Wand2, Sparkles, Mic, MicOff, RefreshCw, Send } from 'lucide-react';
import type { ActionInputMode } from '../../types';

interface ActionBarProps {
  native?: boolean;
  inputMode: ActionInputMode;
  inputText: string;
  advantage: boolean;
  disadvantage: boolean;
  isListening: boolean;
  loading: boolean;
  onSetInputMode: (mode: ActionInputMode) => void;
  onSetInputText: (text: string) => void;
  onToggleAdvantage: () => void;
  onToggleDisadvantage: () => void;
  onToggleSpeech: () => void;
  onSubmitAction: (e: React.FormEvent) => void;
}

export const ActionBar: React.FC<ActionBarProps> = ({
  native = false,
  inputMode,
  inputText,
  advantage,
  disadvantage,
  isListening,
  loading,
  onSetInputMode,
  onSetInputText,
  onToggleAdvantage,
  onToggleDisadvantage,
  onToggleSpeech,
  onSubmitAction
}) => {
  return (
    <div className="action-bar-wrapper">
      <div className="mode-selector">
        <span style={{ fontSize: '0.7rem', color: '#8b92a5', textTransform: 'uppercase', marginRight: 4 }}>Mode:</span>
        <button onClick={() => onSetInputMode("do")} className={`mode-btn ${inputMode === "do" ? "active" : ""}`}>Do</button>
        <button onClick={() => onSetInputMode("say")} className={`mode-btn ${inputMode === "say" ? "active" : ""}`}>Say</button>
        <button onClick={() => onSetInputMode("story")} className={`mode-btn ${inputMode === "story" ? "active" : ""}`}>Story</button>
        <button onClick={() => onSetInputMode("attack")} className={`mode-btn ${inputMode === "attack" ? "active" : ""}`}>
          <Sword size={12} style={{ display: 'inline', marginRight: 3 }} /> Attack
        </button>
        <button onClick={() => onSetInputMode("check")} className={`mode-btn ${inputMode === "check" ? "active" : ""}`}>Check</button>
        {!native && <button onClick={() => onSetInputMode("cast")} className={`mode-btn ${inputMode === "cast" ? "active" : ""}`}>
          <Wand2 size={12} style={{ display: 'inline', marginRight: 3 }} /> Cast
        </button>}
        <button onClick={() => onSetInputMode("see")} className={`mode-btn ${inputMode === "see" ? "active" : ""}`}>
          <Sparkles size={12} style={{ display: 'inline', marginRight: 3 }} /> See
        </button>
        <button onClick={() => onSetInputMode("rest")} className={`mode-btn ${inputMode === "rest" ? "active" : ""}`}>Rest</button>

        {!native && <div style={{ marginLeft: 'auto', display: 'flex', gap: 6 }}>
          <button
            onClick={onToggleAdvantage}
            className={`mode-btn ${advantage ? "active" : ""}`}
            title="Roll with Advantage (2d20 pick highest)"
          >
            ADV
          </button>
          <button
            onClick={onToggleDisadvantage}
            className={`mode-btn ${disadvantage ? "active" : ""}`}
            title="Roll with Disadvantage (2d20 pick lowest)"
          >
            DIS
          </button>
        </div>}
      </div>

      <form onSubmit={onSubmitAction} className="input-row">
        {/* Voice Input STT Microphone */}
        <button
          type="button"
          onClick={onToggleSpeech}
          className="hp-btn"
          style={{
            padding: '10px 12px',
            background: isListening ? 'rgba(230, 57, 70, 0.2)' : 'var(--bg-card)',
            borderColor: isListening ? '#e63946' : 'var(--border)',
            color: isListening ? '#ff6b6b' : 'var(--text-muted)'
          }}
          title={isListening ? "Listening... click to stop" : "Speak your action (Voice Input)"}
        >
          {isListening ? <MicOff size={16} /> : <Mic size={16} />}
        </button>

        <input
          type="text"
          value={inputText}
          onChange={(e) => onSetInputText(e.target.value)}
          placeholder={
            isListening ? "Listening to your voice..." :
            inputMode === 'do' ? "What do you want to do? (e.g. advance quietly into the fog)" :
            inputMode === 'say' ? "What do you say? (e.g. Who commands this castle?)" :
            inputMode === 'attack' ? "Who or what are you attacking? (e.g. vampire bat with shortsword)" :
            inputMode === 'check' ? "What are you examining? (e.g. investigate the runic altar)" :
            inputMode === 'cast' ? "Enter spell to cast (e.g. Fireball, Cure Wounds, Magic Missile)..." :
            inputMode === 'see' ? "Describe the scene, vista, or creature to illustrate..." :
            inputMode === 'rest' ? "Short rest or long rest?" : "Add narrative details..."
          }
          className="action-input"
          disabled={loading}
        />
        <button type="submit" disabled={loading} className="send-btn">
          {loading ? <RefreshCw className="animate-spin" size={16} /> : <Send size={16} />}
          <span>Take Action</span>
        </button>
      </form>
    </div>
  );
};
