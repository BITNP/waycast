"""Config parsing and model wiring for the LLM fail-fast knobs (offline unit layer)."""

from __future__ import annotations

import pytest

from waycast.config import WaycastConfig, make_model


@pytest.fixture
def clean_llm_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in (
        "WAYCAST_LLM_TIMEOUT",
        "WAYCAST_LLM_MAX_RETRIES",
        "WAYCAST_LLM_REASONING_EFFORT",
        "WAYCAST_LLM_EXTRA_BODY",
    ):
        monkeypatch.delenv(key, raising=False)


def test_llm_timeout_defaults(clean_llm_env: None) -> None:
    config = WaycastConfig.from_env()
    assert config.llm_timeout_seconds == 120.0
    assert config.llm_max_retries == 1
    assert config.llm_reasoning_effort == ""
    assert config.llm_extra_body == {}


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


def test_llm_extra_body_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WAYCAST_LLM_EXTRA_BODY", '{"enable_thinking": false}')
    config = WaycastConfig.from_env()
    assert config.llm_extra_body == {"enable_thinking": False}


def test_llm_extra_body_rejects_non_object(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WAYCAST_LLM_EXTRA_BODY", "[1, 2]")
    with pytest.raises(TypeError, match="JSON object"):
        WaycastConfig.from_env()


def test_make_model_wires_extra_body() -> None:
    config = WaycastConfig(
        base_url="http://127.0.0.1:9/v1",
        api_key="unit-test-key",
        llm_extra_body={"enable_thinking": False},
    )
    model = make_model(config)
    assert model.reasoning_effort is None
    assert model.extra_body == {"enable_thinking": False}


def test_llm_reasoning_effort_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WAYCAST_LLM_REASONING_EFFORT", "none")
    config = WaycastConfig.from_env()
    assert config.llm_reasoning_effort == "none"


def test_make_model_wires_reasoning_effort_natively() -> None:
    config = WaycastConfig(
        base_url="http://127.0.0.1:9/v1",
        api_key="unit-test-key",
        llm_reasoning_effort="none",
    )
    model = make_model(config)
    assert model.reasoning_effort == "none"


def test_standard_reasoning_effort_wins_over_extra_body_duplicate() -> None:
    # Both knobs set the same field -> the standard parameter carries it and
    # the dialect duplicate is stripped, so the request never sends it twice.
    config = WaycastConfig(
        base_url="http://127.0.0.1:9/v1",
        api_key="unit-test-key",
        llm_reasoning_effort="low",
        llm_extra_body={"reasoning_effort": "none", "other_flag": 1},
    )
    model = make_model(config)
    assert model.reasoning_effort == "low"
    assert model.extra_body == {"other_flag": 1}
