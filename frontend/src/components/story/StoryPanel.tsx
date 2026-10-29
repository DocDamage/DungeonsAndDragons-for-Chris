import React, { type RefObject } from 'react';
import { Skull, RotateCcw, RotateCw } from 'lucide-react';
import type { GameSession, ActionInputMode, ActionTurn, D6Options } from '../../types';
import { TacticalCombatBanner } from './TacticalCombatBanner';
import { NarrativeStream } from './NarrativeStream';
import { ActionBar } from './ActionBar';
import { D6VehiclePanel } from './D6VehiclePanel';
import { D6ForcePanel } from './D6ForcePanel';
import { D6AdvancementPanel } from './D6AdvancementPanel';
import { D6DarkSidePanel } from './D6DarkSidePanel';
import { D6CreationPanel } from './D6CreationPanel';
import { D6SpeciesPanel } from './D6SpeciesPanel';
import { D6DroidPanel } from './D6DroidPanel';

const D6NavigationPanel = React.lazy(() => import('./D6NavigationPanel').then(module => ({ default: module.D6NavigationPanel })));
const D6EngineeringPanel = React.lazy(() => import('./D6EngineeringPanel').then(module => ({ default: module.D6EngineeringPanel })));
const D6TaskPanel = React.lazy(() => import('./D6TaskPanel').then(module => ({ default: module.D6TaskPanel })));
const D6HazardsPanel = React.lazy(() => import('./D6HazardsPanel').then(module => ({ default: module.D6HazardsPanel })));
const D6TemplatePanel = React.lazy(() => import('./D6TemplatePanel').then(module => ({ default: module.D6TemplatePanel })));
const D6EquipmentPanel = React.lazy(() => import('./D6EquipmentPanel').then(module => ({ default: module.D6EquipmentPanel })));
const D6MedicalPanel = React.lazy(() => import('./D6MedicalPanel').then(module => ({ default: module.D6MedicalPanel })));
const D6ExplosivesPanel = React.lazy(() => import('./D6ExplosivesPanel').then(module => ({ default: module.D6ExplosivesPanel })));
const D6GearEffectsPanel = React.lazy(() => import('./D6GearEffectsPanel').then(module => ({ default: module.D6GearEffectsPanel })));
const StrahdProgressPanel = React.lazy(() => import('./StrahdProgressPanel').then(module => ({ default: module.StrahdProgressPanel })));

interface StoryPanelProps {
  session: GameSession;
  onSessionChanged: (session: GameSession) => void;
  inputMode: ActionInputMode;
  inputText: string;
  advantage: boolean;
  disadvantage: boolean;
  isListening: boolean;
  loading: boolean;
  editingTurnId: string | null;
  editTurnText: string;
  illustratingTurnId: string | null;
  selectedTargetId: string | null;
  storyEndRef: RefObject<HTMLDivElement | null>;
  onStartCombat: () => void;
  onEndCombat: () => void;
  onUndo: () => void;
  onRedo: () => void;
  onSelectTarget: (id: string) => void;
  onAttackTarget: (options?: D6Options) => void;
  onEnemyAttack: (actorId: string, options: D6Options) => void;
  actionError: string | null;
  onCompanionAttack: (companionId: string) => void;
  onCastCombatSpell: (spellName: string) => void;
  onNextTurn: () => void;
  onEditChange: (text: string) => void;
  onSaveAlteration: (turnId: string) => void;
  onCancelAlteration: () => void;
  onStartEditing: (turn: ActionTurn) => void;
  onSpeakTurn: (text: string) => void;
  onIllustrateTurn: (turnId: string, text: string) => void;
  onViewImage: (url: string) => void;
  onSetInputMode: (mode: ActionInputMode) => void;
  onSetInputText: (text: string) => void;
  onToggleAdvantage: () => void;
  onToggleDisadvantage: () => void;
  onToggleSpeech: () => void;
  onSubmitAction: (e: React.FormEvent) => void;
}

