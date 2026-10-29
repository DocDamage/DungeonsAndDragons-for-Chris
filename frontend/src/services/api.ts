import type {
  GameSession,
  Character,
  StoryCard,
  RollResult,
  CampaignSummary,
  SaveSlot,
  CompendiumEntry,
  ActionTurn,
  CombatEncounter,
  Combatant,
  CombatEnemy,
  RuleEvaluationResult,
  LibraryCatalog,
  LibraryJob,
  SourcePassage,
  D6Options,
  D6Vehicle,
  ForceCatalog,
  ForceActor,
  D6AdvancementView,
  D6TrainingRequest,
  D6TrainingQuote,
  D6RewardRecord,
  D6CreationCatalog,
  D6CreationRequest,
  DarkSideView
} from '../types';

export const API_BASE = "/api";

async function nativeRequest<T>(path: string, payload: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}/weg-d6/${path}`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const error = await res.json();
    throw new Error(typeof error.detail === 'string' ? error.detail : Array.isArray(error.detail) ? error.detail.map((item: { msg: string }) => item.msg).join('; ') : 'Native D6 request failed');
  }
  return res.json();
}

type NativeResponse = { session: GameSession; eval_result?: RuleEvaluationResult; turn?: ActionTurn };

export const api = {
  async nativeCreationCatalog(signal?: AbortSignal): Promise<D6CreationCatalog> {
    const response = await fetch(`${API_BASE}/weg-d6/creation/catalog`, { signal });
    if (!response.ok) throw new Error('Unable to load native character creation');
    return response.json();
  },
  nativeCreationPreview(payload: D6CreationRequest) {
    return nativeRequest<{ character: Character; notes: string[]; source: string }>('creation/preview', payload);
  },
  nativeCreationStart(payload: D6CreationRequest) {
    return nativeRequest<{ session: GameSession; backup_slot: string }>('creation/start', payload);
  },
  nativeCreationRecruit(payload: D6CreationRequest) {
    return nativeRequest<NativeResponse>('creation/recruit', payload);
  },
  nativeSpeciesAction(action: string, payload: unknown) {
    return nativeRequest<NativeResponse>(`creation/${action}`, payload);
  },
  nativeDroidWork(payload: unknown) {
    return nativeRequest<NativeResponse>('droids/work', payload);
  },
  async nativeDarkSideState(signal?: AbortSignal): Promise<DarkSideView> {
    const res = await fetch(`${API_BASE}/weg-d6/dark-side/state`, { signal });
    if (!res.ok) throw new Error('Unable to load Dark Side state');
    return res.json();
  },
  nativeDarkSideAction(action: string, payload: unknown) {
    return nativeRequest<NativeResponse>(`dark-side/${action}`, payload);
  },
  async nativeAdvancementState(signal?: AbortSignal): Promise<D6AdvancementView> {
    const res = await fetch(`${API_BASE}/weg-d6/advancement/state`, { signal });
    if (!res.ok) throw new Error('Unable to load advancement');
    return res.json();
  },
  nativeAdvancementQuote(payload: D6TrainingRequest) {
    return nativeRequest<{ quote: D6TrainingQuote; affordable: boolean }>('advancement/quote', payload);
  },
  nativeAdvancementAction(action: string, payload: unknown) {
    return nativeRequest<NativeResponse>(`advancement/${action}`, payload);
  },
  nativeRewardQuote(payload: unknown) {
    return nativeRequest<{ quote: D6RewardRecord }>('advancement/reward-quote', payload);
  },
  async nativeForceCatalog(signal?: AbortSignal): Promise<ForceCatalog> {
    const res = await fetch(`${API_BASE}/weg-d6/force/catalog`, { signal });
    if (!res.ok) throw new Error('Unable to load Force powers');
    return res.json();
  },
  async nativeForceActors(signal?: AbortSignal): Promise<{ actors: ForceActor[] }> {
    const res = await fetch(`${API_BASE}/weg-d6/force/actors`, { signal });
    if (!res.ok) throw new Error('Unable to load Force actors');
    return res.json();
  },
  nativeForceAction(action: string, payload: unknown) {
    return nativeRequest<NativeResponse>(`force/${action}`, payload);
  },
  async nativeVehicleCatalog(signal?: AbortSignal): Promise<{ presets: D6Vehicle[] }> {
    const res = await fetch(`${API_BASE}/weg-d6/vehicles/catalog`, { signal });
    if (!res.ok) throw new Error('Unable to load native craft presets');
    return res.json();
  },
  nativeVehicleAction(action: string, payload: unknown = {}) {
    return nativeRequest<NativeResponse>(`vehicles/${action}`, payload);
  },
  nativePool(code: string, mishap: 'penalty' | 'complication' = 'penalty') {
    return nativeRequest<RollResult>('pool', { code, mishap });
  },
  nativeCheck(payload: { skill: string; difficulty: number; actions?: number; force_point?: boolean; character_points?: number; mishap?: 'penalty' | 'complication' }) {
    return nativeRequest<NativeResponse>('check', payload);
  },
  nativeBoost(points: number) {
    return nativeRequest<NativeResponse>('boost', { points });
  },
  nativeDeclare(payload: { actor_id?: string; actions: number; force_point: boolean }) {
    return nativeRequest<NativeResponse>('declare', payload);
  },
  nativeDefend(payload: { actor_id?: string; skill: string; full: boolean; use_roll: boolean; character_points: number }) {
    return nativeRequest<NativeResponse>('defend', payload);
  },
  nativeInitiative(winnerFirst: boolean) {
    return nativeRequest<NativeResponse>(`initiative?winner_first=${winnerFirst}`, {});
  },
  nativeRecover(payload: { method: 'rest' | 'natural' | 'medpac'; minutes?: number; days?: number; healer_id?: string }) {
    return nativeRequest<NativeResponse>('recover', payload);
  },
  async getLibrary(signal?: AbortSignal): Promise<LibraryCatalog> {
    const res = await fetch(`${API_BASE}/library`, { signal });
    if (!res.ok) throw new Error("Failed to load the local source library");
    return res.json();
  },

  async indexLibrary(folderId?: string): Promise<{ job: LibraryJob }> {
    const query = folderId ? `?folder_id=${encodeURIComponent(folderId)}` : '';
    const res = await fetch(`${API_BASE}/library/index${query}`, { method: 'POST' });
    if (!res.ok) throw new Error("Failed to start importing sources");
    return res.json();
  },

  async searchLibrary(query: string, folderId?: string): Promise<SourcePassage[]> {
    const params = new URLSearchParams({ q: query });
    if (folderId) params.set('folder_id', folderId);
    const res = await fetch(`${API_BASE}/library/search?${params}`);
    if (!res.ok) throw new Error("Failed to search local sources");
    return (await res.json()).results;
  },

  async getSession(signal?: AbortSignal): Promise<GameSession> {
    const res = await fetch(`${API_BASE}/session`, { signal });
    if (!res.ok) throw new Error("Failed to fetch session");
    return res.json();
  },

  async setEdition(edition: string): Promise<GameSession> {
    const res = await fetch(`${API_BASE}/session/edition?edition=${edition}`, { method: "POST" });
    if (!res.ok) throw new Error("Failed to set edition");
    return res.json();
  },

  async sendAction(payload: {
    mode: string;
    text: string;
    advantage?: boolean;
    disadvantage?: boolean;
    target_ac?: number;
    target_dc?: number;
    weapon_name?: string;
  }): Promise<{ turn: ActionTurn; session: GameSession }> {
    const res = await fetch(`${API_BASE}/action`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    if (!res.ok) {
      const error = await res.json();
      throw new Error(typeof error.detail === 'string' ? error.detail : 'Failed to execute action');
    }
    return res.json();
  },

  async alterTurn(turnId: string, newText: string): Promise<{ turn: ActionTurn; session: GameSession }> {
    const res = await fetch(`${API_BASE}/turn/alter`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ turn_id: turnId, new_text: newText })
    });
    if (!res.ok) throw new Error("Failed to alter turn");
    return res.json();
  },

  async undoTurn(): Promise<{ undone: ActionTurn; session: GameSession }> {
    const res = await fetch(`${API_BASE}/turn/undo`, { method: "POST" });
    if (!res.ok) throw new Error("Failed to undo turn");
    return res.json();
  },

  async redoTurn(): Promise<{ redone: ActionTurn; session: GameSession }> {
    const res = await fetch(`${API_BASE}/turn/redo`, { method: "POST" });
    if (!res.ok) throw new Error("Failed to redo turn");
    return res.json();
  },

  async updateCharacter(char: Character): Promise<Character> {
    const res = await fetch(`${API_BASE}/character`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(char)
    });
    if (!res.ok) {
      const error = await res.json();
      throw new Error(typeof error.detail === 'string' ? error.detail : Array.isArray(error.detail) ? error.detail.map((item: { msg: string }) => item.msg).join('; ') : 'Failed to update character');
    }
    return res.json();
  },

  async rollCharacterStats(): Promise<{ stats: Record<string, number>; breakdowns: Record<string, string> }> {
    const res = await fetch(`${API_BASE}/character/roll-stats`, { method: "POST" });
    if (!res.ok) throw new Error("Failed to roll stats");
    return res.json();
  },

  async rollDice(expression: string): Promise<RollResult> {
    const res = await fetch(`${API_BASE}/dice/roll`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ expression })
    });
    if (!res.ok) {
      const error = await res.json();
      throw new Error(typeof error.detail === 'string' ? error.detail : "Failed to roll dice");
    }
    return res.json();
  },

  async useItem(itemName: string): Promise<{ status: string; effect: string; character: Character; session: GameSession }> {
    const res = await fetch(`${API_BASE}/character/use-item?item_name=${encodeURIComponent(itemName)}`, { method: "POST" });
    if (!res.ok) throw new Error("Failed to use item");
    return res.json();
  },

  async saveStoryCard(card: StoryCard): Promise<StoryCard> {
    const res = await fetch(`${API_BASE}/story-cards`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(card)
    });
    if (!res.ok) throw new Error("Failed to save story card");
    return res.json();
  },

  async deleteStoryCard(cardId: string): Promise<void> {
    const res = await fetch(`${API_BASE}/story-cards/${cardId}`, { method: "DELETE" });
    if (!res.ok) throw new Error("Failed to delete story card");
  },

  async getCampaigns(signal?: AbortSignal): Promise<CampaignSummary[]> {
    const res = await fetch(`${API_BASE}/campaigns`, { signal });
    if (!res.ok) throw new Error("Failed to fetch campaigns");
    const data = await res.json();
    return data.campaigns;
  },

  async switchCampaign(campaignId: string): Promise<{ status: string; campaign: string; session: GameSession }> {
    const res = await fetch(`${API_BASE}/campaign/switch/${campaignId}`, { method: "POST" });
    if (!res.ok) throw new Error("Failed to switch campaign");
    return res.json();
  },

  async getSaves(): Promise<SaveSlot[]> {
    const res = await fetch(`${API_BASE}/session/saves`);
    if (!res.ok) throw new Error("Failed to list saves");
    const data = await res.json();
    return data.saves;
  },

  async getSaveSlots(): Promise<SaveSlot[]> {
    return this.getSaves();
  },

  async saveSession(slotName?: string): Promise<{ status: string; slot_id: string; session: GameSession }> {
    const url = slotName ? `${API_BASE}/session/save?slot_name=${encodeURIComponent(slotName)}` : `${API_BASE}/session/save`;
    const res = await fetch(url, { method: "POST" });
    if (!res.ok) throw new Error("Failed to save session");
    return res.json();
  },

  async loadSession(slotId: string): Promise<{ status: string; session: GameSession }> {
    const res = await fetch(`${API_BASE}/session/load/${slotId}`, { method: "POST" });
    if (!res.ok) throw new Error("Failed to load session");
    return res.json();
  },

  async deleteSave(slotId: string): Promise<void> {
    const res = await fetch(`${API_BASE}/session/save/${slotId}`, { method: "DELETE" });
    if (!res.ok) throw new Error("Failed to delete save slot");
  },

  async exportMarkdownChronicle(): Promise<string> {
    const res = await fetch(`${API_BASE}/session/export/markdown`);
    if (!res.ok) throw new Error("Failed to export markdown chronicle");
    return res.text();
  },

  async startCombat(enemies: CombatEnemy[] = []): Promise<{ encounter: CombatEncounter; session: GameSession }> {
    const res = await fetch(`${API_BASE}/combat/start`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enemies })
    });
    if (!res.ok) {
      const error = await res.json();
      throw new Error(typeof error.detail === 'string' ? error.detail : 'Failed to start combat');
    }
    return res.json();
  },

  async combatAttack(params: {
    target_id: string;
    weapon_name?: string;
    advantage?: boolean;
    disadvantage?: boolean;
    d6_options?: D6Options;
    attacker_id?: string;
  }): Promise<{ eval_result: RuleEvaluationResult; encounter: CombatEncounter; session: GameSession }> {
    const res = await fetch(`${API_BASE}/combat/attack`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(params)
    });
    if (!res.ok) {
      const error = await res.json();
      throw new Error(typeof error.detail === 'string' ? error.detail : 'Failed to execute combat attack');
    }
    return res.json();
  },

  async combatNextTurn(): Promise<{ active_combatant: Combatant | null; encounter: CombatEncounter; session: GameSession }> {
    const res = await fetch(`${API_BASE}/combat/next`, { method: "POST" });
    if (!res.ok) throw new Error("Failed to advance combat turn");
    return res.json();
  },

  async combatEnd(): Promise<{ status: string; session: GameSession }> {
    const res = await fetch(`${API_BASE}/combat/end`, { method: "POST" });
    if (!res.ok) throw new Error("Failed to end combat");
    return res.json();
  },

  async searchCompendium(query: string = "", category: string = "all", edition: string = "all", limit: number = 40): Promise<CompendiumEntry[]> {
    const params = new URLSearchParams({ q: query, category, edition, limit: limit.toString() });
    const res = await fetch(`${API_BASE}/compendium/search?${params.toString()}`);
    if (!res.ok) throw new Error("Failed to search compendium");
    const data = await res.json();
    return data.results;
  },

  async configLLM(payload: { provider: string; api_key?: string; base_url?: string; model?: string }): Promise<void> {
    const res = await fetch(`${API_BASE}/config/llm`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    if (!res.ok) throw new Error("Failed to configure LLM");
  },

  async illustrateScene(payload: { prompt?: string; turn_id?: string; style_preset?: string }): Promise<{ image_url: string; session: GameSession }> {
    const res = await fetch(`${API_BASE}/scene/illustrate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    if (!res.ok) throw new Error("Failed to illustrate scene");
    return res.json();
  },

  async castSpell(payload: {
    spell_name: string;
    slot_level: number;
    target_id?: string;
    target_ac_or_dc?: number;
    damage_or_healing?: string;
  }): Promise<{ status: string; turn: ActionTurn; slots_remaining: number; session: GameSession }> {
    const res = await fetch(`${API_BASE}/character/cast-spell`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Failed to cast spell");
    }
    return res.json();
  },

  async restoreSpellSlots(level?: number): Promise<{ spell_slots: Record<string, any>; session: GameSession }> {
    const url = level !== undefined ? `${API_BASE}/character/spell-slots/restore?level=${level}` : `${API_BASE}/character/spell-slots/restore`;
    const res = await fetch(url, { method: "POST" });
    if (!res.ok) throw new Error("Failed to restore spell slots");
    return res.json();
  },

  async learnSpell(spellName: string): Promise<{ known_spells: string[]; session: GameSession }> {
    const res = await fetch(`${API_BASE}/character/spells/learn`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ spell_name: spellName })
    });
    if (!res.ok) throw new Error("Failed to learn spell");
    return res.json();
  },

  async unlearnSpell(spellName: string): Promise<{ known_spells: string[]; session: GameSession }> {
    const res = await fetch(`${API_BASE}/character/spells/${encodeURIComponent(spellName)}`, {
      method: "DELETE"
    });
    if (!res.ok) throw new Error("Failed to unlearn spell");
    return res.json();
  },

  async addCompanion(payload: {
    name: string;
    race?: string;
    class_name?: string;
    level?: number;
    current_hp?: number;
    max_hp?: number;
    ac?: number;
    attack_name?: string;
    damage?: string;
    avatar_url?: string;
    notes?: string;
  }): Promise<{ companion: any; session: GameSession }> {
    const res = await fetch(`${API_BASE}/character/companions`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    if (!res.ok) throw new Error("Failed to add companion");
    return res.json();
  },

  async deleteCompanion(companionId: string): Promise<{ session: GameSession }> {
    const res = await fetch(`${API_BASE}/character/companions/${companionId}`, {
      method: "DELETE"
    });
    if (!res.ok) throw new Error("Failed to delete companion");
    return res.json();
  },

  async adjustCompanionHp(companionId: string, hpChange: number): Promise<{ companion: any; session: GameSession }> {
    const res = await fetch(`${API_BASE}/character/companions/${companionId}/hp`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ hp_change: hpChange })
    });
    if (!res.ok) throw new Error("Failed to adjust companion HP");
    return res.json();
  },

  async companionAttack(payload: {
    companion_id: string;
    target_id: string;
    advantage?: boolean;
    disadvantage?: boolean;
  }): Promise<{ eval_result: RuleEvaluationResult; encounter: CombatEncounter; session: GameSession }> {
    const res = await fetch(`${API_BASE}/combat/companion-attack`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Companion attack failed");
    }
    return res.json();
  }
};
