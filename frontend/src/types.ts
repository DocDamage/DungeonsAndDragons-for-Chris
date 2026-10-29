export interface AbilityScores {
  str: number;
  dex: number;
  con: number;
  int: number;
  wis: number;
  cha: number;
}

export interface Item {
  id?: string;
  catalog_id?: string | null;
  equipped_by?: string | null;
  ammo?: number | null;
  ammo_capacity?: number | null;
  power_ammo?: number | null;
  power_ammo_capacity?: number | null;
  d6_can_stun?: boolean;
  stun_mode?: boolean;
  weapon_damage_state?: string;
  armor_damage_state?: string;
  name: string;
  quantity: number;
  item_type: string;
  damage?: string;
  ac_bonus?: number;
  equipped: boolean;
  description?: string;
  d6_skill?: string | null;
  d6_difficulty?: number | null;
  damage_type?: 'energy' | 'physical';
  sealed_survival_suit?: boolean;
}

export interface SpellSlot {
  level: number;
  current: number;
  max_slots: number;
}

export interface Companion {
  d6_weapon?: Item | null;
  id: string;
  name: string;
  race: string;
  class_name: string;
  level: number;
  current_hp: number;
  max_hp: number;
  ac: number;
  attack_name: string;
  damage: string;
  avatar_url?: string;
  notes?: string;
  d6?: D6Character | null;
}

export interface Character {
  id: string;
  name: string;
  race: string;
  class_name: string;
  level: number;
  alignment: string;
  edition: string;
  abilities: AbilityScores;
  current_hp: number;
  max_hp: number;
  ac: number;
  gold: number;
  inventory: Item[];
  spell_slots?: Record<string, SpellSlot>;
  known_spells?: string[];
  companions?: Companion[];
  conditions: string[];
  d6?: D6Character | null;
}

