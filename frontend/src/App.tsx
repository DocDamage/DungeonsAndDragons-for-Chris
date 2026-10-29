import React, { useState, useEffect, useRef, useCallback } from 'react';
import confetti from 'canvas-confetti';
import type {
  GameSession,
  Character,
  CampaignSummary,
  CombatEnemy,
  D6Options,
  SaveSlot,
  CompendiumEntry,
  RollResult,
  ActionInputMode,
  ActionTurn
} from './types';
import { api } from './services/api';
import { toggleAmbiance } from './audio';
import { Header } from './components/Header';
import { CharacterSidebar } from './components/sidebar/CharacterSidebar';
import { StoryPanel } from './components/story/StoryPanel';
import { RightSidebar } from './components/tabs/RightSidebar';
import { CampaignModal } from './components/modals/CampaignModal';
import { SaveSlotsModal } from './components/modals/SaveSlotsModal';
import { CharacterModal } from './components/modals/CharacterModal';
import { RecruitCompanionModal } from './components/modals/RecruitCompanionModal';
import { ImageLightboxModal } from './components/modals/ImageLightboxModal';

export default function App() {
  const [session, setSession] = useState<GameSession | null>(null);
  const [initializationError, setInitializationError] = useState<string | null>(null);
  const [connectionAttempt, setConnectionAttempt] = useState(0);
  const [loading, setLoading] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [inputText, setInputText] = useState("");
  const [inputMode, setInputMode] = useState<ActionInputMode>("do");
  const [advantage, setAdvantage] = useState(false);
  const [disadvantage, setDisadvantage] = useState(false);

  // Turn alteration & Speech
  const [editingTurnId, setEditingTurnId] = useState<string | null>(null);
  const [editTurnText, setEditTurnText] = useState("");
  const [illustratingTurnId, setIllustratingTurnId] = useState<string | null>(null);
  const [viewingImageUrl, setViewingImageUrl] = useState<string | null>(null);
  const [ambianceOn, setAmbianceOn] = useState(false);
  const [isListening, setIsListening] = useState(false);

  // Combat State
  const [targetSelection, setTargetSelection] = useState<{ encounterId: string; targetId: string } | null>(null);
  const encounter = session?.encounter;
  const availableTargets = encounter?.active
    ? encounter.combatants.filter(combatant => !combatant.is_player && !combatant.is_defeated && (session?.edition === 'weg_d6' || combatant.current_hp > 0))
    : [];
  const selectedTargetId = (
    encounter?.id === targetSelection?.encounterId
      ? availableTargets.find(target => target.id === targetSelection?.targetId)
      : undefined
  )?.id ?? availableTargets[0]?.id ?? null;

  // Compendium & Dice State
  const [compResults, setCompResults] = useState<CompendiumEntry[]>([]);
  const [diceHistory, setDiceHistory] = useState<RollResult[]>([]);
  const [diceError, setDiceError] = useState<string | null>(null);

  // Modals & Lists
  const [showCampaignModal, setShowCampaignModal] = useState(false);
  const [showSavesModal, setShowSavesModal] = useState(false);
  const [showCharModal, setShowCharModal] = useState(false);
  const [showAddCompanionModal, setShowAddCompanionModal] = useState(false);
  const [campaignList, setCampaignList] = useState<CampaignSummary[]>([]);
  const [campaignError, setCampaignError] = useState<string | null>(null);
  const [saveSlots, setSaveSlots] = useState<SaveSlot[]>([]);

  const storyEndRef = useRef<HTMLDivElement>(null);

  const refreshCampaigns = useCallback(async () => {
    try {
      setCampaignList(await api.getCampaigns());
      setCampaignError(null);
    } catch (err) {
      setCampaignError(err instanceof Error ? err.message : 'Unable to load campaigns');
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();

    async function initializeSession() {
      try {
        const data = await api.getSession(controller.signal);
        if (!controller.signal.aborted) setSession(data);
      } catch (err) {
        if (!controller.signal.aborted) {
          setInitializationError(err instanceof Error ? err.message : "Failed to connect to DungeonForge");
        }
      }
    }

    async function initializeCampaigns() {
      try {
        const campaigns = await api.getCampaigns(controller.signal);
        if (!controller.signal.aborted) setCampaignList(campaigns);
      } catch (err) {
        if (!controller.signal.aborted) console.error("Failed to load campaigns:", err);
      }
    }

    void initializeSession();
    void initializeCampaigns();
    return () => controller.abort();
  }, [connectionAttempt]);

  useEffect(() => {
    storyEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [session?.history]);

  const handleSelectTarget = (targetId: string) => {
    if (encounter && availableTargets.some(target => target.id === targetId)) {
      setTargetSelection({ encounterId: encounter.id, targetId });
    }
  };

  const fetchSaveSlots = async () => {
    try {
      const saves = await api.getSaveSlots();
      setSaveSlots(saves);
    } catch (err) {
      console.error("Failed to fetch saves:", err);
    }
  };

  const handleSendAction = async (e?: React.FormEvent, directText?: string, directMode?: ActionInputMode) => {
    if (e) e.preventDefault();
    const actionText = directText || inputText;
    const modeToSend = directMode || inputMode;
    if (!actionText.trim() || loading) return;

    setLoading(true);
    setActionError(null);
    try {
      const data = await api.sendAction({
        mode: modeToSend,
        text: actionText.trim(),
        advantage: session?.edition === 'weg_d6' ? false : advantage,
        disadvantage: session?.edition === 'weg_d6' ? false : disadvantage
      });
      setSession(data.session);
      if (!directText) setInputText("");
      if (data.turn?.rule_result?.is_crit) {
        confetti({ particleCount: 100, spread: 70, origin: { y: 0.6 } });
      }
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Action failed');
    } finally {
      setLoading(false);
    }
  };

  const handleTravelToRoom = (roomName: string) => {
    handleSendAction(undefined, `Travel carefully into the ${roomName}`, "do");
  };

  const handleUndo = async () => {
    try {
      const data = await api.undoTurn();
      setSession(data.session);
    } catch (err) {
      console.error("Undo error:", err);
    }
  };

  const handleRedo = async () => {
    try {
      const data = await api.redoTurn();
      setSession(data.session);
    } catch (err) {
      console.error("Redo error:", err);
    }
  };

  const handleAlterTurn = async (turnId: string) => {
    try {
      const data = await api.alterTurn(turnId, editTurnText);
      setSession(data.session);
      setEditingTurnId(null);
    } catch (err) {
      console.error("Alter turn error:", err);
    }
  };

  const handleQuickHp = async (delta: number) => {
    if (!session) return;
    const char = { ...session.character };
    char.current_hp = Math.max(0, Math.min(char.max_hp, char.current_hp + delta));
    try {
      await api.updateCharacter(char);
      setSession(await api.getSession());
    } catch (err) {
      console.error("HP update error:", err);
    }
  };

  const handleUseItem = async (itemName: string) => {
    try {
      const data = await api.useItem(itemName);
      setSession(data.session);
    } catch (err) {
      console.error("Use item error:", err);
    }
  };

  const handleSwitchEdition = async (edition: string) => {
    try {
      const updated = await api.setEdition(edition);
      setSession(updated);
    } catch (err) {
      console.error("Edition switch error:", err);
    }
  };

  const handleSwitchCampaign = async (cid: string) => {
    setLoading(true);
    setCampaignError(null);
    try {
      const data = await api.switchCampaign(cid);
      setSession(data.session);
      setShowCampaignModal(false);
      setAdvantage(false);
      setDisadvantage(false);
      setInputMode('do');
      setInputText('');
      setActionError(null);
    } catch (err) {
      setCampaignError(err instanceof Error ? err.message : 'Unable to switch campaigns');
    } finally {
      setLoading(false);
    }
  };

  const handleRollDice = async (expr: string) => {
    setDiceError(null);
    try {
      const roll = session?.edition === 'weg_d6' ? await api.nativePool(expr) : await api.rollDice(expr);
      if (session?.edition === 'weg_d6') setSession(previous => previous?.edition === 'weg_d6' ? {
        ...previous, native_boost: null,
        vehicle_encounter: previous.vehicle_encounter ? { ...previous.vehicle_encounter, boost: null } : null,
      } : previous);
      setDiceHistory(history => [roll, ...history.slice(0, 9)]);
      if (roll.is_crit) {
        confetti({ particleCount: 80, spread: 60 });
      }
    } catch (err) {
      setDiceError(err instanceof Error ? err.message : "Failed to roll dice");
    }
  };

  // Combat Handlers
  const handleStartCombat = async (enemies?: CombatEnemy[]) => {
    setActionError(null);
    try {
      const data = await api.startCombat(enemies || []);
      setSession(data.session);
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Failed to start encounter');
    }
  };

  const handleCombatAttack = async (options?: D6Options) => {
    if (!selectedTargetId) return;
    setActionError(null);
    try {
      const data = await api.combatAttack({
        target_id: selectedTargetId,
        advantage: session?.edition === 'weg_d6' ? false : advantage,
        disadvantage: session?.edition === 'weg_d6' ? false : disadvantage,
        d6_options: options,
      });
      setSession(data.session);
      if (data.eval_result?.is_crit) {
        confetti({ particleCount: 100, spread: 70 });
      }
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Attack failed');
    }
  };

  const handleEnemyAttack = async (actorId: string, options: D6Options) => {
    if (!session) return;
    setActionError(null);
    try {
      const data = await api.combatAttack({ attacker_id: actorId, target_id: session.character.id, d6_options: options });
      setSession(data.session);
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Enemy attack failed');
    }
  };

  const handleCombatNextTurn = async () => {
    setActionError(null);
    try {
      const data = await api.combatNextTurn();
      setSession(data.session);
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Unable to advance turn');
    }
  };

  const handleCombatEnd = async () => {
    try {
      const data = await api.combatEnd();
      setSession(data.session);
    } catch (err) {
      console.error("Combat end error:", err);
    }
  };

  // Compendium Handlers
  const handleSearchCompendium = async (q: string = "", cat: string = "all", ed: string = "all") => {
    try {
      const results = await api.searchCompendium(q, cat, ed);
      setCompResults(results);
    } catch (err) {
      console.error("Compendium search error:", err);
    }
  };

  const handleSpawnMonster = (m: CompendiumEntry) => {
    if (session?.edition === 'weg_d6') {
      setActionError('This compendium entry uses a D&D HP/AC stat block. Start an Imperial Patrol for native D6 enemies.');
      return;
    }
    let hp = 30;
    let ac = 13;
    const hpMatch = m.description.match(/HP:\s*(\d+)/i);
    const acMatch = m.description.match(/AC:\s*(\d+)/i);
    if (hpMatch) hp = parseInt(hpMatch[1], 10);
    if (acMatch) ac = parseInt(acMatch[1], 10);

    handleStartCombat([{
      name: m.name,
      hp,
      ac,
      dex_mod: 2,
      image_url: m.name.toLowerCase().includes("strahd") ? "/static/images/strahd/Burebis_hi-res.jpg" : undefined
    }]);
  };

  // Sound & Speech
  const handleToggleAmbianceSound = () => {
    const active = toggleAmbiance();
    setAmbianceOn(active);
  };

  const handleToggleSpeech = () => {
    const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!SpeechRecognition) {
      alert("Speech recognition is not supported in this browser.");
      return;
    }

    if (isListening) {
      setIsListening(false);
      return;
    }

    try {
      const recognition = new SpeechRecognition();
      recognition.continuous = false;
      recognition.interimResults = false;
      recognition.lang = 'en-US';

      recognition.onstart = () => setIsListening(true);
      recognition.onresult = (event: any) => {
        const transcript = event.results[0][0].transcript;
        setInputText(prev => prev ? `${prev} ${transcript}` : transcript);
      };
      recognition.onerror = () => setIsListening(false);
      recognition.onend = () => setIsListening(false);
      recognition.start();
    } catch (err) {
      console.error("Speech recognition error:", err);
      setIsListening(false);
    }
  };

  const handleSpeakTurn = (text: string) => {
    if (!('speechSynthesis' in window)) return;
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.rate = 0.95;
    utterance.pitch = 0.95;
    window.speechSynthesis.speak(utterance);
  };

  // Saves & Chronicle
  const handleSaveSession = async (slotName?: string) => {
    try {
      const data = await api.saveSession(slotName);
      setSession(data.session);
      alert("Adventure saved successfully!");
      fetchSaveSlots();
    } catch (err) {
      console.error("Save error:", err);
    }
  };

  const handleLoadSession = async (slotId: string) => {
    try {
      const data = await api.loadSession(slotId);
      setSession(data.session);
      setShowSavesModal(false);
    } catch (err) {
      console.error("Load save error:", err);
    }
  };

  const handleDeleteSave = async (slotId: string) => {
    if (!confirm("Are you sure you want to delete this save slot?")) return;
    try {
      await api.deleteSave(slotId);
      fetchSaveSlots();
    } catch (err) {
      console.error("Delete save error:", err);
    }
  };

  const handleDownloadChronicle = async () => {
    try {
      const text = await api.exportMarkdownChronicle();
      const blob = new Blob([text], { type: "text/markdown;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${session?.title.toLowerCase().replace(/\s+/g, '_') || 'adventure'}_chronicle.md`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (err) {
      console.error("Export chronicle error:", err);
    }
  };

  // Character Customizer
  const handleRollStats = async () => {
    const data = await api.rollCharacterStats();
    confetti({ particleCount: 90, spread: 60 });
    return data;
  };

  const handleSaveChar = async (updatedChar: Character) => {
    await api.updateCharacter(updatedChar);
    setSession(await api.getSession());
    setShowCharModal(false);
  };

  // Scene Illustration
  const handleIllustrateTurn = async (turnId?: string, text?: string) => {
    setIllustratingTurnId(turnId || "custom");
    try {
      const data = await api.illustrateScene({
        turn_id: turnId,
        prompt: text || (turnId ? undefined : inputText)
      });
      setSession(data.session);
    } catch (err) {
      console.error("Illustration error:", err);
    } finally {
      setIllustratingTurnId(null);
    }
  };

  // Magic & Spells
  const handleCastSpell = async (spellName: string, slotLevel: number = 1, targetId?: string) => {
    setLoading(true);
    try {
      const data = await api.castSpell({
        spell_name: spellName,
        slot_level: slotLevel,
        target_id: targetId || (session?.encounter?.active ? selectedTargetId || undefined : undefined)
      });
      setSession(data.session);
      confetti({ particleCount: 70, spread: 60, colors: ['#a8dadc', '#457b9d', '#d4af37'] });
    } catch (err: any) {
      console.error("Cast spell error:", err);
      alert(err.message || "Failed to cast spell");
    } finally {
      setLoading(false);
    }
  };

  const handleRestoreSpellSlots = async (level?: number) => {
    try {
      const data = await api.restoreSpellSlots(level);
      setSession(data.session);
    } catch (err) {
      console.error("Restore slots error:", err);
    }
  };

  const handleLearnSpell = async (spellName: string) => {
    try {
      const data = await api.learnSpell(spellName);
      setSession(data.session);
    } catch (err) {
      console.error("Learn spell error:", err);
    }
  };

  const handleUnlearnSpell = async (spellName: string) => {
    try {
      const data = await api.unlearnSpell(spellName);
      setSession(data.session);
    } catch (err) {
      console.error("Unlearn spell error:", err);
    }
  };

  // Companions
  const handleCompanionAttack = async (companionId: string) => {
    if (!selectedTargetId) {
      alert("Please select an enemy target first!");
      return;
    }
    try {
      const data = await api.companionAttack({
        companion_id: companionId,
        target_id: selectedTargetId,
        advantage: session?.edition === 'weg_d6' ? false : advantage,
        disadvantage: session?.edition === 'weg_d6' ? false : disadvantage
      });
      setSession(data.session);
      if (data.eval_result?.is_crit) {
        confetti({ particleCount: 100, spread: 70 });
      }
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Companion attack failed');
    }
  };

  const handleAdjustCompanionHp = async (companionId: string, delta: number) => {
    try {
      const data = await api.adjustCompanionHp(companionId, delta);
      setSession(data.session);
    } catch (err) {
      console.error("Companion HP update error:", err);
    }
  };

  const handleAddCompanion = async (compData: any) => {
    try {
      const data = await api.addCompanion(compData);
      setSession(data.session);
      setShowAddCompanionModal(false);
    } catch (err) {
      console.error("Add companion error:", err);
    }
  };

  const handleDeleteCompanion = async (companionId: string) => {
    try {
      const data = await api.deleteCompanion(companionId);
      setSession(data.session);
    } catch (err) {
      console.error("Delete companion error:", err);
    }
  };

  // LLM Config
  const handleSaveLLMConfig = async (payload: { provider: string; api_key?: string; base_url?: string; model?: string }) => {
    try {
      await api.configLLM(payload);
      alert("LLM settings updated successfully!");
    } catch (err) {
      console.error("LLM config error:", err);
    }
  };

  if (!session) {
    return (
      <div style={{ minHeight: '100vh', padding: 24, display: 'flex', flexDirection: 'column', gap: 16, alignItems: 'center', justifyContent: 'center', background: '#0a0b0e', color: '#d4af37', textAlign: 'center' }}>
        {initializationError ? (
          <>
            <h1 style={{ fontSize: '1.25rem', margin: 0 }}>Unable to connect to DungeonForge</h1>
            <p role="alert" style={{ color: '#e2e4ec', margin: 0 }}>{initializationError}</p>
            <p style={{ color: '#8b92a5', margin: 0 }}>Make sure the DungeonForge server is running, then try again.</p>
            <button className="send-btn" onClick={() => {
              setInitializationError(null);
              setConnectionAttempt(attempt => attempt + 1);
            }}>Retry connection</button>
          </>
        ) : <p role="status">Loading DungeonForge tabletop engine...</p>}
      </div>
    );
  }

  return (
    <>
      <Header
        hasNativeSheet={Boolean(session.character.d6)}
        edition={session.edition}
        ambianceOn={ambianceOn}
        onToggleAmbiance={handleToggleAmbianceSound}
        onOpenCampaignModal={() => { setShowCampaignModal(true); void refreshCampaigns(); }}
        onOpenSavesModal={() => {
          fetchSaveSlots();
          setShowSavesModal(true);
        }}
        onDownloadChronicle={handleDownloadChronicle}
        onSwitchEdition={handleSwitchEdition}
      />

      <div className="app-container">
        {/* Left Panel: Character Sheet, Spells & Party */}
        <CharacterSidebar
          vehicleCombatActive={Boolean(session.vehicle_encounter)}
          nativeBoost={session.native_boost}
          encounter={session.encounter}
          onSessionChanged={setSession}
          character={session.character}
          edition={session.edition}
          isCombatActive={Boolean(session.encounter?.active)}
          selectedTargetId={selectedTargetId}
          onOpenCharModal={() => setShowCharModal(true)}
          onQuickHp={handleQuickHp}
          onUseItem={handleUseItem}
          onCastSpell={handleCastSpell}
          onRestoreSlots={handleRestoreSpellSlots}
          onLearnSpell={handleLearnSpell}
          onUnlearnSpell={handleUnlearnSpell}
          onOpenRecruitModal={() => setShowAddCompanionModal(true)}
          onDeleteCompanion={handleDeleteCompanion}
          onAdjustCompanionHp={handleAdjustCompanionHp}
          onCompanionAttack={handleCompanionAttack}
        />

        {/* Center Panel: Tactical Encounter Banner, Story Stream, Omni Action Bar */}
        <StoryPanel
          session={session}
          onSessionChanged={setSession}
          inputMode={inputMode}
          inputText={inputText}
          advantage={advantage}
          disadvantage={disadvantage}
          isListening={isListening}
          loading={loading}
          editingTurnId={editingTurnId}
          editTurnText={editTurnText}
          illustratingTurnId={illustratingTurnId}
          selectedTargetId={selectedTargetId}
          storyEndRef={storyEndRef}
          onStartCombat={() => handleStartCombat()}
          onEndCombat={handleCombatEnd}
          onUndo={handleUndo}
          onRedo={handleRedo}
          onSelectTarget={handleSelectTarget}
          onAttackTarget={handleCombatAttack}
          onEnemyAttack={handleEnemyAttack}
          actionError={actionError}
          onCompanionAttack={handleCompanionAttack}
          onCastCombatSpell={(spellName) => handleCastSpell(spellName, 1, selectedTargetId || undefined)}
          onNextTurn={handleCombatNextTurn}
          onEditChange={setEditTurnText}
          onSaveAlteration={handleAlterTurn}
          onCancelAlteration={() => setEditingTurnId(null)}
          onStartEditing={(turn: ActionTurn) => {
            setEditingTurnId(turn.id);
            setEditTurnText(turn.dm_output);
          }}
          onSpeakTurn={handleSpeakTurn}
          onIllustrateTurn={handleIllustrateTurn}
          onViewImage={setViewingImageUrl}
          onSetInputMode={setInputMode}
          onSetInputText={setInputText}
          onToggleAdvantage={() => { setAdvantage(!advantage); setDisadvantage(false); }}
          onToggleDisadvantage={() => { setDisadvantage(!disadvantage); setAdvantage(false); }}
          onToggleSpeech={handleToggleSpeech}
          onSubmitAction={handleSendAction}
        />

        {/* Right Panel: Story Cards, Quests, Map, Compendium & Dice */}
        <RightSidebar
          edition={session.edition}
          cards={session.story_cards}
          activeQuests={session.active_quests}
          compendiumResults={compResults}
          diceHistory={diceHistory}
          diceError={diceError}
          onTravelToRoom={handleTravelToRoom}
          onSearchCompendium={handleSearchCompendium}
          onSpawnMonster={handleSpawnMonster}
          onRollDice={handleRollDice}
          onSaveLLMConfig={handleSaveLLMConfig}
        />
      </div>

      {/* Modals */}
      {showCampaignModal && (
        <CampaignModal
          campaignList={campaignList}
          activeSessionId={session.id}
          onSwitchCampaign={handleSwitchCampaign}
          onRefreshCampaigns={refreshCampaigns}
          busy={loading}
          error={campaignError}
          onClose={() => setShowCampaignModal(false)}
        />
      )}

      {showSavesModal && (
        <SaveSlotsModal
          saveSlots={saveSlots}
          onSaveSession={handleSaveSession}
          onLoadSession={handleLoadSession}
          onDeleteSave={handleDeleteSave}
          onClose={() => setShowSavesModal(false)}
        />
      )}

      {showCharModal && (
        <CharacterModal
          initialCharacter={session.character}
          onSaveCharacter={handleSaveChar}
          onRollStats={handleRollStats}
          onClose={() => setShowCharModal(false)}
        />
      )}

      {showAddCompanionModal && (
        <RecruitCompanionModal
          onAddCompanion={handleAddCompanion}
          onClose={() => setShowAddCompanionModal(false)}
        />
      )}

      {viewingImageUrl && (
        <ImageLightboxModal
          imageUrl={viewingImageUrl}
          onClose={() => setViewingImageUrl(null)}
        />
      )}
    </>
  );
}
