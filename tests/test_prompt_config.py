"""User-customizable Agent system prompt (waycast.toml) tests.

Covers TOML parsing, the default-prompt fallback when no config exists, and
the concatenation of user instructions with the auto-generated catalog.
"""

from __future__ import annotations

import os

from waycast.agent import _build_system_prompt
from waycast.demo import build_registry
from waycast.prompt_config import AgentSystemPromptConfig, build_system_prompt_with_config


def test_missing_file_yields_empty_config(tmp_path):
    cfg = AgentSystemPromptConfig.from_toml_path(tmp_path / "nope.toml")
    assert cfg.is_empty()


def test_default_env_path_when_unset(tmp_path, monkeypatch):
    # No WAYCAST_AGENT_CONFIG and no ./waycast.toml in cwd -> empty.
    monkeypatch.delenv("WAYCAST_AGENT_CONFIG", raising=False)
    monkeypatch.chdir(tmp_path)
    cfg = AgentSystemPromptConfig.from_toml_path()
    assert cfg.is_empty()


def test_parses_all_fields(tmp_path):
    p = tmp_path / "waycast.toml"
    p.write_text(
        "[agent.system_prompt]\n"
        'role = "weather-assistant"\n'
        'scenario = "daily-clothing-tips"\n'
        'custom_prefix = "check-weather-first"\n'
        'custom_suffix = "be-concise"\n',
        encoding="utf-8",
    )
    cfg = AgentSystemPromptConfig.from_toml_path(p)
    assert cfg.role == "weather-assistant"
    assert cfg.scenario == "daily-clothing-tips"
    assert cfg.custom_prefix == "check-weather-first"
    assert cfg.custom_suffix == "be-concise"


def test_empty_config_leaves_default_prompt(tmp_path):
    reg = build_registry()
    default = _build_system_prompt(reg)
    empty = _build_system_prompt(reg, AgentSystemPromptConfig())
    assert default == empty
    assert "notify" in default
    assert "memory_log" in default


def test_user_instructions_concatenated_with_catalog(tmp_path):
    reg = build_registry()
    cfg = AgentSystemPromptConfig(
        role="天气助手",
        scenario="推送穿衣建议",
        custom_prefix="必须用中文",
        custom_suffix="结尾写日志",
    )
    prompt = build_system_prompt_with_config(
        reg.describe_output_modules(), cfg
    )
    # catalog still present
    assert "notify" in prompt and "memory_log" in prompt
    # ordered user instructions: prefix, role, scenario, suffix
    assert prompt.index("必须用中文") < prompt.index("天气助手")
    assert prompt.index("天气助手") < prompt.index("推送穿衣建议")
    assert prompt.index("推送穿衣建议") < prompt.index("结尾写日志")


def test_env_var_path_is_used(tmp_path, monkeypatch):
    p = tmp_path / "custom.toml"
    p.write_text('[agent.system_prompt]\nrole = "X"\n', encoding="utf-8")
    monkeypatch.setenv("WAYCAST_AGENT_CONFIG", str(p))
    cfg = AgentSystemPromptConfig.from_toml_path()
    assert cfg.role == "X"
