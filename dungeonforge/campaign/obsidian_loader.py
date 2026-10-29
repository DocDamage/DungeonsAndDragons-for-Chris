import os
import re
import zipfile
import hashlib
from pathlib import Path, PurePosixPath
from urllib.parse import quote
from typing import List, Dict, Tuple, Optional
import yaml
from dungeonforge.context.story_cards import StoryCard


class ObsidianCampaignLoader:
    """Parses an Obsidian Vault (e.g., Curse of Strahd Reloaded) into StoryCards and Quests."""

    @classmethod
    def load_from_zip(
        cls,
        zip_path: str,
        max_cards: int = 150,
        images_dir: Optional[str] = None
    ) -> Tuple[List[StoryCard], Dict[str, List[str]]]:
        cards: List[StoryCard] = []
        quests_by_act: Dict[str, List[str]] = {}

        if not os.path.exists(zip_path):
            return cards, quests_by_act

        # Collect available static images for matching
        available_images: List[str] = []
        if images_dir and os.path.exists(images_dir):
            available_images = [f for f in os.listdir(images_dir) if f.lower().endswith(('.png', '.jpg', '.jpeg', '.webp'))]

        with zipfile.ZipFile(zip_path, "r") as z:
            for filename in z.namelist():
                if not filename.endswith(".md"):
                    continue
                # Skip hidden files
                if "/." in filename or filename.startswith("."):
                    continue

                try:
                    raw_bytes = z.read(filename)
                    text = raw_bytes.decode("utf-8", errors="ignore")
                except Exception:
                    continue

                card = cls.parse_markdown(filename, text, available_images)
                if card and len(cards) < max_cards:
                    cards.append(card)

                # Check if Act / Arc structure
                if "Act " in filename and ("Arc " in filename or "Summary" in filename):
                    act_match = re.search(r"Act\s+([IVXLCDM]+|\d+)", filename)
                    act_name = f"Act {act_match.group(1)}" if act_match else "Prologue"
                    clean_title = os.path.splitext(os.path.basename(filename))[0]
                    if act_name not in quests_by_act:
                        quests_by_act[act_name] = []
                    quests_by_act[act_name].append(clean_title)

        return cards, quests_by_act

    @classmethod
    def parse_markdown(cls, filepath: str, content: str, available_images: Optional[List[str]] = None) -> Optional[StoryCard]:
        clean_name = os.path.splitext(os.path.basename(filepath))[0]
        # Ignore empty or tiny files
        if len(content.strip()) < 50:
            return None

        frontmatter = {}
        body = content

        # Extract YAML frontmatter if present
        fm_match = re.match(r"^---\s*\n(.*?)\n---\s*\n", content, re.DOTALL)
        if fm_match:
            try:
                frontmatter = yaml.safe_load(fm_match.group(1)) or {}
            except Exception:
                frontmatter = {}
            body = content[fm_match.end():]

        # Extract wiki-links [[Target]] to use as keywords
        wiki_links = re.findall(r"\[\[(.*?)\]\]", body)
        clean_keys = set()
        clean_keys.add(clean_name.lower())

        # Also add parts of the title
        for word in re.findall(r"\b[A-Z][a-z]{3,}\b", clean_name):
            clean_keys.add(word.lower())

        # Check for explicit embedded image: ![[something.png]]
        embedded_img_match = re.search(r"!\[\[(.*?\.(?:png|jpg|jpeg|webp))\]\]", body, re.IGNORECASE)
        image_url = None
        if embedded_img_match:
            img_file = os.path.basename(embedded_img_match.group(1))
            if available_images and img_file in available_images:
                image_url = f"/static/images/strahd/{quote(img_file)}"

        for link in wiki_links:
            # Handle aliases [[Target|Alias]]
            target = link.split("|")[0].strip()
            if target and len(target) > 3:
                clean_keys.add(target.lower())

        # Match against available images if no embedded image was found
        if not image_url and available_images:
            norm_name = re.sub(r"[^a-z0-9]", "", clean_name.lower())
            for img in available_images:
                norm_img = re.sub(r"[^a-z0-9]", "", os.path.splitext(img)[0].lower())
                if norm_name in norm_img or norm_img in norm_name or any(k in norm_img for k in clean_keys if len(k) > 4):
                    image_url = f"/static/images/strahd/{quote(img)}"
                    break

        # Categorize card type
        card_type = "lore"
        fp_lower = filepath.lower()
        if "npc" in fp_lower or "character" in fp_lower or "strahd" in clean_name.lower():
            card_type = "npc"
        elif "location" in fp_lower or "town" in fp_lower or "room" in fp_lower or "house" in fp_lower:
            card_type = "location"
        elif "item" in fp_lower or "loot" in fp_lower:
            card_type = "item"
        elif "arc" in fp_lower or "act" in fp_lower:
            card_type = "quest"

        # Trim body to a concise summary so it fits comfortably in prompt context
        clean_body = re.sub(r"\[\[(.*?)(?:\|.*?)?\]\]", r"\1", body)  # Replace [[link|text]] with text
        clean_body = re.sub(r"#{1,6}\s+", "", clean_body)              # Remove markdown header hashes
        clean_body = re.sub(r"\n{2,}", "\n", clean_body).strip()

        # Limit entry text to ~600 chars for concise prompt insertion
        entry_text = clean_body[:600] + ("..." if len(clean_body) > 600 else "")

        return StoryCard(
            id=re.sub(r"[^a-zA-Z0-9_]", "_", clean_name).lower() + "_" + hashlib.sha1(filepath.encode()).hexdigest()[:10],
            title=clean_name,
            keys=list(clean_keys)[:12],
            entry=entry_text,
            card_type=card_type,
            priority=120 if card_type == "quest" else (110 if card_type == "npc" else 90),
            enabled=True,
            image_url=image_url
        )

    @classmethod
    def load_from_archives(cls, zip_paths, max_cards=300, images_dir=None):
        """Load split vaults, including image-only parts, without extracting executable files."""
        if images_dir:
            destination = Path(images_dir).resolve()
            destination.mkdir(parents=True, exist_ok=True)
            for zip_path in zip_paths:
                with zipfile.ZipFile(zip_path) as archive:
                    for info in archive.infolist():
                        relative = PurePosixPath(info.filename.replace("\\", "/"))
                        if (info.is_dir() or any(part.startswith(".") for part in relative.parts)
                                or relative.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}
                                or info.file_size > 20_000_000):
                            continue
                        target = (destination / relative.name).resolve()
                        if target.parent != destination or target.exists():
                            continue
                        target.write_bytes(archive.read(info))
        cards, quests = {}, {}
        for zip_path in zip_paths:
            part_cards, part_quests = cls.load_from_zip(zip_path, max_cards=max_cards, images_dir=images_dir)
            for card in part_cards:
                if len(cards) < max_cards:
                    cards[card.id] = card
            for act, titles in part_quests.items():
                quests.setdefault(act, [])
                quests[act].extend(title for title in titles if title not in quests[act])
        return list(cards.values()), quests
