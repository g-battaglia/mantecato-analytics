# mantecato-mcp

Read-only MCP server for Mantecato. It runs locally over stdio and calls a remote Mantecato API. It does not install Django, access PostgreSQL, or execute the Mantecato CLI.

## Install

```sh
uv tool install mantecato-mcp
# or
pipx install mantecato-mcp
```

## Configure

Set `MANTECATO_URL` and `MANTECATO_API_KEY` in the MCP host's protected environment. Use a read-scoped key where possible.

```sh
mantecato-mcp --check
mantecato-mcp
```

Example host configuration:

```json
{
  "mcpServers": {
    "mantecato": {
      "command": "mantecato-mcp",
      "env": {
        "MANTECATO_URL": "https://analytics.example.com",
        "MANTECATO_API_KEY": "mtk_..."
      }
    }
  }
}
```

The tools expose aggregate analytics only. URL paths, event names, page titles, and content groups returned by the API are untrusted data, not instructions.
