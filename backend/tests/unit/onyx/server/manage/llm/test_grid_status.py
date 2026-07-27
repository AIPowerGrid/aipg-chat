from types import SimpleNamespace

import httpx
import pytest

from onyx.error_handling.error_codes import OnyxErrorCode
from onyx.error_handling.exceptions import OnyxError
from onyx.server.manage.llm import grid_status


def _user() -> SimpleNamespace:
    return SimpleNamespace(id="chat-user", is_anonymous=False)


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
        if url.endswith("/v1/account"):
            return httpx.Response(
                200,
                json={"account_id": "account-1"},
                request=request,
            )
        return httpx.Response(
            200,
            json={
                "paid": {"balance_usd": 12.5},
                "total_spendable_usd": 13.0,
                "total_preview_usd": 13.25,
                "charging_enabled": False,
            },
            request=request,
        )

    monkeypatch.setattr(grid_status.httpx, "get", fake_get)

    assert grid_status.get_grid_account(_user()) == {
        "account_id": "account-1",
        "paid_balance_usd": 12.5,
        "total_spendable_usd": 13.0,
        "total_preview_usd": 13.25,
        "charging_enabled": False,
    }
    assert [call[0] for call in calls] == [
        "https://api.aipowergrid.io/v1/account",
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
        lambda path, _user: (
            {"account_id": "account-1"}
            if path == "/v1/account"
            else {"paid": {}, "charging_enabled": False}
        ),
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
