"""Waycast: a pluggable agent service.

Modules run as independent services and connect to the Agent hub over a single
multiplexed WebSocket per module (ADR-0008).  Inputs arrive as input frames;
each input triggers one Agent invocation; the Agent runs a multi-round LLM
tool-calling loop and emits a list of output units targeted at connected output
modules, which accept them fire-and-forget and return an immediate output
result that feeds the next invocation.
"""

from waycast.agent import (
    Agent,
    AgentOutput,
    BASE_SYSTEM_PROMPT,
    DEFAULT_RULES,
    InvocationResult,
    WaycastAgentState,
    build_agent,
    run_invocation,
)
from waycast.bridge import CapabilityBridge
from waycast.blocks import results_as_message
from waycast.capabilities import CapabilityCatalog, ModuleEndpoint
from waycast.config import WaycastConfig, make_model
from waycast.hub import Hub
from waycast.prompt_config import (
    build_system_prompt_with_user,
    read_user_system_prompt,
)
from waycast.protocols import OutputUnit, UnifiedInput, WaycastError
from waycast.service import Service
from waycast.state import MemoryHop, OutputResult, OutputResultState, build_state
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

__version__ = "0.2.0"

__all__ = [
    "Agent", "AgentOutput", "BASE_SYSTEM_PROMPT", "DEFAULT_RULES",
    "InvocationResult", "WaycastAgentState",
    "build_agent", "run_invocation",
    "CapabilityBridge", "results_as_message",
    "CapabilityCatalog", "ModuleEndpoint",
    "WaycastConfig", "make_model",
    "Hub",
    "build_system_prompt_with_user", "read_user_system_prompt",
    "OutputUnit", "UnifiedInput", "WaycastError",
    "Service",
    "MemoryHop", "OutputResult", "OutputResultState", "build_state",
    "PROTOCOL_VERSION", "Capability", "InputCapability", "OutputCapability",
    "StatusCapability", "WireFrame", "make_frame", "parse_frame",
]
