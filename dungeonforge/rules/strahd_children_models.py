"""Durst child spirits and their source-specific, explicitly reviewed side quest."""
import time
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class DurstSpirit(BaseModel):
    id: Literal["rose", "thorn"]
    name: str
    host_id: str | None = None
    host_name: str | None = None
    remains_location: Literal["unreviewed", "carried", "family_crypt", "buried_outside"] = "unreviewed"
    carrier_id: str | None = None
    carrier_name: str | None = None


class DurstChildrenEvent(BaseModel):
    id: str
    action: str
    actor_id: str | None = None
    actor_name: str | None = None
    spirit: str | None = None
    spell: str | None = None
    reason: str
    source_path: str
    effects: list[str] = Field(default_factory=list)
    confirmations: dict[str, bool] = Field(default_factory=dict)
    before: dict = Field(default_factory=dict)
    after: dict = Field(default_factory=dict)
    created_at: float = Field(default_factory=time.time)


class DurstChildrenState(BaseModel):
    met: bool = False
    diary_found: bool = False
    diary_holder_id: str | None = None
    diary_holder_name: str | None = None
    secret_revealed: bool = False
    burial_promised: bool = False
    invited: bool = False
    at_peace: bool = False
    spirits: list[DurstSpirit] = Field(default_factory=lambda: [
        DurstSpirit(id="rose", name='Rosavalda "Rose" Durst'),
        DurstSpirit(id="thorn", name='Thornboldt "Thorn" Durst'),
    ])
    events: list[DurstChildrenEvent] = Field(default_factory=list)


class DurstChildrenRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_id: str = Field(min_length=1, max_length=120, pattern=r"^[A-Za-z0-9_-]+$")
    action: Literal["meet", "find_diary", "rose_bargain", "invite_children", "consent_possession", "release_possession", "take_remains", "transfer_remains", "place_in_crypt", "retrieve_remains", "use_ability", "bury_children", "leave_children"]
    actor_id: str
    spirit: Literal["rose", "thorn"] | None = None
    spell: Literal["Mending", "Light", "Shocking Grasp", "Mage Hand"] | None = None
    actual_event_confirmed: bool = False
    burial_promise_confirmed: bool = False
    friendly_host_confirmed: bool = False
    player_host_confirmed: bool = False
    host_consent_confirmed: bool = False
    spell_requirements_confirmed: bool = False
    reason: str = Field(min_length=1, max_length=2000)
    expected_updated_at: float | None = None