export type D6Attribute = 'dexterity' | 'knowledge' | 'mechanical' | 'perception' | 'strength' | 'technical';
export interface CorruptionEvent { id: string; source: string; reason: string; before: number; after: number; fall_die: number | null; fell: boolean; cp_awarded: number; adventure: number | null }
export interface AtonementCycle { started_adventure: number; next_review: number; consecutive: number; status: 'active' | 'completed' | 'failed' | 'abandoned'; intention: string; reviews: { adventure: number; approved: boolean; reason: string }[] }
export interface CorruptionState { events: CorruptionEvent[]; atonement: AtonementCycle | null; atonement_history: AtonementCycle[]; calls_adventure: number; calls: number; pending_demand: { cp_loss: number; roll: RollResult } | null; refuses_force: boolean; control_mode: 'player' | 'gm' | 'redemption'; fallen_adventure: number | null; redemption_deadline: number | null; npc_permanent: boolean; moment_keys: string[]; dead: boolean }
export interface DarkActor { id: string; name: string; kind: 'party' | 'encounter' | 'instructor'; dark_side_points: number; consumed: boolean; force_sensitive: boolean; character_points: number; force_points: number; attributes: Record<string, string>; force_skills: Record<string, string>; corruption: CorruptionState; round_state: D6RoundState | null; wound: string }
export interface DarkSideView { adventure: number; actors: DarkActor[]; source: string; notes: string[] }
export type D6Wound = 'healthy' | 'wounded' | 'incapacitated' | 'mortally_wounded' | 'dead';
export type ForceSkill = 'control' | 'sense' | 'alter';
export interface ForceSkillRoll { skill: string; difficulty: number; success: boolean; roll: RollResult; opposition?: RollResult | null; character_points: number }
export interface ForcePower { id: string; name: string; skills: ForceSkill[]; prerequisites: string[]; can_keep_up: boolean; preparation_rounds: number; target: string; description: string; profiles: Record<string, string>; difficulty_notes: string; source: string }
export interface ForceCatalog { powers: ForcePower[]; relationship: Record<string, number>; proximity: Record<string, number> }
export interface ForceEffect { id: string; power_id: string; source_id: string; target_id: string | null; skills: ForceSkill[]; maintained: boolean; recipient: boolean; activation_round: boolean; ready_in_rounds: number; rounds_remaining: number | null; parameters: Record<string, unknown> }
export interface ForceAttempt { id: string; power_id: string; skills: ForceSkill[]; rolls: ForceSkillRoll[]; preparation_remaining: number; preparation_committed: boolean; failed: boolean }
export interface ForceState { known_powers: string[]; effects: ForceEffect[]; attempt: ForceAttempt | null; saber_locked: boolean; reduce_injury_available: boolean; remain_pending: boolean; remain_actions: number | null; elapsed_rounds: number; healing_rolls_remaining: number; permanent_injuries: string[]; heroic_force_returns: number; dark_side_consumed: boolean }
export interface ForceActor { id: string; name: string; race: string; d6: D6Character }
export type D6TrainingKind = 'skill' | 'specialization' | 'advanced' | 'attribute' | 'force_skill' | 'force_power' | 'sensitivity' | 'move';
export interface D6Instructor { id?: string; name: string; attributes: Record<string, string>; skills: Record<string, string>; skill_attributes: Record<string, string>; specialization_parents: Record<string, string>; force_skills: Record<string, string>; known_powers: string[]; full_time: boolean; studying_with_master: boolean; dark_side_points?: number; notes: string }
export interface D6TrainingRequest { actor_id?: string; kind: D6TrainingKind; key: string; attribute?: string; parent_skill?: string; teacher_id?: string | null; days_saved: number; power_days_saved: number; powers: string[]; gm_study_days: number }
export interface D6TrainingQuote { kind: D6TrainingKind; key: string; old_code: string; new_code: string; cp_cost: number; base_cp: number; days: number; teacher_name: string | null; powers: string[]; power_slots: number; eligible_powers: string[]; notes: string[]; source: string }
export interface D6TrainingProject { id: string; quote: D6TrainingQuote; days_completed: number; started_adventure: number; finished_adventure: number | null; status: 'studying' | 'completed' | 'cancelled' | 'suspended' | 'released' | 'forfeited'; student_roll: RollResult | null; maximum_roll: RollResult | null }
export interface D6PowerGrant { id: string; skill: string; remaining: number; teacher_id: string; allowed_powers: string[]; project_id: string }
export interface D6AdvancementState { project: D6TrainingProject | null; history: D6TrainingProject[]; improved: Record<string, number>; power_grants: D6PowerGrant[] }
export type ForceRuling = 'unheroic' | 'heroic' | 'heroic_climax' | 'evil' | 'evil_climax';
export interface ForceExpenditure { id: string; adventure: number | null; source: string; consumed: boolean; guaranteed_heroic: boolean; forfeited: boolean; ruling: ForceRuling | null; reason: string; returned: number }
export interface D6Rewards { baseline_known: boolean; starting_force_points: number | null; expenditures: ForceExpenditure[] }
export interface D6RewardActorRecord { actor_id: string; reason: string; force_returned: number; zero_point_award: number; force_converted: number; conversion_cp: number; character_points_awarded: number; force_points: number; character_points: number; reviews: ForceExpenditure[] }
export interface D6RewardRecord { adventure: number; label: string; actors: D6RewardActorRecord[] }
export interface D6AdvancementCampaign { adventure: number; label: string; instructors: D6Instructor[]; rewards: D6RewardRecord[] }
export interface D6AdvancementView { campaign: D6AdvancementCampaign; actors: ForceActor[]; rules: { training_week_days: number; standard_month_days: number; notes: string[] } }
export interface D6RoundState {
  dark_side_called?: boolean;
  dark_side_active?: boolean;
  declared_actions: number;
  actions_taken: number;
  force_active: boolean;
  character_points_spent: boolean;
  defense_skill: string | null;
  defense_total: number | null;
  full_defense: boolean;
  use_defense_roll: boolean;
  blocked: boolean;
}
export interface D6Character {
  hazards?: D6HazardState;
  species_id?: string;
  species_context?: D6SpeciesContext;
  droid?: D6DroidState | null;
  origin?: { method: string; species_id: string; attribute_budget: number; skill_budget: number; background: string; gm_approval: string; source: string; template_id?: string; force_tradition?: 'standard' | 'tyia' };
  sentient?: boolean;
  rewards?: D6Rewards;
  corruption?: CorruptionState;
  advancement?: D6AdvancementState;
  specialization_parents?: Record<string, string>;
  species_attribute_maximums?: Partial<Record<D6Attribute, string>>;
  move?: number;
  move_maximum?: number | null;
  force?: ForceState;
  attributes: Record<D6Attribute, string>;
  skills: Record<string, string>;
  skill_attributes: Record<string, D6Attribute>;
  advanced_skills: string[];
  specializations: string[];
  force_skills: Record<'control' | 'sense' | 'alter', string>;
  force_sensitive: boolean;
  character_points: number;
  force_points: number;
  dark_side_points: number;
  credits: number;
  armor_energy: string;
  armor_physical: string;
  dexterity_penalty: number;
  wound: D6Wound;
  stun_count: number;
  stun_durations: number[];
  stun_expiries: number[];
  unconscious_rounds: number;
  vacuum_unconscious?: boolean;
  survival_suit?: string | null;
  mortal_rounds: number;
  medpacs_used: number;
  medpac_blocked: boolean;
  care_elapsed_minutes: number;
  recovery_days: number;
  round_state: D6RoundState;
}

