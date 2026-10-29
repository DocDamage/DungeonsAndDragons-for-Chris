from typing import List
from pydantic import BaseModel, Field


class Memory(BaseModel):
    """Pinned top-of-context facts that never roll off the sliding window."""
    front_memory: str = ""
    pinned_facts: List[str] = Field(default_factory=list)

    def compile(self) -> str:
        parts = []
        if self.front_memory.strip():
            parts.append(self.front_memory.strip())
        if self.pinned_facts:
            facts_str = "\n".join(f"- {f.strip()}" for f in self.pinned_facts if f.strip())
            parts.append(f"Essential Facts:\n{facts_str}")
        return "\n\n".join(parts)
