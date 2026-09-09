"""Durable one-shot image claims. No network calls or automatic resubmission.

Use a dedicated short-lived Session: claim/finish commit before returning.
The server supplies the authenticated owner, assistant message and image slot;
none may be taken from LLM arguments. Core remains the billing authority.
"""

import json
import re
from dataclasses import dataclass
from typing import Any
from uuid import UUID
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from onyx.configs.constants import MessageType
from onyx.db.models import ChatMessage
from onyx.db.models import ChatSession
from onyx.db.models import GridImageRequest


class ImageRequestConflict(ValueError):
    pass


@dataclass(frozen=True)
class ImageRequestReceipt:
    id: UUID
    state: str
    grid_job_id: UUID | None
    result: dict[str, Any] | None
    may_submit: bool = False


def _receipt(row: GridImageRequest, *, may_submit: bool = False) -> ImageRequestReceipt:
    return ImageRequestReceipt(
        row.id, row.state, row.grid_job_id, row.result, may_submit
    )


def claim_image_request(
    db_session: Session,
    *,
    user_id: UUID,
    message_id: int,
    slot: str,
    request_sha256: str,
) -> ImageRequestReceipt:
    """Only the winning committed insert permits one POST, even across restarts.

    A crash before the POST still leaves an attempted claim. A recovery 404 is
    not proof of no dispatch and must never reset this claim or permit a retry.
    """
    if not slot or len(slot) > 128 or not re.fullmatch(r"[0-9a-f]{64}", request_sha256):
        raise ValueError("Invalid image request identity")
    owned = db_session.scalar(
        select(ChatMessage.id)
        .join(ChatSession, ChatMessage.chat_session_id == ChatSession.id)
        .where(
            ChatMessage.id == message_id,
            ChatMessage.message_type == MessageType.ASSISTANT,
            ChatSession.user_id == user_id,
        )
        .with_for_update(of=ChatMessage)
    )
    if owned is None:
        raise ImageRequestConflict("Image request message is unavailable")
    existing = db_session.scalar(
        select(GridImageRequest).where(
            GridImageRequest.message_id == message_id,
            GridImageRequest.slot == slot,
        )
    )
    if existing is not None:
        if existing.user_id != user_id or existing.request_sha256 != request_sha256:
            db_session.rollback()
            raise ImageRequestConflict(
                "Image request does not match its original claim"
            )
        receipt = _receipt(existing)
        db_session.commit()
        return receipt
    # The last two components are the parallel tool tab and batch item.
    # Serialize on the assistant row so an LLM retry cannot buy another group,
    # including after settlement succeeds but downloading the paid asset fails.
    group = slot.rsplit(":", 2)[0]
    previous = db_session.execute(
        select(GridImageRequest.id, GridImageRequest.slot).where(
            GridImageRequest.message_id == message_id,
        )
    ).all()
    for previous_id, previous_slot in previous:
        if previous_slot.rsplit(":", 2)[0] != group:
            db_session.rollback()
            raise ImageRequestConflict(
                f"This response already requested images. Recover request {previous_id}; "
                "a new generation requires a new user request."
            )
    inserted = db_session.scalar(
        insert(GridImageRequest)
        .values(
            id=uuid4(),
            user_id=user_id,
            message_id=message_id,
            slot=slot,
            request_sha256=request_sha256,
            state="attempted",
        )
        .on_conflict_do_nothing(constraint="uq_grid_image_request_slot")
        .returning(GridImageRequest.id)
    )
    row = db_session.scalar(
        select(GridImageRequest).where(
            GridImageRequest.message_id == message_id, GridImageRequest.slot == slot
        )
    )
    if row is None or row.user_id != user_id or row.request_sha256 != request_sha256:
        db_session.rollback()
        raise ImageRequestConflict("Image request does not match its original claim")
    receipt = _receipt(row, may_submit=inserted is not None)
    db_session.commit()
    return receipt


def read_image_request(
    db_session: Session, *, user_id: UUID, request_id: UUID
) -> ImageRequestReceipt | None:
    row = db_session.scalar(
        select(GridImageRequest).where(
            GridImageRequest.id == request_id, GridImageRequest.user_id == user_id
        )
    )
    return _receipt(row) if row else None


def list_image_requests(
    db_session: Session, *, user_id: UUID, message_id: int
) -> list[ImageRequestReceipt]:
    rows = db_session.scalars(
        select(GridImageRequest)
        .where(
            GridImageRequest.user_id == user_id,
            GridImageRequest.message_id == message_id,
        )
        .order_by(GridImageRequest.created_at, GridImageRequest.id)
        .limit(100)
    ).all()
    return [_receipt(row) for row in rows]


def finish_image_request(
    db_session: Session,
    *,
    user_id: UUID,
    request_id: UUID,
    grid_job_id: UUID,
    result: dict[str, Any] | None,
) -> ImageRequestReceipt:
    """Store a validated Core terminal, never an inferred timeout/failure.

    Result contains bounded output metadata, not credentials or base64 assets.
    None means Core explicitly closed the reservation without a result.
    """
    if result is not None and len(json.dumps(result, allow_nan=False).encode()) > 65536:
        raise ValueError("Image recovery result is too large")
    row = db_session.scalar(
        select(GridImageRequest)
        .where(GridImageRequest.id == request_id, GridImageRequest.user_id == user_id)
        .with_for_update()
    )
    if row is None:
        raise ImageRequestConflict("Image request is unavailable")
    state = "completed" if result is not None else "closed"
    if row.state == "attempted":
        row.state, row.grid_job_id, row.result = state, grid_job_id, result
    elif (row.state, row.grid_job_id, row.result) != (state, grid_job_id, result):
        db_session.rollback()
        raise ImageRequestConflict("Conflicting image terminal")
    receipt = _receipt(row)
    db_session.commit()
    return receipt
