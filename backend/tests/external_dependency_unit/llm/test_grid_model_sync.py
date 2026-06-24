"""External-dependency unit tests for the AIPG grid model sync.

These exercise `sync_grid_models` against a real Postgres while mocking only the
network call to the grid's `/v1/models` endpoint. The focus is the reconcile
behavior that drives which models show up in the chat dropdown:

- first sync seeds the provider and inserts grid models as *visible*,
- a model dropped from the grid is *hidden* (not deleted),
- a model added to the grid appears (visible) on the next sync,
- the default is reassigned when the current default is dropped from the grid,
- the sync is a clean no-op when disabled / unconfigured / the grid returns nothing.
"""

from collections.abc import Generator
from uuid import uuid4

import pytest
from pytest import MonkeyPatch
from sqlalchemy.orm import Session

import onyx.llm.aipg.grid_model_sync as grid_module
from onyx.db.llm import fetch_default_llm_model
from onyx.db.llm import fetch_existing_llm_provider
from onyx.db.llm import remove_llm_provider
from onyx.db.llm import update_default_provider
from onyx.llm.aipg.grid_model_sync import sync_grid_models
from onyx.server.manage.llm.models import SyncModelEntry


def _entry(
    name: str,
    *,
    supports_image_input: bool = False,
    supports_reasoning: bool = False,
) -> SyncModelEntry:
    return SyncModelEntry(
        name=name,
        display_name=name,
        supports_image_input=supports_image_input,
        supports_reasoning=supports_reasoning,
    )


def _visibility(db_session: Session, provider_name: str) -> dict[str, bool]:
    provider = fetch_existing_llm_provider(name=provider_name, db_session=db_session)
    assert provider is not None
    return {mc.name: mc.is_visible for mc in provider.model_configurations}


def _configure_grid(
    monkeypatch: MonkeyPatch,
    provider_name: str,
    *,
    enabled: bool = True,
    api_base: str | None = "https://grid.example/v1",
) -> None:
    """Point the grid sync module at a unique, enabled test provider."""
    monkeypatch.setattr(grid_module, "AIPG_GRID_SYNC_ENABLED", enabled)
    monkeypatch.setattr(grid_module, "AIPG_GRID_API_BASE", api_base)
    monkeypatch.setattr(grid_module, "AIPG_GRID_API_KEY", "grid-test-key")
    monkeypatch.setattr(grid_module, "AIPG_GRID_PROVIDER_NAME", provider_name)


def _mock_grid_models(
    monkeypatch: MonkeyPatch, models: list[SyncModelEntry]
) -> None:
    monkeypatch.setattr(
        grid_module,
        "fetch_openai_compatible_models",
        lambda *_, **__: list(models),
    )


@pytest.fixture
def provider_name(db_session: Session) -> Generator[str, None, None]:
    name = f"AI Power Grid {uuid4().hex[:8]}"
    yield name
    db_session.rollback()
    provider = fetch_existing_llm_provider(name=name, db_session=db_session)
    if provider:
        remove_llm_provider(db_session, provider.id)


def test_first_sync_seeds_provider_and_inserts_visible_models(
    db_session: Session,
    provider_name: str,
    monkeypatch: MonkeyPatch,
) -> None:
    _configure_grid(monkeypatch, provider_name)
    _mock_grid_models(
        monkeypatch,
        [_entry("grid/model-a"), _entry("grid/model-b", supports_reasoning=True)],
    )

    # Provider does not exist yet.
    assert fetch_existing_llm_provider(name=provider_name, db_session=db_session) is None

    result = sync_grid_models(db_session)

    assert result is not None
    assert result.added == 2
    # Seeded provider exists and both grid models are visible in the dropdown.
    visibility = _visibility(db_session, provider_name)
    assert visibility == {"grid/model-a": True, "grid/model-b": True}


