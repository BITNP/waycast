# Modules connect to the Agent over a unified network protocol

## Status

Accepted

## Context

Waycast started as a same-process plugin system: input/output modules register
directly with the Agent and are invoked via in-process method calls. That model
fails the user's requirement that the source repository contain "only the core,
no mocks": every built-in module in \`src\` is a placeholder (in-memory notify
channel, mock weather tool, ...). The real architecture is microservices:
inputs and outputs arrive from and go to independent services.

## Decision

Modules run as independent services and connect to the Agent over WebSockets
using a unified JSON Wire protocol. The Agent is the hub: it exposes one
WebSocket endpoint; modules connect to it, authenticate, and announce their
capabilities. A single multiplexed connection carries all frame types - capability
advertisement, input frames, output-unit frames, result frames, and status
queries - distinguished by the frame type field. A module may act as an input
module, an output module, or both over the same connection.

**Transport decoupling**: the Wire protocol is a JSON message frame format,
independent of any particular transport. The default (and first) implementation
is WebSocket; other transports (HTTP, SSE, ...) can be added without changing
the message format.

**Connection & identity**: the Agent exposes a single endpoint (e.g.
\`/ws/modules\`); modules are configured with the Agent address. The unique
module name is the connection identity: the Agent enforces uniqueness and treats
reconnects as idempotent (a new connection with the same name replaces the old
one). A simple connection token is validated on connect; stronger security
(mTLS / PKI) is future work.

**Capability advertisement**: the first frame after connect is a \`capability\`
frame carrying, depending on the module kind:
- input: unique name + arbitrary natural-language description;
- output: unique name + JSON Schema + semantic description of what accepting a
  unit does;
- optional: a status-query channel whose semantics are defined by the module itself; the Agent exposes it to the model as a per-module status tool (e.g. status_<module>) via the capability-bridge middleware, not as an MCP server. Status query is **optional**: a module that has nothing to query simply does not advertise it, and no tool is created for it. (A genuine third-party MCP Server tool may still be wired in as a separate optional tool per ADR-0004, but that is orthogonal to module capability advertisement.)

The natural-language descriptions become part of the Agent's system prompt
alongside the user-customized text. The Agent keeps schema validation before
dispatch (existing behavior); schema travels as JSON Schema over the wire, not
as pydantic objects.

**Inputs**: all inputs arrive as module `input` frames over WebSocket
connections to the hub, flow into the same bounded queue and the same
single-consumer worker; backpressure is globally consistent (ADR-0006).
WebSocket is the only input channel; there is no HTTP input path.

**Output results**: a module returns a \`result\` frame over the same
connection after accepting an output unit; the Agent accumulates it into
\`OutputResultState\` for the next invocation (ADR-0002).

**Reference modules**: example input/output modules live under \`examples/\`,
runnable as standalone services; they double as tests and as developer
references.


**Schema validation**: the Agent validates each output unit against the
advertised JSON Schema before sending it to the module; invalid units are
turned into result frames with status error and are not dispatched.

**System prompt assembly**: on each invocation, the capability bridge rebuilds
the system prompt from [user-customized prompt] + [current capability
catalog] + [default rules]. Module joins/leaves are reflected in the next
invocation without rebuilding the agent graph.

**Lifecycle**: a module that disconnects is removed from the capability
catalog; the fact of its disconnection is carried into the next invocation
prompt as a result-frame observation. Reconnects re-add it.

**Connection token**: WAYCAST_HUB_TOKEN shared secret, sent during the
WebSocket handshake or in the first capability frame; mismatches are closed.

## Consequences

- \`src/\` contains only the core: protocol, Agent, service, the hub, and the
  WebSocket module endpoint. WebSocket is the only input channel.
- No mocks live in production code.
- The in-process \`ModuleRegistry\` evolves into a registry of connected
  endpoints with capability discovery.

