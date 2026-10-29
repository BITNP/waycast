# Memory is one global thread, not per-session state

The user chose global single-state memory over session-scoped memory: every input, from any input module, accumulates into one shared conversation history and output-result feed, because inputs are processed one at a time in a single consumer. We realize this with a LangGraph checkpointer (InMemorySaver) and a fixed thread_id for every invocation. There are no sessions or per-source isolation; a future session layer can be added without changing the memory primitive.
