import re
from typing import List, Set, Optional, Dict
from pydantic import BaseModel, Field


class StoryCard(BaseModel):
    id: str
    title: str
    keys: List[str] = Field(default_factory=list)  # Trigger keywords/phrases
    entry: str                                      # Content injected when triggered
    card_type: str = "lore"                        # npc, location, item, faction, quest, rule
    priority: int = 100                             # Higher = earlier/higher priority
    enabled: bool = True
    image_url: Optional[str] = None


class StoryCardManager:
    """Manages Lorebook / Story Cards and performs context-aware keyword triggering."""

    def __init__(self, cards: Optional[List[StoryCard]] = None):
        self.cards: Dict[str, StoryCard] = {c.id: c for c in (cards or [])}

    def add_card(self, card: StoryCard):
        self.cards[card.id] = card

    def remove_card(self, card_id: str):
        self.cards.pop(card_id, None)

    def get_triggered_cards(self, text_context: str, max_cards: int = 6) -> List[StoryCard]:
        """Scans the text for trigger keys and returns matched cards sorted by priority."""
        triggered: List[StoryCard] = []
        lowered_text = text_context.lower()

        for card in self.cards.values():
            if not card.enabled:
                continue
            for key in card.keys:
                clean_key = key.strip().lower()
                if not clean_key:
                    continue
                # Match whole words or boundary phrases
                pattern = r"(?<!\w)" + re.escape(clean_key) + r"(?!\w)"
                if re.search(pattern, lowered_text):
                    triggered.append(card)
                    break

        # Sort by priority descending
        triggered.sort(key=lambda c: c.priority, reverse=True)
        return triggered[:max_cards]
