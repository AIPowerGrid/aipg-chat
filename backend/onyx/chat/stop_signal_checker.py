from collections.abc import Callable
from contextvars import ContextVar
from uuid import UUID

from onyx.cache.interface import CacheBackend

# Per-request cancellation hook, set inside each model's worker thread
# (process_message._run_model). When it returns True the user pressed stop and
# any in-flight upstream LLM stream should be torn down rather than drained to
# completion. Kept in a ContextVar so it reaches the litellm streaming loop in
# the same thread/context without threading a callback through every signature.
# (process_message submits workers via ``ctx.run`` on a copied context, so a
# value set inside the worker is visible to everything it calls downstream.)
stream_cancelled_check: ContextVar[Callable[[], bool] | None] = ContextVar(
    "stream_cancelled_check", default=None
)


def is_stream_cancelled() -> bool:
    """True if the current worker context has a cancellation hook that has fired.

    Safe to call from anywhere: returns False when no hook is registered (e.g.
    background jobs, tests) and swallows any error from the hook itself so a
    transient cache hiccup never aborts a generation by mistake.
    """
    check = stream_cancelled_check.get()
    if check is None:
        return False
    try:
        return check()
    except Exception:
        return False


PREFIX = "chatsessionstop"
FENCE_PREFIX = f"{PREFIX}_fence"
FENCE_TTL = 10 * 60  # 10 minutes


def _get_fence_key(chat_session_id: UUID) -> str:
    """Generate the cache key for a chat session stop signal fence.

    Args:
        chat_session_id: The UUID of the chat session

    Returns:
        The fence key string. Tenant isolation is handled automatically
        by the cache backend (Redis key-prefixing or Postgres schema routing).
    """
    return f"{FENCE_PREFIX}_{chat_session_id}"


def set_fence(chat_session_id: UUID, cache: CacheBackend, value: bool) -> None:
    """Set or clear the stop signal fence for a chat session.

    Args:
        chat_session_id: The UUID of the chat session
        cache: Tenant-aware cache backend
        value: True to set the fence (stop signal), False to clear it
    """
    fence_key = _get_fence_key(chat_session_id)
    if not value:
        cache.delete(fence_key)
        return
    cache.set(fence_key, 0, ex=FENCE_TTL)


def is_connected(chat_session_id: UUID, cache: CacheBackend) -> bool:
    """Check if the chat session should continue (not stopped).

    Args:
        chat_session_id: The UUID of the chat session to check
        cache: Tenant-aware cache backend

    Returns:
        True if the session should continue, False if it should stop
    """
    return not cache.exists(_get_fence_key(chat_session_id))


def reset_cancel_status(chat_session_id: UUID, cache: CacheBackend) -> None:
    """Clear the stop signal for a chat session.

    Args:
        chat_session_id: The UUID of the chat session
        cache: Tenant-aware cache backend
    """
    cache.delete(_get_fence_key(chat_session_id))
