"""Optional language-model help for mapping labels that no rule could place.

Off by default. When SPREADER_MODEL_URL points at a local OpenAI-compatible server (llama.cpp's
llama-server), rows the deterministic cascade left unmapped are offered to the model, which may
only answer with a line id from a closed list or "none". Numbers never go to the model.

SPREADER_MODEL_ROLE says what the model is for (DECISIONS D52):
- `live` (the default when a URL is set): the last step of the mapping cascade, as above.
- `shadow`: a learning period. The model takes no part in spreading; after each run it gives a hidden second
  opinion on every row (spreader.shadow), kept apart from the spread for later comparison with the analyst.
"""

from __future__ import annotations

import os
from typing import Any

ROLES = ("live", "shadow")


def _role() -> str:
    role = os.environ.get("SPREADER_MODEL_ROLE", "live").strip().lower()
    if role not in ROLES:
        raise ValueError(f"SPREADER_MODEL_ROLE must be one of {', '.join(ROLES)}, not {role!r}")
    return role


def _mapper() -> Any:
    from .local import LocalModelMapper

    return LocalModelMapper(os.environ["SPREADER_MODEL_URL"], model_name=os.environ.get("SPREADER_MODEL_NAME", "local"))


def configured_model() -> tuple[Any, str]:
    """The model that takes part in spreading, and its id for the run record; (None, "none") when there is none."""
    if not os.environ.get("SPREADER_MODEL_URL") or _role() != "live":
        return None, "none"
    mapper = _mapper()
    return mapper, f"local:{mapper.model_name}"


def shadow_model() -> tuple[Any, str]:
    """The model that gives the hidden second opinion, and its id; (None, "none") unless the role is `shadow`."""
    if not os.environ.get("SPREADER_MODEL_URL") or _role() != "shadow":
        return None, "none"
    mapper = _mapper()
    return mapper, f"local:{mapper.model_name}"