export interface D6SpeciesContext { environment: 'neutral' | 'moist' | 'dry'; scent_tracking: boolean; climbing_claws: boolean; enhanced_senses: boolean; familiar_destination: boolean; berserk: boolean; heavy_grasper: boolean; long_range_sensor: boolean; moving_target_sensor: boolean; target_distance_m: number; visited_locations: string[] }
export interface D6HazardState { fatigue_failures: number; fatigued: boolean; exhausted: boolean; willpower_driven: boolean; exertion_rounds: number; rest_rounds: number; swim_round: number; drowning: { round: number; initial_difficulty: number; rescue_difficulty: number; attempted_round: number; declared_round: number } | null; history: Record<string, unknown>[] }
export interface D6DroidState { model: string; owner: string; degree: number; equipment: string[]; hardwired_skills: Record<string, string>; tasks: string[]; route_memory?: { origin: string; destination: string; reason: string }[]; memory_wipes: number; destroyed: boolean; repair_attempts: number; work_history: { operation: string; skill: string; success: boolean; minutes: number; cp_spent: number; credits: number; reason: string }[] }
export interface D6Species { id: string; name: string; attribute_dice: number; minimums: Record<D6Attribute, string>; maximums: Record<D6Attribute, string>; suggested_attributes: Record<D6Attribute, string>; move: number; move_maximum: number; notes: string[]; creation_bonus_skills: string[]; source: string }
export interface D6DroidChassis { id: string; name: string; degree: number; pc_attributes: Record<D6Attribute, string>; move: number; notes: string[]; equipment: string[] }
export interface D6CreationCatalog { species: D6Species[]; droids: D6DroidChassis[]; skills: Record<string, string>; equipment: (Item & { id: string })[]; source: string }
export interface D6CreationRequest { name: string; occupation: string; species_id: string; droid_model: string | null; owner: string; attributes: Record<string, string>; skill_dice: Record<string, number>; skill_attributes: Record<string, string>; specializations: { name: string; parent: string }[]; force_skills: string[]; force_sensitive: boolean; powers: string[]; force_background: string; background: string; gm_approval: string; equipment: string[]; credits: number; include_medic: boolean; expected_updated_at: number }
export interface D6Options {
  target_weapon?: boolean;
  distance_m?: number;
  bowcaster_strength_character_points?: number;
  attack_cover?: boolean;
  hit_location?: 'random' | 'head' | 'torso' | 'left_arm' | 'right_arm' | 'left_leg' | 'right_leg';
  called_shot?: boolean;
  location_damage?: boolean;
  attack_side?: 'front' | 'back';
  lightsaber_control_dice?: number;
  range_band?: 'point_blank' | 'short' | 'medium' | 'long';
  difficulty?: number;
  character_points?: number;
  resistance_character_points?: number;
  stun?: boolean;
  mishap?: 'penalty' | 'complication';
}

