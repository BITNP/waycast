"""User-customizable Agent system prompt (plain-text file).

The user may supply a plain-text file (default ``waycast.prompt.txt``,
overridable via the ``WAYCAST_AGENT_CONFIG`` environment variable) whose
entire content becomes the *user* part of the Agent's system prompt.  The
automatically generated output-module catalog and protocol rules are always
appended afterwards, so the protocol specification stays authoritative and
consistent with ADR-0002 / ADR-0007.

The file is read as-is: no TOML, no escaping.  Every line you write is part
of the prompt, so multi-paragraph instructions are natural to express.
"""
from __future__ import annotations

import os
from pathlib import Path


def read_user_system_prompt(path: str | os.PathLike | None = None) -> str | None:
    """Return the plain-text user system prompt, or ``None`` when absent.

    When ``path`` is None, use ``WAYCAST_AGENT_CONFIG`` if set, else
    ``./waycast.prompt.txt``.  A missing or empty file yields ``None`` so the
    default prompt stays unchanged.
    """
    if path is None:
        env = os.getenv("WAYCAST_AGENT_CONFIG")
        path = env or "waycast.prompt.txt"
    p = Path(path)
    if not p.is_file():
        return None
    content = p.read_text(encoding="utf-8")
    content = content.strip()
    return content or None


def build_system_prompt_with_user(
    catalog: str,
    user_prompt: str | None = None,
) -> str:
    """Build the full system prompt: user instructions (if any) + catalog."""
    from waycast.agent import SYSTEM_PROMPT_TEMPLATE

    template = SYSTEM_PROMPT_TEMPLATE.format(output_module_catalog=catalog)
    if not user_prompt:
        return template
    return user_prompt + "\n\n" + template


__all__ = [
    "read_user_system_prompt",
    "build_system_prompt_with_user",
]
