"""Canonical Core identity exchange for the AIPG provider.

The filename remains stable for the small AIPG fork surface, but live requests
use Core-issued user tokens. Legacy signed assertions are no longer emitted.
"""

from __future__ import annotations

import hashlib
import os
import threading
import time
import weakref
from collections import OrderedDict
from collections.abc import Callable
from typing import Any
from typing import TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    from onyx.db.models import User
    from onyx.server.manage.llm.models import LLMProviderView

_USER_TOKEN_HEADER = "X-Grid-User-Token"
_LEGACY_ASSERTION_HEADER = "X-Grid-User-Assertion"
_CACHE_LIMIT = 10_000
_REFRESH_EARLY_SECONDS = 60
_HTTP_TIMEOUT_SECONDS = 10.0
_cache_lock = threading.Lock()
_token_cache: OrderedDict[str, tuple[str, float]] = OrderedDict()
_token_locks: weakref.WeakValueDictionary[str, threading.Lock] = (
    weakref.WeakValueDictionary()
)


class GridIdentityError(RuntimeError):
    pass


def _grid_config(api_key: str | None = None) -> tuple[str, str]:
    base = (os.environ.get("AIPG_GRID_API_BASE") or "").strip().rstrip("/")
    key = (api_key or os.environ.get("AIPG_GRID_API_KEY") or "").strip()
    if not base or not key:
        raise GridIdentityError("Grid identity exchange is not configured")
    return base, key


def _invalidate_subject_tokens(subject: str) -> None:
    """Drop cached Core tokens after a proof changes the subject's account."""
    with _cache_lock:
        stale = [
            cache_key
            for cache_key in _token_cache
            if cache_key.partition(":")[2] == subject
        ]
        for cache_key in stale:
            _token_cache.pop(cache_key, None)


def _app_subject(user: User | None) -> str | None:
    if user is None:
        instance = os.environ.get("AIPG_CHAT_INSTANCE_ID", "default").strip()
        return f"aipg-chat:system:{instance or 'default'}"
    if user.is_anonymous:
        return None
    return f"aipg-chat:{user.id}"


def _response_payload(response: httpx.Response) -> dict[str, Any]:
    if response.status_code != 200:
        raise GridIdentityError(
            f"Grid identity exchange failed with status {response.status_code}"
        )
    try:
        payload = response.json()
    except ValueError as exc:
        raise GridIdentityError("Grid identity exchange returned invalid JSON") from exc
    if not isinstance(payload, dict):
        raise GridIdentityError("Grid identity exchange returned invalid JSON")
    return payload


def _require_identity(payload: dict[str, Any]) -> dict[str, Any]:
    if not payload.get("access_token") or not payload.get("account_id"):
        raise GridIdentityError(
            "Grid identity exchange returned an incomplete identity"
        )
    return payload


def _service_token(api_key: str, subject: str) -> str:
    base, key = _grid_config(api_key)
    cache_key = f"{hashlib.sha256(key.encode()).hexdigest()}:{subject}"
    now = time.monotonic()
    with _cache_lock:
        cached = _token_cache.get(cache_key)
        if cached and cached[1] > now:
            _token_cache.move_to_end(cache_key)
            return cached[0]
        _token_cache.pop(cache_key, None)
        subject_lock = _token_locks.get(cache_key)
        if subject_lock is None:
            subject_lock = threading.Lock()
            _token_locks[cache_key] = subject_lock

    # Coalesce a cold burst for one user without serializing exchanges for
    # unrelated users. The weak lock disappears when no caller references it.
    with subject_lock:
        now = time.monotonic()
        with _cache_lock:
            cached = _token_cache.get(cache_key)
            if cached and cached[1] > now:
                _token_cache.move_to_end(cache_key)
                return cached[0]
        try:
            response = httpx.post(
                f"{base}/auth/service/exchange",
                headers={"apikey": key},
                json={"subject": subject},
                timeout=_HTTP_TIMEOUT_SECONDS,
            )
        except httpx.HTTPError as exc:
            raise GridIdentityError("Grid identity exchange is unavailable") from exc
        payload = _require_identity(_response_payload(response))
        token = str(payload["access_token"])
        ttl = max(60, int(payload.get("expires_in") or 900))
        expires = now + max(1, ttl - _REFRESH_EARLY_SECONDS)
        with _cache_lock:
            _token_cache[cache_key] = (token, expires)
            _token_cache.move_to_end(cache_key)
            while len(_token_cache) > _CACHE_LIMIT:
                _token_cache.popitem(last=False)
        return token


def grid_user_token(user: User) -> str:
    """Return a short-lived Core token for one authenticated Chat user."""
    subject = _app_subject(user)
    if subject is None:
        raise GridIdentityError("Anonymous users do not have a Grid identity")
    _base, key = _grid_config()
    return _service_token(key, subject)


