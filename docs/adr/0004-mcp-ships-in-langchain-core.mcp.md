# MCP tool access is built into `langchain.mcp` (v1.4+), not `langchain-mcp-adapters`

The standalone `langchain-mcp-adapters` package is replaced by the `langchain.mcp` namespace (requires `langchain[mcp]>=1.4.0`, built on FastMCP, currently beta). Any MCP tool integration in Waycast uses `MCPAdapter` from the in-tree `langchain.mcp` namespace rather than the deprecated adapter package.