export interface RollResult {
  expression: string;
  dice_count: number;
  die_type: number;
  raw_rolls: number[];
  kept_rolls: number[];
  modifier: number;
  total: number;
  is_crit: boolean;
  is_fumble: boolean;
  breakdown: string;
  system?: string;
  wild_rolls?: number[];
  mishap?: string | null;
  bonus_rolls?: number[];
}

export interface RuleEvaluationResult {
  force_rolls?: ForceSkillRoll[];
  action_type: string;
  success: boolean;
  is_crit: boolean;
  is_fumble: boolean;
  roll_result: RollResult;
  summary: string;
  damage_dealt?: number;
  damage_roll?: RollResult | null;
  resistance_roll?: RollResult | null;
  wound_result?: string | null;
}

export interface ActionTurn {
  id: string;
  mode: string;
  player_input: string;
  rule_result?: RuleEvaluationResult;
  dm_output: string;
  image_url?: string;
  timestamp?: number;
  source_references?: SourceReference[];
}

export interface StoryCard {
  id: string;
  title: string;
  keys: string[];
  entry: string;
  card_type: string;
  priority: number;
  enabled: boolean;
  image_url?: string;
}

export interface Combatant {
  armor?: Item[];
  inventory?: Item[];
  cover_id?: string | null;
  cover_fraction?: string;
  concealment_dice?: number;
  weapon?: Item | null;
  id: string;
  name: string;
  is_player: boolean;
  initiative: number;
  current_hp: number;
  max_hp: number;
  ac: number;
  conditions: string[];
  image_url?: string;
  is_defeated: boolean;
  d6?: D6Character | null;
}

export interface CombatEncounter {
  d6_round_closing?: boolean;
  cover_objects?: { id: string; name: string; body: string; damage_state: string; reason: string }[];
  id: string;
  active: boolean;
  round: number;
  current_turn_index: number;
  combatants: Combatant[];
  combat_log: string[];
  system?: string;
  d6_actions_started?: boolean;
  d6_turn_acted?: boolean;
  d6_initiative_winner?: boolean;
}

export interface CombatEnemy {
  name: string;
  hp?: number;
  ac?: number;
  dex_mod?: number;
  image_url?: string;
  d6?: D6Character;
  weapon?: Item;
}

export interface CompendiumEntry {
  id: string;
  name: string;
  category: string;
  edition: string;
  level_or_cr?: string;
  school_or_type?: string;
  summary: string;
  description: string;
  source: string;
}

export interface GameSession {
  updated_at?: number;
  d6_advancement?: D6AdvancementCampaign;
  force_boost?: { actor_id: string; turn_id: string; attempt_id: string; points_spent: number; limit: number; force_used: boolean } | null;
  id: string;
  title: string;
  edition: string;
  character: Character;
  story_cards: StoryCard[];
  history: ActionTurn[];
  active_quests: Record<string, string[]>;
  campaign_name: string;
  encounter?: CombatEncounter | null;
  native_boost?: D6BoostWindow | null;
  vehicles?: D6Vehicle[];
  vehicle_encounter?: D6VehicleEncounter | null;
  d6_navigation?: { journeys: D6Journey[] };
  d6_hazard_round?: number;
}

