from types import SimpleNamespace

from onyx.llm.aipg import grid_model_sync


def test_existing_managed_provider_uses_environment_connection(monkeypatch) -> None:
    provider = SimpleNamespace(
        api_base="http://old-grid.internal/v1",
        api_key="old-user-key",
    )
    monkeypatch.setattr(
        grid_model_sync,
        "fetch_existing_llm_provider",
        lambda **_kwargs: provider,
    )
    monkeypatch.setattr(
        grid_model_sync,
        "AIPG_GRID_API_BASE",
        "https://grid.example/v1",
    )
    monkeypatch.setattr(
        grid_model_sync,
        "AIPG_GRID_API_KEY",
        "grid-service-key",
    )

    grid_model_sync._ensure_grid_provider(SimpleNamespace())

    assert provider.api_base == "https://grid.example/v1"
    assert provider.api_key == "grid-service-key"
