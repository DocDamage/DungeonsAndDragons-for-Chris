from pydantic import BaseModel


class AuthorsNote(BaseModel):
    """Directorial instructions injected near the end of prompt to steer tone, genre, and style."""
    text: str = "Style: Dark Gothic Fantasy; Tone: Grim, immersive; Format: 2nd-person sensory narrative."
    enabled: bool = True

    def compile(self) -> str:
        if not self.enabled or not self.text.strip():
            return ""
        # Standard AI Dungeon format using square brackets for meta-instruction
        return f"[{self.text.strip()}]"