export type D6Scale = 'character' | 'speeder' | 'walker' | 'starfighter' | 'capital' | 'death_star';
export type D6Arc = 'front' | 'back' | 'left' | 'right';
export type D6Station = 'pilot' | 'gunner' | 'shields' | 'engineer';
export interface D6Crew {
  id: string;
  name: string;
  character_id: string | null;
  stations: D6Station[];
  d6: D6Character;
  control_penalty: number;
  next_control_penalty: number;
  evacuated: boolean;
}
export interface D6VehicleWeapon {
  id: string;
  name: string;
  system: string;
  skill: string;
  scale: D6Scale | null;
  arcs: D6Arc[];
  fire_control: string;
  damage: string;
  kind: 'energy' | 'ion' | 'missile' | 'tractor';
  space_ranges: [number, number, number, number];
  atmosphere_ranges: [number, number, number, number];
  operator_id: string | null;
  pilot_operated: boolean;
  ammo: number | null;
  status: 'operational' | 'disabled' | 'destroyed';
  purchase_value?: number;
  repair_damage?: 'intact' | 'lightly_damaged' | 'heavily_damaged' | 'severely_damaged' | 'destroyed';
}
export interface D6Vehicle {
  id: string;
  name: string;
  kind: 'vehicle' | 'starship';
  scale: D6Scale;
  is_player: boolean;
  occupied: boolean;
  piloting_skill: string;
  hull: string;
  maneuverability: string;
  shields: string;
  space_move: number;
  atmosphere_move: number;
  airborne: boolean;
  altitude: number;
  crew: D6Crew[];
  weapons: D6VehicleWeapon[];
  source: string;
  damage: 'intact' | 'lightly_damaged' | 'heavily_damaged' | 'severely_damaged' | 'destroyed';
  maneuverability_lost: number;
  shields_lost: number;
  speed_losses: number;
  ion_durations: number[];
  frozen_rounds: number;
  forced_moves: number;
  forced_half_speed: boolean;
  controls_dead: boolean;
  drives_disabled: boolean;
  weapons_disabled: boolean;
  hyperdrive_disabled: boolean;
  particle_shields: boolean;
  destruction_countdown: number | null;
  destruction_cause: 'generator' | 'structure' | null;
  generator_shutdown: boolean;
  shield_allocation: Partial<Record<D6Arc, string>>;
  shields_rolled: boolean;
  dodge_roll: RollResult | null;
  full_dodge: boolean;
  declared_moves: number;
  half_speed: boolean;
  moves_taken: number;
  distance_moved: number;
  spin_rounds: number;
  captured_by: string | null;
  captured_weapon: string | null;
  tractor_distance: number;
  damage_log: string[];
  purchase_value?: number;
  hyperdrive_multiplier?: number | null;
  backup_hyperdrive?: number | null;
  nav_computer?: boolean;
  nav_computer_disabled?: boolean;
  escape_pods_disabled?: boolean;
  hull_breached?: boolean;
  location?: string;
  repair_projects?: D6CraftRepairProject[];
}
export interface D6CraftRepairRequest {
  craft_id: string; system: 'maneuverability' | 'moves' | 'shields' | 'drives' | 'hyperdrive' | 'generator' | 'controls' | 'weapon' | 'weapons' | 'nav_computer' | 'escape_pods';
  weapon_id: string | null; asset_value: number; assessed_damage: 'lightly_damaged' | 'heavily_damaged' | 'severely_damaged' | 'destroyed';
  replacement: boolean; gm_difficulty: number | null; gm_cost: number | null; parts_item: string | null; reason: string; expected_updated_at?: number;
}
export interface D6CraftRepairQuote { craft_id: string; key: string; skill: string; difficulty: number; parts_cost: number; percent: number | null; fingerprint: string; notes: string[]; source: string }
export interface D6CraftRepairProject { id: string; request: D6CraftRepairRequest; quote: D6CraftRepairQuote; paid_credits: number; parts_source: string; status: 'pending' | 'completed' | 'cancelled'; attempts: { actor_id?: string; minutes: number; success: boolean; interrupted?: boolean; reason?: string; timing_reason?: string; roll?: RollResult; cp?: number; fp?: boolean }[] }
export interface D6NavigationRequest {
  craft_id: string; actor_id: string | null; origin: string; destination: string; base_hours: number | null; base_difficulty: number;
  route_type: 'major' | 'common' | 'light' | 'infrequent' | 'old' | 'unexplored'; backup: boolean; hasty: boolean; obstacles: number; extra_hours: number;
  clearance_units: number; boarding_confirmed: boolean; plotting_rounds: number; astromech_id: string | null; destination_visited?: boolean; character_points: number; force_point: boolean; reason: string; expected_updated_at: number | null;
}
export interface D6Journey {
  id: string; request: D6NavigationRequest; quote: { difficulty: number; hours: number; rounds: number; has_navigation: boolean; multiplier: number; notes: string[] };
  status: string; remaining_rounds: number; elapsed_rounds: number; roll: RollResult; miss: number; mishap: number | null; auxiliary_rolls: RollResult[]; travellers: string[];
  crew_exposure: Record<string, { protected: boolean; phase: string; suit_round?: number; breath_round?: number; suit_name?: string | null; last_action_round?: number; acted_round?: number }>;
  emergency_round: number; resolution: string[];
}
export interface D6VehicleEncounter {
  id: string;
  active: boolean;
  environment: 'space' | 'atmosphere';
  round: number;
  craft: D6Vehicle[];
  actor_order: string[];
  current_turn_index: number;
  turn_acted: boolean;
  actions_started: boolean;
  initiative_winner: boolean;
  initiative: Record<string, number>;
  combat_log: string[];
  boost?: { actor_id: string; turn_id: string; kind: 'dodge' | 'shields'; points_spent: number; force_used: boolean } | null;
}

