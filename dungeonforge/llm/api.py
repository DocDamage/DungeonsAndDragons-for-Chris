import json
import re
from typing import List, Dict, Any, Optional
import httpx
from dungeonforge.llm.base import BaseLLMClient, LLMResponse


class APIClient(BaseLLMClient):
    """Universal API client supporting OpenAI, OpenRouter, Ollama, and local OpenAI-compatible endpoints."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = "http://localhost:11434/v1",  # Defaults to local Ollama
        model: str = "llama3"
    ):
        self.api_key = api_key or "sk-no-key-required"
        self.base_url = base_url.rstrip("/")
        self.model = model

    async def generate(self, messages: List[Dict[str, str]], temperature: float = 0.8) -> LLMResponse:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": 1024
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(f"{self.base_url}/chat/completions", headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
            raw_text = data["choices"][0]["message"]["content"]

        # Parse state updates if model output has ```state_update JSON
        clean_text, state_updates = self._extract_state_updates(raw_text)

        return LLMResponse(
            text=clean_text,
            state_updates=state_updates,
            model=self.model
        )

    def _extract_state_updates(self, text: str) -> tuple[str, Dict[str, Any]]:
        pattern = r"```(?:state_update|json)?\s*(\{\s*.*?\s*\})\s*```"
        match = re.search(pattern, text, re.DOTALL)
        state_updates = {}
        clean_text = text
        if match:
            try:
                state_updates = json.loads(match.group(1))
                clean_text = text[:match.start()].strip() + "\n" + text[match.end():].strip()
            except Exception:
                pass
        return clean_text.strip(), state_updates
