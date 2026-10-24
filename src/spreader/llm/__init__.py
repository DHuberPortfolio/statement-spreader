"""Optional language-model help for mapping labels that no rule could place.

Off by default. When SPREADER_MODEL_URL points at a local OpenAI-compatible server (llama.cpp's
llama-server), rows the deterministic cascade left unmapped are offered to the model, which may
only answer with a line id from a closed list or "none". Numbers never go to the model.
"""

from __future__ import annotations

import os
from typing import Any


def configured_model() -> tuple[Any, str]:
    url = os.environ.get("SPREADER_MODEL_URL")
    if not url:
        return None, "none"
    from .local import LocalModelMapper

    mapper = LocalModelMapper(url, model_name=os.environ.get("SPREADER_MODEL_NAME", "local"))
    return mapper, f"local:{mapper.model_name}"
