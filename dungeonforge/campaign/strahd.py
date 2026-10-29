"""Source-backed fresh-start data for the supplied Curse of Strahd Reloaded vault.

This module creates new presets only. It never migrates or modifies a saved game.
"""
from dungeonforge.context.story_cards import StoryCard
from dungeonforge.rules.base import AbilityScores, Character, Item, SpellSlot


ARCHIVE = "curse of straud/Curse_of_Strahd_Reloaded_Part_1_of_3.zip"
VAULT = "Curse_of_Strahd_Reloaded"
ACTS = (
    "Act I: Into the Mists",
    "Act II: The Shadowed Town",
    "Act III: The Broken Land",
    "Act IV: Secrets of the Ancient",
    "Act V: The Curse of Strahd",
)
ARCS = (
    ("A", "Escape From Death House", 1),
    ("B", "Welcome to Barovia", 1),
    ("C", "Into the Valley", 1),
    ("D", "St. Andral's Feast", 2),
    ("E", "The Missing Vistana", 2),
    ("F", "Lady Wachter's Wish", 2),
    ("G", "The Strazni Siblings", 2),
    ("H", "The Lost Soul", 2),
    ("I", "The Walls of Krezk", 2),
    ("J", "The Stolen Gem", 3),
    ("K", "The Fallen Abbey", 3),
    ("L", "The Den of Wolves", 3),
    ("M", "The Dragon's Manor", 3),
    ("N", "Tales of Vallaki", 3),
    ("O", "Dinner with the Devil", 3),
    ("P", "Ravenloft Heist", 3),
    ("Q", "A Shining Beacon", 3),
    ("R", "Trials of the Mountain", 4),
    ("S", "A Sword of Sunlight", 4),
    ("T", "The Three Fanes", 4),
    ("U", "Dreams of Dawn", 5),
)
SOURCES = {
    "opening": f"{VAULT}/Act I - Into the Mists/Arc A - Escape From Death House.md",
    "structure": f"{VAULT}/Chapter 3 - Running the Game/Adventure Summary.md",
    "precedence": f"{VAULT}/Introduction/Using This Guide.md",
    "party": f"{VAULT}/Chapter 1 - Beginning the Campaign/Session Zero.md",
    "ranger": "5e/Player's Handbook.pdf, PDF pp.84–85 / printed pp.90–91",
}


def arc_sources():
    """Keep archive provenance separate from the guide's narrative act structure."""
    result = []
    for letter, title, act in ARCS:
        archive_act = 4 if letter == "U" else act
        folder = ACTS[archive_act - 1].replace(":", " -")
        result.append({"id": letter, "title": f"Arc {letter} - {title}", "act": ACTS[act - 1],
            "archive": ARCHIVE, "path": f"{VAULT}/{folder}/Arc {letter} - {title}.md"})
    return result


def quest_catalog():
    """All 21 adventure arcs, with the finale under the summary's Act V."""
    result = {act: [] for act in ACTS}
    for item in arc_sources():
        result[item["act"]].append(item["title"])
    result[ACTS[-1]].append("Epilogue")
    return result