def test_dropped_model_is_hidden_not_deleted(
    db_session: Session,
    provider_name: str,
    monkeypatch: MonkeyPatch,
) -> None:
    _configure_grid(monkeypatch, provider_name)
    _mock_grid_models(
        monkeypatch,
        [_entry("grid/keep"), _entry("grid/drop")],
    )
    sync_grid_models(db_session)

    # Next sync: the grid no longer serves "grid/drop".
    _mock_grid_models(monkeypatch, [_entry("grid/keep")])
    result = sync_grid_models(db_session)

    assert result is not None
    assert result.hidden == 1
    visibility = _visibility(db_session, provider_name)
    # Row is kept (re-enable / history) but hidden from the dropdown.
    assert visibility == {"grid/keep": True, "grid/drop": False}


def test_new_model_appears_visible_on_next_sync(
    db_session: Session,
    provider_name: str,
    monkeypatch: MonkeyPatch,
) -> None:
    _configure_grid(monkeypatch, provider_name)
    _mock_grid_models(monkeypatch, [_entry("grid/model-a")])
    sync_grid_models(db_session)

    _mock_grid_models(
        monkeypatch, [_entry("grid/model-a"), _entry("grid/model-b")]
    )
    result = sync_grid_models(db_session)

    assert result is not None
    assert result.added == 1
    visibility = _visibility(db_session, provider_name)
    assert visibility == {"grid/model-a": True, "grid/model-b": True}


def test_default_reassigned_when_current_default_dropped(
    db_session: Session,
    provider_name: str,
    monkeypatch: MonkeyPatch,
) -> None:
    _configure_grid(monkeypatch, provider_name)
    _mock_grid_models(
        monkeypatch, [_entry("grid/alpha"), _entry("grid/beta")]
    )
    sync_grid_models(db_session)

    # Make the grid explicitly own the default, pointed at a model we will drop.
    provider = fetch_existing_llm_provider(name=provider_name, db_session=db_session)
    assert provider is not None
    update_default_provider(provider.id, "grid/beta", db_session)
    current_default = fetch_default_llm_model(db_session)
    assert current_default is not None
    assert current_default.name == "grid/beta"

    # Grid drops the current default model.
    _mock_grid_models(monkeypatch, [_entry("grid/alpha")])
    result = sync_grid_models(db_session)

    assert result is not None
    # Default falls back to the remaining grid model so the provider stays usable.
    assert result.default_model == "grid/alpha"
    new_default = fetch_default_llm_model(db_session)
    assert new_default is not None
    assert new_default.name == "grid/alpha"


def test_noop_when_disabled(
    db_session: Session,
    provider_name: str,
    monkeypatch: MonkeyPatch,
) -> None:
    _configure_grid(monkeypatch, provider_name, enabled=False)
    _mock_grid_models(monkeypatch, [_entry("grid/model-a")])

    assert sync_grid_models(db_session) is None
    # Disabled sync must not seed a provider.
    assert fetch_existing_llm_provider(name=provider_name, db_session=db_session) is None


def test_noop_when_api_base_missing(
    db_session: Session,
    provider_name: str,
    monkeypatch: MonkeyPatch,
) -> None:
    _configure_grid(monkeypatch, provider_name, api_base=None)
    _mock_grid_models(monkeypatch, [_entry("grid/model-a")])

    assert sync_grid_models(db_session) is None
    assert fetch_existing_llm_provider(name=provider_name, db_session=db_session) is None


def test_empty_grid_response_skips_reconcile(
    db_session: Session,
    provider_name: str,
    monkeypatch: MonkeyPatch,
) -> None:
    _configure_grid(monkeypatch, provider_name)
    _mock_grid_models(monkeypatch, [_entry("grid/model-a")])
    sync_grid_models(db_session)

    # A transient empty listing must NOT hide every model.
    _mock_grid_models(monkeypatch, [])
    result = sync_grid_models(db_session)

    assert result is None
    visibility = _visibility(db_session, provider_name)
    assert visibility == {"grid/model-a": True}