export const StoryPanel: React.FC<StoryPanelProps> = ({
  session,
  onSessionChanged,
  inputMode,
  inputText,
  advantage,
  disadvantage,
  isListening,
  loading,
  editingTurnId,
  editTurnText,
  illustratingTurnId,
  selectedTargetId,
  storyEndRef,
  onStartCombat,
  onEndCombat,
  onUndo,
  onRedo,
  onSelectTarget,
  onAttackTarget,
  onEnemyAttack,
  actionError,
  onCompanionAttack,
  onCastCombatSpell,
  onNextTurn,
  onEditChange,
  onSaveAlteration,
  onCancelAlteration,
  onStartEditing,
  onSpeakTurn,
  onIllustrateTurn,
  onViewImage,
  onSetInputMode,
  onSetInputText,
  onToggleAdvantage,
  onToggleDisadvantage,
  onToggleSpeech,
  onSubmitAction
}) => {
  const isCombatActive = Boolean(session.encounter && session.encounter.active);

  return (
    <main className="panel-center">
      {/* Subheader: Campaign info & Controls */}
      <div style={{ padding: '8px 20px', borderBottom: '1px solid #282d3d', display: 'flex', flexShrink: 0, justifyContent: 'space-between', alignItems: 'center' }}>
        <div style={{ fontSize: '0.85rem', color: '#d4af37', fontWeight: 600 }}>
          {session.campaign_name}{session.title !== session.campaign_name && ` • ${session.title}`}
        </div>
        <div style={{ display: 'flex', gap: 6 }}>
          {!isCombatActive ? (
            <button
              onClick={onStartCombat}
              disabled={Boolean(session.vehicle_encounter) || Boolean(session.d6_navigation?.journeys.some(journey => !['arrived', 'aborted', 'interrupted', 'off_course', 'abandoned', 'travelling'].includes(journey.status))) || [session.character, ...(session.character.companions ?? [])].some(person => person.d6?.hazards?.drowning && person.d6.wound !== 'dead')}
              className="hp-btn"
              style={{ color: '#ff6b6b', borderColor: '#e63946', display: 'flex', alignItems: 'center', gap: 4 }}
            >
              <Skull size={12} /> {session.edition === 'weg_d6' ? 'Start Imperial Patrol' : 'Start Ambush'}
            </button>
          ) : (
            <button
              onClick={onEndCombat}
              className="hp-btn"
              style={{ color: '#8b92a5' }}
            >
              End Combat
            </button>
          )}
          <button onClick={onUndo} className="hp-btn" title="Undo last turn">
            <RotateCcw size={12} /> Undo
          </button>
          <button onClick={onRedo} className="hp-btn" title="Redo turn">
            <RotateCw size={12} /> Redo
          </button>
        </div>
      </div>

      {/* Tactical Combat Encounter Banner (Fable AI Style) */}
      {actionError && <p role="alert" style={{ color: '#ff6b6b', padding: '8px 20px' }}>{actionError}</p>}
      {session.edition !== 'weg_d6' && session.campaign_name === 'Curse of Strahd Reloaded' && <React.Suspense fallback={null}><StrahdProgressPanel key={`strahd-${session.id}`} session={session} onSessionChanged={onSessionChanged} /></React.Suspense>}
      {session.edition === 'weg_d6' && <D6VehiclePanel session={session} onSessionChanged={onSessionChanged} />}
      {session.edition === 'weg_d6' && <React.Suspense fallback={<p className="native-help">Loading travel and repairs…</p>}>
        <D6NavigationPanel key={`navigation-${session.id}`} session={session} onSessionChanged={onSessionChanged} />
        <D6EngineeringPanel key={`engineering-${session.id}`} session={session} onSessionChanged={onSessionChanged} />
        <D6TaskPanel key={`task-${session.id}`} session={session} onSessionChanged={onSessionChanged} />
        <D6HazardsPanel key={`hazards-${session.id}`} session={session} onSessionChanged={onSessionChanged} />
        <D6TemplatePanel key={`templates-${session.id}`} session={session} onSessionChanged={onSessionChanged} />
        <D6EquipmentPanel key={`equipment-${session.id}`} session={session} onSessionChanged={onSessionChanged} />
        <D6MedicalPanel key={`medical-${session.id}`} session={session} onSessionChanged={onSessionChanged} />
        <D6ExplosivesPanel key={`explosives-${session.id}`} session={session} onSessionChanged={onSessionChanged} />
        <D6GearEffectsPanel key={`gear-effects-${session.id}`} session={session} onSessionChanged={onSessionChanged} />
      </React.Suspense>}
      {session.edition === 'weg_d6' && <D6CreationPanel key={`creation-${session.id}`} session={session} onSessionChanged={onSessionChanged} />}
      {session.edition === 'weg_d6' && <D6SpeciesPanel key={`species-${session.id}`} session={session} onSessionChanged={onSessionChanged} />}
      {session.edition === 'weg_d6' && <D6DroidPanel key={`droid-${session.id}`} session={session} onSessionChanged={onSessionChanged} />}
      {session.edition === 'weg_d6' && <D6ForcePanel session={session} onSessionChanged={onSessionChanged} />}
      {session.edition === 'weg_d6' && <D6AdvancementPanel session={session} onSessionChanged={onSessionChanged} />}
      {session.edition === 'weg_d6' && <D6DarkSidePanel session={session} onSessionChanged={onSessionChanged} />}
      {isCombatActive && session.encounter && (
        <TacticalCombatBanner
          session={session}
          onSessionChanged={onSessionChanged}
          encounter={session.encounter}
          companions={session.character.companions}
          knownSpells={session.character.known_spells}
          selectedTargetId={selectedTargetId}
          onSelectTarget={onSelectTarget}
          onAttackTarget={onAttackTarget}
          playerId={session.character.id}
          onEnemyAttack={onEnemyAttack}
          onCompanionAttack={onCompanionAttack}
          onCastCombatSpell={onCastCombatSpell}
          onNextTurn={onNextTurn}
        />
      )}

      {/* Narrative Turn Stream */}
      <NarrativeStream
        history={session.history}
        editingTurnId={editingTurnId}
        editTurnText={editTurnText}
        illustratingTurnId={illustratingTurnId}
        storyEndRef={storyEndRef}
        onEditChange={onEditChange}
        onSaveAlteration={onSaveAlteration}
        onCancelAlteration={onCancelAlteration}
        onStartEditing={onStartEditing}
        onSpeakTurn={onSpeakTurn}
        onIllustrateTurn={onIllustrateTurn}
        onViewImage={onViewImage}
      />

      {/* Omni Action Bar */}
      <ActionBar
        native={session.edition === 'weg_d6'}
        inputMode={inputMode}
        inputText={inputText}
        advantage={advantage}
        disadvantage={disadvantage}
        isListening={isListening}
        loading={loading}
        onSetInputMode={onSetInputMode}
        onSetInputText={onSetInputText}
        onToggleAdvantage={onToggleAdvantage}
        onToggleDisadvantage={onToggleDisadvantage}
        onToggleSpeech={onToggleSpeech}
        onSubmitAction={onSubmitAction}
      />
    </main>
  );
};
