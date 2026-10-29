from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from pydantic import BaseModel


class LLMResponse(BaseModel):
    text: str
    state_updates: Dict[str, Any] = {}
    model: str = "mock"


class BaseLLMClient(ABC):
    @abstractmethod
    async def generate(self, messages: List[Dict[str, str]], temperature: float = 0.8) -> LLMResponse:
        pass
