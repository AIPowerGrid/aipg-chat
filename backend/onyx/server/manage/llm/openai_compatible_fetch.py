"""Reusable helpers for fetching the model list from an OpenAI-compatible
`/v1/models` endpoint.

This logic originally lived inline in `api.py`. It was extracted into this
sibling module so non-router code (e.g. the AIPG grid model-sync Celery task)
can fetch models without importing the FastAPI router layer in `api.py`.
"""

import httpx

from onyx.error_handling.error_codes import OnyxErrorCode
from onyx.error_handling.exceptions import OnyxError
from onyx.server.manage.llm.models import SyncModelEntry
from onyx.server.manage.llm.utils import infer_vision_support
from onyx.server.manage.llm.utils import is_embedding_model
from onyx.server.manage.llm.utils import is_reasoning_model
from onyx.utils.logger import setup_logger

logger = setup_logger()


def fetch_openai_compatible_models_response(
    url: str,
    source_name: str,
    api_key: str | None = None,
) -> dict:
    """Fetch model metadata from an OpenAI-compatible `/models` endpoint."""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "HTTP-Referer": "https://onyx.app",
        "X-Title": "Onyx",
    }
    if not api_key:
        headers.pop("Authorization")

    try:
        response = httpx.get(url, headers=headers, timeout=10.0)
        response.raise_for_status()
        return response.json()
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 401:
            raise OnyxError(
                OnyxErrorCode.VALIDATION_ERROR,
                f"Authentication failed: invalid or missing API key for {source_name}.",
            )
        elif e.response.status_code == 404:
            raise OnyxError(
                OnyxErrorCode.VALIDATION_ERROR,
                f"{source_name} models endpoint not found at {url}. Please verify the API base URL.",
            )
        else:
            raise OnyxError(
                OnyxErrorCode.BAD_GATEWAY,
                f"Failed to fetch {source_name} models: {e}",
            )
    except httpx.RequestError as e:
        logger.warning(
            "Failed to fetch models from OpenAI-compatible endpoint",
            extra={"source": source_name, "url": url, "error": str(e)},
            exc_info=True,
        )
        raise OnyxError(
            OnyxErrorCode.BAD_GATEWAY,
            f"Failed to fetch {source_name} models: {e}",
        )
    except ValueError as e:
        logger.warning(
            "Received invalid model response from OpenAI-compatible endpoint",
            extra={"source": source_name, "url": url, "error": str(e)},
            exc_info=True,
        )
        raise OnyxError(
            OnyxErrorCode.BAD_GATEWAY,
            f"Failed to fetch {source_name} models: {e}",
        )


def build_openai_compatible_models_url(api_base: str) -> str:
    """Normalize an api_base to its `/v1/models` listing URL."""
    cleaned_api_base = api_base.strip().rstrip("/")
    if cleaned_api_base.endswith("/v1"):
        return f"{cleaned_api_base}/models"
    return f"{cleaned_api_base}/v1/models"


def fetch_openai_compatible_models(
    api_base: str,
    api_key: str | None = None,
    source_name: str = "OpenAI-Compatible",
) -> list[SyncModelEntry]:
    """Fetch and parse the chat models served by an OpenAI-compatible endpoint.

    Embedding models are filtered out. Returns the parsed models sorted by name.
    Does NOT raise when the endpoint returns zero models — callers decide how to
    treat an empty list (the grid sync, for instance, skips reconciliation rather
    than hiding every model on a transient empty response).
    """
    url = build_openai_compatible_models_url(api_base)
    response_json = fetch_openai_compatible_models_response(
        url=url, source_name=source_name, api_key=api_key
    )

    raw_models = response_json.get("data", [])
    if not isinstance(raw_models, list):
        return []

    results: list[SyncModelEntry] = []
    for model in raw_models:
        try:
            model_id = model.get("id", "")
            model_name = model.get("name", model_id)

            if not model_id:
                continue

            if is_embedding_model(model_id):
                continue

            results.append(
                SyncModelEntry(
                    name=model_id,
                    display_name=model_name,
                    max_input_tokens=model.get("context_length"),
                    # Prefer an explicit capability advertised by the endpoint
                    # (the grid emits input_modalities per model); fall back to
                    # name-based inference for plain OpenAI-compatible providers.
                    supports_image_input=(
                        "image" in (model.get("input_modalities") or [])
                        or infer_vision_support(model_id)
                    ),
                    supports_reasoning=is_reasoning_model(model_id, model_name),
                )
            )
        except Exception as e:
            logger.warning(
                "Failed to parse OpenAI-compatible model entry",
                extra={"error": str(e), "item": str(model)[:1000]},
            )

    return sorted(results, key=lambda m: m.name.lower())
