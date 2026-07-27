"""AIPG fork: read-only proxy to the AI Power Grid's live status endpoints.

The chat UI shows which grid workers are online and how each model is performing
(tokens/sec, TTFT, latency). Rather than let the browser call the grid directly
(CORS + exposing the grid base URL/key), the frontend hits these backend routes,
which fan out to the configured grid base URL and return the JSON unchanged.

Isolated in its own module (mirrors grid_model_sync) to keep the fork rebasable
onto upstream Onyx.
"""

from typing import Any

import httpx
from fastapi import APIRouter
from fastapi import Depends

from onyx.auth.users import current_chat_accessible_user
from onyx.auth.users import current_limited_user
from onyx.configs.app_configs import AIPG_GRID_API_BASE
from onyx.configs.app_configs import AIPG_GRID_API_KEY
from onyx.db.models import User
from onyx.error_handling.error_codes import OnyxErrorCode
from onyx.error_handling.exceptions import OnyxError
from onyx.llm.aipg.identity_assertion import grid_user_token
from onyx.llm.aipg.identity_assertion import GridIdentityError
from onyx.utils.logger import setup_logger

logger = setup_logger()

basic_router = APIRouter(prefix="/grid")


def _grid_origin() -> str:
    """The grid origin (scheme://host[:port]), with any trailing `/v1` or slash
    stripped, so we can append the canonical `/v1/...` paths ourselves."""
    if not AIPG_GRID_API_BASE:
        raise OnyxError(
            OnyxErrorCode.VALIDATION_ERROR,
            "The AI Power Grid status API is not configured (AIPG_GRID_API_BASE).",
        )
    base = AIPG_GRID_API_BASE.strip().rstrip("/")
    if base.endswith("/v1"):
        base = base[: -len("/v1")]
    return base


def _grid_get(path: str) -> dict | list:
    """GET a grid path (e.g. `/v1/workers`) and return parsed JSON. Read-only,
    short timeout; upstream failures surface as a 502 rather than a 500."""
    url = f"{_grid_origin()}{path}"
    headers = {"X-Title": "AIPG Chat"}
    if AIPG_GRID_API_KEY:
        headers["Authorization"] = f"Bearer {AIPG_GRID_API_KEY}"
    try:
        response = httpx.get(url, headers=headers, timeout=8.0)
        response.raise_for_status()
        return response.json()
    except httpx.HTTPStatusError as e:
        raise OnyxError(
            OnyxErrorCode.BAD_GATEWAY,
            f"Grid status request failed: {e}",
            status_code_override=e.response.status_code,
        )
    except (httpx.RequestError, ValueError) as e:
        logger.warning("Grid status fetch failed", extra={"url": url, "error": str(e)})
        raise OnyxError(OnyxErrorCode.BAD_GATEWAY, f"Grid status request failed: {e}")


def _grid_user_get(path: str, user: User) -> dict[str, Any]:
    """Fetch one authenticated Core account resource without exposing credentials."""
    if not AIPG_GRID_API_KEY:
        raise OnyxError(
            OnyxErrorCode.SERVICE_UNAVAILABLE,
            "The AI Power Grid account bridge is not configured.",
        )
    try:
        token = grid_user_token(user)
        response = httpx.get(
            f"{_grid_origin()}{path}",
            headers={
                "apikey": AIPG_GRID_API_KEY,
                "X-Grid-User-Token": token,
                "X-Title": "AIPG Chat",
            },
            timeout=8.0,
        )
        response.raise_for_status()
        payload = response.json()
    except GridIdentityError as exc:
        logger.warning("Grid account identity exchange failed")
        raise OnyxError(
            OnyxErrorCode.SERVICE_UNAVAILABLE,
            "The AI Power Grid account bridge is unavailable.",
        ) from exc
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("Grid account fetch failed", extra={"path": path})
        raise OnyxError(
            OnyxErrorCode.BAD_GATEWAY,
            "The AI Power Grid account service is unavailable.",
        ) from exc
    if not isinstance(payload, dict):
        raise OnyxError(
            OnyxErrorCode.BAD_GATEWAY,
            "The AI Power Grid account service returned an invalid response.",
        )
    return payload


def _number(value: Any, field: str) -> int | float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise OnyxError(
            OnyxErrorCode.BAD_GATEWAY,
            f"The AI Power Grid account response omitted {field}.",
        )
    return value


@basic_router.get("/workers")
def get_grid_workers(
    _user: User | None = Depends(current_chat_accessible_user),
) -> dict | list:
    """Currently-connected grid workers: {count, workers:[{id,name,models,...}]}."""
    return _grid_get("/v1/workers")


@basic_router.get("/models")
def get_grid_model_status(
    _user: User | None = Depends(current_chat_accessible_user),
) -> dict | list:
    """Per-model live status + recent performance (count, tokens_per_s, ttft...)."""
    return _grid_get("/v1/status/models")


@basic_router.get("/account")
def get_grid_account(
    user: User = Depends(current_limited_user),
) -> dict[str, Any]:
    """Canonical Core account and balance for the signed-in Chat user."""
    credits = _grid_user_get("/v1/account/credits", user)
    account_id = credits.get("account_id")
    paid = credits.get("paid")
    if not isinstance(account_id, str) or not account_id:
        raise OnyxError(
            OnyxErrorCode.BAD_GATEWAY,
            "The AI Power Grid account response omitted account_id.",
        )
    if not isinstance(paid, dict):
        raise OnyxError(
            OnyxErrorCode.BAD_GATEWAY,
            "The AI Power Grid account response omitted paid balance.",
        )
    return {
        "account_id": account_id,
        "paid_balance_usd": _number(paid.get("balance_usd"), "paid balance"),
        "total_spendable_usd": _number(
            credits.get("total_spendable_usd"),
            "spendable balance",
        ),
        "total_preview_usd": _number(
            credits.get("total_preview_usd"),
            "preview balance",
        ),
        "charging_enabled": credits.get("charging_enabled") is True,
        "charging_mode": str(credits.get("charging_mode") or "off"),
    }
