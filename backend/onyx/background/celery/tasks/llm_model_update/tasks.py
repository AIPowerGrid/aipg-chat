from celery import shared_task
from celery import Task

from onyx.background.celery.apps.app_base import task_logger
from onyx.configs.app_configs import AIPG_GRID_SYNC_ENABLED
from onyx.configs.app_configs import AUTO_LLM_CONFIG_URL
from onyx.configs.constants import OnyxCeleryTask
from onyx.db.engine.sql_engine import get_session_with_current_tenant
from onyx.llm.aipg.grid_model_sync import sync_grid_models
from onyx.llm.well_known_providers.auto_update_service import (
    sync_llm_models_from_github,
)


@shared_task(
    name=OnyxCeleryTask.CHECK_FOR_AUTO_LLM_UPDATE,
    ignore_result=True,
    soft_time_limit=300,  # 5 minute timeout
    trail=False,
    bind=True,
)
def check_for_auto_llm_updates(
    self: Task,  # noqa: ARG001
    *,
    tenant_id: str,  # noqa: ARG001
) -> bool | None:
    """Periodic task to fetch LLM model updates from GitHub
    and sync them to providers in Auto mode.

    This task checks the GitHub-hosted config file and updates all
    providers that have is_auto_mode=True.
    """
    if not AUTO_LLM_CONFIG_URL:
        task_logger.debug("AUTO_LLM_CONFIG_URL not configured, skipping")
        return None

    try:
        # Sync to database
        with get_session_with_current_tenant() as db_session:
            results = sync_llm_models_from_github(db_session)

            if results:
                task_logger.info(f"Auto mode sync results: {results}")
            else:
                task_logger.debug("No model updates applied")

    except Exception:
        task_logger.exception("Error in auto LLM update task")
        raise

    return True


@shared_task(
    name=OnyxCeleryTask.SYNC_GRID_MODELS,
    ignore_result=True,
    soft_time_limit=120,  # 2 minute timeout
    trail=False,
    bind=True,
)
def sync_grid_models_task(
    self: Task,  # noqa: ARG001
    *,
    tenant_id: str,  # noqa: ARG001
) -> bool | None:
    """AIPG fork: periodic task that refreshes the AI Power Grid provider's visible
    model list from its live OpenAI-compatible /v1/models endpoint, so newly added or
    removed grid models appear/disappear in the chat dropdown without admin action.

    Safe no-op when AIPG_GRID_SYNC_ENABLED is not set.
    """
    if not AIPG_GRID_SYNC_ENABLED:
        task_logger.debug("AIPG_GRID_SYNC_ENABLED not set, skipping grid model sync")
        return None

    try:
        with get_session_with_current_tenant() as db_session:
            result = sync_grid_models(db_session)
            if result is not None:
                task_logger.info(f"Grid model sync result: {result}")
    except Exception:
        task_logger.exception("Error in grid model sync task")
        raise

    return True
