import threading
import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import httpx
import pytest

from onyx.llm.aipg import identity_assertion


def _provider(name: str = "AI Power Grid") -> SimpleNamespace:
    return SimpleNamespace(
        id=1,
        name=name,
        provider="openai-compatible",
        api_key="grid_test_bridge",
        api_base="https://api.aipowergrid.io/v1",
    )


def _headers(headers, provider, user) -> dict[str, str]:
    clean, factory = identity_assertion.grid_identity_headers(headers, provider, user)
    if factory is not None:
        clean.update(factory())
    return clean


@pytest.fixture(autouse=True)
def _grid_env(monkeypatch):
    monkeypatch.setenv("AIPG_GRID_API_BASE", "https://api.aipowergrid.io/v1")
    monkeypatch.setenv("AIPG_GRID_API_KEY", "grid_test_bridge")
    monkeypatch.setenv("AIPG_GRID_PROVIDER_NAME", "AI Power Grid")
    with identity_assertion._cache_lock:
        identity_assertion._token_cache.clear()
        identity_assertion._token_locks.clear()


def test_google_user_uses_canonical_native_token(monkeypatch) -> None:
    subjects = []

    def fake_token(_api_key, subject):
        subjects.append(subject)
        return "gridu_canonical"

    monkeypatch.setattr(identity_assertion, "_service_token", fake_token)
    user = SimpleNamespace(id="user-id", is_anonymous=False)
    headers = _headers(
        {
            "X-Grid-User-Assertion": "attacker-value",
            "X-Grid-User-Token": "attacker-token",
            "X-Trace": "ok",
        },
        _provider(),
        user,
    )
    assert headers == {
        "X-Trace": "ok",
        "X-Grid-User-Token": "gridu_canonical",
    }
    assert subjects == ["aipg-chat:user-id"]


def test_identity_header_never_leaks_to_other_provider(monkeypatch) -> None:
    monkeypatch.setattr(
        identity_assertion,
        "_service_token",
        lambda *_args: pytest.fail("non-Grid provider exchanged identity"),
    )
    headers = _headers(
        {
            "x-grid-user-assertion": "attacker-value",
            "x-grid-user-token": "attacker-token",
        },
        _provider(name="Not Grid"),
        None,
    )
    assert headers == {}


def test_anonymous_user_gets_no_grid_identity(monkeypatch) -> None:
    monkeypatch.setattr(
        identity_assertion,
        "_service_token",
        lambda *_args: pytest.fail("anonymous user exchanged identity"),
    )
    user = SimpleNamespace(is_anonymous=True)
    assert _headers({}, _provider(), user) == {}


def test_image_headers_bind_each_user_and_refresh_per_request(monkeypatch) -> None:
    calls = []

    def fake_token(key, subject):
        calls.append((key, subject))
        return f"gridu_image_{len(calls)}"

    monkeypatch.setattr(identity_assertion, "_service_token", fake_token)
    user_a = SimpleNamespace(id="user-a", is_anonymous=False)
    user_b = SimpleNamespace(id="user-b", is_anonymous=False)
    provider = _provider()
    first = identity_assertion.grid_image_headers_factory(
        provider.api_base,
        provider.api_key,
        user_a,
    )
    second = identity_assertion.grid_image_headers_factory(
        provider.api_base,
        provider.api_key,
        user_b,
    )
    assert first is not None and second is not None
    assert calls == []
    assert first() == {"X-Grid-User-Token": "gridu_image_1"}
    assert second() == {"X-Grid-User-Token": "gridu_image_2"}
    assert first() == {"X-Grid-User-Token": "gridu_image_3"}
    assert calls == [
        ("grid_test_bridge", "aipg-chat:user-a"),
        ("grid_test_bridge", "aipg-chat:user-b"),
        ("grid_test_bridge", "aipg-chat:user-a"),
    ]


@pytest.mark.parametrize(
    "user,key",
    [
        (None, "grid_test_bridge"),
        (SimpleNamespace(is_anonymous=True), "grid_test_bridge"),
        (SimpleNamespace(id="user", is_anonymous=False), None),
        (SimpleNamespace(id="user", is_anonymous=False), "other-service"),
    ],
)
def test_image_headers_reject_missing_identity_or_wrong_service(monkeypatch, user, key):
    monkeypatch.setattr(
        identity_assertion,
        "_service_token",
        lambda *_args: pytest.fail("invalid image identity must not exchange"),
    )
    factory = identity_assertion.grid_image_headers_factory(
        _provider().api_base,
        key,
        user,
    )
    assert factory is not None
    with pytest.raises(identity_assertion.GridIdentityError):
        factory()


@pytest.mark.parametrize(
    "base", [None, "https://example.com/v1", "https://api.aipowergrid.io.evil.test/v1"]
)
def test_image_headers_never_send_grid_identity_to_other_endpoint(base):
    assert (
        identity_assertion.grid_image_headers_factory(
            base,
            "grid_test_bridge",
            SimpleNamespace(id="user", is_anonymous=False),
        )
        is None
    )


def test_internal_call_uses_non_promotional_app_identity(monkeypatch) -> None:
    monkeypatch.setenv("AIPG_CHAT_INSTANCE_ID", "prod")
    monkeypatch.setattr(
        identity_assertion,
        "_service_token",
        lambda _key, subject: f"token-for:{subject}",
    )
    headers = _headers({}, _provider(), None)
    assert headers["X-Grid-User-Token"] == "token-for:aipg-chat:system:prod"


