# ⚔️ DungeonForge: Multi-System AI RPG Engine & Companion

**DungeonForge** merges open-ended AI storytelling with deterministic RPG mechanics, tactical combat, and state persistence. It supports **AD&D 2e**, **D&D 3.5e**, **D&D 5e**, and native **WEG Star Wars D6 Second Edition** character, vehicle, and starship combat.

---

## 🚀 Quick Start

### 1. Launch in One Click (Windows)
For a fresh clone, install the frontend once with `cd frontend && npm ci && npm run build`, then return to the project root. Python dependencies are installed by `uv run`.

Double-click `start.bat` or run:
```bash
uv run python run.py
```
This automatically starts the FastAPI backend + compiled React frontend and opens `http://127.0.0.1:8000` in your default browser.

Player saves, generated databases, imported campaign artwork, browser captures, and local source PDFs/archives are not versioned. Supply your own source library through the campaign/source controls; artwork is imported from those local archives. The deterministic campaign and rules controls work without the optional source files. Source-audit tests skip when the corresponding local book/archive is absent.

### 2. Development Mode
To develop with live hot-reloading:
- **Backend**: `uv run uvicorn dungeonforge.main:app --reload --port 8000`
- **Frontend**: `cd frontend && npm run dev`

The frontend uses `/api` on its current origin. Vite proxies `/api` and `/static` to the backend on port 8000 during development, so the UI also works when served under a different hostname or production port. If the initial connection fails, start the backend and click **Retry connection**.

---

## 🏛️ Core Features

### 1. Voice Narration & Speech Input (Fable AI)
- 🎙️ **Voice Action Input (STT)**: Click the microphone icon in the action bar to speak your actions or dialogue directly into the prompt using native browser speech recognition.
- 🔊 **Spoken DM Narration (TTS)**: Click the **Read Aloud** button on any turn to have the Dungeon Master narrate the story using native speech synthesis.
- 🌧️ **Procedural Atmospheric Soundscapes**: Real-time synthesized gothic rain and castle drafts generated via the Web Audio API with zero external downloads.

### 2. Dynamic Scene Illustrator & "See" Mode (AI Dungeon & Fable AI)
- 🎨 **Instant Scene Illustration**: Click the **Illustrate Scene** / **Regenerate Art** button on any DM turn to generate vivid, dark fantasy scene paintings on the fly.
- 👁️ **"See" Action Mode**: Select the **See** mode or type `/see <scene description>` to have the AI generate both narrative description and custom scene art.
- 🔍 **Cinematic Lightbox Viewer**: Click any illustrated scene banner in the adventure chronicle to expand it into full-screen high-resolution modal view.

