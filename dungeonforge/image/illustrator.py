import re
import random
import urllib.parse
from typing import Optional


class SceneIllustrator:
    """Generates visual scene illustrations for turns, locations, and tactical encounters.

    Uses zero-friction Pollinations Flux/Turbo pipeline with dark fantasy tabletop styling.
    """

    DEFAULT_STYLE = "dark fantasy oil painting, tabletop RPG scene illustration, atmospheric moody lighting, high detail, masterpiece"

    @classmethod
    def clean_text_for_prompt(cls, text: str) -> str:
        """Strips roll breakdowns, state tags, and question prompts from DM narration."""
        # Strip code blocks or state update tags
        clean = re.sub(r"```[\s\S]*?```", "", text)
        # Strip bracketed notices
        clean = re.sub(r"\[[\s\S]*?\]", "", clean)
        # Strip common trailing prompts
        clean = re.sub(r"What (would|do) you (like to )?do\??", "", clean, flags=re.IGNORECASE)
        # Take the first two most descriptive sentences
        sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", clean) if len(s.strip()) > 15]
        if sentences:
            return " ".join(sentences[:2])
        return clean.strip()[:200]

    @classmethod
    def generate_image_url(
        cls,
        prompt: Optional[str] = None,
        context_text: Optional[str] = None,
        style: Optional[str] = None,
        width: int = 800,
        height: int = 512,
        seed: Optional[int] = None
    ) -> str:
        """Constructs an image generation URL with seed and visual styling."""
        core_prompt = ""
        if prompt and prompt.strip():
            core_prompt = prompt.strip()
        elif context_text and context_text.strip():
            core_prompt = cls.clean_text_for_prompt(context_text)
        else:
            core_prompt = "adventurers exploring a misty dark gothic dungeon"

        chosen_style = style or cls.DEFAULT_STYLE
        full_prompt = f"{core_prompt}, {chosen_style}"

        # Clean non-alphanumeric noise, keep readable punctuation
        clean_prompt = re.sub(r"[^\w\s,.-]", "", full_prompt)
        encoded = urllib.parse.quote(clean_prompt[:350])

        random_seed = seed if seed is not None else random.randint(100000, 999999)
        return f"https://image.pollinations.ai/prompt/{encoded}?width={width}&height={height}&nologo=true&seed={random_seed}&model=flux"
