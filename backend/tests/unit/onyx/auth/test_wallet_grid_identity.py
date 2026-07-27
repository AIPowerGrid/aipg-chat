from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from onyx.auth import wallet
from onyx.llm.aipg.identity_assertion import GridIdentityError


def _request() -> Request:
    return Request({"type": "http", "method": "POST", "path": "/"})


@pytest.mark.asyncio
async def test_wallet_verify_binds_core_identity_before_login(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = SimpleNamespace(id="local-user-id")
    manager = SimpleNamespace(get_by_email=AsyncMock(return_value=user))
    exchange = AsyncMock(
        return_value={
            "access_token": "core-step-up-token",
            "account_id": "canonical-account-id",
            "wallet": "0xAbC",
        }
    )
    bind = AsyncMock(return_value={"account_id": "canonical-account-id"})
    login = AsyncMock(return_value={"session": "issued"})
    monkeypatch.setattr(wallet, "ENABLE_WALLET_LOGIN", True)
    monkeypatch.setattr(wallet, "exchange_wallet_identity", exchange)
    monkeypatch.setattr(wallet, "bind_local_identity", bind)
    monkeypatch.setattr(wallet.auth_backend, "login", login)

    result = await wallet.wallet_verify(
        wallet.WalletVerifyRequest(
            message="core-issued-siwe",
            signature="0xsigned",
            address="0xAbC",
        ),
        _request(),
        user_manager=manager,
        strategy=object(),
    )

    assert result == {"session": "issued"}
    manager.get_by_email.assert_awaited_once_with("0xabc@wallet.local")
    bind.assert_awaited_once_with("core-step-up-token", "local-user-id")
    login.assert_awaited_once()


@pytest.mark.asyncio
async def test_wallet_verify_does_not_login_when_core_bind_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = SimpleNamespace(id="local-user-id")
    manager = SimpleNamespace(get_by_email=AsyncMock(return_value=user))
    login = AsyncMock()
    monkeypatch.setattr(wallet, "ENABLE_WALLET_LOGIN", True)
    monkeypatch.setattr(
        wallet,
        "exchange_wallet_identity",
        AsyncMock(
            return_value={
                "access_token": "core-step-up-token",
                "account_id": "canonical-account-id",
                "wallet": "0xabc",
            }
        ),
    )
    monkeypatch.setattr(
        wallet,
        "bind_local_identity",
        AsyncMock(side_effect=GridIdentityError("Core unavailable")),
    )
    monkeypatch.setattr(wallet.auth_backend, "login", login)

    with pytest.raises(HTTPException) as exc_info:
        await wallet.wallet_verify(
            wallet.WalletVerifyRequest(
                message="core-issued-siwe",
                signature="0xsigned",
                address="0xabc",
            ),
            _request(),
            user_manager=manager,
            strategy=object(),
        )

    assert exc_info.value.status_code == 503
    login.assert_not_awaited()