### 3. Spellbook & Interactive Spell Slot Engine
- 🔮 **Spell Slot Tracker**: Live bubble trackers (`Level 1: [●] [●] [○]`) reflecting expended vs ready slots, with 1-click **Restore All Slots**.
- 📜 **Prepared Spells**: Quick-cast prepared spells (*Cure Wounds*, *Hunter's Mark*, *Hail of Thorns*, *Fireball*) with deterministic damage/healing dice rolling and encounter integration.
- 📖 **Spell Learning & Compendium Integration**: Add or remove spells dynamically from your character sheet.

### 4. Party Companions & Tactical Ally Strikes
- 👥 **Party Allies Management**: Travel with loyal companions (*Ireena Kolyana*, *Ismark the Lesser*, *Ezmerelda d'Avenir*), complete with individual portraits, class levels, AC, and HP trackers.
- ⚔️ **Tactical Ally Attacks**: In combat encounters, command companions to strike selected enemy targets alongside your character using their unique weapon proficiencies.
- 🤝 **Recruit Companions**: Add new allies and hirelings to your party using the recruitment wizard with custom stats, attack dice, and backstories.

### 5. Adventure Saves & Book Export (.md)
- **Multi-Slot Save System**: Save your adventures into named slots, browse past campaigns, and resume play anytime.
- **Export Chronicle**: Download your entire generated campaign as an illustrated Markdown book (`.md`) formatted into chapters, character sheets, and roll breakdowns.

### 6. Dynamic Auto-Card Entity Extractor (AI Dungeon)
- **Object Permanence**: Automatically identifies newly introduced NPCs, factions, relics, and locations mentioned in the DM's narrative.
- Creates and injects draft **Story Cards** into the Lorebook with auto-generated trigger keys and context sentences.

### 7. Interactive Consumable Inventory Engine
- Click **Use** beside potions, scrolls, or rations in your inventory.
- Automatically rolls healing or spell effects, adjusts character HP, decrements the item quantity, and logs the action turn.

### 8. Campaign Hub & Multi-Genre Scenarios
Switch seamlessly between distinct adventures in the **Campaigns Menu**:
- 🏰 **Curse of Strahd Reloaded** (*Gothic Horror, 5e/2e*): Navigate the mists of Barovia and confront Count Strahd in Castle Ravenloft.
- 🧪 **The Lost Dungeon of Rickedness** (*Sci-Fi Parody, 5e*): Rick Sanchez DMs an absurd multidimensional dungeon crawl with Morty, laser daggers, and portal fluid.
- 🦸 **Marvel 5e: Superhero Chronicles** (*Urban Superhero, 5e*): Defend Manhattan with Peter Parker (Spider-Man), web shooters, and superhero abilities.
- ⛏️ **Minecraft: Lightning Keep** (*Voxel Fantasy, 5e*): Delve into dark brick dungeons with diamond swords, facing Creepers and Nether blazes.
- 🌌 **Star Wars: Galactic Rebellion** (*Space Opera, WEG D6*): Native attribute and skill pools, blasters, armor, wounds, and Imperial patrol encounters.

### 9. Interactive Dungeon Map & Fog-of-War Explorer
- **Room Node Visualizer**: An interactive spatial map of connected chambers (Foyer, Conservatory, Dining Hall, Attic, Dungeon Crypts).
- **Fog of War**: Unvisited chambers remain veiled in darkness until scouted.
- **One-Click Travel**: Click adjacent rooms and click **Travel Here** to automatically transition and have the DM narrate your arrival.

### Local Campaign and Rules Library

Open **Campaigns → Source folders & rules** to browse and search the local library. The default location is the parent of this project (`F:\dev\dandd` in this checkout). Set `DUNGEONFORGE_LIBRARY_DIR` before starting the server to use another location.

| Folder | Content |
| --- | --- |
| `2e` | AD&D 2nd Edition rules, including the combined 26-book PDF |
| `3.5e` | D&D 3.5 rulebooks and supplements; existing OCR text is preferred over duplicate PDFs |
| `5e` | D&D 5e rules, monster references, and supplements |
| `curse of straud` | All three Strahd vault archives, including their image assets |
| `marvel` | Marvel 5e setting and character rules |
| `minecraft` | Lightning Keep adventure and Minecraft creature compendium |
| `rick and morty` | The Lost Dungeon of Rickedness adventure |
| `star wars` | Star Wars WEG 2nd Edition, using the D6 system |

Click **Import all folders** or **Import folder** to update the search index. Imports run in the background, show progress, and skip unchanged sources. Source PDFs and text files stay in their original folders; the rebuildable `library.sqlite3` index stays inside this project. Archive metadata, download artifacts, and duplicate OCR/PDF representations are excluded. A source with no readable text is reported rather than treated as searchable.

You can also import from the command line:

```bash
uv run python -m dungeonforge.library
uv run python -m dungeonforge.library --folder minecraft
```

During play, relevant passages from the selected campaign and its active rules system are supplied to the DM. **Sources consulted** beneath a turn links to the referenced files, with PDF page numbers where available. This supplements the deterministic rules engine; importing a book does not implement every rule in it.

### Native Star Wars D6

Choose **Campaigns → Star Wars: Galactic Rebellion** to start a native `weg_d6` session with a Rebel pilot, a field medic, and D6 equipment. **Edit D6 sheet** edits the six attributes, absolute skill pools, Force training, points, armor, and wounds. Untrained skills use their governing attribute; advanced skills and Force skills require training. The Dice tab rolls native pools such as `3D+2`, including the Wild Die.

The implementation follows the local **1992 WEG Second Edition** source, `../star wars/The Roleplaying Game 2nd Edition WEG40055.pdf`, particularly printed pages 28–30, 52–62, and 67. It uses that edition's wound progression: a second wound incapacitates. It does not use the later Revised & Expanded "wounded twice" step.

- **Checks:** Roll skill or attribute against a GM difficulty, with an exploding Wild Die and a choice of Wild-1 penalty or complication. Character Points add independent exploding dice. After a check or defense, **Add CP to last roll** spends points without rerolling, until another roll or action closes the window.
- **Force Points:** Double attribute and skill dice and pips before action and wound penalties. Weapon and armor dice stay fixed. Force and Character Points cannot combine in a round. Rest does not replenish points.
- **Combat:** **Start Imperial Patrol**, choose whether the winning side acts first or last, declare actions for each combatant, and roll any defenses before attacking. Multiple actions apply their dice penalty to the entire round. **Next Turn** resolves one action per actor in repeated passes; advancing past an unused action skips it. Initiative rolls again each round.
- **Attacks and defense:** Range or a GM base difficulty, normal/full dodge and parries, trained blaster/melee/brawling pools, armor by damage type, and weapon damage opposed by full Strength resistance. Use **Resolve enemy attack** on enemy turns. Attack/resistance Character Points can be selected before those rolls. Wounds replace HP and AC; native combat results remain in the chronicle after the encounter ends.
- **Recovery:** Stun penalties and unconsciousness, worsening wounds, mortal death checks, consumed medpacs with first aid, and natural healing after the required days of rest. A field medic can treat an unconscious player. A night's rest does not erase wounds.
- **Persistence:** Saves retain native sheets, wounds, points, and active combat declarations. Older AD&D-adapted Star Wars saves keep their original rules; start a new native campaign to use D6. The former `star_wars_2e` campaign ID remains an alias for new native sessions.

The native Force panel executes the 22 Force powers in the 1992 corebook. Native advancement tracks CP spending, instructors, intensive study, and adventure-end rewards. Dark Side controls resolve corruption checks, atonement, calls and redemption. Moral judgments, species-specific exceptions, instructor fees, and facilities remain GM adjudicated.

### Star Wars completion audit

The active development goal is complete coverage of the **1992 WEG Second Edition corebook already selected for this project**. The following is an implementation checklist, not a completion percentage. Existing general checks and GM sheet editing do not count as implementations of the dedicated subsystems below. Narrative judgments, fictional facts, and sourcebook decisions explicitly assigned to the GM continue to require GM input.

| Area | Current evidence | Remaining work / verification |
| --- | --- | --- |
| Character creation and species | All 16 printed templates, custom-template budgets, nine main species, four Droid chassis, reviewed GM-defined species, Tyia starting rules and saved deferred starting powers; creation/template/custom-species/starting-equipment tests and browser checks | Final source audit, remaining story-factor interactions and full-session coverage |
| Species and Droid play | Scene-conditioned species bonuses, rage/calm, immediate stamina retry, Droid software/refinement, cartridges, memory wipes, hardwiring, parts-based repairs; `test_weg_creation.py`, `test_weg_droids.py` | Full source audit of hardware interactions, remaining training exceptions, species story-factor workflow and complete-session coverage |
| Skills and action economy | Native skills, Wild Die, CP/FP, declared actions/defenses, scene Command chart, preparation/rushing and saved required-stage tasks; `test_weg_d6.py`, `test_weg_tasks.py` | Combined personal/ship combat and split fire, distributing individual points across aggregate group rolls, remaining opposed/social/technical skill procedures and each skill's exceptions |
| Personal combat and medical care | Physical cover/objects, concealment, called body/weapon shots, actual gear damage/ammunition/fire rates, reload/draw/settings, preparation, point-target frag/thermal grenades with timers/scatter/toss-away, saved bacta and natural care; native/tactics/medical/explosive tests and browser checks | Mines, scaled or obstructed blasts, further movement/medical exceptions and complete encounters |
| Force and morality | 22 core powers, Tyia timing/Alter rules and automatic powers, corruption/calls/atonement/redemption, persistent rare GM favors with one-use DSP consequences, and adventure rewards; Force/Dark Side/reward/template/favor tests | Final source-by-source audit and complete-session coverage |
| Vehicles and capital ships | Persistent native combat, scale caps, crew actions, shields, subsystem damage, collisions, nine craft presets, paid subsystem repair projects and replacement weapons; `test_weg_vehicles.py`, `test_weg_engineering.py` | Complete corebook craft catalog, capital crew/combined batteries, sensors, remaining damage/engineering interactions; starship modification mechanics are explicitly beyond this corebook's scope |
| Travel and hazards | Astrogation, all 66 gazetteer routes, installed hyperdrives/R2 memory, hyperspace timing/mishaps, saved vacuum emergencies, falling, fatigue/Willpower, shared-round swimming/drowning; navigation/hazard/shared-clock tests | Remaining environmental/atmospheric/vacuum cases, dedicated Force actions inside crew emergencies, full movement/chase procedures, lifting and other printed hazards |
| Equipment, creatures and setting | 61 source equipment/acquisition references, paid purchases with availability/license facts, distinct inventory IDs, actual loadouts, compatible ammunition, paid-once gear repairs/improvements, source metadata on new starter gear; equipment/context/starting-equipment tests and browser checks | Remaining conditional gear functions, complete creatures/settings and craft catalogs; campaign scenes that exercise the full rules sequence |
| Persistence and end-to-end play | Native saves, travel/repair context and chronicle export; browser checks for creation, hyperspace travel/arrival, hull breach round persistence, ship repairs, advancement and rewards | Complete-session scenarios spanning all systems; final requirement-by-requirement completion audit |

### Native character creation, species & Droids

Open **Create a native D6 character** above the story. Custom templates allocate exactly the species' PC attribute budget: Human and most listed species have 18D, while Gamorreans and Twi'leks have 17D. Attribute limits, native Move, and species maximums come from the source. Spend 7D on skills, at most 2D per skill before species bonuses; an optional 1D package grants three +1D specializations. Medicine requires First Aid 5D. Starting Force skills cost one attribute die each, require a plausible training background, and begin at 1D; selected powers must have trained skills and prerequisites. All new characters start healthy, with 5 CP and 1 FP (2 if Force-sensitive).

Ewoks double initial hide/search/sneak allocations and cannot begin with vehicle or starship operations/repair skills, except glider. Gamorreans double melee/brawling/thrown-weapon allocations. The species scene controls apply Ewok scent, Sullustan senses/familiar destinations, Mon Calamari environmental modifiers, and Wookiee claws/rage. Rage requires actual immediate deadly danger; calming requires controlled enemies and a Moderate penalized Perception check, with optional FP or GM-recorded close-friend coordination. Gamorreans can retry their immediately preceding failed stamina check once without using another declared action. Language, reputation, and other story factors still need the GM's actual fictional rulings.

The R2, 9G, K4, and 3PO Droid chassis use their printed attributes **plus 1D to every attribute**, retain their equipment, and receive 10D to allocate to skills. They receive no example NPC skills. Droids require an owner, cannot be Force-sensitive or train Force skills/powers, and have a 13D skill ceiling. R2/9G graspers and 9G conditional sensors have native check controls. K4 body armor and internal rifle are recorded. Wound codes are reused internally for mechanical damage, but Droids do not make organic mortal-death checks, naturally heal, or receive chassis repairs from medpacs or organic Force healing.

Choose **Review new D6 character**, then either **Recruit this character to the party** or **Save current adventure & start this character**. Recruitment keeps the current hero, retains the companion's actual native weapon type, and puts carried gear in party inventory. Starting a new adventure first saves the full previous adventure to a unique `before_character_creation_…` slot. The new hero starts a fresh adventure with new points, history and advancement state. A stale review cannot replace a changed adventure.

Use **Droid programming & repairs** for installed-skill refinement, introductory software, specializations/Medicine prerequisites, purchased skill cartridges, specific tasks, attachments, repairs, hardwiring and memory wipes. New skills begin one pip above their attribute; the programmer must know that skill at least 2D above the Droid's new rating. Refinement spends the Droid's CP, improves one pip, and respects adventure limits. Software, connected computers, actual commercial costs, work times and situational modifiers are recorded by the GM; time passes in the whole scene and fleet. Hardwiring adds 30 difficulty. Wipes remove learned skills/tasks while retaining hardwired skills and equipment. Repairs require actual replacement inventory, use the damage-appropriate repair band, and take at least 15 minutes, then one hour, then two hours on retries. Successful work, failed attempts, costs and resulting state are saved and exported.

Creation/species/Droid sources: local `../star wars/The Roleplaying Game 2nd Edition WEG40055.pdf`, PDF pp.11, 13, 16, 126–130, 147–149 (printed pp.10, 12, 15, 133–137, 158–160), with Droid programming/repair on PDF pp.85–86 (printed pp.88–89). The remaining completion checklist above stays open until its source audits and end-to-end checks pass.

### Native adventure-end rewards

Open **Advancement & Force training → Finish adventure & rewards**. Every normal Force Point declaration, Reduce Injury expenditure, Transfer Force expenditure, and successful Dark Side call records a saved expenditure for its user, including crew and companions. A successful call's granted point is spent immediately without deducting a stored point; its eventual return is reviewed under the same moral rules. Failed calls grant no point to review. Character Point awards remain explicit GM decisions.

Review each party member and each pending use, supply reasons, name the next adventure, and select **Preview adventure rewards**. **Finish adventure & award rewards** applies the whole party's rewards and records the adventure boundary together. A stale review, missing or duplicate expenditure, invalid party member, or point overflow rejects the entire operation. The completed adventure cannot be claimed again. The older boundary-only control grants no rewards and requires pending Force uses to be reviewed first.

- **Ordinary characters:** unheroic uses are lost; heroic uses return one FP; heroic uses at a dramatically appropriate moment return two. These are GM judgments about the actual scene, independent of whether the dice succeeded. Reduce Injury may qualify as heroic when saving the Jedi also saves others; Transfer Force is always heroic.
- **Evil uses:** record their moral consequence in **Dark Side & atonement** first, then link that saved event in the reward review. Reviews never award a duplicate DSP or reroll corruption. Ordinary characters lose evil-use points, including at a decisive moment. Consumed characters receive two FP only for evil at a dramatically appropriate moment, and cannot receive ordinary adventure CP or the zero-start heroic award. A character consumed by adventure end uses these restrictions even for earlier spending. Redemption forfeits pending FP claims along with held points.
- **Doing the Right Thing:** a character who began the adventure with zero FP may receive one for GM-confirmed heroism at a dramatically appropriate moment, regardless of risk. Spending the last point during this adventure does not qualify. Starting balances are captured at each boundary; older saves with an unknown starting balance become eligible for tracking at the next boundary.
- **Maximums:** non-sensitive characters keep at most five FP. Every excess point becomes three CP; voluntary conversion below the limit is unavailable. Force-sensitive characters have no rules maximum (the implementation's storage limit remains one million).
- **Persistence:** pending uses, rulings, starting balances, completed awards, and reasons survive saves and appear in the chronicle. Older saves retain explicitly recorded Transfer Force returns; unrecorded past ordinary spending is not reconstructed. Completing an adventure advances no time, heals no wounds, and does not approve atonement automatically; its completed boundary becomes available for the separate GM conduct review.

Reward sources: local `../star wars/The Roleplaying Game 2nd Edition WEG40055.pdf`, PDF pp.51–54 (printed pp.54–57), Reduce Injury on PDF p.138 (printed p.149), and Transfer Force on PDF p.141 (printed p.152).

### Native Dark Side corruption & atonement

Open **Dark Side & atonement** above the story. It supports the party, personal opponents, current ship crew, and recorded instructors. Each new Dark Side Point for an unconsumed character rolls a **plain 1D6**, without a Wild Die, Character Points or Force Point bonuses. A result **strictly below the new DSP total** causes a fall: the first point cannot consume a character; a 6 at six points survives; seven points always consume. A fall retains existing CP/FP, marks the character as GM-controlled, and removes forbidden Emptiness effects. Subsequent DSP give a consumed character one CP instead of another fall check. Consumed characters cannot receive ordinary adventuring CP awards.

**GM: award a Dark Side Point** records the moral decision and reason. Ordinary awards require that the player was warned and proceeded. Force-sensitive characters receive points for evil; Force-trained Jedi can also receive them for knowingly failing to make a reasonable effort to oppose evil. Ordinary non-sensitive characters receive the evil-use point when spending a Force Point. The latter control records an already-spent point; it does not deduct another. An evil temptation during active atonement does not require a repeated warning. Injure/Kill, telekinetic attacks, and Force teaching penalties already award/check their points automatically; do not manually award those same consequences twice. Post-roll CP boosts retain the original corruption event and do not reroll it.

**Atonement** is available to living, unconsumed characters with DSP, including non-sensitives. Record an intention to follow the Jedi code, actively oppose evil, fast and reflect. Use the advancement panel to record completed adventure boundaries, then review those adventures here in order. A boundary, rest, study, or elapsed time does not approve conduct. Two consecutive GM-approved completed adventures remove one DSP and grant no CP or FP. Rejection resets the two-adventure count; receiving another DSP interrupts and archives the cycle. A completed cycle cannot be reused, and removing another point requires two further adventures. Fallen characters use redemption instead of ordinary atonement.

**Call upon the Dark Side** declares a Control or Perception action before the action phase or defenses; it consumes one declared action. Reserve another action to use the result. Non-consumed Force-sensitives start at Easy, non-sensitives at Moderate. An intention not meant to cause harm or pain adds two difficulty bands. The call always gives a DSP and checks corruption, even on failure. Success grants one FP spent immediately for the round; no stored FP is added. A normal FP can be declared as well. Characters refusing to believe in the Force cannot call; stock Imperial stormtroopers and TIE/Star Destroyer crews record this refusal. NPC instructor records need full native encounter sheets to perform action rolls.

Consumed callers start at Easy and increase one difficulty band for each additional call in the adventure, with the same non-harmful modifier. Adventure boundaries reset this count. The book gives no numeric bands beyond Heroic; attempts beyond that require GM adjudication. A failed call by a consumed character rolls another plain 1D6: the saved demand must be paid with that many CP or one whole die from a chosen attribute/Force skill. Paying is a penalty, not spending CP for bonus dice. Insufficient CP requires choosing a die loss. Demands block further skill actions and training and survive rounds, rest and saves. A pool reduced to no whole die, including 0D+1/+2, is treated as the book's fatal 0D result: consumed and dead. The chosen pool alone is reduced; other absolute learned skills are unchanged. Fatal zero-attribute sheets can be saved and loaded.

Normal and Dark Side FP boosts affect personal pools and Strength-based damage, never weapon, armor, hull or other equipment dice. This engine interprets the explicitly allowed additional FP as another doubling: **normal + Dark Side = ×4 personal pools**. The corebook does not spell out this stacking arithmetic, so it is an explicit convention. Character Point dice are forbidden for the entire calling round, even when the call fails, including defense, resistance, post-roll boosts and ship crew actions. Scene check and Force controls use the call's remaining declared actions before starting a new round. No later R&E per-DSP temptation bonus dice are imported.

**Redemption** follows printed p.58. A fallen party hero defaults to GM control; the GM can authorize a player redemption arc lasting at most three adventures from the fall. The deadline is saved and checked at adventure boundaries. Expiry makes the character permanently GM-controlled, even if later redeemed. Sheets stay available for GM resolution rather than being deleted; player-action narration is blocked under GM control, while Story and native mechanical panels remain available to the GM.

A **Moment of Doubt** requires a real confrontation in which a present, conscious Jedi of the Light affirms the Light Side's power. Choose that Jedi and record a unique confrontation key. The target loses DSP equal to the Jedi's whole Control dice count plus one plain 1D6, ignoring pips, temporary boosts and action penalties. The same confrontation key cannot be reused for that character. Reducing DSP to zero redeems. A **heroic sacrifice** risking certain death in defense of the innocent, in a Light Jedi's presence, also redeems; the GM may record actual death as part of that sacrifice. Redemption requires settling an outstanding failed-call demand first.

The final redemption toll removes all held CP and FP. To prevent recovering pre-redemption reserves afterward, suspended CP and unclaimed prior heroic FP returns are also forfeited. Learned skills and powers remain. A redeemed hero returns to player control only during an authorized, unexpired redemption arc; a continuing NPC remains GM-controlled. Ordinary sheet editing preserves corruption ledgers and cannot bypass DSP checks or change consumption. **GM: legacy / explicit corruption correction** records a deliberate import/correction without retrospective dice or a redemption toll and logs its reason. Older saves get empty ledgers without retrospective fall rolls.

Corruption events, atonement reviews, calls, failed demands and redemption deadlines persist in saves, history, chronicles and narrative context. Actual moral judgments, scene eligibility, and rare Dark Side “favors” remain with the GM. The adventure-end reward review handles Force Point returns: consumed characters receive them only for evil at the dramatically appropriate moment, and ordinary heroic Transfer Force uses return no points for them. These are the **1992** rules, sourced from local `../star wars/The Roleplaying Game 2nd Edition WEG40055.pdf`, PDF pp.16, 53–55, 133 (printed pp.15, 56–58, 140).

### Native advancement & Force training

Expand **Advancement & Force training** above the story. Select the hero or a native companion, an advancement type, and self-study or a qualified instructor. **Review training cost** shows the exact CP charge, new rank, time, and relevant rules before **Pay CP & begin study**. Points are paid up front; ranks and powers remain unchanged until study finishes. One intensive project can run per student. **Record intensive study** credits explicitly completed days and advances real scene time for everyone, including Force durations, mortality and occupied-craft countdowns. Ordinary rest and narration do not credit study days. The API can record several selected students studying concurrently with time passing once. An interrupted or abandoned course refunds neither CP nor days.

**Basic skills** advance one pip at a time, costing the current whole dice number. A new skill starts one pip above its governing attribute. Trained study takes 3 days at 4D or less, 7 days above 4D through 7D, and 14 days above 7D; self-study doubles these durations. Each additional CP saves one day, to a minimum of one day. A teacher must equal or exceed the target rank; a basic skill or one of its specializations can qualify the teacher. New unusual/custom skills require an assigned attribute, an instructor, and GM-confirmed facilities.

**Specializations** cost half the current whole-dice cost, rounded up. A new specialization starts one pip above its parent; this is advancement, not the character-creation allocation of three specializations for 1D. Parent and specialization advance separately. **Advanced Medicine** requires First Aid 5D, begins at 1D independent of Technical, costs twice the usual CP, and takes triple normal training time. Its dice augment First Aid rolls. Medicine is the advanced skill supplied by this corebook; other advanced skills need GM rules.

The same basic skill, specialization, advanced skill, or Force skill can be advanced only once in an adventure window. **GM: awards & adventure boundary** records earned CP with a reason and marks the boundary after an adventure to renew that eligibility. Awards do not reset eligibility; a boundary grants no CP and passes no time. A course reserves its skill increase when payment is made; completion in a later window uses that later window too. Cancellation leaves the reservation used. These reservations prevent duplicate projects and repeated included-power awards.

**Attributes** cost ten times their current whole dice per pip. Study takes two Standard Months at 4D or less, six above 4D, doubled without an instructor. Extra CP cannot shorten it. At completion the engine rolls the unmodified current attribute against the species maximum; equal or lower succeeds. Success also raises governed basic skills and specializations one pip, preserving their absolute pools; advanced skills stay unchanged. Failure grants no increase and holds the CP in suspension until after the next adventure. The GM can then **release held CP** once; a new attempt starts a new course. The book does not specify a fuller retry procedure, so this release is explicit and logged. Human defaults are 4D attribute maxima and Move 10/12. Record other species' maxima in **Edit D6 sheet** before advancement. **Move** costs the current Move to gain one meter, up to the species maximum, with no book-specified training time. Becoming **Force sensitive** costs 20 CP, immediately grants one Force Point, and is permanent; it grants no skills or powers.

**Force instructors** need at least 3D in each skill taught and sufficient rank for the student's target. A Jedi studying with a master cannot take a pupil. A normal instructor takes one active Force pupil; a GM-recorded full-time NPC instructor can take a small group. Party teachers use their live sheets; other teachers are recorded under **GM: instructors** with actual ratings and learned powers. Teaching a student with Dark Side Points awards the teacher one Dark Side Point when instruction starts, recorded once per course. Teacher availability and qualification are checked again when study is credited.

Learning a **new Force skill** requires sensitivity, a teacher, 20 CP, and ten training weeks; the skill becomes 1D only at completion. It includes three powers using that skill, subject to required skills, prerequisite powers, and instructor knowledge. Select them with the course or keep unselected choices recorded with that instructor; the latter do not grant usable powers. This also handles the core catalog's limited Alter-only choices without inventing powers. **Improving a trained Force skill** with a teacher costs its whole dice number and takes one training week, with one instructor-known power included. Self-study doubles the pip cost and takes a Standard Month, reducible only to a training week. A bundled power unknown to an otherwise qualified instructor adds 5 CP and a week; unaided bundled research uses the standalone 10 CP rate plus a week. That additional week can be reduced separately to one day. **Force power only** study grants no skill pip and costs 5 CP when the instructor knows it, otherwise 10 CP; its duration is supplied by the GM because the book gives no separate duration for this case. No prerequisite powers are silently granted.

Timing conventions are displayed in the panel: training weeks use the explicit **seven-day** example on printed p.14, while a **Standard Month is 35 days** (the calendar on printed p.132 uses five-day standard weeks). Advanced training follows the main 4D/7D thresholds; the example's later “above 6D” conflicts with them. The unaided Force paragraph's “Character Point cost” being reduced to “one week” is treated as a training-time typo. These choices are explicit instead of importing Revised & Expanded advancement rules.

Saves retain active projects, paid costs, completed days, instructors, adventure eligibility, suspended points and included power choices. Older saves load with no projects and no automatic awards. Training and awards appear in history and exported chronicles, and the narrative context includes pending study. **Edit D6 sheet** remains a GM correction tool; active study blocks rank edits, and ordinary sheet edits preserve the advancement ledger. This workflow covers standard organic training. Use Droid programming & repairs for Droid software and hardware work; Tyia and other species/culture-specific training exceptions remain in the completion audit.

Advancement sources: local `../star wars/The Roleplaying Game 2nd Edition WEG40055.pdf`, PDF pp.11, 13–16 (printed pp.10, 12–15), PDF pp.125–126 (printed pp.132–133), and PDF pp.134–136 (printed pp.145–147).

### Native Force powers

Use **Advancement & Force training** to learn or improve **Control / Sense / Alter** and purchase powers with CP and study time. **Edit D6 sheet** also supports explicit GM corrections: selecting a power there selects its prerequisites; removing a prerequisite removes its dependent powers. Existing Force-sensitive heroes retain their current training and start with no automatically learned powers. The editor can equip a standard 5D lightsaber; its native base difficulty is 20.

Expand **Force powers** above the story. Select a party member, personal opponent, or active ship crew station, a learned power, and any target, relationship, proximity, or intended effect. The panel shows the book's difficulty notes and source page. Defaults use the upper end of each difficulty band; **GM difficulty choices** can choose a base within the band or record an opposing total already rolled. Affect Mind requires a declared effect and a GM Alter complexity. Fictional facts, surface thoughts, memory contents, illusions, and environmental effects are supplied by the GM after the rolls.

Each Control, Sense, or Alter component is a separate action. **Begin** resolves the first component; **Continue activation** resolves subsequent components. Scene declarations can include all components in one round with multiple-action penalties, or stage them in consecutive rounds. In combat, declare sufficient actions and use the normal action passes. Preparation occupies full otherwise unused rounds: Magnify Senses needs three rounds; healing, Resist Stun, and Transfer Force need a minute. Use **Advance Force time** for quiet preparation outside combat or normal combat rounds and Continue during combat. Unfinished activations, effects, and the latest unresolved component's CP window survive saves. CP can improve that component without rerolling before another roll/action; completed automatic damage/reactions use CP selected in advance.

Kept-up powers cost one ongoing action per required Force skill in later rounds, including penalties on piloting and gunnery. The activation round already includes the declared component actions. Stun or worse drops maintained powers; another injury requires a new Control Pain activation. Recipient pain effects end when the caster drops the power. Dropping a power refunds no actions or points. Rest and Force time advance durations and mortality; they do not grant new powers or points.

Lightsaber Combat follows the book's main paragraph: **Sense adds to lightsaber attacks/parries; Control adds or subtracts damage dice**. The worked example reverses those skills, so the implementation explicitly follows the prose. Force Points double the character's contributions, while the weapon's 5D stays fixed. Missing a saber's base difficulty by more than ten causes normal weapon damage to its wielder. A failed activation cannot be retried in the same battle. Roll **Lightsaber parry** in the defense controls before attacks; active Lightsaber Combat allows it to parry blasters. **Prepare personal energy reaction** can reserve an additional Control action to redirect a specified shooter's parried bolt at a declared target, using the original bolt's damage. Absorb/Dissipate Energy must be prepared before a personal energy hit and rolls against 15 + its actual damage; it does not protect a ship's hull.

Control Pain suppresses penalties from the following round without healing or stopping mortal death checks. Remain Conscious rolls first on the next round after a qualifying injury and permits one further declared action; Control Pain can sustain consciousness afterward. Reduce Injury is an immediate injury reaction: it reduces a new incapacitating, mortal, or killing injury to wounded, costs a separate Force Point without dice doubling, and records a permanent sacrifice for a killing blow. Resolve it before another roll. Accelerated healing grants at most two +2 natural rolls for the current day; another's rolls require the granting Jedi's presence and touch. Transfer Force spends a point, stabilizes a willing touched mortal patient in hibernation for up to six weeks, and records the heroic point owed back at adventure end. Further injury ends stabilization.

Hibernation blocks actions until its declared time or a GM-confirmed waking stimulus. Emptiness tracks meditation, exit eligibility and the Control exit roll, its incoming Force difficulty ward, and a temporary +6 minus Dark Side Points bonus lasting as long as meditation. Air, food, water, and waking stimuli are adjudicated by the GM. Life Detection offers free opposed checks for approaching living creatures within ten meters. Telekinesis tracks one object per activation; attacking requires a separate Control action and applies its mass-based damage and the 1992 scale caps. Injure/Kill requires touch (a successful brawling attack in the same combat round) and uses Alter against the target's resisting mind for damage. Both harmful uses award their explicit automatic Dark Side Point, including a failed attempt. Telepathy and Affect Mind reject Droids.

Force sources: local `../star wars/The Roleplaying Game 2nd Edition WEG40055.pdf`, PDF pp.136–141 (printed pp.147–152), with lightsabers on PDF p.146 (printed p.157). This catalog uses the 1992 edition; it does not import later Revised & Expanded powers such as Concentration or Force Lightning.

### Native D6 Vehicles and Starships

In a Star Wars session, open **Vehicles & starships** above the story. Add a craft from the source-based catalog: YT-1300, Ghtroc freighter, X-wing, Y-wing, TIE/ln, Rebel combat airspeeder, AT-ST, Corellian Corvette, or Imperial Star Destroyer. The fleet is saved with the adventure. Existing native saves start with an empty fleet.

**Edit craft & crew** changes hull/body strength, maneuverability, shields, movement ratings, pilot, gunners, shield operators, and engineers. Mounted weapons have their own scale, fire control, damage, fire arcs, ranges, system group, ammunition, and assigned operator. Crew skills come from the actual party sheets, with native attribute fallback for untrained skills. The 1992 skill distinction applies: **vehicle blasters uses Dexterity**, while starship gunnery and piloting use Mechanical. Capital ships use their capital piloting/gunnery/shields skills.

To play an encounter:

1. Choose a party craft, **Space** (units) or **Ground / atmosphere** (meters), and one to eight enemy craft. Surface vehicles cannot enter space combat. One party craft is active at a time. Capital ship presets represent individual stations/emplacements, not entire fleets or batteries; NPC crews use scenario ratings. Preset source notes identify representative equipment and scenario ammunition loads.
2. Choose whether the side that won Perception initiative acts first or last. Select each **Declaration station** and declare that operator's total actions, pilot moves (up to four), and any Force Point. A normal move counts as an action. A single half-speed move is free on Very Easy through Moderate terrain; harder terrain still requires an action and a difficulty reduced by three bands.
3. Roll vehicle dodges and deploy shields before actions begin. Piloting adds the craft's remaining maneuverability; gunnery adds the weapon's remaining fire control. A normal vehicle dodge uses the higher of the base attack difficulty and its capped dodge; a full dodge adds both and must be the pilot's only skill action. A free half-speed move remains possible. Each operator tracks their own multiple-action and injury penalties. Force Points double crew skill dice/pips, **never equipment dice**.
4. Allocate shields to front, back, left, and right arcs within the remaining pool. Default deployment difficulties are 10/15/20/30 for one/two/three/four covered arcs, with a GM override. Successful energy shields add only to hull resistance against energy attacks from their assigned arcs. Shield deployment is a defensive action and must be renewed each round. **Add CP to last craft defense** can improve the latest dodge or shields roll without rerolling, before another roll/action closes the window. Gunnery and movement CP are selected before rolling.
5. Use the **Current station** controls for movement, mounted fire, or system actions. The GM supplies distance, relative arcs, terrain, maneuver difficulty, and accidental collision angle; the panel does not infer positions from a tactical map. Ranges come from the mounted weapon, with a GM base-difficulty override. **Next crew action** resolves repeated action passes and rolls new side initiative each round. It skips an unused current skill action; skipping mandatory frozen-controls piloting checks causes an automatic crash.

The implementation uses the **1992 scale die-cap charts**, not R&E bonus dice. Attack, dodge, damage, and resistance each use their appropriate chart, including weapons whose scale differs from their platform. Capped Wild/CP sixes still explode, every die in the chain is capped, and pips remain unchanged. Some scale pairs cannot hit, dodge, damage, or resist at all.

Weapon damage is opposed by hull/body strength and eligible shields, without HP or AC. Vehicles and starships use separate subsystem-damage tables. Light damage can recur, heavy damage worsens on another light/heavy hit, and further structural damage to a severely damaged craft destroys it. Lost maneuverability, shields, speed, weapons, drives, and hyperdrive status persist. Damaged weapon groups can fail together.

Ion weapons bypass energy shields and cause temporary control penalties, frozen controls, or dead controls. Frozen craft maintain their declared speed and direction and still need piloting checks. Missiles expend ammunition even on misses, add difficulty for the target's declared speed, and drop the launcher's particle shields for the round; a starship with particle shields down loses 2D of hull resistance. Tractor beams establish a lock, allow one unit of pull per declared use, and can be opposed with hull escape or released by their operator.

Failed maneuvers can impose control penalties, spins, or collisions. Collision damage uses declared speed, failure severity, and collision angle. Intentional rams damage both craft with the appropriate scale caps. Set **Airborne in gravity** and altitude in the craft editor when relevant: destroyed propulsion can cause a crash or fall even at half speed. Exposed crew suffer character-scale passenger damage resisted by full Strength; the GM can shelter remote crew, while a destroyed occupied gun emplacement still damages its gunner. Evacuation assumes the GM confirms a safe exit or escape pod; survival outside the craft is adjudicated separately.

Generator overload and structural-breakup countdowns advance with rounds. An engineer can shut down an overloaded generator, sacrificing power to prevent the explosion. **End craft encounter** retains damage, injuries, ammunition, and points. It does not stop countdowns: rest advances fleet time, and **Advance fleet time 1 round** is available outside combat. Crew remain aboard until they evacuate, safely disembark, or board another craft. Pending destruction can injure occupants after combat ends.

Use **Craft repair projects** and **Hyperspace navigation** for the dedicated procedures below. Full capital-crew coordination/combined batteries and detailed positioning still need implementation. **GM damage and completed repairs** remains an explicit correction tool for work already adjudicated by the GM. Rest never repairs hull or equipment or refills ammunition. Character and craft encounters are mutually exclusive; finish the craft encounter before personal mechanical checks, recovery, or sheet edits. Saves preserve active stations, action passes, shield arcs, locks, timers, and defense CP windows; mounted-fire results remain in the exported chronicle.

Vehicle rules were checked against the local WEG40055 PDF: p.68 (printed p.71) for scale; pp.89–94 (printed pp.92–97) for movement, collisions, vehicles, and passenger damage; pp.101–103 for starship damage, shields, ion weapons, missiles, and tractor beams; pp.96–100 and 109–114 for the catalog. The stock YT-1300's contradictory atmospheric Move listing uses the book's Space-to-Atmosphere conversion table and is identified in its source note.

### Native prepared tasks and scene Command

Use **Combined actions, preparation & focused tasks** to declare a real exclusive task and every required stage, skill, difficulty and duration before work. Preparation adds equal preparation time and +1D on eligible skills; the printed exclusions also apply to specializations. Rushing is available from two rounds, halves work time and dice, and requires an explicit GM up/down decision whenever dice, pips or rounds produce fractions. More time, failed checks or narration never complete a stage automatically. Unrelated scene time interrupts saved exclusive continuity; workers must finish or cancel the project before taking other actions.

Combined scene tasks use actual party workers, a named commander, contact, a visible shared target, matching ranges and a GM hands-on limit. The original 15×8 Command chart rounds worker counts and skill averages down; partial Command results determine the actually coordinated workers in declared priority order. A participating commander takes −1D on both actions. Command CP/FP are paid once and persist. The group check uses the coordinated workers' actual average whole skill dice plus the source bonus. Generic task outcomes record what was checked; they do not bypass the paid repair, Droid, training or equipment workflows. Encounter-level combined attacks, split fire and allocating personal points across aggregate workers remain in the audit.

Task procedures use WEG40055 (1992), printed pp.30, 55, 58, 65, 68–70.

### Native environmental hazards

Use **Environmental hazards** for actual party members. Falling uses the standard-gravity distance table (3–6m 2D, 7–12m 3D, 13–18m 4D, 19–30m 5D, 31–50m 7D, 51m+ 9D), opposed by full Strength and physical armor. Between whole-meter bands the engine rounds distance up; falls below three meters or nonstandard gravity need a GM damage code. Actual GM impacts can injure an actor during another task without granting extra actions.

Exertion advances the whole scene before a real Stamina check. Failure causes a single −1D fatigue penalty; the third failed check causes exhaustion. Actual rest equal to accumulated exertion clears fatigue, or twice that time after complete exhaustion. Willpower can drive a character onward with harder checks; stopping or failing the push requires double rest. The follow-up can be declared with the initial check as two actions, using normal penalties and separate actual CP costs. If the failed Stamina check would genuinely cause environmental damage, the GM can provide its already-resisted damage margin; pushing worsens the resulting injury by one wound level. Gamorreans can declare their one immediate Stamina retry before fatigue, injury or Willpower consequences; this also works for saved vacuum breathing checks.

A failed Swimming check starts drowning when breathing is actually at risk. At the beginning of each later saved round, a plain 2D total below that swimmer's drowning-round count causes death. Each conscious swimmer has one self-rescue attempt at the next difficulty band, without the −3D penalty applied to other actions. Multiple swimmers share one scene clock and retain their own drowning duration; additional swimmers can enter the current round without advancing it again. Actions, CP/FP, passed opportunities, completed GM rescue facts and death checks persist. Droids do not drown; the GM explicitly records other actual breathing protection. Routine checks and time skips cannot bypass these rounds. Heroic checks have no higher printed band, so a harder Heroic Willpower or rescue target requires an explicit GM difficulty.

Hazard procedures use WEG40055 (1992), printed pp.79, 86 and 97. Other environmental cases, movement/chases and dedicated Force actions during these emergencies remain in the audit.

### Native craft repair projects

Open **Craft repair projects**, select the actual damaged subsystem, and review its difficulty and parts quote. The source tables cover maneuverability, lost Moves, shields, drives and mounted weapons. Hyperdrive repair uses Moderate difficulty with an explicit GM price; systems without a printed repair table require a GM procedure, difficulty and cost. Quotes use the actual craft or weapon value. Destroyed weapons need replacement and installation; destroyed craft cannot be restored by a normal project. Hull breaches remain recorded for separate GM resolution.

Starting a project purchases parts once or reserves one explicitly appropriate inventory item. Failed attempts retain those paid parts. Each attempt uses a real conscious party technician's relevant skill, CP/FP and native roll, and advances time for everyone. Standard retries are 15 minutes, one hour, one day, then two days; walkers use six hours on the second attempt, and vehicle blasters use two hours from the third attempt. Custom times require a GM explanation. Changed subsystem damage invalidates an old project; cancellation gives no automatic refund. Successful work restores only the selected system. The editor preserves the project ledger.

Repair procedures use WEG40055 (1992), printed pp.87–91. This edition explicitly leaves starship/vehicle modification rules outside the corebook; personal armor and blaster modification procedures remain in the completion audit.

### Native hyperspace travel and hull breaches

Open **Hyperspace navigation** after adding a starship and assigning its astrogator. The craft editor records main/backup hyperdrive multipliers, installed navigation equipment and actual location. Review a route from the complete 12-system, 66-pair printed gazetteer or enter the GM's actual base duration. Confirm boarding and at least 50 space units of planetary clearance. Only installed working equipment applies; an R2 supplies navigation support for a stored route, with ten preprogrammed jumps maximum. A Sullustan's +1D applies to this actual previously visited destination, including recorded arrivals, rather than carrying over an unrelated scene condition.

Frequency and hyperdrive multiply the base duration; hasty entry doubles the subtotal difficulty and duration. Missing navigation adds 30 difficulty and doubles the duration subtotal. Light/heavy damage adds 5/10 difficulty and actual travel hours. Actual extra hours lower difficulty one per hour; saved hours raise it. The engine applies actual-hour adjustments last and records that ordering convention in the quote.

Astrogation and plain-dice mishaps are saved. A miss above ten prevents entry; misses of one through nine use the printed mishap table. The source omits exactly ten, so that result waits for an explicit GM choice without rerolling astrogation. Dropouts require the actual location; a close call requires the damaged system. Arrival occurs when the shared travel clock expires and records the destination in the travellers' visited locations. Rest, repairs, Droid work and personal combat rounds advance that same clock. Countdown damage takes effect at its actual event boundary during longer actions.

A collision can leave a heavily damaged, breached ship and a saved crew emergency. The GM identifies actual exposure; existing sealed suits and Droids provide appropriate protection. An exposed character has an initial Moderate Survival opportunity to fit an available suit, or explicitly passes that opportunity if unable to attempt it. Later rounds require increasingly difficult Stamina checks before another suit attempt. Multiple actions, CP/FP, real suit quantities, unconsciousness and protected rescuers persist across save/load. Protecting the crew does not repair the breached craft. No unprinted vacuum death timer is invented. Routine scene checks, combat starts and time skips cannot bypass a pending navigation ruling or emergency.

Navigation uses WEG40055 (1992), printed pp.110–112. Remaining environmental cases and full Force-action integration in emergency rounds remain in the completion audit.

### 10. Character Creation & 4d6 Stat Wizard
- Customize your character's name, lineage, class, level, and alignment.
- **Roll 4d6 Drop Lowest (`4d6kh3`)**: Instant stat generator rolling authentic physical dice with breakdown and celebratory confetti.
- Real-time stat modifier calculations and HP adjustments.

### 11. Tactical Encounter & Combat System
- **Initiative Order Tracking**: Automatically rolls Dexterity-based initiative for all combatants, sorting turn order.
- **Visual Combatant Tracker**: Real-time HP bars, AC ratings, condition indicators, and active turn highlights.
- **Targeted Combat**: Click any enemy to target them, roll attacks with your equipped weapon, apply advantage/disadvantage, command companions, or unleash combat spells.
- **Target Recovery**: Target selection stays within the current encounter and moves to a surviving enemy when the selected foe is defeated. Enemy cards also support keyboard selection with Enter or Space.
- **Instant Spawning**: Launch an ambush or spawn any monster directly from the Compendium into an active encounter with a single click.

### 12. D&D Multi-Edition Compendium Database
- SQLite full-text index containing **over 520+ pre-indexed spells, monsters, and magic items** parsed directly from your local library (Spell Compendium, Magic Item Compendium, and Monster Manuals).
- Instant search by keyword, category (Spell, Monster, Item), and edition (2e, 3.5e, 5e).
- View complete stat blocks, descriptions, spell components, and source references.
- One-click "Fight Monster" button to spawn any bestiary entry directly into tactical combat.

### 13. Multi-Edition Rules Engine
- **AD&D 2nd Edition**:
  - Descending AC ($10$ unarmored to $-10$ godlike).
  - **THAC0** matrix: Target roll needed on $d20 = \text{THAC0} - \text{Target AC}$.
  - 5 Classic Saving Throws (*Paralyzation/Poison/Death*, *Rod/Staff/Wand*, *Petrification/Polymorph*, *Breath Weapon*, *Spell*).
  - Ability checks: Roll $1d20 \le \text{Ability Score}$.
- **D&D 3.5e**:
  - Ascending AC, Base Attack Bonus (BAB), touch AC, and flat-footed AC.
  - Critical threat ranges (e.g. 18–20) with separate **confirmation rolls** vs AC.
  - Saving Throws: *Fortitude* (Con), *Reflex* (Dex), *Will* (Wis).
  - Skill ranks with ability modifiers.
- **D&D 5e**:
  - Bounded accuracy & Proficiency bonus ($+2$ to $+6$).
  - Advantage & Disadvantage mechanics ($2d20$ take max/min).
  - 6 Ability Saving Throws matching stats.
  - Death saving throws tracking ($3$ successes / $3$ failures).

### Custom Dice Rolls

The **Dice** tab accepts standard rolls (`2d6+3`, `d20-2`), keep-highest and keep-lowest rolls (`4d6kh3`, `2d20kl1+5`), and mixed damage pools (`2d6+1d4+3`). Add `adv` / `advantage` or `dis` / `disadvantage` to a single d20 roll; supplying both cancels them. Bonuses apply after dice selection. Invalid expressions display an error without adding a roll to history.

Rolls are limited to 256 characters, 1,000 dice total, and 1,000,000 sides per die. Mixed pools report `die_type: 0` in the API; `raw_rolls`, `kept_rolls`, and `breakdown` retain the roll details.

## Development Checks

Run the backend smoke checks and deterministic dice/combat regression tests:

```bash
uv run python -m unittest discover -s tests -v
```

Check and build the frontend:

```bash
cd frontend
npm run lint
npm run build
```

---

## 🤖 Supported LLM Providers
Configure in the **LLM tab** inside the app:
1. **Offline Mock Engine (Default)**: Ready out of the box with zero configuration or API keys needed.
2. **Local Ollama**: Connect to `http://localhost:11434/v1` running Llama 3, Mistral, Qwen, or Phi.
3. **Cloud Models**: Direct support for Google Gemini, OpenAI (GPT-4o), Anthropic Claude, or OpenRouter.


### Curse of Strahd Reloaded development audit

New Strahd campaigns follow the supplied Reloaded opening: a 2nd-level sample ranger shelters at the Nightmare's Bridle in Daggerford before entering Death House. Ireena and Ismark are introduced through later play. The guide assumes five player characters; this starter creates one actual PC, so the GM must review the party and encounter balance. Existing saves and earned companions are unchanged.

The source-backed outline contains all 21 arcs A–U across five narrative acts, plus the epilogue. Act II is **The Shadowed Town**. The Adventure Summary places the 10th-level finale in **Act V: The Curse of Strahd**; its `Arc U - Dreams of Dawn.md` file happens to be stored under the Act IV archive folder. Imported reference cards and image assets supplement this outline; summary documents are not additional quests.

Reloaded takes precedence over the original adventure and refers to original material only where explicitly cited. Its baseline is **D&D 5e (2014)**. The sample ranger's 20 HP, two known 1st-level spells, two spell slots, saving throw proficiencies, and Defense fighting style match the local 2014 handbook. Other class/racial features, equipment changes and source-specific rulings remain GM adjudicated.

Verified data and regression coverage live in `dungeonforge/campaign/strahd.py` and `tests/test_strahd_campaign.py`. Sources are the supplied `../curse of straud/Curse_of_Strahd_Reloaded_Part_1_of_3.zip` entries `Introduction/Using This Guide.md`, `Chapter 3 - Running the Game/Adventure Summary.md`, and `Act I - Into the Mists/Arc A - Escape From Death House.md`; ranger rules are in `../5e/Player's Handbook.pdf`, PDF pp.84–85 / printed pp.90–91.

The saved GM progress workflow now catalogs 38 source milestone events, requires actual completion evidence and per-PC eligibility review, and awards the full listed XP to each eligible PC. Baseline XP is explicitly enrolled; old saves begin with unknown XP. Ledger totals give pending level guidance without silently changing classes, HP or spells. Arc status is a separate zero-XP review. Context and Markdown chronicles preserve actual reviews, exclusions and source paths.

Arc A also has its native **Death House dice clock**: the GM starts it at the Main Hall's six-o'clock chime, then reviews actual new-floor entries (once per floor), whole-room Perception/Investigation checks (each actual check), and short-rest time. The source's three dice, 20-minute pips, hourly chimes and midnight pursuit are saved, previewed without mutation, and protected against stale or repeated submissions. Early awakening, actual mound destruction and actual escape require distinct GM confirmation. Sacrifice does **not** free the party. Generic rest recovery is blocked during the explicitly active house; the clock records short-rest time and haunting reminders, while the GM reviews actual recovery separately. The clock creates no enemies, damage, XP or allies. Tests cover midnight, retries, partial rest at midnight, old saves, save/load, context and chronicle continuity.

The opening **Rose and Thorn** workflow now saves their actual meeting, Rose's secret-entry bargain and burial promise, the invitation to accompany the party, and each actual player host's separate friendly consent. Temporary Rose cantrips and Thorn's invisible, component-free Mage Hand permission are displayed without permanently editing known spells or inventing NPC statistics. Actual ability use can be recorded after separate normal spell resolution. Each child's remains has one reviewed carrier/location; dungeon coffins explicitly do not bring peace. Actual house exit ends saved possessions, while a separate actual outside burial of both sets of carried remains releases the children. Departure without burial leaves the quest unresolved. Preview, stale/retry protection, save/load, context and chronicle preserve evidence and source citations. These procedures follow Arc A's **Children's Room**, **Family Crypts**, and **Outside Death House** sections; they grant no automatic XP, healing or permanent magic.

Remaining campaign work includes the broader persistent Barovian calendar and deadlines, source-specific encounters and later NPC recruitment, the opening escape's Gustav/cult-obstacle procedures, a saved Tarokka reading, and complete-session tests through the finale. Source search and the quest outline provide reference; they do not implement those campaign procedures automatically.
