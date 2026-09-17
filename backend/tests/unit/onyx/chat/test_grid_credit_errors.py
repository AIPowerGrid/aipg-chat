import pytest

from onyx.llm.aipg.credit_errors import GRID_CREDIT_ERROR
from onyx.llm.aipg.credit_errors import grid_credit_error


class ProviderError(Exception):
    status_code = 402


@pytest.fixture(autouse=True)
def grid_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIPG_GRID_API_BASE", "https://grid.example/v1")


def test_credit_error_is_constant_not_upstream_body() -> None:
    error = ProviderError("insufficient credits; Authorization: secret-token")
    assert grid_credit_error(error, "https://grid.example/v1/") == GRID_CREDIT_ERROR


def test_nested_credit_error() -> None:
    wrapper = RuntimeError("LLM stream failed")
    wrapper.__cause__ = ProviderError("Insufficient Grid credits")
    assert grid_credit_error(wrapper, "https://grid.example/v1") == GRID_CREDIT_ERROR


@pytest.mark.parametrize(
    "error,base",
    [
        (ProviderError("unpriced model"), "https://grid.example/v1"),
        (RuntimeError("insufficient credits"), "https://grid.example/v1"),
        (ProviderError("insufficient credits"), "https://other.example/v1"),
        (ProviderError("insufficient credits"), None),
    ],
)
def test_other_errors_do_not_send_users_to_grid_funding(
    error: Exception, base: str | None
) -> None:
    assert grid_credit_error(error, base) is None


def test_missing_config_and_exception_cycle(monkeypatch: pytest.MonkeyPatch) -> None:
    error = ProviderError("insufficient credits")
    monkeypatch.delenv("AIPG_GRID_API_BASE")
    assert grid_credit_error(error, "https://grid.example/v1") is None
    monkeypatch.setenv("AIPG_GRID_API_BASE", "https://grid.example/v1")
    cyclic_error = RuntimeError("failure")
    cyclic_error.__cause__ = cyclic_error
    assert grid_credit_error(cyclic_error, "https://grid.example/v1") is None
