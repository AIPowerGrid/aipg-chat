"""Owner-bound image submission and read-only recovery from committed Core results."""

import base64
import hashlib
import json
import os
from collections.abc import Callable
from contextlib import AbstractContextManager
from functools import partial
from typing import Any
from typing import Literal
from uuid import UUID

import httpx
from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field
from pydantic import HttpUrl
from sqlalchemy.orm import Session

from onyx.db.engine.sql_engine import get_session_with_tenant
from onyx.db.grid_image_requests import claim_image_request
from onyx.db.grid_image_requests import finish_image_request
from onyx.db.grid_image_requests import ImageRequestReceipt
from onyx.db.grid_image_requests import read_image_request
from onyx.db.models import User
from onyx.image_gen.interfaces import ImageGenerationProvider
from onyx.llm.aipg.identity_assertion import grid_image_headers_factory
from onyx.llm.aipg.identity_assertion import GridIdentityError
from onyx.utils.b64 import get_image_type_from_bytes
from onyx.utils.url import ssrf_safe_get
from shared_configs.contextvars import get_current_tenant_id


class GridImageRecoveryError(RuntimeError):
    pass


def recovery_for_user(
    user: User, *, api_base: str | None = None, api_key: str | None = None
) -> "GridImageRecovery":
    base = os.environ.get("AIPG_GRID_API_BASE", "") if api_base is None else api_base
    key = os.environ.get("AIPG_GRID_API_KEY", "") if api_key is None else api_key
    headers = grid_image_headers_factory(base, key, user)
    if headers is None or user.is_anonymous:
        raise GridIdentityError(
            "Grid image recovery requires an authenticated identity"
        )
    return GridImageRecovery(
        user_id=user.id,
        api_base=base,
        api_key=key,
        headers_factory=headers,
        sessions=partial(get_session_with_tenant, tenant_id=get_current_tenant_id()),
    )


