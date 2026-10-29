# FastAPI hub with a bounded, blocking, single-consumer input queue

Waycast runs as an HTTP service (FastAPI + uvicorn). Every input - module
`input` frames over WebSocket - flows into one bounded queue. A single worker
consumes inputs one at a time. The queue is bounded and producers block when
it is full: that blocking, not rejection or throttling, is the backpressure
contract the user asked for. WebSocket is the only input channel (ADR-0008).
