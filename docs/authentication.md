# Authentication

Mantecato uses **API keys** to authenticate CLI and MCP access. You generate keys from the web dashboard, and they're stored securely as SHA-256 hashes.

## Create an API Key

1. Log in to the Mantecato web dashboard
2. Go to **Settings > API Keys**
3. Click **New Key** and give it a name (e.g., "OpenCode MCP", "CLI laptop")
4. Copy the generated key (`mtk_...`) — it won't be shown again

## Use Your Key

The simplest way is to set an environment variable:

```bash
export MANTECATO_API_KEY="mtk_your-key-here"
```

This works for both CLI and MCP. You can also:

- Pass it as a CLI flag: `--api-key "mtk_..."`
- Add it to your `.env` file: `MANTECATO_API_KEY=mtk_...`
- Set it in your MCP configuration's `env` block (see [AI Agent Setup](ai-agents.md))

### Docker

Pass the key via `.env` file or environment variable:

```bash
# Via .env file (recommended)
docker compose --profile cli run --rm cli stats --site kerykeion.net

# Via explicit env var
docker compose --profile cli run --rm \
  -e MANTECATO_API_KEY="mtk_your-key-here" \
  cli stats --site kerykeion.net
```

## Manage Keys

You can manage keys from the web UI (**Settings > API Keys**) or via the API:

| Action | Endpoint |
|--------|----------|
| List all keys | `GET /api/api-keys` |
| Create a key | `POST /api/api-keys` with `{ "name": "My key" }` |
| Delete a key | `DELETE /api/api-keys` with `{ "id": "key-uuid" }` |

The list endpoint only returns key prefixes, never the full key.

---

## Security Details

- **Hashed storage** — Only the SHA-256 hash is stored, never the plaintext key
- **User-scoped** — Each key inherits the creating user's permissions
- **Audit trail** — Last-used timestamp is updated on every use
- **Instant revocation** — Delete a key from the web UI and it stops working immediately
- **No expiration** — Keys are valid until you delete them
- **Format**: `mtk_<base64url-encoded-32-random-bytes>`

Keys are stored in the `report` table (the only table Mantecato writes to) with `type = 'api-key'`.
