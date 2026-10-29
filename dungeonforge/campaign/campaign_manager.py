import os
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from dungeonforge.rules.base import Character, AbilityScores, Item, Companion, SpellSlot
from dungeonforge.context.story_cards import StoryCard
from dungeonforge.context.memory import Memory
from dungeonforge.context.authors_note import AuthorsNote
from dungeonforge.rules.weg_models import D6Character


class CampaignPreset(BaseModel):
    id: str
    title: str
    edition: str
    genre: str
    banner_image: Optional[str] = None
    description: str
    initial_memory: str
    default_authors_note: str
    prologue_prompt: str
    starter_character: Character
    story_cards: List[StoryCard] = Field(default_factory=list)
    active_quests: Dict[str, List[str]] = Field(default_factory=dict)
    source_folder: str = ""
    source_rule_system: str = ""
    rules_note: Optional[str] = None


class CampaignManager:
    """Manages preset and user-imported campaigns across multiple genres and editions."""

    @classmethod
    def get_available_campaigns(cls) -> List[Dict[str, Any]]:
        return [
            {
                "id": "strahd",
                "title": "Curse of Strahd Reloaded",
                "edition": "5e",
                "genre": "Gothic Horror / Dark Fantasy",
                "banner_image": "/static/images/strahd/Strahd%20at%20Dinner.png",
                "description": "Begin in storm-soaked Daggerford, survive Death House, and follow the Reloaded campaign through the liberation of Barovia.",
                "acts_count": 5
            },
            {
                "id": "rick_and_morty",
                "title": "The Lost Dungeon of Rickedness: Big Rick Energy",
                "edition": "5e",
                "genre": "Sci-Fi Parody / Multiverse Comedy",
                "banner_image": None,
                "description": "Rick Sanchez has dragged the family into an interdimensional dungeon crawl filled with absurd traps, malfunctioning clones, and weird sci-fi loot.",
                "acts_count": 2
            },
            {
                "id": "marvel_5e",
                "title": "Marvel 5e: Superhero Chronicles",
                "edition": "5e",
                "genre": "Superhero / Urban Action",
                "banner_image": None,
                "description": "Protect New York City from criminal syndicates and supervillains using superhuman abilities, mutant powers, and high-tech gadgets.",
                "acts_count": 3
            },
            {
                "id": "minecraft_dnd",
                "title": "Minecraft: Lightning Keep",
                "edition": "5e",
                "genre": "Voxel Fantasy / Dungeon Delve",
                "banner_image": None,
                "description": "Recover six magical lightning rods and restore Lightning Keep's protective shield to shelter refugees from a marauding dragon.",
                "acts_count": 2
            },
            {
                "id": "star_wars_d6",
                "title": "Star Wars: Galactic Rebellion (WEG D6)",
                "edition": "weg_d6",
                "genre": "Space Opera / Sci-Fi Adventure",
                "banner_image": None,
                "description": "Join the Rebel Alliance against the Galactic Empire. Wield blasters and the Force across star systems and Imperial outposts.",
                "acts_count": 3
            }
        ]

    @classmethod
    def load_campaign(cls, campaign_id: str) -> CampaignPreset:
        cid = campaign_id.lower().strip()

        if cid in ["rick_and_morty", "rick", "morty"]:
            preset = cls._get_rick_and_morty()
            preset.source_folder = "rick_and_morty"
        elif cid in ["marvel_5e", "marvel", "superhero"]:
            preset = cls._get_marvel()
            preset.source_folder = "marvel"
        elif cid in ["minecraft_dnd", "minecraft", "lightning_keep"]:
            preset = cls._get_minecraft()
            preset.source_folder = "minecraft"
        elif cid in ["star_wars_d6", "star_wars_2e", "starwars", "star_wars"]:
            preset = cls._get_star_wars()
            preset.source_folder = "star_wars"
            preset.source_rule_system = "Star Wars WEG 2nd Edition (D6)"
            preset.rules_note = "Native WEG Star Wars Second Edition (1992): character wounds, vehicle/starship hull combat, scale die caps, crew declarations, piloting, gunnery, shields, persistent system damage, and 22 learned Force powers with staged activation, upkeep, and native effects. Native advancement tracks CP, qualified instructors, intensive study and one-pip adventure limits. Dark Side controls record moral rulings, plain-die corruption checks, calls and demands, two-adventure atonement and GM-approved redemption. Use the native controls; narration cannot grant training, erase corruption or bypass deterministic rolls."
        elif cid in ["strahd", "curse_of_strahd"]:
            preset = cls._get_strahd()
            preset.source_folder = "strahd"
        else:
            raise ValueError("Unknown campaign.")
        if not preset.source_rule_system:
            preset.source_rule_system = f"D&D {preset.edition}"
        return preset

    @classmethod
    def campaign_catalog(cls):
        from dungeonforge.library import get_library
        folders = {folder["id"]: folder for folder in get_library().catalog()["folders"]}
        campaigns = []
        for summary in cls.get_available_campaigns():
            preset = cls.load_campaign(summary["id"])
            folder = folders[preset.source_folder]
            campaigns.append({
                **summary, "title": preset.title, "acts_count": len(preset.active_quests),
                "source_folder": preset.source_folder, "source_rule_system": preset.source_rule_system,
                "rules_note": preset.rules_note, "source_count": folder["source_count"],
                "indexed_sources": folder["indexed_count"], "source_passages": folder["chunk_count"],
            })
        return campaigns

    @classmethod
    def _get_strahd(cls) -> CampaignPreset:
        from dungeonforge.campaign.strahd import build_preset
        return build_preset()

    @classmethod
    def _get_rick_and_morty(cls) -> CampaignPreset:
        return CampaignPreset(
            id="rick_and_morty",
            title="The Lost Dungeon of Rickedness",
            edition="5e",
            genre="Sci-Fi Parody / Multiverse Comedy",
            description="Rick Sanchez drags the family into an interdimensional dungeon crawl filled with absurd traps, quantum blasters, and fourth-wall breaking mockery.",
            initial_memory=(
                "You are inside Rick Sanchez's customized holographic dungeon module. "
                "Rick is the omniscient, cynical Dungeon Master who constantly comments on your choices and mocks tabletop RPG tropes."
            ),
            default_authors_note="Style: Dan Harmon comedic parody, irreverent sci-fi; Tone: Absurd, snarky, fourth-wall breaking.",
            prologue_prompt=(
                "'Alright, listen up *burp* adventurers,' Rick's voice booms over an unseen PA system. 'Welcome to the "
                "Lost Dungeon of Rickedness. I spent forty-five minutes coding this entire dungeon while taking a dump, "
                "so try not to disappoint me by dying in the first room like Jerry did.' "
                "Before you sits an iron door glowing with pulsating green portal energy. Beside it is a vending machine "
                "selling Plumbus components. What do you do?"
            ),
            starter_character=Character(
                name="Morty Smith",
                race="Human (Anxious)",
                class_name="Rogue",
                level=3,
                alignment="Neutral Good",
                edition="5e",
                abilities=AbilityScores(str=10, dex=15, con=12, int=11, wis=14, cha=13),
                current_hp=21,
                max_hp=21,
                ac=14,
                gold=12,
                inventory=[
                    Item(name="Laser Dagger", quantity=1, item_type="weapon", damage="1d6+2", equipped=True),
                    Item(name="Rick's Defective Portal Fluid Vial", quantity=1, item_type="quest", description="Do not drink."),
                    Item(name="Yellow T-Shirt of Destiny", quantity=1, item_type="armor", ac_bonus=2, equipped=True)
                ]
            ),
            story_cards=[
                StoryCard(
                    id="rick_dm_card",
                    title="Rick Sanchez (The DM)",
                    keys=["rick", "sanchez", "portal gun", "citadel"],
                    entry="Rick is running this tabletop simulation and will periodically insult the player's tactical decisions or alter physics when he gets bored.",
                    card_type="npc",
                    priority=150
                ),
                StoryCard(
                    id="plumbus_card",
                    title="Plumbus of Power",
                    keys=["plumbus", "dinglebop", "schleem", "chumble"],
                    entry="A standard domestic household device with inexplicably potent magical and kinetic properties.",
                    card_type="item",
                    priority=110
                )
            ],
            active_quests={
                "Level 1: Big Rick Energy": ["Disable the Meeseeks Trap", "Find the Keycard to the Cloning Vat"],
                "Level 2: The Council's Vault": ["Defeat the Gilded Jerry Golem", "Retrieve the Szechuan Sauce Artifact"]
            }
        )

    @classmethod
    def _get_marvel(cls) -> CampaignPreset:
        return CampaignPreset(
            id="marvel_5e",
            title="Marvel 5e: Superhero Chronicles",
            edition="5e",
            genre="Superhero / Urban Action",
            description="Protect Manhattan from organized supervillains and alien incursions with superhuman powers, high-tech suits, and martial arts.",
            initial_memory=(
                "You are an active hero based in New York City. The city is currently facing an escalation of super-powered crimes, "
                "with rumors that an underground syndicate is acquiring Chitauri and Oscorp experimental technology."
            ),
            default_authors_note="Style: Marvel Cinematic / Comic Book Action; Tone: Dynamic, heroic, high-stakes cinematic combat.",
            prologue_prompt=(
                "Sirens wail through the canyon of skyscrapers along 5th Avenue. Police cruisers have established a perimeter "
                "around the Manhattan Municipal Bank, where shattered armored vehicles and scorched asphalt tell of heavy weapons fire. "
                "Smoke billows from the bank's demolished lobby vault, and civilian screams echo across the avenue. "
                "Perched atop a nearby gargoyle, what do you do?"
            ),
            starter_character=Character(
                name="Peter Parker (Spider-Man)",
                race="Mutated Human",
                class_name="Monk / Acrobat",
                level=4,
                alignment="Lawful Good",
                edition="5e",
                abilities=AbilityScores(str=16, dex=18, con=14, int=16, wis=14, cha=14),
                current_hp=34,
                max_hp=34,
                ac=16,
                gold=5,
                inventory=[
                    Item(name="Web Shooters", quantity=2, item_type="weapon", damage="1d8", description="Shoots synthetic web fluid; restrains target on DC 14 Dex save", equipped=True),
                    Item(name="Spider-Suit", quantity=1, item_type="armor", ac_bonus=2, equipped=True),
                    Item(name="Spider-Tracer", quantity=5, item_type="misc")
                ]
            ),
            story_cards=[
                StoryCard(
                    id="spider_sense_card",
                    title="Spider-Sense",
                    keys=["spider-sense", "tingle", "ambush", "danger", "dodge"],
                    entry="An precognitive warning sense granting advantage on Dexterity saving throws and perception against hidden threats.",
                    card_type="rule",
                    priority=140
                ),
                StoryCard(
                    id="daily_bugle_card",
                    title="The Daily Bugle",
                    keys=["daily bugle", "jameson", "jjj", "headline"],
                    entry="New York's premier tabloid, led by J. Jonah Jameson, who relentlessly paints vigilantes as public menaces.",
                    card_type="faction",
                    priority=100
                )
            ],
            active_quests={
                "Episode 1: The Heist": ["Investigate the Bank Robbery", "Track the Oscorp Shrew"],
                "Episode 2: Shadow Syndicate": ["Infiltrate the Docks", "Confront the Crime Boss"]
            }
        )

    @classmethod
    def _get_minecraft(cls) -> CampaignPreset:
        return CampaignPreset(
            id="minecraft_dnd",
            title="Minecraft: Lightning Keep",
            edition="5e",
            genre="Voxel Fantasy / Dungeon Delve",
            description="Recover six magical lightning rods and restore Lightning Keep's protective shield to shelter refugees from a marauding dragon.",
            initial_memory=(
                "You are an intrepid builder and warrior exploring the Overworld. "
                "Refugees have been displaced by a marauding dragon. Search the abandoned Lightning Keep for six magical lightning rods. "
                "Installing the rods atop its battlements activates a protective lightning shield, making the keep a haven for the refugees. "
                "The keep's rooms and battlements have K-numbered location keys. Consult the local Lightning Keep adventure and Minecraft creature compendium."
            ),
            default_authors_note="Style: Minecraft adventure fantasy; Tone: Atmospheric, survivalist, dangerous dungeon crawl.",
            prologue_prompt=(
                "Thunder rumbles across the blocky horizon as rain lashes against the weathered stone bricks of Lightning Keep. "
                "Beyond its iron-barred portcullis lies an abandoned castle that could shelter the refugees from a marauding dragon. "
                "Six magical lightning rods hidden within can restore a protective shield around its battlements. "
                "Gripping your diamond sword, what do you do?"
            ),
            starter_character=Character(
                name="Steve the Pioneer",
                race="Human",
                class_name="Fighter",
                level=3,
                alignment="Neutral Good",
                edition="5e",
                abilities=AbilityScores(str=16, dex=14, con=16, int=12, wis=13, cha=10),
                current_hp=31,
                max_hp=31,
                ac=16,
                gold=64,
                inventory=[
                    Item(name="Diamond Sword", quantity=1, item_type="weapon", damage="1d8+3", equipped=True),
                    Item(name="Iron Armor", quantity=1, item_type="armor", ac_bonus=4, equipped=True),
                    Item(name="Shield", quantity=1, item_type="armor", ac_bonus=2, equipped=True),
                    Item(name="Golden Apple", quantity=2, item_type="potion", description="Restores 4d4+4 HP and grants 5 temp HP")
                ]
            ),
            story_cards=[
                StoryCard(
                    id="creeper_card",
                    title="Creeper",
                    keys=["creeper", "hiss", "explosion", "gunpowder"],
                    entry="A silent stalking monstrosity that approaches undetected before detonating in a devastating explosion (DC 13 Dex save for 4d6 bludgeoning).",
                    card_type="npc",
                    priority=130
                ),
                StoryCard(
                    id="enderman_card",
                    title="Enderman",
                    keys=["enderman", "teleport", "purple eyes", "ender pearl"],
                    entry="A tall, shadow-cloaked entity that teleports instantaneously and turns hostile if stared directly in the eyes.",
                    card_type="npc",
                    priority=130
                )
            ],
            active_quests={
                "Explore Lightning Keep": ["Reach the Abandoned Keep", "Find the Six Magical Lightning Rods", "Clear the Keep of Dangerous Monsters"],
                "A Haven for Refugees": ["Install the Rods on the Battlements", "Activate the Lightning Shield", "Notify the Refugees That the Keep Is Safe"]
            }
        )

    @classmethod
    def _get_star_wars(cls) -> CampaignPreset:
        return CampaignPreset(
            id="star_wars_d6",
            title="Star Wars: Galactic Rebellion",
            edition="weg_d6",
            genre="Space Opera / Galactic Adventure",
            description="Join the Rebel Alliance against the Galactic Empire using blasters, starfighters, and the Force.",
            initial_memory=(
                "You are an operative of the Rebel Alliance operating in the Outer Rim. "
                "The Galactic Empire has tightened its iron grip on the sector, hunting for suspected insurgents and Force sensitives."
            ),
            default_authors_note="Style: Classic Star Wars space opera; Tone: Heroic, fast-paced, cinematic.",
            prologue_prompt=(
                "Steam rises from the vents of the docking bay on the dusty planet of Tatooine. "
                "Your light freighter sits on the landing pad with its sublight engines cooling. "
                "Suddenly, the hangar blast doors hiss open, and a squad of Imperial Stormtroopers enters with E-11 blaster rifles raised, "
                "led by an Imperial Officer who shouts: 'Halt, Rebel scum! Hands where we can see them!' "
                "What do you do?"
            ),
            starter_character=Character(
                name="Corran Horn",
                race="Human",
                class_name="Rebel Pilot / Force Sensitive",
                level=1,
                alignment="Neutral Good",
                edition="weg_d6",
                abilities=AbilityScores(str=12, dex=17, con=13, int=14, wis=15, cha=14),
                current_hp=24,
                max_hp=24,
                ac=10,
                gold=250,
                inventory=[
                    Item(name="Heavy Blaster Pistol", quantity=1, item_type="weapon", damage="5D", d6_skill="blaster", equipped=True),
                    Item(name="Light Blast Vest", quantity=1, item_type="armor", description="+1D physical resistance; no energy bonus.", equipped=True),
                    Item(name="Comlink", quantity=1, item_type="misc"),
                    Item(name="Medpac", quantity=2, item_type="consumable", description="First aid can improve one wound level. Repeated use increases difficulty.")
                ],
                d6=D6Character(
                    attributes={"dexterity": "3D+2", "knowledge": "2D", "mechanical": "3D+1", "perception": "3D", "strength": "3D", "technical": "3D"},
                    skills={"blaster": "5D+2", "dodge": "4D+2", "space_transports": "4D+1", "astrogation": "4D+1", "search": "4D", "first_aid": "4D"},
                    force_sensitive=True, force_points=2, armor_physical="1D", credits=250,
                ),
                companions=[Companion(
                    id="rebel_medic", name="Rebel Field Medic", class_name="Medic", attack_name="Blaster Pistol", damage="4D",
                    notes="A Rebel medic travelling with the crew; can administer your medpacs.",
                    d6=D6Character(
                        attributes={"dexterity": "2D+2", "knowledge": "3D", "mechanical": "2D+1", "perception": "3D", "strength": "3D", "technical": "4D"},
                        skills={"blaster": "3D+2", "first_aid": "5D"},
                    ),
                )],
            ),
            story_cards=[
                StoryCard(
                    id="the_force_card",
                    title="The Force",
                    keys=["the force", "jedi", "lightsaber", "telekinesis"],
                    entry="An energy field created by all living things that surrounds us, penetrates us, and binds the galaxy together.",
                    card_type="rule",
                    priority=150
                ),
                StoryCard(
                    id="stormtrooper_card",
                    title="Imperial Stormtroopers",
                    keys=["stormtrooper", "empire", "imperial", "e-11", "blaster"],
                    entry="The elite shock troops of the Galactic Empire, clad in white plastoid armor and fanatically loyal to Emperor Palpatine.",
                    card_type="npc",
                    priority=120
                )
            ],
            active_quests={
                "Act I: Tatooine Escape": ["Evade the Imperial Hangar Squad", "Hyperjump Past the Star Destroyer"],
                "Act II: The Rebel Safehouse": ["Contact Alliance Command", "Deliver the Encrypted Data Tape"]
            }
        )

    @classmethod
    def d6_stormtroopers(cls):
        return [{
            "name": name,
            "d6": D6Character(
                attributes={"dexterity": "3D", "knowledge": "2D", "mechanical": "2D", "perception": "2D", "strength": "2D", "technical": "2D"},
                skills={"blaster": "4D", "dodge": "4D"},
                armor_physical="2D", armor_energy="1D", dexterity_penalty=1,
                character_points=0, force_points=0,
                corruption={"refuses_force": True},
            ).model_dump(),
            "weapon": {"name": "E-11 Blaster Rifle", "damage": "5D", "d6_skill": "blaster", "damage_type": "energy"},
        } for name in ("Imperial Stormtrooper Alpha", "Imperial Stormtrooper Beta")]
