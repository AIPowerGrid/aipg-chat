import httpx
import pytest

from onyx.db.models import User
from onyx.error_handling.error_codes import OnyxErrorCode
from onyx.error_handling.exceptions import OnyxError
from onyx.server.manage.llm import grid_status


def _user() -> User:
    return User(id="chat-user")


@pytest.fixture(autouse=True)
def _grid_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        grid_status,
        "AIPG_GRID_API_BASE",
        "https://api.aipowergrid.io/v1",
    )
    monkeypatch.setattr(grid_status, "AIPG_GRID_API_KEY", "grid_service_key")


def test_grid_account_uses_delegated_token_and_normalizes_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, dict]] = []

    monkeypatch.setattr(grid_status, "grid_user_token", lambda _user: "gridu_user")

    def fake_get(url: str, **kwargs) -> httpx.Response:
        calls.append((url, kwargs))
        request = httpx.Request("GET", url)
        return httpx.Response(
            200,
            json={
                "account_id": "account-1",
                "paid": {"balance_usd": 12.5},
                "promotional": {"remaining_usd": 0.25, "active": True},
                "free": {"remaining_usd": 0.1, "active": False},
                "total_spendable_usd": 13.0,
                "total_preview_usd": 13.25,
                "charging_enabled": False,
                "charging_mode": "off",
            },
            request=request,
        )

    monkeypatch.setattr(grid_status.httpx, "get", fake_get)

    assert grid_status.get_grid_account(_user()) == {
        "account_id": "account-1",
        "paid_balance_usd": 12.5,
        "promotional_balance_usd": 0.25,
        "promotional_active": True,
        "daily_balance_usd": 0.1,
        "daily_active": False,
        "total_spendable_usd": 13.0,
        "total_preview_usd": 13.25,
        "charging_enabled": False,
        "charging_mode": "off",
    }
    assert [call[0] for call in calls] == [
        "https://api.aipowergrid.io/v1/account/credits",
    ]
    assert all(
        call[1]["headers"]["X-Grid-User-Token"] == "gridu_user" for call in calls
    )
    assert all(call[1]["headers"]["apikey"] == "grid_service_key" for call in calls)


def test_grid_account_rejects_incomplete_core_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        grid_status,
        "_grid_user_get",
        lambda _path, _user: {
            "account_id": "account-1",
            "paid": {},
            "promotional": {},
            "free": {},
            "charging_enabled": False,
        },
    )

    with pytest.raises(OnyxError) as exc:
        grid_status.get_grid_account(_user())

    assert exc.value.error_code is OnyxErrorCode.BAD_GATEWAY


def test_grid_account_hides_upstream_error_details(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(grid_status, "grid_user_token", lambda _user: "gridu_user")

    def unavailable(*_args, **_kwargs):
        raise httpx.ConnectError("secret internal host")

    monkeypatch.setattr(grid_status.httpx, "get", unavailable)

    with pytest.raises(OnyxError) as exc:
        grid_status.get_grid_account(_user())

    assert exc.value.error_code is OnyxErrorCode.BAD_GATEWAY
    assert "secret internal host" not in exc.value.detail


def test_grid_text_quote_counts_prompt_and_context_and_uses_delegated_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import tiktoken

    calls: list[tuple[str, dict]] = []
    monkeypatch.setattr(grid_status, "grid_user_token", lambda _user: "gridu_user")
    monkeypatch.setattr(
        tiktoken.get_encoding("o200k_base"),
        "encode",
        lambda prompt: [1, 2, 3] if prompt == "hello grid" else [],
    )

    def fake_post(url: str, **kwargs) -> httpx.Response:
        calls.append((url, kwargs))
        request = httpx.Request("POST", url)
        return httpx.Response(
            200,
            json={
                "account_id": "account-1",
                "total_spendable_usd": 0.02,
                "charging_enabled": True,
                "estimate": {
                    "priced": True,
                    "cost_usd": 0.0049,
                    "balance_sufficient": True,
                },
            },
            request=request,
        )

    monkeypatch.setattr(grid_status.httpx, "post", fake_post)

    result = grid_status.get_grid_text_quote(
        grid_status.GridTextQuoteRequest(
            model="gpt-oss-120b",
            prompt="hello grid",
            context_tokens=7,
            max_tokens=2048,
        ),
        _user(),
    )

    assert result["estimate"]["cost_usd"] == 0.0049
    assert calls == [
        (
            "https://api.aipowergrid.io/v1/account/credits/quote",
            {
                "headers": {
                    "apikey": "grid_service_key",
                    "X-Grid-User-Token": "gridu_user",
                    "X-Title": "AIPG Chat",
                },
                "json": {
                    "model": "gpt-oss-120b",
                    "modality": "text",
                    "prompt_tokens": 10,
                    "max_tokens": 2048,
                },
                "timeout": 8.0,
            },
        )
    ]


def test_grid_text_quote_rejects_extra_or_oversized_inputs() -> None:
    assert (
        grid_status.GridTextQuoteRequest(
            model="gpt-oss-120b",
            prompt="hello",
        ).max_tokens
        == 32_768
    )
    with pytest.raises(ValueError):
        grid_status.GridTextQuoteRequest.model_validate(
            {
                "model": "gpt-oss-120b",
                "prompt": "hello",
                "context_tokens": 0,
                "unexpected": True,
            }
        )
    with pytest.raises(ValueError):
        grid_status.GridTextQuoteRequest(
            model="gpt-oss-120b",
            prompt="hello",
            context_tokens=2_000_001,
        )
