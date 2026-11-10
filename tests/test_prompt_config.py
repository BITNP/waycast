"""User-customizable Agent system prompt (plain-text file) tests."""

from __future__ import annotations

from waycast.prompt_config import (
    build_system_prompt_with_user,
    read_user_system_prompt,
)


def test_missing_file_returns_none(tmp_path):
    assert read_user_system_prompt(tmp_path / "nope.txt") is None


def test_default_path_when_unset(tmp_path, monkeypatch):
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
    assert "你是一位天气预报助手" in got
    assert "务必先调用天气工具再回复" in got
    assert got.count("\n") >= 4


def test_empty_file_returns_none(tmp_path):
    p = tmp_path / "waycast.prompt.txt"
    p.write_text("   \n  ", encoding="utf-8")
    assert read_user_system_prompt(p) is None


def test_catalog_and_rules_after_user_prompt():
    user = "你是一位天气预报助手。\n每天早晨推送天气与穿衣建议。\n务必先调用天气工具再回复。"
    prompt = build_system_prompt_with_user(
        user,
        base="BASE",
        catalog="CATALOG",
        status="STATUS",
        rules="RULES",
    )
    assert prompt.count("\n\n") == 4
    parts = prompt.split("\n\n")
    assert parts[0] == "BASE"
    assert parts[1] == user
    assert parts[2] == "CATALOG"
    assert parts[3] == "STATUS"
    assert parts[4] == "RULES"


def test_empty_parts_are_dropped():
    prompt = build_system_prompt_with_user(
        None, base="", catalog="", status="", rules=""
    )
    assert prompt == ""


def test_env_var_path_is_used(tmp_path, monkeypatch):
    p = tmp_path / "custom.txt"
    p.write_text("只保留这一句。", encoding="utf-8")
    monkeypatch.setenv("WAYCAST_AGENT_CONFIG", str(p))
    got = read_user_system_prompt()
    assert got is not None
    assert "只保留这一句" in got
