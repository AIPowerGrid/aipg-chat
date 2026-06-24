# SPDX-License-Identifier: MIT
"""SIWE (Sign-In With Ethereum) wallet login.

Passwordless wallet auth alongside the standard email/password flow: the client
signs a short-lived, single-use server nonce with their wallet; we recover the
signer, find-or-create a user keyed by that wallet, and issue the normal session
cookie via the same `auth_backend.login()` path the password flow uses.

Self-contained and gated by ENABLE_WALLET_LOGIN so it composes cleanly with the
existing auth stack (and stays easy to upstream).
"""
import os
import re
import secrets

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi_users.exceptions import UserAlreadyExists, UserNotExists
from pydantic import BaseModel

from onyx.auth.schemas import UserCreate, UserRole
from onyx.auth.users import auth_backend, get_user_manager
from onyx.redis.redis_pool import get_redis_client
from onyx.utils.logger import setup_logger

logger = setup_logger()

ENABLE_WALLET_LOGIN = os.environ.get("ENABLE_WALLET_LOGIN", "").lower() == "true"
WALLET_EMAIL_DOMAIN = os.environ.get("WALLET_EMAIL_DOMAIN", "wallet.local")
NONCE_TTL_SECONDS = 300
_NONCE_PREFIX = "wallet_nonce:"

router = APIRouter(prefix="/auth/wallet", tags=["auth"])


class NonceResponse(BaseModel):
    nonce: str
    message: str


class WalletVerifyRequest(BaseModel):
    message: str
    signature: str
    address: str


def _require_enabled() -> None:
    if not ENABLE_WALLET_LOGIN:
        raise HTTPException(status_code=404, detail="Wallet login is not enabled")


@router.post("/nonce", response_model=NonceResponse)
async def wallet_nonce(request: Request) -> NonceResponse:
    """Issue a single-use nonce + the exact message the wallet should sign."""
    _require_enabled()
    nonce = secrets.token_hex(16)
    get_redis_client(tenant_id=None).set(f"{_NONCE_PREFIX}{nonce}", "1", ex=NONCE_TTL_SECONDS)
    host = request.headers.get("host", "this site")
    message = (
        f"{host} wants you to sign in with your Ethereum account.\n\n"
        f"Sign in to AI Power Grid.\n\nNonce: {nonce}"
    )
    return NonceResponse(nonce=nonce, message=message)


@router.post("/verify")
async def wallet_verify(
    body: WalletVerifyRequest,
    request: Request,
    user_manager=Depends(get_user_manager),
    strategy=Depends(auth_backend.get_strategy),
):
    """Verify a SIWE signature and issue an Onyx session cookie for the wallet."""
    _require_enabled()
    try:
        from eth_account import Account
        from eth_account.messages import encode_defunct
    except ImportError:
        raise HTTPException(status_code=501, detail="Wallet login unavailable (eth-account not installed)")

    # 1) Nonce must be one we issued and not yet used (single-use → anti-replay).
    match = re.search(r"Nonce: ([0-9a-fA-F]+)", body.message)
    nonce = match.group(1) if match else None
    if not nonce or not get_redis_client(tenant_id=None).delete(f"{_NONCE_PREFIX}{nonce}"):
        raise HTTPException(status_code=401, detail="Invalid or expired nonce. Please retry.")

    # 2) Signature must recover to the claimed address.
    try:
        recovered = Account.recover_message(encode_defunct(text=body.message), signature=body.signature)
    except Exception:
        raise HTTPException(status_code=401, detail="Signature verification failed.")
    if recovered.lower() != body.address.lower():
        raise HTTPException(status_code=401, detail="Signature does not match address.")

    wallet = recovered.lower()
    email = f"{wallet}@{WALLET_EMAIL_DOMAIN}"

    # 3) Find or create the wallet's user, then issue the standard session cookie.
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

    return await auth_backend.login(strategy, user)
