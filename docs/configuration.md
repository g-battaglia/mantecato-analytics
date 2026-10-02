# Server configuration

Copy [.env.example](../.env.example) for local setup; never commit credentials.
The server needs PostgreSQL, Python 3.12+, a secret signing key and applied
migrations. Run production with `DEBUG=False`, restrictive `ALLOWED_HOSTS`, HTTPS,
secure session/CSRF cookies and appropriately trusted proxy headers. Review
[Railway](RAILWAY.md) for platform setup and [privacy](privacy.md) for the separate
tracked-site collector policy.

| Setting | Default / purpose |
| --- | --- |
| `DATABASE_URL` | Required PostgreSQL URL; never reuse production for tests |
| `TEST_DATABASE_URL` | Optional development override when DEBUG is enabled |
| `SECRET_KEY` | Required; rotation invalidates signed sessions and credentials |
| `ALLOWED_HOSTS` | Explicit host allowlist is required for a public deployment |
| `CSRF_TRUSTED_ORIGINS` | HTTPS origins, not hostnames alone |
| `QUERY_SUMMARY_LOG` | `False`; detailed production request SQL summaries are opt-in |
| `CONN_MAX_AGE` | `0`; persistent Django connections must remain disabled under ASGI |
| `GUNICORN_WORKER_CONNECTIONS` | `16` in the shipped ASGI manifests |
| `MANTECATO_PUBLIC_URL` | Canonical HTTPS origin, e.g. `https://analytics.example.com`; makes remote MCP/OAuth available when valid; leave blank when unused |
| `AI_MCP_ALLOWED_ORIGINS` | Optional additional exact browser origins, comma-separated |
| `FORWARDED_ALLOW_IPS` | Environment IP/CIDR allowlist read by Gunicorn and the MCP-only HTTPS scheme adapter; default loopback only |

MCP uses the official v1 SDK on Gunicorn 26's native ASGI worker. Deployment
commands explicitly disable keep-alive after isolated compatibility tests found
persistent-socket stalls. WSGI remains available for legacy deployments without
remote MCP. Gunicorn 26 ASGI does not translate forwarded scheme headers; the
MCP-only adapter honors a single HTTPS header from an environment-allowlisted
peer. Django's proxy SSL setting is separate. Verify the real proxy boundary
before enabling public access; never assume a wildcard trust setting is safe.
[AI connections](AI-CONNECTIONS.md) documents audience, scopes,
credential lifetimes, OAuth discovery, bounded concurrency and provider guides.
The CLI and local stdio MCP package keep their existing API-key configuration.

Run `manage.py run_daily_maintenance` in a separate terminating daily job, not
HTTP or web startup. It independently attempts visitor maintenance and 90-day AI
audit/credential cleanup. Activating a production scheduler and enabling external
AI access are separate operator decisions. Restore-test backups and validate
proxy/host configuration before activation.

Monthly deduplication, IP truncation, 396-day visitor-digest retention, GPC/DNT
semantics and the 15-second tracker heartbeat are unchanged and not AI settings.
See [performance](PERFORMANCE.md) for isolated benchmarks and load-test limits.