export interface D6BoostWindow {
  turn_id: string;
  actor_id: string;
  skill: string;
  points_spent: number;
  limit: number;
  force_used: boolean;
  defensive: boolean;
  total: number;
}

export interface CampaignSummary {
  id: string;
  title: string;
  edition: string;
  genre: string;
  banner_image?: string;
  description: string;
  acts_count: number;
  source_folder?: string;
  source_rule_system?: string;
  rules_note?: string | null;
  source_count?: number;
  indexed_sources?: number;
  source_passages?: number;
}

export interface SourceReference {
  source_id: string;
  title: string;
  section: string;
  file_url: string;
}

export interface SourcePassage extends SourceReference {
  folder_id: string;
  edition: string;
  text: string;
}

export interface LibrarySource {
  id: string;
  title: string;
  path: string;
  file_url: string;
  status: 'pending' | 'indexed' | 'empty' | 'error';
  pages: number;
  chunks: number;
  error: string | null;
}

export interface LibraryFolder {
  id: string;
  directory: string;
  title: string;
  edition: string;
  kind: string;
  available: boolean;
  source_count: number;
  indexed_count: number;
  chunk_count: number;
  sources: LibrarySource[];
}

export interface LibraryJob {
  running: boolean;
  completed: number;
  total: number;
  current: string;
  error: string | null;
}

export interface LibraryCatalog {
  root: string;
  folders: LibraryFolder[];
  job: LibraryJob;
}

export interface SaveSlot {
  slot_id: string;
  title: string;
  campaign_name: string;
  edition: string;
  character_name: string;
  turns_count: number;
  saved_at: number;
}

export type ActionInputMode = "do" | "say" | "story" | "attack" | "check" | "rest" | "cast" | "see";
export type LeftSidebarTab = "inventory" | "spells" | "companions";
export type RightSidebarTab = "cards" | "quests" | "map" | "compendium" | "dice" | "settings";
