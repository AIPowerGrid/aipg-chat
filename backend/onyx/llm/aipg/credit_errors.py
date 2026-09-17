"""Client-safe credit errors; never persist provider bodies or credentials."""

import os
import re

GRID_CREDIT_ERROR = "Insufficient Grid credits. Add credits to continue."


def grid_credit_error(exc: Exception, api_base: str | None) -> str | None:
    configured_base = os.environ.get("AIPG_GRID_API_BASE", "").rstrip("/")
    if not configured_base or (api_base or "").rstrip("/") != configured_base:
        return None

    # LiteLLM/agent-loop wrappers can nest the original HTTP exception.
    current: BaseException | None = exc
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if getattr(current, "status_code", None) == 402 and re.search(
            r"\binsufficient (?:grid )?credits?\b", str(current), re.IGNORECASE
        ):
            return GRID_CREDIT_ERROR
        current = current.__cause__ or current.__context__
    return None
