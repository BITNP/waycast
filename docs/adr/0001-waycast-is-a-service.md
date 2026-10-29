# Waycast is a long-running service, not a library

The user's original framing ("a simple agent on the existing scaffold") could have been a drop-in library, but the requirements — persistent outputs whose results feed the next input, bounded queues with backpressure, and "any input module → Agent → any output subset" routing across process lifetimes — only make sense in a long-running process. We build Waycast as a service loop: single consumer, one input at a time, with an explicit bounded input queue.
