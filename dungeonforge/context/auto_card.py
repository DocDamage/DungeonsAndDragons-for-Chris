import re
from typing import List, Optional, Set
from dungeonforge.context.story_cards import StoryCard


class AutoCardGenerator:
    """Detects newly introduced characters, locations, and artifacts in DM narrative."""

    # Words to ignore for auto-entity detection
    STOPWORDS = {
        "the", "this", "that", "there", "then", "when", "what", "where", "with",
        "from", "into", "onto", "your", "their", "castle", "hall", "room",
        "dungeon", "action", "check", "round", "turn", "success", "failure",
        "barovia", "strahd"  # Already seeded
    }

    @classmethod
    def extract_new_cards(cls, narrative_text: str, existing_cards: List[StoryCard]) -> List[StoryCard]:
        new_cards: List[StoryCard] = []
        existing_keys: Set[str] = set()
        for c in existing_cards:
            existing_keys.add(c.title.lower())
            for k in c.keys:
                existing_keys.add(k.lower())

        # Patterns for entity introductions:
        # e.g., "named Father Lucian", "known as Madam Eva", "Lady Wachter", "Sir Godfrey"
        entity_patterns = [
            r"(?:named|called|known as)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)",
            r"\b(Lady\s+[A-Z][a-z]+|Lord\s+[A-Z][a-z]+|Father\s+[A-Z][a-z]+|Madam\s+[A-Z][a-z]+|Sir\s+[A-Z][a-z]+)\b",
            r"\b([A-Z][a-z]+\s+of\s+[A-Z][a-z]+)\b"
        ]

        found_names = set()
        for pat in entity_patterns:
            matches = re.findall(pat, narrative_text)
            for m in matches:
                clean_name = m.strip()
                if clean_name.lower() not in cls.STOPWORDS and len(clean_name) > 3:
                    found_names.add(clean_name)

        sentences = re.split(r"(?<=[.!?])\s+", narrative_text)

        for name in found_names:
            norm_name = name.lower()
            if norm_name in existing_keys or any(norm_name in k for k in existing_keys):
                continue

            # Find matching context sentence
            context_sentence = next((s for s in sentences if name in s), f"Encountered in Barovia: {name}")

            # Determine card type
            card_type = "npc"
            lower_name = name.lower()
            if any(w in lower_name for w in ["hall", "temple", "tower", "dungeon", "crypt", "castle"]):
                card_type = "location"
            elif any(w in lower_name for w in ["sword", "blade", "amulet", "ring", "scroll", "orb"]):
                card_type = "item"

            card_id = "auto_" + re.sub(r"[^a-zA-Z0-9_]", "_", norm_name)
            new_card = StoryCard(
                id=card_id,
                title=name,
                keys=[norm_name, name.split()[0].lower()],
                entry=context_sentence.strip(),
                card_type=card_type,
                priority=105,
                enabled=True
            )
            new_cards.append(new_card)
            existing_keys.add(norm_name)

        return new_cards
