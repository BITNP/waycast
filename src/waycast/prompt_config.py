"""User-customizable Agent system prompt (plain-text file).

The user may supply a plain-text file (default ``waycast.prompt.txt``,
overridable via the ``WAYCAST_AGENT_CONFIG`` environment variable) whose
entire content becomes the *user* part of the Agent system prompt.  The
capability bridge appends the automatically generated catalog and the
protocol rules afterwards, so the protocol specification stays authoritative
and consistent with ADR-0002 / ADR-0007.

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
    user_prompt: str | None = None,
    *,
    base: str = "",
    catalog: str = "",
    status: str = "",
    rules: str = "",
) -> str:
    """Build the full system prompt: user instructions (if any), the
    auto-generated catalog, the status-tool list, and the default rules.

    The order is always base first, then the user prompt, then catalog, then
    status tools, then rules, so the fixed base stays authoritative and the
    rules stay at the bottom.  Empty parts are dropped.  The prompt carries
    no per-invocation output-results feed (ADR-0014).
    """
    parts = [p for p in (base, user_prompt, catalog, status, rules) if p]
    return "\n\n".join(parts)


__all__ = [
    "read_user_system_prompt",
    "build_system_prompt_with_user",
]