class CoreImage(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    url: HttpUrl
    key: str = Field(min_length=1, max_length=2048)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    seed: int | None = None


class CoreImageResult(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)
    media: list[CoreImage] = Field(min_length=1, max_length=1)
    model: str = Field(min_length=1, max_length=255)
    worker: str = Field(max_length=255)
    gen_time: float = Field(ge=0)
    recipe_root: str | None = Field(default=None, max_length=255)


class CoreImageReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    job_id: UUID
    state: Literal["completed", "pending", "closed_without_result"]
    actual_micro: int | None = Field(default=None, ge=0, strict=True)
    result: CoreImageResult | None


class GridImageRecovery:
    def __init__(
        self,
        *,
        user_id: UUID,
        api_base: str,
        api_key: str,
        headers_factory: Callable[[], dict[str, str]],
        sessions: Callable[[], AbstractContextManager[Session]],
    ) -> None:
        self.user_id = user_id
        self.api_base = api_base.rstrip("/")
        self.api_key = api_key
        self.headers_factory = headers_factory
        self.sessions = sessions

    def _get(
        self,
        path: str,
        *,
        params: dict[str, str] | None = None,
        missing_ok: bool = False,
    ) -> dict[str, Any] | None:
        headers = {"apikey": self.api_key, **self.headers_factory()}
        try:
            with httpx.Client(timeout=10.0, follow_redirects=False) as client:
                with client.stream(
                    "GET", self.api_base + path, params=params, headers=headers
                ) as response:
                    if response.status_code == 404 and missing_ok:
                        return None
                    response.raise_for_status()
                    body = bytearray()
                    for chunk in response.iter_bytes():
                        body.extend(chunk)
                        if len(body) > 96 * 1024:
                            raise ValueError("Oversized Core image response")
            payload = json.loads(body)
            if not isinstance(payload, dict):
                raise ValueError("Invalid Core image response")
            return payload
        except (httpx.HTTPError, ValueError) as exc:
            raise GridImageRecoveryError(
                "Grid image status is temporarily unavailable"
            ) from exc

    def recover(self, request_id: UUID) -> ImageRequestReceipt | None:
        with self.sessions() as session:
            receipt = read_image_request(
                session, user_id=self.user_id, request_id=request_id
            )
        if receipt is None or receipt.state != "attempted":
            return receipt
        payload = self._get(
            "/media/results", params={"client_ref": str(receipt.id)}, missing_ok=True
        )
        if payload is None:
            # No reservation may mean pre-dispatch crash OR a delayed request.
            # Neither permits a second POST.
            return receipt
        try:
            core = CoreImageReceipt.model_validate(payload)
            if (core.state == "completed") != (core.result is not None):
                raise ValueError("Inconsistent Core image terminal")
            if core.state == "completed" and core.actual_micro is None:
                raise ValueError("Core image terminal is missing its settled cost")
            if core.state == "pending":
                return receipt
            result = core.result.model_dump(mode="json") if core.result else None
            with self.sessions() as session:
                return finish_image_request(
                    session,
                    user_id=self.user_id,
                    request_id=receipt.id,
                    grid_job_id=core.job_id,
                    result=result,
                )
        except ValueError as exc:
            raise GridImageRecoveryError(
                "Grid image returned an invalid recovery result"
            ) from exc

    def generate(
        self,
        *,
        provider: ImageGenerationProvider,
        message_id: int,
        slot: str,
        prompt: str,
        model: str,
        size: str,
    ) -> ImageRequestReceipt:
        digest = hashlib.sha256(
            json.dumps(
                {
                    "api_base": self.api_base,
                    "prompt": prompt,
                    "model": model,
                    "size": size,
                    "n": 1,
                },
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode()
        ).hexdigest()
        with self.sessions() as session:
            receipt = claim_image_request(
                session,
                user_id=self.user_id,
                message_id=message_id,
                slot=slot,
                request_sha256=digest,
            )
        if receipt.may_submit:
            credits = self._get("/account/credits")
            if not credits or credits.get("charging_enabled") is not True:
                raise GridImageRecoveryError(
                    "Paid image generation is not enabled for this account yet"
                )
            try:
                provider.generate_image(
                    prompt=prompt,
                    model=model,
                    size=size,
                    n=1,
                    response_format="url",
                    extra_body={"progress_token": str(receipt.id)},
                    extra_headers=self.headers_factory(),
                )
            except Exception as exc:
                # An error after dispatch is not evidence of a refund or permission
                # to retry. Persist/return only Core's owner-checked terminal.
                recovered = self.recover(receipt.id)
                if recovered and recovered.state == "completed":
                    return recovered
                if getattr(exc, "status_code", None) == 402:
                    raise GridImageRecoveryError(
                        "Insufficient image credits. Add funds at "
                        "https://console.aipowergrid.io/dashboard/funding. "
                        f"Recovery ID: {receipt.id}. The request was not resubmitted."
                    ) from exc
                raise GridImageRecoveryError(
                    f"Image status is unconfirmed. Recovery ID: {receipt.id}. "
                    "The request was not resubmitted."
                ) from exc
        recovered = self.recover(receipt.id)
        if not recovered or recovered.state != "completed":
            raise GridImageRecoveryError(
                f"Image status: {recovered.state if recovered else 'unknown'}. "
                f"Recovery ID: {receipt.id}. The request was not resubmitted."
            )
        return recovered


def image_base64(result: dict[str, Any]) -> str:
    """Download only the validated output, without credentials, with a hard bound."""
    output = CoreImageResult.model_validate(result).media[0]
    with ssrf_safe_get(
        str(output.url), timeout=30, follow_redirects=False, stream=True
    ) as response:
        if response.status_code != 200:
            raise GridImageRecoveryError("The saved image is temporarily unavailable")
        content = bytearray()
        for chunk in response.iter_content(chunk_size=64 * 1024):
            content.extend(chunk)
            if len(content) > 20 * 1024 * 1024:
                raise GridImageRecoveryError(
                    "The saved image exceeds the download limit"
                )
    if hashlib.sha256(content).hexdigest() != output.sha256:
        raise GridImageRecoveryError("The saved image failed its integrity check")
    get_image_type_from_bytes(bytes(content))
    return base64.b64encode(content).decode("ascii")
