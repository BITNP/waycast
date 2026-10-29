"""Waycast: a pluggable agent service.

Inputs arrive through pluggable input modules; each input triggers one Agent
invocation; the Agent runs a multi-round LLM tool-calling loop and emits a list
of output units targeted at registered output modules, which accept them
fire-and-forget and return an immediate output result that feeds the next
invocation.
"""

from waycast.agent import (
    Agent,
    AgentOutput,
    InvocationResult,
    WaycastAgentState,
    build_agent,
    run_invocation,
)
from waycast.blocks import BlockError, ExpressionBlock, TextBlock
from waycast.config import WaycastConfig, make_model
from waycast.demo import build_agent as build_demo_agent
from waycast.demo import build_registry, build_service
from waycast.modules import (
    HttpInputModule,
    MemoryLogOutputModule,
    NotifyOutputModule,
    default_input_modules,
    default_output_modules,
)
from waycast.protocols import (
    InputModule,
    ModuleRegistry,
    OutputModule,
    OutputUnit,
    UnifiedInput,
    WaycastError,
)
from waycast.service import InputEnvelope, Service
from waycast.state import MemoryHop, OutputResult, OutputResultState, build_state
from waycast.tools import default_tools

__version__ = "0.1.0"

__all__ = [
    "Agent", "AgentOutput", "InvocationResult",
    "WaycastAgentState",
    "build_agent", "build_demo_agent", "run_invocation",
    "BlockError", "ExpressionBlock", "TextBlock",
    "WaycastConfig", "make_model",
    "build_registry", "build_service",
    "HttpInputModule", "MemoryLogOutputModule", "NotifyOutputModule",
    "default_input_modules", "default_output_modules",
    "InputModule", "ModuleRegistry", "OutputModule", "OutputUnit",
    "UnifiedInput", "WaycastError",
    "InputEnvelope", "Service",
    "MemoryHop", "OutputResult", "OutputResultState", "build_state",
    "default_tools",
]
