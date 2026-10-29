# Build on LangChain v1 `create_agent` (not v0.x AgentExecutor/`create_react_agent`)

The user requires the latest LangChain versions and docs. Current LangChain is v1.x: `create_agent` is the high-level agent factory (with `tools`, `system_prompt`, `middleware`, `response_format`, `checkpointer`), and the old `AgentExecutor`/`create_react_agent` pattern from 0.x is legacy. Content from `langchain-community` is no longer maintained and must be avoided. We depend on `langchain` (and `langchain-core`) at their current v1 versions.
