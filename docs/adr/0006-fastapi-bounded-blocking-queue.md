# FastAPI service with a bounded, blocking, single-consumer input queue

Waycast runs as an HTTP service (FastAPI + uvicorn) exposing POST /input, which enqueues a unified input and returns 202 immediately. A single worker consumes inputs one at a time. The queue is bounded and producers block when it is full: that blocking, not rejection or throttling, is the backpressure contract the user asked for.