def build_preset():
    from dungeonforge.campaign.campaign_manager import CampaignPreset

    return CampaignPreset(
        id="strahd", title="Curse of Strahd Reloaded", edition="5e", genre="Gothic Horror / Dark Fantasy",
        banner_image="/static/images/strahd/Strahd%20at%20Dinner.png",
        description="Begin in storm-soaked Daggerford, survive Death House, and follow the Reloaded campaign through the liberation of Barovia.",
        source_folder="strahd", source_rule_system="D&D 5e (2014); Curse of Strahd Reloaded",
        rules_note=(
            "Use the supplied Curse of Strahd Reloaded guide with D&D 5e 2014 rules. Reloaded is the primary adventure: "
            "use original Curse of Strahd material only where the guide references it, and let Reloaded override conflicting details. "
            "The fresh opening is Arc A in Daggerford, before entering Barovia. The guide targets five 2nd-level player characters; "
            "the sample starter is one actual PC, so the GM must review party size and encounter balance rather than assume four extra heroes. "
            "Ireena and Ismark are met later in Arc B and join only through actual play. Reveal source secrets only when discovered. "
            "Adventure Summary supplies five narrative acts; Arc U is the Act V finale despite its archive folder under Act IV. "
            "Use the explicit GM progress and Death House clock controls for reviewed events and milestone XP. "
            "Calendar deadlines, NPC recruitment and source-specific encounters remain GM tracked; the quest list is an outline, not completed progress."
        ),
        initial_memory=(
            "The adventure is at its opening, Arc A: Escape From Death House. Varis Holimion is a 2nd-level High Elf ranger "
            "sheltering in the hayloft of the Nightmare's Bridle tavern in Daggerford on the stormy night before Highharvesttide. "
            "No campaign NPC has joined the party. Death House and the journey into Barovia lie ahead."
        ),
        default_authors_note=(
            "Style: heroic fantasy in a gothic horror setting; Tone: tense, atmospheric, humane. "
            "Follow the supplied Reloaded scenes and current discoveries. Begin in Daggerford at the Nightmare's Bridle; "
            "introduce Barovia and its NPCs through play. Treat future arc notes as GM reference, not events already experienced. "
            "Keep meaningful choices, fair foreshadowing, NPC relationships and recorded consequences."
        ),
        prologue_prompt=(
            "Rain hammers the roof of the Nightmare's Bridle in Daggerford. Beyond the stable walls, "
            "the town prepares for Highharvesttide: warm windows glow above muddy streets, and distant laughter carries through the storm. "
            "Your shelter for the night is a patch of hay beneath a leaking roof. Thunder rolls overhead as you settle your belongings beside you. "
            "What would you like to do?"
        ),
        starter_character=Character(
            name="Varis Holimion", race="High Elf", class_name="Ranger", level=2, alignment="Chaotic Good", edition="5e",
            abilities=AbilityScores(str=12, dex=16, con=14, int=13, wis=15, cha=10),
            current_hp=20, max_hp=20, ac=16, gold=45, proficiency_bonus=2,
            saving_throws={"str": 1, "dex": 1},
            skills={"nature": 1, "stealth": 1, "survival": 1, "perception": 1},
            inventory=[
                Item(name="Longbow", quantity=1, item_type="weapon", damage="1d8", equipped=True),
                Item(name="Arrows", quantity=20, item_type="ammunition"),
                Item(name="Shortsword", quantity=2, item_type="weapon", damage="1d6"),
                Item(name="Studded Leather Armor", quantity=1, item_type="armor", ac_bonus=2, equipped=True),
                Item(name="Potion of Healing", quantity=2, item_type="potion", description="Restores 2d4+2 HP"),
            ],
            spell_slots={"1": SpellSlot(level=1, current=2, max_slots=2)},
            known_spells=["Hunter's Mark", "Cure Wounds"], companions=[],
            notes=(
                "Sample 2014 ranger for the Reloaded opening; customize before play. HP uses the fixed d10 values: "
                "10+2 at level 1, then 6+2 at level 2. Defense fighting style adds +1 AC while wearing armor "
                "(studded leather 12 + Dexterity 3 + Defense 1 = 16). Class proficiencies: Nature, Stealth, Survival; "
                "elf Perception; Strength and Dexterity saves. The GM adjudicates other class/racial features and equipment changes. "
                "The guide assumes five PCs; this starter creates one PC and no unearned NPC allies."
            ),
        ),
        story_cards=[
            StoryCard(id="strahd_reloaded_opening", title="Reloaded Opening: Daggerford", keys=["daggerford", "nightmare's bridle", "highharvesttide"],
                entry="Arc A begins with 2nd-level characters in Daggerford on the eve of Highharvesttide. The Nightmare's Bridle offers its stable hayloft as shelter from a storm. Death House draws the adventurers onward; their arrival in Barovia occurs after they escape it. Use the actual party and its chosen hooks.",
                card_type="location", priority=150),
            StoryCard(id="strahd_card", title="Count Strahd von Zarovich", keys=["strahd", "vampire lord", "zarovich", "ravenloft"],
                entry="Strahd von Zarovich rules Barovia from Castle Ravenloft. Follow the supplied Reloaded profile, motives and staged encounters; reveal his secrets as the party discovers them. The campaign begins outside his realm, in Daggerford, before Death House transports the party into Barovia.",
                card_type="npc", priority=120, image_url="/static/images/strahd/Strahd%20at%20Dinner.png"),
            StoryCard(id="barovia_card", title="The Village of Barovia", keys=["village of barovia", "blood on the vine", "mad mary", "ismark", "ireena"],
                entry="The village of Barovia is reached in Arc B after the escape from Death House. Here the party can meet Ismark and Ireena, consider an escort to Vallaki, help bury Kolyan Indirovich, and encounter Donavich and Doru. NPC recruitment and these choices must occur in play.",
                card_type="location", priority=110),
            StoryCard(id="death_house_card", title="Death House", keys=["death house", "durst", "rose and thorn", "flesh mound"],
                entry="Reloaded Arc A is written for five 2nd-level characters. The Main Hall clock starts a six-hour countdown to the lurking mound's awakening. Sacrificing a living creature does not free the party: its hunger cannot be sated. Actual destruction opens the front door and begins the collapsing-house escape; actual exit leads to Barovia. Use the GM Death House clock for source time, actual discoveries and outcomes.",
                card_type="location", priority=130, image_url="/static/images/strahd/The%20Durst%20Family.png"),
        ],
        active_quests=quest_catalog(),
    )
