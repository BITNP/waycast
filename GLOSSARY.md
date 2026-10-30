# Waycast

A long-running agent service. Inputs arrive one at a time, each triggering one Agent invocation that runs a multi-round LLM tool-calling loop and emits a list of output units to registered output modules.

## Language

**Agent**:
The core runtime of the service. It accepts one input at a time, runs a multi-round LLM tool-calling loop, and emits a list of output units.
_Avoid_: bot, chat endpoint, worker

**Input module**:
A pluggable component that delivers external signals into the Agent. Every input carries the same unified data structure, and every input triggers exactly one Agent invocation.
_Avoid_: trigger, source, adapter

**Unified input**:
The single data structure shared by every input module, wrapped around any module-specific content.
_Avoid_: raw payload, event

**Invocation**:
One Agent run triggered by exactly one input.

**Output module**:
A pluggable component that consumes Agent output. It registers with the Agent and declares the JSON schema it accepts for an output unit. Accepting a unit returns an output result immediately.
_Avoid_: sink, destination, subscriber

**Output unit**:
One element of an Agent's output list: a JSON object that satisfies one registered output module's schema, enveloped with the target module's name. The output list may combine units for any subset of output modules, or be empty to do nothing.
_Avoid_: message, event, action

**Output result**:
The immediate value an output module returns after accepting a unit: success/failure status or textual detail. The result is carried into the state of the next invocation.
_Avoid_: ack, callback result, response

**Tool**:
An LLM-callable capability, either a plain function or an MCP tool, that the Agent may invoke across multiple rounds.
_Avoid_: action, plugin, capability

**Backpressure**:
A property of the input path: inputs are processed one at a time, and when the bounded input queue is full, producers block until space frees up.
_Avoid_: rate limiting, throttling

**Global memory**:
The single accumulation of Agent memory shared by every input: all invocations append to one conversation history and output results, since inputs are processed one at a time in a single state. There are no sessions or threads.
_Avoid_: session, thread, per-source state

**Checkpointer**:
LangChain/LangGraph's persistence mechanism that snapshots graph state under a session key (thread_id), giving the Agent short-term memory across invocations.
_Avoid_: store, database, memory object

**Response format (response_format)**:
The schema the Agent is instructed to emit structured output against, via create_agent's response_format parameter; the validated result is carried in the agent state's structured_response key.
_Avoid_: output schema, result contract

**Provider prefix (provider:model)**:
The way model strings are written to LangChain (e.g. openai:gpt-5.5); the prefix selects the integration package, and the part after the colon is the provider's model id.
_Avoid_: model name, model string, llm name


**Module connection**:
A live network link (WebSocket) between a module and the Agent. It is a single multiplexed, full-duplex connection carrying all frame types (capability, input, output unit, result, status query), distinguished by the frame type field. A module may act as input, output, or both over the same connection.
_Avoid_: plugin instance, registered module, local object

**Capability advertisement**:
The set of facts a module announces when it connects to the Agent: its unique
name, a natural-language description (for inputs) or schema and semantic
description (for outputs), and optionally that it offers a status-query
ability. Status query is implemented as a per-module status tool via the
capability-bridge middleware, not as an MCP server.
_Avoid_: registration payload, handshake

**Module endpoint**:
The concrete network address a module listens on or the Agent listens on for modules; how a module is reached (URL) and how it connects.
_Avoid_: socket, port, route

**Wire protocol**:
The JSON message envelope exchanged over a Module connection: typed frames such as input, output_unit, result, and capability that carry UnifiedInput / OutputUnit / OutputResult as payloads.
_Avoid_: api, transport, channel


**Capability catalog**:
The set of capability advertisements held by the Agent for all currently
connected modules, used to build the module part of the system prompt and to
route output units.
_Avoid_: registry, module list, directory

**Connection token**:
A simple shared secret a module presents when connecting to the Agent; the
Agent validates it before accepting capability advertisement.
_Avoid_: password, api key, auth header


**Status query**:
A request on a module connection asking the module to report its current state; the semantics of the reported state are defined by the module itself. Exposed to the Agent's model as a status tool via the capability-bridge middleware (not as an MCP server).
+

---

## Raspberry Girl context

Raspberry Girl (树莓娘) is a product built on Waycast: every input arrives as a Waycast input module, every expression is an output unit to a Waycast output module, and the Agent decides all turn-taking. Terms below are the shared vocabulary for that product layer; deprecated legacy terms are marked.

**Raspberry Girl (树莓娘)**:
The product: a front-facing multimodal agent that interacts through voice, IM, danmaku, and a Live2D avatar. Built on Waycast as its core.
_Avoid_: 看板娘, 树莓女孩, 树莓少女

**网协 (BIT Network Pioneers Association)**:
The Beijing Institute of Technology student association that designed Raspberry Girl and owns her as its official mascot; "网协" is the only sanctioned short form.
_Avoid_: 网络开拓者协会 (without school affiliation)

**Aggregate output module (聚合输出模块)**:
The single Waycast module that combines the Godot frontend (Live2D avatar, subtitle, emotion, motion) with TTS synthesis and playback, plus PPT display/flip. capability.kind = "both"; it receives output units and sends frontend interactions back as input frames. See ADR-0010.
_Avoid_: separate TTS module, separate frontend module, PPT module

**Frontend interaction (前端交互)**:
An event produced by the user in the Godot frontend (click, request) that the aggregate output module sends back to the hub as an input frame, triggering a new Invocation.
_Avoid_: UI event, command

**Final input (最终输入)**:
Every input frame that reaches the hub triggers exactly one Invocation. There is no partial/final distinction; input-side modules decide when to send, and do not mark entry as partial. See ADR-0011.
_Avoid_: partial transcript, final transcript, barge-in candidate

**Turn-taking decision (话权决定)**:
The Agent's own reasoning about whether to interrupt current expression and how to continue, encoded as output units to the aggregate output module. No dedicated turn controller exists. See ADR-0011.
_Avoid_: floor controller, turn epoch, clear-stop, new-reply-replace

**Core enhancement (核心增强)**:
A capability that helps the Agent reason but is not an input/output module ability (e.g. RAG retrieval, prompt assembly, memory strategy) and is implemented inside Waycast core without changing the external contract. See ADR-0012.
_Avoid_: module, plugin, adapter
