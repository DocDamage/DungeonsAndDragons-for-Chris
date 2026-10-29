import os
import re
from typing import List
from dungeonforge.compendium.db import CompendiumDB, CompendiumEntry


class CompendiumIndexer:
    """Builds and populates the compendium from raw source files and core seeds."""

    @classmethod
    def index_all(cls, db: CompendiumDB, base_dir: str = "F:/dev/dandd"):
        entries: List[CompendiumEntry] = []

        # 1. Seed Core Iconic Monsters with 2e, 3.5e, and 5e stats
        entries.extend(cls._seed_monsters())

        # 2. Parse 3.5e Spell Compendium
        spell_file = os.path.join(base_dir, "3.5e", "D&D 3.5 - Spell Compendium (Premium Edition)_djvu.txt")
        if os.path.exists(spell_file):
            spells = cls._parse_35_spells(spell_file, max_count=500)
            entries.extend(spells)

        # 3. Parse 3.5e Magic Item Compendium
        item_file = os.path.join(base_dir, "3.5e", "D&D 3.5 - Magic-Item-Compendium_djvu.txt")
        if os.path.exists(item_file):
            items = cls._parse_35_items(item_file, max_count=300)
            entries.extend(items)

        # 4. Seed Core 5e Spells
        entries.extend(cls._seed_5e_spells())

        # Insert into database
        db.insert_batch(entries)
        return len(entries)

    @classmethod
    def _parse_35_spells(cls, filepath: str, max_count: int = 500) -> List[CompendiumEntry]:
        spells: List[CompendiumEntry] = []
        try:
            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read(2000000)  # Read 2MB slice
        except Exception:
            return spells

        # Pattern: ALL CAPS TITLE followed by School
        pattern = r"\n([A-Z\s\',-]{4,30})\n(Abjuration|Conjuration|Divination|Enchantment|Evocation|Illusion|Necromancy|Transmutation)(.*?)(?=\n[A-Z\s\',-]{4,30}\n(?:Abjuration|Conjuration|Divination|Enchantment|Evocation|Illusion|Necromancy|Transmutation)|\Z)"
        matches = re.finditer(pattern, content, re.DOTALL)

        for m in matches:
            raw_title = m.group(1).strip()
            school = m.group(2).strip()
            body = m.group(3).strip()

            # Clean title
            clean_title = re.sub(r"\s+", " ", raw_title).title()
            if any(skip in clean_title.lower() for skip in ["chapter", "contents", "introduction", "descriptions"]):
                continue

            # Extract Level
            lvl_match = re.search(r"Level:\s*(.*?)\n", body, re.IGNORECASE)
            level_str = lvl_match.group(1).strip() if lvl_match else "Spell"

            # Summary from first 200 chars
            summary_match = re.sub(r"^(?:Components|Casting Time|Range|Target|Duration|Saving Throw|Spell Resistance):.*?\n", "", body, flags=re.MULTILINE)
            summary = re.sub(r"\s+", " ", summary_match).strip()[:180]

            spell_id = "spell_35_" + re.sub(r"[^a-zA-Z0-9_]", "_", clean_title).lower()
            spells.append(CompendiumEntry(
                id=spell_id,
                name=clean_title,
                category="spell",
                edition="3.5e",
                level_or_cr=level_str[:40],
                school_or_type=school,
                summary=summary,
                description=body[:1000],
                source="Spell Compendium (3.5e)"
            ))
            if len(spells) >= max_count:
                break

        return spells

    @classmethod
    def _parse_35_items(cls, filepath: str, max_count: int = 300) -> List[CompendiumEntry]:
        items: List[CompendiumEntry] = []
        try:
            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read(1500000)
        except Exception:
            return items

        pattern = r"\n([A-Z\s\',-]{4,35})\nPrice(?:\s*\(Item\s*Level\))?:\s*(.*?)\nBody\s*Slot:\s*(.*?)\n(.*?)(?=\n[A-Z\s\',-]{4,35}\nPrice|\Z)"
        matches = re.finditer(pattern, content, re.DOTALL | re.IGNORECASE)

        for m in matches:
            raw_title = m.group(1).strip()
            price = m.group(2).strip()
            slot = m.group(3).strip()
            body = m.group(4).strip()

            clean_title = re.sub(r"\s+", " ", raw_title).title()
            if "Chapter" in clean_title or len(clean_title) < 3:
                continue

            clean_desc = re.sub(r"\s+", " ", body).strip()
            item_id = "item_35_" + re.sub(r"[^a-zA-Z0-9_]", "_", clean_title).lower()
            items.append(CompendiumEntry(
                id=item_id,
                name=clean_title,
                category="item",
                edition="3.5e",
                level_or_cr=price[:30],
                school_or_type=slot[:30],
                summary=clean_desc[:180],
                description=f"Price: {price} | Slot: {slot}\n\n{clean_desc[:800]}",
                source="Magic Item Compendium (3.5e)"
            ))
            if len(items) >= max_count:
                break

        return items

    @classmethod
    def _seed_monsters(cls) -> List[CompendiumEntry]:
        return [
            CompendiumEntry(
                id="mon_strahd_5e",
                name="Count Strahd von Zarovich",
                category="monster",
                edition="5e",
                level_or_cr="CR 15",
                school_or_type="Undead (Shapechanger)",
                summary="The ancient vampire dread lord and master of Castle Ravenloft.",
                description="AC: 16 (Natural Armor) | HP: 144 (17d8+68) | Speed: 30 ft\nStats: STR 18 (+4), DEX 18 (+4), CON 18 (+4), INT 20 (+5), WIS 15 (+2), CHA 18 (+4)\nSaving Throws: Dex +9, Wis +7, Cha +9\nDamage Resistances: Necrotic; Bludgeoning, Piercing, and Slashing from Nonmagical Attacks\nActions: Multiattack (Unarmed Strike x2), Unarmed Strike (+9 to hit, 1d8+4 bludgeoning + 4d6 necrotic), Bite (+9 to hit, 1d6+4 piercing + 3d6 necrotic), Charm (DC 17 Wis save). Legendary Actions: Move, Unarmed Strike, Bite (Costs 2).",
                source="Curse of Strahd (5e)"
            ),
            CompendiumEntry(
                id="mon_strahd_2e",
                name="Count Strahd von Zarovich (AD&D 2e)",
                category="monster",
                edition="2e",
                level_or_cr="16 HD",
                school_or_type="Undead Vampire / Mage",
                summary="AD&D 2nd Edition Ravenloft Darklord statblock.",
                description="AC: -1 (Descending) | THAC0: 9 | HP: 65 | Movement: 12\nSaves: PPDM 5, RSW 7, PP 6, BW 8, Sp 8\nAttacks: 1 unarmed strike (1d6+4 + energy drain 2 levels) or spells as 16th-level necromancer.\nSpecial Defenses: +1 or better magical weapon to hit; regenerates 3 hp/round; immune to sleep, charm, hold, poison, cold, electricity.",
                source="Ravenloft Campaign Setting (2e)"
            ),
            CompendiumEntry(
                id="mon_vampire_spawn_5e",
                name="Vampire Spawn",
                category="monster",
                edition="5e",
                level_or_cr="CR 5",
                school_or_type="Undead",
                summary="Savage undead predator subservient to true vampires.",
                description="AC: 15 (Natural Armor) | HP: 82 (11d8+33) | Speed: 30 ft, climb 30 ft\nStats: STR 16 (+3), DEX 16 (+3), CON 16 (+3), INT 11 (+0), WIS 10 (+0), CHA 12 (+1)\nRegeneration: 10 HP at start of turn unless in sunlight or running water.\nSpider Climb: Can climb difficult surfaces including upside down without ability check.\nActions: Multiattack (Claws and Bite), Claws (+6 to hit, 2d4+3 slashing), Bite (+6 to hit, 1d6+3 piercing + 2d6 necrotic).",
                source="Monster Manual (5e)"
            ),
            CompendiumEntry(
                id="mon_dire_wolf_5e",
                name="Dire Wolf",
                category="monster",
                edition="5e",
                level_or_cr="CR 1",
                school_or_type="Beast",
                summary="Enormous, vicious wolf that prowls the Svalich Woods in packs.",
                description="AC: 14 (Natural Armor) | HP: 37 (5d10+10) | Speed: 50 ft\nStats: STR 17 (+3), DEX 15 (+2), CON 15 (+2), INT 3 (-4), WIS 12 (+1), CHA 7 (-2)\nKeen Hearing and Smell: Advantage on Perception checks relying on hearing/smell.\nPack Tactics: Advantage on attack rolls if an ally is within 5 ft of target.\nActions: Bite (+5 to hit, reach 5 ft, 2d6+3 piercing. Target must succeed on DC 13 Str save or be knocked prone).",
                source="Monster Manual (5e)"
            ),
            CompendiumEntry(
                id="mon_skeleton_5e",
                name="Skeleton",
                category="monster",
                edition="5e",
                level_or_cr="CR 1/4",
                school_or_type="Undead",
                summary="Animated bones bound together by dark necromancy.",
                description="AC: 13 (Armor Scraps) | HP: 13 (2d8+4) | Speed: 30 ft\nStats: STR 10 (+0), DEX 14 (+2), CON 15 (+2), INT 6 (-2), WIS 8 (-1), CHA 5 (-3)\nDamage Vulnerability: Bludgeoning | Damage Immunity: Poison\nActions: Shortsword (+4 to hit, 1d6+2 piercing) or Shortbow (+4 to hit, range 80/320, 1d6+2 piercing).",
                source="Monster Manual (5e)"
            ),
            CompendiumEntry(
                id="mon_zombie_5e",
                name="Zombie",
                category="monster",
                edition="5e",
                level_or_cr="CR 1/4",
                school_or_type="Undead",
                summary="Shambling corpse driven by relentless hunger.",
                description="AC: 8 | HP: 22 (3d8+9) | Speed: 20 ft\nStats: STR 13 (+1), DEX 6 (-2), CON 16 (+3), INT 3 (-4), WIS 6 (-2), CHA 5 (-3)\nUndead Fortitude: If damage reduces the zombie to 0 HP, it must make a Con saving throw with a DC of 5 + the damage taken (unless radiant or critical hit). On success, it drops to 1 HP instead.\nActions: Slam (+3 to hit, 1d6+1 bludgeoning).",
                source="Monster Manual (5e)"
            ),
            CompendiumEntry(
                id="mon_owlbear_5e",
                name="Owlbear",
                category="monster",
                edition="5e",
                level_or_cr="CR 3",
                school_or_type="Monstrosity",
                summary="Fierce monstrosity with the head of an owl and body of a bear.",
                description="AC: 13 (Natural Armor) | HP: 59 (7d10+21) | Speed: 40 ft\nStats: STR 20 (+5), DEX 12 (+1), CON 17 (+3), INT 3 (-4), WIS 12 (+1), CHA 7 (-2)\nKeen Sight and Smell: Advantage on Perception checks.\nActions: Multiattack (Beak and Claws), Beak (+7 to hit, 1d10+5 piercing), Claws (+7 to hit, 2d8+5 slashing).",
                source="Monster Manual (5e)"
            ),
            CompendiumEntry(
                id="mon_mind_flayer_5e",
                name="Mind Flayer",
                category="monster",
                edition="5e",
                level_or_cr="CR 7",
                school_or_type="Aberration",
                summary="Psionic tyrant with tentacled maw that consumes humanoid brains.",
                description="AC: 15 (Breastplate) | HP: 71 (13d8+13) | Speed: 30 ft\nStats: STR 11 (+0), DEX 12 (+1), CON 12 (+1), INT 19 (+4), WIS 17 (+3), CHA 17 (+3)\nMagic Resistance: Advantage on saves against spells and magical effects.\nActions: Tentacles (+7 to hit, 2d10+4 psychic, target is grappled escape DC 15 and stunned). Extract Brain (+7 to hit vs incapacitated target, 10d10 piercing; kills target if reduced to 0 HP). Mind Blast (Recharge 5-6, 60 ft cone, DC 15 Int save, 4d8+4 psychic and stunned for 1 min).",
                source="Monster Manual (5e)"
            )
        ]

    @classmethod
    def _seed_5e_spells(cls) -> List[CompendiumEntry]:
        return [
            CompendiumEntry(
                id="spell_5e_fireball",
                name="Fireball",
                category="spell",
                edition="5e",
                level_or_cr="3rd Level",
                school_or_type="Evocation",
                summary="A bright streak flashes from your pointing finger to a point you choose and then blossoms with a low roar into an explosion of flame.",
                description="Casting Time: 1 action | Range: 150 feet | Components: V, S, M (a tiny ball of bat guano and sulfur) | Duration: Instantaneous\nEach creature in a 20-foot-radius sphere centered on that point must make a Dexterity saving throw. A target takes 8d6 fire damage on a failed save, or half as much damage on a successful one. The fire spreads around corners. It ignites flammable objects in the area that aren't being worn or carried.\nAt Higher Levels: Damage increases by 1d6 for each slot level above 3rd.",
                source="Player's Handbook (5e)"
            ),
            CompendiumEntry(
                id="spell_5e_cure_wounds",
                name="Cure Wounds",
                category="spell",
                edition="5e",
                level_or_cr="1st Level",
                school_or_type="Evocation",
                summary="A creature you touch regains a number of hit points equal to 1d8 + your spellcasting ability modifier.",
                description="Casting Time: 1 action | Range: Touch | Components: V, S | Duration: Instantaneous\nA creature you touch regains a number of hit points equal to 1d8 + your spellcasting ability modifier. This spell has no effect on undead or constructs.\nAt Higher Levels: The healing increases by 1d8 for each slot level above 1st.",
                source="Player's Handbook (5e)"
            ),
            CompendiumEntry(
                id="spell_5e_magic_missile",
                name="Magic Missile",
                category="spell",
                edition="5e",
                level_or_cr="1st Level",
                school_or_type="Evocation",
                summary="You create three glowing darts of magical force. Each dart hits a creature of your choice that you can see within range.",
                description="Casting Time: 1 action | Range: 120 feet | Components: V, S | Duration: Instantaneous\nYou create three glowing darts of magical force. Each dart hits a creature of your choice that you can see within range. A dart deals 1d4 + 1 force damage to its target. The darts all strike simultaneously, and you can direct them to hit one creature or several.\nAt Higher Levels: You create one more dart for each slot level above 1st.",
                source="Player's Handbook (5e)"
            ),
            CompendiumEntry(
                id="spell_5e_eldritch_blast",
                name="Eldritch Blast",
                category="spell",
                edition="5e",
                level_or_cr="Cantrip",
                school_or_type="Evocation",
                summary="A beam of crackling energy streaks toward a creature within range.",
                description="Casting Time: 1 action | Range: 120 feet | Components: V, S | Duration: Instantaneous\nMake a ranged spell attack against the target. On a hit, the target takes 1d10 force damage.\nThe spell creates more than one beam when you reach higher levels: two beams at 5th level, three beams at 11th level, and four beams at 17th level.",
                source="Player's Handbook (5e)"
            ),
            CompendiumEntry(
                id="spell_5e_shield",
                name="Shield",
                category="spell",
                edition="5e",
                level_or_cr="1st Level",
                school_or_type="Abjuration",
                summary="An invisible barrier of magical force appears and protects you, adding +5 to AC and negating magic missile.",
                description="Casting Time: 1 reaction, which you take when you are hit by an attack or targeted by the magic missile spell | Range: Self | Components: V, S | Duration: 1 round\nAn invisible barrier of magical force appears and protects you. Until the start of your next turn, you have a +5 bonus to AC, including against the triggering attack, and you take no damage from magic missile.",
                source="Player's Handbook (5e)"
            )
        ]
