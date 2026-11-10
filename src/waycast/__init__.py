"""Waycast: a pluggable agent service.

Modules run as independent services and connect to the Agent hub over a single
multiplexed WebSocket per module (ADR-0008).  Inputs arrive as input frames;
each input triggers one Agent invocation; the Agent runs a multi-round LLM
tool-calling loop and emits a list of output units targeted at connected output
modules, which accept them fire-and-forget and return an immediate output
result that rides at the head of the next invocation's input message exactly
once (ADR-0002 / ADR-0014).
"""

from waycast.agent import (
    BASE_SYSTEM_PROMPT,
    DEFAULT_RULES,
    Agent,
    AgentOutput,
    InvocationResult,
)
from waycast.bridge import CapabilityBridge
from waycast.capabilities import CapabilityCatalog, ModuleEndpoint
from waycast.config import WaycastConfig, make_model
from waycast.hub import Hub
from waycast.prompt_config import (
    build_system_prompt_with_user,
    read_user_system_prompt,
)
from waycast.protocols import OutputUnit, UnifiedInput, WaycastError
from waycast.service import Service
from waycast.state import (
    OutputResult,
    OutputResultState,
    input_content_with_feed,
    results_as_text,
)
from waycast.wire import (
    PROTOCOL_VERSION,
    Capability,
    InputCapability,
    OutputCapability,
    StatusCapability,
    WireFrame,
    make_frame,
    parse_frame,
)

__version__ = "0.1.0"

__all__ = [
    "BASE_SYSTEM_PROMPT",
    "DEFAULT_RULES",
    "PROTOCOL_VERSION",
    "Agent",
    "AgentOutput",
    "Capability",
    "CapabilityBridge",
    "CapabilityCatalog",
    "Hub",
    "InputCapability",
    "InvocationResult",
    "ModuleEndpoint",
    "OutputCapability",
    "OutputResult",
    "OutputResultState",
    "OutputUnit",
    "Service",
    "StatusCapability",
    "UnifiedInput",
    "WaycastConfig",
    "WaycastError",
    "WireFrame",
    "build_system_prompt_with_user",
    "input_content_with_feed",
    "make_frame",
    "make_model",
    "parse_frame",
    "read_user_system_prompt",
    "results_as_text",
]
