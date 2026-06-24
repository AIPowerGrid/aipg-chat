"""AIPG fork — periodic sync of the AI Power Grid's live models into the chat dropdown.

The grid exposes an OpenAI-compatible `/v1/models` endpoint. This service refreshes the
managed grid `LLMProvider`'s visible model list to match what the grid currently serves,
so newly added/removed grid models appear/disappear in the chat model dropdown without
any admin action. It is driven by a periodic Celery task and is a safe no-op when not
configured.

Kept under an `aipg` namespace to isolate fork-specific behavior for rebasability. It
imports a few data/util modules from `onyx.server.manage.llm` (provider models, the
generic `/v1/models` fetch helper, the provider-listing cache) — none of which pull in
the FastAPI router — so it is safe to import from a background worker.
"""

from sqlalchemy.orm import Session

from onyx.configs.app_configs import AIPG_GRID_API_BASE
from onyx.configs.app_configs import AIPG_GRID_API_KEY
from onyx.configs.app_configs import AIPG_GRID_PROVIDER_NAME
from onyx.configs.app_configs import AIPG_GRID_SYNC_ENABLED
from onyx.db.llm import fetch_existing_llm_provider
from onyx.db.llm import GridModelReconcileResult
from onyx.db.llm import reconcile_grid_model_configurations
from onyx.db.llm import upsert_llm_provider
from onyx.llm.constants import LlmProviderNames
from onyx.server.manage.llm.models import LLMProviderUpsertRequest
from onyx.server.manage.llm.openai_compatible_fetch import (
    fetch_openai_compatible_models,
)
from onyx.server.manage.llm.provider_cache import invalidate_provider_listing_cache
from onyx.utils.logger import setup_logger

logger = setup_logger()


def _ensure_grid_provider(db_session: Session) -> None:
    """Seed the managed grid provider from env config if it doesn't exist yet.

    Only creates when missing — an existing provider's credentials and settings are left
    exactly as the admin configured them; this service only refreshes its model list.
    """
    existing = fetch_existing_llm_provider(
        name=AIPG_GRID_PROVIDER_NAME, db_session=db_session
    )
    if existing is not None:
        return

    logger.info(
        "Seeding AIPG grid LLM provider '%s' from env config",
        AIPG_GRID_PROVIDER_NAME,
    )
    upsert_llm_provider(
        llm_provider_upsert_request=LLMProviderUpsertRequest(
            name=AIPG_GRID_PROVIDER_NAME,
            provider=LlmProviderNames.OPENAI_COMPATIBLE.value,
            api_base=AIPG_GRID_API_BASE,
            api_key=AIPG_GRID_API_KEY,
            is_public=True,
            model_configurations=[],
        ),
        db_session=db_session,
    )


def sync_grid_models(db_session: Session) -> GridModelReconcileResult | None:
    """Refresh the grid provider's visible models from its live `/v1/models` endpoint.

    Returns the reconcile result, or None when the sync is disabled / not configured /
    the grid returned no models (treated as a transient anomaly rather than a signal to
    hide every model).
    """
    if not AIPG_GRID_SYNC_ENABLED:
        logger.debug("AIPG grid sync disabled, skipping")
        return None
    if not AIPG_GRID_API_BASE:
        logger.warning(
            "AIPG_GRID_SYNC_ENABLED is set but AIPG_GRID_API_BASE is missing; skipping"
        )
        return None

    _ensure_grid_provider(db_session)

    models = fetch_openai_compatible_models(
        api_base=AIPG_GRID_API_BASE,
        api_key=AIPG_GRID_API_KEY,
        source_name=AIPG_GRID_PROVIDER_NAME,
    )
    if not models:
        # Never hide every model on a transient empty/failed listing.
        logger.warning(
            "Grid returned no models from %s; skipping reconcile",
            AIPG_GRID_API_BASE,
        )
        return None

    result = reconcile_grid_model_configurations(
        db_session=db_session,
        provider_name=AIPG_GRID_PROVIDER_NAME,
        models=models,
    )
    invalidate_provider_listing_cache()

    logger.info(
        "AIPG grid model sync: +%d new, %d shown, %d hidden (default=%s)",
        result.added,
        result.shown,
        result.hidden,
        result.default_model,
    )
    return result
