# Authentication

Mantecato uses **API keys** to authenticate CLI and MCP server access. Keys are generated from the web UI and stored as SHA-256 hashes in the database — the raw key is shown only once at creation time.

## How It Works

1. Log in to the Mantecato web dashboard
2. Go to **Settings > API Keys**
3. Click **New Key**, give it a name (e.g. "OpenCode MCP", "CLI laptop")
4. Copy the generated key (format: `mtk_...`) — it will not be shown again
5. Use it in CLI or MCP server via environment variable or flag

## Key Format

```
mtk_<base64url-encoded-32-random-bytes>
```

- Prefix `mtk_` identifies Mantecato keys
- 32 bytes of cryptographic randomness (via `crypto.randomBytes`)
- Only the SHA-256 hash is stored in the database
- The `prefix` field (first 12 chars + `...`) is stored for display purposes

## Security Properties

- **Keys are never stored in plaintext** — only their SHA-256 hash
- **Keys are scoped to a user** — each key inherits the creating user's permissions
- **Last used timestamp** is updated on each use (for audit purposes)
- **Keys can be revoked** instantly from the web UI
- **No expiration by default** — delete the key when no longer needed

## Using API Keys

### CLI

Set the environment variable (recommended):

```bash
export MANTECATO_API_KEY="mtk_your-key-here"
mantecato stats --site kerykeion.net
```

Or pass it as a flag:

```bash
mantecato stats --site kerykeion.net --api-key "mtk_your-key-here"
```

### MCP Server

Set the environment variable in your MCP client configuration:

```json
{
  "mcpServers": {
    "mantecato": {
      "command": "npx",
      "args": ["tsx", "src/mcp/server.ts"],
      "cwd": "/path/to/mantecato",
      "env": {
        "DATABASE_URL": "postgresql://...",
        "MANTECATO_API_KEY": "mtk_your-key-here"
      }
    }
  }
}
```

### Docker

Pass the key via environment variable:

```bash
# CLI
docker compose --profile cli run --rm \
  -e MANTECATO_API_KEY="mtk_your-key-here" \
  cli stats --site kerykeion.net

# MCP
docker compose --profile mcp run --rm \
  -e MANTECATO_API_KEY="mtk_your-key-here" \
  mcp
```

Or add it to a `.env` file:

```env
DATABASE_URL=postgresql://...
SESSION_SECRET=your-session-secret
MANTECATO_API_KEY=mtk_your-key-here
```

## API Key Management API

### List keys

```
GET /api/api-keys
```

Returns all keys for the authenticated user (prefix only, never the full key).

### Create key

```
POST /api/api-keys
Content-Type: application/json

{ "name": "My CLI key" }
```

Returns the full key in the response (shown only once).

### Delete key

```
DELETE /api/api-keys
Content-Type: application/json

{ "id": "key-uuid" }
```

## Storage

API keys are stored in the `report` table (the only table Mantecato writes to) with:
- `type = 'api-key'`
- `parameters` JSON containing `{ keyHash, prefix, scopes, createdAt, lastUsedAt }`
- `user_id` linking to the creating user
