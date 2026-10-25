"""The exception queue every engine shares: what a person must look at, and how it was settled.

An exception has a stable id built from its reason code and the content of the records it is
about. Rerunning on the same inputs reproduces the same id, so a person's resolution carries
over; if a record changes, the id changes and the exception opens again rather than inheriting
a decision made about different data.

Who may resolve: a named person. Resolutions by "system", "model", "ai" or an empty name are
refused, so a generated explanation can never close an exception by itself. Blockers need a
written note.
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from .fingerprint import content_hash


class Severity(str, Enum):
    BLOCKER = "blocker"  # must be resolved before the result can be used
    WARNING = "warning"  # should be looked at; does not stop the result
    INFO = "info"  # recorded for the audit trail


class ExceptionStatus(str, Enum):
    OPEN = "open"
    RESOLVED = "resolved"


class Resolution(BaseModel):
    action: str  # from the engine's closed list, e.g. "accept_difference", "write_off", "escalate"
    note: str = ""
    actor: str
    at: str


class ExceptionItem(BaseModel):
    id: str
    engine: str  # recon | invoice | statements
    code: str  # reason code, e.g. AMOUNT_DIFFERENCE
    severity: Severity
    title: str  # one line a finance analyst understands
    detail: str  # what was found, with the numbers
    subjects: list[str]  # ids of the records it is about
    evidence: dict[str, Any] = Field(default_factory=dict)
    suggested_action: str = ""
    status: ExceptionStatus = ExceptionStatus.OPEN
    resolution: Resolution | None = None


def exception_id(engine: str, code: str, subject_fingerprints: list[str]) -> str:
    return f"{code.lower()}-{content_hash([engine, code, sorted(subject_fingerprints)], 12)}"


_AUTOMATED = {"system", "model", "ai", "llm", "bot", "auto", "automation", "automated", "assistant", "claude", "gpt",
              "chatgpt", "copilot", "agent", "gemini", "script", "service", "robot", "rpa", "localuser", "anonymous",
              "unknown", "default", "user", "test"}


def is_person(actor: str | None) -> bool:
    """A name that could be a person's: has letters, and no word that names an automated actor.

    This is a guard against obvious misuse ("system", "AI assistant", "Claude Code", "local_user"), not identity:
    names are unverified until the deployment adds sign-in (THREAT_MODEL T26).
    """
    words = re.findall(r"[a-z]+", (actor or "").lower().replace("local-user", "localuser").replace("local_user", "localuser"))
    if not words or sum(len(w) for w in words) < 2:
        return False
    return not any(w in _AUTOMATED or w.startswith("gpt") for w in words)


def same_person(a: str | None, b: str | None) -> bool:
    """'alice', 'Alice.' and ' ALICE ' are the same name."""
    return re.sub(r"[^a-z0-9]", "", (a or "").lower()) == re.sub(r"[^a-z0-9]", "", (b or "").lower())


class ResolutionError(ValueError):
    pass


def check_resolution(item: ExceptionItem, action: str, note: str, actor: str, allowed_actions: set[str]) -> None:
    """Refuse a resolution that does not meet the queue's rules (raises ResolutionError)."""
    if not is_person(actor):
        raise ResolutionError("A named reviewer must resolve exceptions; automated or anonymous actors cannot.")
    if action not in allowed_actions:
        raise ResolutionError(f"'{action}' is not a resolution for {item.code}; use one of: {', '.join(sorted(allowed_actions))}")
    if item.severity is Severity.BLOCKER and len(note.strip()) < 5:
        raise ResolutionError("A blocker needs a written note explaining the resolution.")
