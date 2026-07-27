# SPDX-License-Identifier: MIT
"""Core-verified SIWE wallet login.

Passwordless wallet auth alongside the standard email/password flow: Core
issues and verifies the service-, origin-, wallet-, chain-, and nonce-bound
message. Chat finds or creates its local user, binds that stable local identity
to the canonical Core account, and only then issues the normal Chat session.

The integration is gated by ENABLE_WALLET_LOGIN so it composes cleanly with the
existing auth stack.
"""

import os
import secrets

from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException
from fastapi import Request
from fastapi_users.exceptions import UserAlreadyExists
from fastapi_users.exceptions import UserNotExists
from pydantic import BaseModel

from onyx.auth.schemas import UserCreate
from onyx.auth.schemas import UserRole
from onyx.auth.users import auth_backend
from onyx.auth.users import get_user_manager
from onyx.llm.aipg.identity_assertion import bind_local_identity
from onyx.llm.aipg.identity_assertion import exchange_wallet_identity
from onyx.llm.aipg.identity_assertion import GridIdentityError
from onyx.llm.aipg.identity_assertion import wallet_challenge
from onyx.utils.logger import setup_logger

logger = setup_logger()

ENABLE_WALLET_LOGIN = os.environ.get("ENABLE_WALLET_LOGIN", "").lower() == "true"
WALLET_EMAIL_DOMAIN = os.environ.get("WALLET_EMAIL_DOMAIN", "wallet.local")
router = APIRouter(prefix="/auth/wallet", tags=["auth"])


class NonceResponse(BaseModel):
    nonce: str
    message: str


class WalletVerifyRequest(BaseModel):
    message: str
    signature: str
    address: str


class WalletChallengeRequest(BaseModel):
    address: str


def _require_enabled() -> None:
    if not ENABLE_WALLET_LOGIN:
        raise HTTPException(status_code=404, detail="Wallet login is not enabled")


@router.post("/nonce", response_model=NonceResponse)
async def wallet_nonce(body: WalletChallengeRequest) -> NonceResponse:
    """Proxy Core's service-, wallet-, origin-, and nonce-bound SIWE message."""
    _require_enabled()
    try:
        proof = await wallet_challenge(body.address)
    except GridIdentityError as exc:
        logger.warning("Grid wallet challenge failed: %s", exc)
        raise HTTPException(
            status_code=503, detail="Wallet login is temporarily unavailable"
        )
    return NonceResponse(nonce=str(proof["nonce"]), message=str(proof["message"]))


@router.post("/verify")
async def wallet_verify(
    body: WalletVerifyRequest,
    request: Request,
    user_manager=Depends(get_user_manager),
    strategy=Depends(auth_backend.get_strategy),
):
    """Verify Core SIWE and issue an Onyx session bound to its canonical account."""
    _require_enabled()
    try:
        grid_identity = await exchange_wallet_identity(
            message=body.message,
            signature=body.signature,
            address=body.address,
        )
    except GridIdentityError as exc:
        logger.warning("Grid wallet verification failed: %s", exc)
        raise HTTPException(status_code=401, detail="Wallet proof was rejected")

    wallet = str(grid_identity["wallet"]).lower()
    email = f"{wallet}@{WALLET_EMAIL_DOMAIN}"

    # Find or create the wallet's local user. Then bind that stable local id to
    # the already-proved canonical wallet account before issuing a session.
    try:
        user = await user_manager.get_by_email(email)
    except UserNotExists:
        try:
            user = await user_manager.create(
                UserCreate(
                    email=email,
                    password=secrets.token_urlsafe(32),
                    role=UserRole.BASIC,
                    is_verified=True,
                ),
                safe=True,
                request=request,
            )
            logger.info("Created wallet user for %s", wallet)
        except UserAlreadyExists:
            user = await user_manager.get_by_email(email)

    try:
        await bind_local_identity(str(grid_identity["access_token"]), user.id)
    except GridIdentityError as exc:
        logger.warning("Grid wallet/local identity bind failed: %s", exc)
        raise HTTPException(
            status_code=503, detail="Wallet login is temporarily unavailable"
        )

    return await auth_backend.login(strategy, user)