def test_native_token_is_cached_between_llm_attempts(monkeypatch) -> None:
    calls = []

    def fake_post(url, **kwargs):
        calls.append((url, kwargs))
        return httpx.Response(
            200,
            json={
                "access_token": "gridu_cached",
                "account_id": "account-1",
                "expires_in": 900,
            },
        )

    monkeypatch.setattr(identity_assertion.httpx, "post", fake_post)
    user = SimpleNamespace(id="user-id", is_anonymous=False)
    clean, factory = identity_assertion.grid_identity_headers({}, _provider(), user)
    assert clean == {}
    assert factory is not None
    assert factory() == {"X-Grid-User-Token": "gridu_cached"}
    assert factory() == {"X-Grid-User-Token": "gridu_cached"}
    assert len(calls) == 1
    assert calls[0][1]["json"] == {"subject": "aipg-chat:user-id"}


def test_concurrent_native_token_refresh_is_coalesced(monkeypatch) -> None:
    calls = 0
    calls_lock = threading.Lock()

    def fake_post(_url, **_kwargs):
        nonlocal calls
        with calls_lock:
            calls += 1
        time.sleep(0.05)
        return httpx.Response(
            200,
            json={
                "access_token": "gridu_coalesced",
                "account_id": "account-1",
                "expires_in": 900,
            },
        )

    monkeypatch.setattr(identity_assertion.httpx, "post", fake_post)
    with ThreadPoolExecutor(max_workers=12) as executor:
        tokens = list(
            executor.map(
                lambda _index: identity_assertion._service_token(
                    "grid_test_bridge",
                    "aipg-chat:shared-user",
                ),
                range(24),
            )
        )

    assert tokens == ["gridu_coalesced"] * 24
    assert calls == 1


@pytest.mark.asyncio
async def test_google_exchange_binds_server_derived_local_subject(monkeypatch) -> None:
    calls = []

    async def fake_post(path, payload):
        calls.append((path, payload))
        return {"access_token": "gridu_google", "account_id": "account-1"}

    monkeypatch.setattr(identity_assertion, "_post_identity", fake_post)
    result = await identity_assertion.exchange_google_identity(
        "google-id-token",
        "local-user-id",
    )
    assert result["account_id"] == "account-1"
    assert calls == [
        (
            "/auth/google/exchange",
            {
                "id_token": "google-id-token",
                "app_subject": "aipg-chat:local-user-id",
            },
        ),
    ]


@pytest.mark.asyncio
async def test_google_exchange_invalidates_pre_link_token(monkeypatch) -> None:
    async def fake_post(_path, _payload):
        return {"access_token": "gridu_google", "account_id": "account-1"}

    monkeypatch.setattr(identity_assertion, "_post_identity", fake_post)
    subject = "aipg-chat:local-user-id"
    with identity_assertion._cache_lock:
        identity_assertion._token_cache[f"{'a' * 64}:{subject}"] = (
            "gridu_pre_link",
            time.monotonic() + 600,
        )
        identity_assertion._token_cache[f"{'b' * 64}:other-subject"] = (
            "gridu_other",
            time.monotonic() + 600,
        )

    await identity_assertion.exchange_google_identity(
        "google-id-token",
        "local-user-id",
    )

    with identity_assertion._cache_lock:
        assert all(
            key.partition(":")[2] != subject for key in identity_assertion._token_cache
        )
        assert f"{'b' * 64}:other-subject" in identity_assertion._token_cache


@pytest.mark.asyncio
async def test_wallet_proof_then_local_bind_use_same_service(monkeypatch) -> None:
    monkeypatch.setenv("WEB_DOMAIN", "https://aipg.chat")
    calls = []

    async def fake_post(path, payload):
        calls.append((path, payload))
        if path.endswith("/challenge"):
            return {"nonce": "n", "message": "m"}
        if path.endswith("/exchange"):
            return {
                "access_token": "gridu_wallet",
                "account_id": "account-1",
                "wallet": "0x0000000000000000000000000000000000000001",
            }
        return {"status": "linked", "account_id": "account-1"}

    monkeypatch.setattr(identity_assertion, "_post_identity", fake_post)
    address = "0x0000000000000000000000000000000000000001"
    await identity_assertion.wallet_challenge(address)
    identity = await identity_assertion.exchange_wallet_identity(
        message="m",
        signature="0xsigned",
        address=address,
    )
    await identity_assertion.bind_local_identity(
        identity["access_token"],
        "local-user-id",
    )
    assert calls[0] == (
        "/auth/wallet/challenge",
        {
            "address": address,
            "domain": "aipg.chat",
            "uri": "https://aipg.chat",
            "chain_id": 8453,
            "app_subject": f"wallet:{address}",
        },
    )
    assert calls[-1] == (
        "/auth/service/bind",
        {
            "subject": "aipg-chat:local-user-id",
            "user_token": "gridu_wallet",
        },
    )


@pytest.mark.asyncio
async def test_local_bind_invalidates_pre_link_token(monkeypatch) -> None:
    async def fake_post(_path, _payload):
        return {"status": "linked", "account_id": "account-1"}

    monkeypatch.setattr(identity_assertion, "_post_identity", fake_post)
    subject = "aipg-chat:local-user-id"
    with identity_assertion._cache_lock:
        identity_assertion._token_cache[f"{'a' * 64}:{subject}"] = (
            "gridu_pre_link",
            time.monotonic() + 600,
        )

    await identity_assertion.bind_local_identity(
        "gridu_wallet",
        "local-user-id",
    )

    with identity_assertion._cache_lock:
        assert not identity_assertion._token_cache
