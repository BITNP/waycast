"""User-customizable Agent system prompt (plain-text) tests.

Covers reading the whole plain-text file as the user part of the system
prompt, the default-prompt fallback when no file exists, and the order:
user prompt first, auto-generated catalog second.
"""

from __future__ import annotations

from waycast.agent import _build_system_prompt
from waycast.demo import build_registry
from waycast.prompt_config import (
    build_system_prompt_with_user,
    read_user_system_prompt,
)


def test_missing_file_returns_none(tmp_path):
    assert read_user_system_prompt(tmp_path / "nope.txt") is None


def test_default_path_when_unset(tmp_path, monkeypatch):
    # No WAYCAST_AGENT_CONFIG and no ./waycast.prompt.txt in cwd -> None.
    monkeypatch.delenv("WAYCAST_AGENT_CONFIG", raising=False)
    monkeypatch.chdir(tmp_path)
    assert read_user_system_prompt() is None


def test_reads_full_plain_text_multiline(tmp_path):
    p = tmp_path / "waycast.prompt.txt"
    p.write_text(
        "你是一位天气预报助手。\n"
        "\n"
        "使用场景：每天早晨推送天气与穿衣建议。\n"
        "\n"
        "务必先调用天气工具再回复；回复要简洁，避免啰嗦。\n",
        encoding="utf-8",
    )
    got = read_user_system_prompt(p)
    assert got is not None
    # whole file read verbatim, no field splitting
    assert "你是一位天气预报助手" in got
    assert "务必先调用天气工具再回复" in got
    assert got.count("\n") >= 4


def test_empty_file_returns_none(tmp_path):
    p = tmp_path / "waycast.prompt.txt"
    p.write_text("   \n  ", encoding="utf-8")
    assert read_user_system_prompt(p) is None


def test_missing_file_leaves_default_prompt(tmp_path):
    reg = build_registry()
    default = _build_system_prompt(reg)
    unchanged = _build_system_prompt(reg, user_system_prompt=None)
    assert default == unchanged
    assert "notify" in default
    assert "memory_log" in default
    assert "You are the Waycast agent" in default


def test_user_prompt_prepended_to_catalog(tmp_path):
    user = "你是一位天气预报助手。\n每天早晨推送天气与穿衣建议。\n务必先调用天气工具再回复。"
    prompt = build_system_prompt_with_user(
        build_registry().describe_output_modules(), user
    )
    # catalog still present, after the user text
    assert "notify" in prompt and "memory_log" in prompt
    assert prompt.index("你是一位天气预报助手") < prompt.index("notify")


def test_env_var_path_is_used(tmp_path, monkeypatch):
    p = tmp_path / "custom.txt"
    p.write_text("只保留这一句。", encoding="utf-8")
    monkeypatch.setenv("WAYCAST_AGENT_CONFIG", str(p))
    got = read_user_system_prompt()
    assert got is not None
    assert "只保留这一句" in got