async def _post_identity(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    base, key = _grid_config()
    try:
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT_SECONDS) as client:
            response = await client.post(
                f"{base}{path}",
                headers={"apikey": key},
                json=payload,
            )
    except httpx.HTTPError as exc:
        raise GridIdentityError("Grid identity exchange is unavailable") from exc
    return _response_payload(response)


async def exchange_google_identity(id_token: str, user_id: object) -> dict[str, Any]:
    if not id_token:
        raise GridIdentityError("Google login did not return an ID token")
    subject = f"aipg-chat:{user_id}"
    identity = _require_identity(
        await _post_identity(
            "/auth/google/exchange",
            {
                "id_token": id_token,
                "app_subject": subject,
            },
        )
    )
    _invalidate_subject_tokens(subject)
    return identity


async def wallet_challenge(address: str) -> dict[str, Any]:
    base_url = (os.environ.get("WEB_DOMAIN") or "http://localhost:3000").rstrip("/")
    parsed = httpx.URL(base_url)
    if not parsed.host:
        raise GridIdentityError("Chat origin is not configured")
    authority = parsed.host
    if parsed.port and parsed.port not in {80, 443}:
        authority = f"{authority}:{parsed.port}"
    result = await _post_identity(
        "/auth/wallet/challenge",
        {
            "address": address,
            "domain": authority,
            "uri": base_url,
            "chain_id": 8453,
            "app_subject": f"wallet:{address.strip().lower()}",
        },
    )
    if not result.get("nonce") or not result.get("message"):
        raise GridIdentityError("Grid wallet challenge was incomplete")
    return result


async def exchange_wallet_identity(
    *,
    message: str,
    signature: str,
    address: str,
) -> dict[str, Any]:
    identity = _require_identity(
        await _post_identity(
            "/auth/wallet/exchange",
            {
                "message": message,
                "signature": signature,
                "address": address,
                "app_subject": f"wallet:{address.strip().lower()}",
            },
        )
    )
    if not identity.get("wallet"):
        raise GridIdentityError("Grid wallet exchange returned an incomplete identity")
    return identity


async def bind_local_identity(user_token: str, user_id: object) -> dict[str, Any]:
    subject = f"aipg-chat:{user_id}"
    result = await _post_identity(
        "/auth/service/bind",
        {
            "subject": subject,
            "user_token": user_token,
        },
    )
    _invalidate_subject_tokens(subject)
    return result


def grid_image_headers_factory(
    api_base: str | None,
    api_key: str | None,
    user: User | None,
) -> Callable[[], dict[str, str]] | None:
    """Bind an image tool to its user, refreshing identity before each request."""
    configured_base = os.environ.get("AIPG_GRID_API_BASE", "").rstrip("/")
    # Image configuration has no provider display name. Require the same
    # service credential as account/login exchange to preserve its namespace.
    configured_key = os.environ.get("AIPG_GRID_API_KEY", "").strip()
    base_matches = (
        bool(configured_base) and (api_base or "").rstrip("/") == configured_base
    )
    grid_key = bool(api_key) and (
        api_key == configured_key or api_key.startswith("grid_")
    )
    if not base_matches and not grid_key:
        return None
    subject = _app_subject(user) if user is not None else None

    def current_user_token() -> dict[str, str]:
        if not base_matches:
            # Do not treat an old alias/misconfigured Grid endpoint as a generic
            # provider: that would bypass delegation and leak the service key.
            raise GridIdentityError(
                "Grid image endpoint must match the configured Grid API"
            )
        if not subject or not api_key or api_key != configured_key:
            raise GridIdentityError(
                "Grid image generation requires an authenticated Chat identity"
            )
        return {_USER_TOKEN_HEADER: _service_token(api_key, subject)}

    return current_user_token


def grid_identity_headers(
    headers: dict[str, str] | None,
    llm_provider: LLMProviderView,
    user: User | None,
) -> tuple[dict[str, str], Callable[[], dict[str, str]] | None]:
    """Return static headers plus a lazy, cached canonical user-token factory."""
    reserved = {_USER_TOKEN_HEADER.lower(), _LEGACY_ASSERTION_HEADER.lower()}
    clean = {
        key: value
        for key, value in (headers or {}).items()
        if key.lower() not in reserved
    }
    configured_base = os.environ.get("AIPG_GRID_API_BASE", "").rstrip("/")
    configured_name = os.environ.get("AIPG_GRID_PROVIDER_NAME", "AI Power Grid")
    provider_base = (llm_provider.api_base or "").rstrip("/")
    provider_api_key = llm_provider.api_key
    if (
        llm_provider.name != configured_name
        or not configured_base
        or provider_base != configured_base
        or not provider_api_key
    ):
        return clean, None

    subject = _app_subject(user)
    if subject is None:
        return clean, None

    def current_user_token() -> dict[str, str]:
        return {_USER_TOKEN_HEADER: _service_token(provider_api_key, subject)}

    return clean, current_user_token
