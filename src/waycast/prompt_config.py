"""User-customizable Agent system prompt configuration.

The user may supply a TOML file (default ``waycast.toml``, overridable via the
``WAYCAST_AGENT_CONFIG`` environment variable) to customize the parts of the
Agent's system prompt that describe the scenario and role.  The automatically
generated output-module catalog is always appended afterwards, so the protocol
specification stays authoritative and consistent with ADR-0002 / ADR-0007.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass
class AgentSystemPromptConfig:
    """Parsed user customization for the Agent system prompt.

    ``role`` and ``scenario`` are the primary knobs; ``custom_prefix`` /
    ``custom_suffix`` are free-form instruction fragments.  All fields are
    optional; an empty config leaves the default prompt unchanged.
    """

    role: str = ""
    scenario: str = ""
    custom_prefix: str = ""
    custom_suffix: str = ""

    @classmethod
    def from_toml_path(
        cls, path: str | os.PathLike | None = None
    ) -> "AgentSystemPromptConfig":
        """Load the config from a TOML file.

        When ``path`` is None, use ``WAYCAST_AGENT_CONFIG`` if set, else
        ``./waycast.toml``.  A missing file yields an empty config.
        """
        if path is None:
            env = os.getenv("WAYCAST_AGENT_CONFIG")
            path = env or "waycast.toml"
        p = Path(path)
        if not p.is_file():
            return cls()
        import tomllib

        with p.open("rb") as f:
            data = tomllib.load(f)
        sp = data.get("agent", {}).get("system_prompt", {})
        if not isinstance(sp, dict):
            sp = {}
        return cls(
            role=str(sp.get("role", "")),
            scenario=str(sp.get("scenario", "")),
            custom_prefix=str(sp.get("custom_prefix", "")),
            custom_suffix=str(sp.get("custom_suffix", "")),
        )

    def as_instructions(self) -> str:
        """Compose the user-supplied instructions (empty when no customization)."""
        parts = []
        if self.custom_prefix.strip():
            parts.append(self.custom_prefix.strip())
        if self.role.strip():
            parts.append(f"你的角色：{self.role.strip()}")
        if self.scenario.strip():
            parts.append(f"使用场景：{self.scenario.strip()}")
        if self.custom_suffix.strip():
            parts.append(self.custom_suffix.strip())
        return "\n".join(parts)

    def is_empty(self) -> bool:
        return not (
            self.role.strip()
            or self.scenario.strip()
            or self.custom_prefix.strip()
            or self.custom_suffix.strip()
        )


def build_system_prompt_with_config(
    catalog: str,
    config: AgentSystemPromptConfig | None = None,
) -> str:
    """Build the full system prompt: user instructions (if any) + catalog."""
    from waycast.agent import SYSTEM_PROMPT_TEMPLATE

    template = SYSTEM_PROMPT_TEMPLATE
    if config is None or config.is_empty():
        return template.format(output_module_catalog=catalog)
    user = config.as_instructions()
    return template.format(output_module_catalog=catalog) + "\n\n" + user


__all__ = [
    "AgentSystemPromptConfig",
    "build_system_prompt_with_config",
]
