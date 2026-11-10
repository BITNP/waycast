"""Config parsing and model wiring for the LLM fail-fast knobs (offline unit layer)."""

from __future__ import annotations

import pytest

from waycast.config import WaycastConfig, make_model


@pytest.fixture
def clean_llm_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in ("WAYCAST_LLM_TIMEOUT", "WAYCAST_LLM_MAX_RETRIES"):
        monkeypatch.delenv(key, raising=False)


def test_llm_timeout_defaults(clean_llm_env: None) -> None:
    config = WaycastConfig.from_env()
    assert config.llm_timeout_seconds == 120.0
    assert config.llm_max_retries == 1


def test_llm_timeout_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WAYCAST_LLM_TIMEOUT", "45.5")
    monkeypatch.setenv("WAYCAST_LLM_MAX_RETRIES", "0")
    config = WaycastConfig.from_env()
    assert config.llm_timeout_seconds == 45.5
    assert config.llm_max_retries == 0


def test_make_model_wires_timeout_and_retries() -> None:
    config = WaycastConfig(
        base_url="http://127.0.0.1:9/v1",
        api_key="unit-test-key",
        llm_timeout_seconds=33.0,
        llm_max_retries=0,
    )
    model = make_model(config)
    assert model.request_timeout == 33.0
    assert model.max_retries == 0
