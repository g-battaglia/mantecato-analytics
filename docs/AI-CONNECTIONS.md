# AI connections: read-only remote MCP

Settings → AI connections links external assistants to aggregate analytics. It
is not a chat interface: Mantecato does not call models or store provider API keys.
The Django/HTMX page provides setup instructions, scoped connections and activity.
Remote access is **disabled by default**.

## Operator setup

Apply the additive `ai_connections` migrations with the normal web release. They
create four authentication/audit models; analytics tables and formulas are unchanged.
Run the official MCP v1 SDK and Django together with native Gunicorn 26 ASGI:

```bash
gunicorn mantecato.asgi:application --worker-class asgi \
  --workers 2 --worker-connections 16 --keep-alive 0 \
  --bind 127.0.0.1:8000 --access-logfile - \
  --access-logformat '%(m)s %(s)s %(D)s'
```

The deployment manifests use this runtime. Isolated tests found persistent-socket
stalls in the native worker, so keep-alive is explicitly disabled. This is a
measured local compatibility workaround, not a production performance guarantee.
HTTP/1 responses explicitly announce connection closure to prevent socket reuse
races; Django request thread contexts also close ORM sockets on cancellation.
Local concurrent-load regressions exercise both paths.
Legacy `mantecato.wsgi:application` remains available **without remote MCP**.

Before enabling access, establish a restore-tested backup, rollback path, daily
cleanup, restrictive host validation and correct HTTPS/proxy trust. Configure:

```dotenv
AI_CONNECTIONS_ENABLED=False
MANTECATO_PUBLIC_URL=https://analytics.example.com
ALLOWED_HOSTS=analytics.example.com
CSRF_TRUSTED_ORIGINS=https://analytics.example.com
CONN_MAX_AGE=0
GUNICORN_WORKER_CONNECTIONS=16
```

Use a canonical origin without a path, query, fragment or credentials. Only HTTPS
is accepted, except DEBUG loopback tests. The endpoint is exactly
`https://analytics.example.com/mcp`, **without a trailing slash**. The
MCP boundary must see `scope.scheme=https` in production. Gunicorn 26's native
ASGI parser reports socket TLS and does **not** translate forwarded scheme
headers, even with its proxy allowlist configured. A narrow **MCP-only** adapter
reads `FORWARDED_ALLOW_IPS` from the environment and accepts one exact
`X-Forwarded-Proto: https` header only from a trusted IP/CIDR. It never rewrites
Host/client IP or changes collector/Django requests; missing, duplicate or chained
values fail closed. Direct socket HTTPS is preserved.

Set the **environment variable**, not only a Gunicorn CLI override, to the actual
trusted proxy addresses when TLS terminates upstream. Default is `127.0.0.1,::1`,
not arbitrary platform proxy peers. Configure Django's proxy SSL header
consistently: `USE_SECURE_PROXY_SSL_HEADER=True` applies only inside Django and
cannot change the MCP ASGI scope. Never trust arbitrary forwarding
headers on an internet-accessible backend. Test `/mcp` through the public proxy
before activation; incorrect scheme/host configuration denies access.

OAuth rate limits are bounded, per-worker best-effort limits, not global quotas.
Their keys hash the client IP resolved by the hardened existing resolver when
`TRUST_PROXY_HEADERS=True` and `TRUSTED_PROXY_COUNT>0` describe the verified proxy
topology. Otherwise they use the socket peer, never the legacy permissive
forwarded-header mode. Unknown proxy topology can put clients in a shared bucket;
configure the real hop count and network trust, or enforce suitable limits at
the trusted edge. This does not change tracker IP extraction or persist audit IPs.

The switch blocks new grants and MCP reads, but leaves existing inventory and
revocation available. Changing the canonical origin or `SECRET_KEY` invalidates
AI credentials and requires reconnection. Password changes and user soft deletion
also invalidate them. Legacy REST keys retain their existing semantics.

Only after operational checks should an operator set `AI_CONNECTIONS_ENABLED=True`
and restart the web workers. Shipping a manifest does not deploy, activate a
cron, connect a provider account, or establish interoperability.

### Public-proxy activation check

Use verified TLS proxy IPs or CIDRs for `FORWARDED_ALLOW_IPS`, not a guessed
platform address range. `*` is appropriate only if network controls ensure that
**only trusted proxies** can reach Gunicorn and those proxies sanitize secure
scheme headers. It is not a safe default for a directly reachable backend.

In an authorized staging/activation check, after the other operational gates pass,
start workers with `AI_CONNECTIONS_ENABLED=True` and the intended public origin.
Then send an **unauthenticated** request through the real public HTTPS endpoint:

```bash
curl --max-time 10 --include --request POST https://analytics.example.com/mcp
```

Expect **401** with a `WWW-Authenticate` challenge pointing to the canonical
HTTPS protected-resource metadata URL. This verifies routing and scheme detection,
not OAuth completion or provider interoperability. **404 `ai_access_unavailable`**
can mean disabled/misconfigured AI access or an untrusted proxy reporting HTTP;
with the flag off, 404 is intentional and cannot prove HTTPS detection. A working
login or health endpoint does not prove the MCP path is configured correctly.
If the check fails, keep/revert the feature off and correct proxy trust; do not
remove the HTTPS guard. Local native-worker tests cover trusted, untrusted and
missing forwarded headers, but do not certify Railway or Render networking.

## Connect an assistant

Open Settings → AI connections → Add connector. Copy the public MCP address,
follow the provider-specific instructions, sign in to Mantecato and explicitly
select sites and read-only permissions. At least one site and permission are
required; **new sites are never added automatically**, even for administrators.

Claude's shortcut pre-fills its custom connector dialog with a name and public
URL, never credentials. ChatGPT, Gemini, Grok and generic clients have manual
instructions and official links. Account, region, age and workspace restrictions
can change. A guide or a declared client name is not provider endorsement or
proof of a working account-specific integration. Provider labels use locally
served identification marks from a pinned public Lobe Icons revision (license
and provenance in `static/images/providers/README.md`). SVGs are local, decorative
images beside text labels, with no third-party image requests or runtime icon
package. Trademark rights remain with their owners; marks do not imply endorsement.

Verify with authenticated `tools/list` or `get_connection_status`; these do not
read statistics. Issuing a token or accepting consent produces an
**authorized, not verified** connection. Verification means a successful MCP
operation, not certification of a client's declared identity. Expired, revoked
and password-invalidated connections remain distinguishable.

A setup prompt is provided without credentials. Never put a password, code or
token in an AI conversation. Cloud assistants cannot reach a localhost URL.

### Clients without OAuth

Create a named personal token with explicitly selected sites/scopes. Default
lifetime: 30 days; maximum: 90 days; no refresh. It is shown once, only in the
creation response, with `Cache-Control: no-store` and HTMX history disabled.
Copy it to a client's protected Bearer credential setting. It is not a model API
key and cannot authenticate the generic REST API. Active connections are limited
to 20 per user by default. This limit includes OAuth grants.

The independent `mantecato-mcp` **stdio** package and CLI are unchanged. They use
legacy `mtk_` API keys and the authenticated REST API; a new remote personal token
cannot be substituted for that API key. See [the stdio guide](../packages/mantecato-mcp/README.md).

## Permissions, tools and limits

Scopes are only `sites:read` and `analytics:read`. Each call intersects approved
UUIDs with the user's current owner/admin access. Access is checked again after
analytics execution; transferring/deleting a site, reducing permissions, revoking
a grant or changing an account does not grant implicit future access. Existing
connections can only lose sites/scopes. Expansions require new consent.

Eight read-only tools: `list_sites`, `describe_analytics`, `query_metrics`,
`query_timeseries`, `compare_breakdown`, `traffic_quality`, `list_dimension_values`,
and `get_connection_status`. They use the existing validated v1 contracts and
read-only SQL services directly, not HTTP loopback, shell commands or arbitrary
SQL. No raw events, visitor digests, user profiles or admin settings are exposed.

Metric definitions, bot filters, half-open dates, timezones, partial buckets,
`null`/unavailable values and truncation metadata retain REST semantics. API daily
uniques are not multi-day distinct people or dashboard monthly uniques. Page
paths, titles, groups and event names are untrusted data, never instructions.

Requests are bounded at 32 KiB; JSON result budgets are 512 KiB. Oversized results
fail and require a narrower query rather than silently appearing complete. One
MCP tool query runs per worker; SQL/lock limits remain those of API v1. Django
connections close explicitly after MCP ORM work and Django request finalization.
ASGI forces connection persistence off even if a legacy environment sets it. Worker HTTP connections default
to 16. Rate controls are bounded and **per-process best-effort**, not global quotas.
Unauthenticated and rate-rejected attempts are not added to the activity log.

Bearer authentication never falls back to browser cookies. MCP browser CORS
allows the canonical origin and documented provider origins, without credentials;
additional exact origins use `AI_MCP_ALLOWED_ORIGINS`. Consent/management use
Django sessions, same-origin CSRF checks and no CORS opening.

## OAuth implementation

Public authorization-server and protected-resource discovery advertise only the
implemented authorization-code and rotating-refresh grants, public-client `none`
authentication and S256 PKCE. Audience/resource must be the canonical `/mcp` URL
at authorization and token exchange. Challenge responses advertise resource
metadata. Codes are one-use, with committed issuance/consumption and connection
locks; valid code/refresh replay revokes the entire connection family.

Defaults: browser-bound consent requests 10 minutes, codes 5 minutes, access
tokens 15 minutes and rotating refresh tokens 30 days. Successful refresh extends
the connection expiry to the new refresh expiry. An expired access token alone
is not an expired OAuth connection. Only opaque, domain/type-separated HMAC
credential digests are persisted; raw tokens/codes are never stored.

Dynamic registration and Client ID Metadata Documents are supported. Redirects
are exact HTTPS URLs or explicit HTTP loopback URLs, never wildcard/native
schemes, userinfo or fragments. Client metadata uses bounded DNS and HTTP I/O,
public-address validation, pinned connections with the original TLS/SNI hostname,
no redirects/proxies, a 16 KiB JSON budget and duplicate-key rejection. Slow
streams are bounded separately; per-I/O timeouts are not an absolute process-kill
deadline. Declared client names are untrusted; consent displays the callback host.

## Privacy and offline retention

Approval permits later automatic requests, not an automatic database upload.
The chosen assistant/provider receives requested aggregates and may retain them.
Paths/titles/labels can contain personal data. Review provider training, sharing,
retention and legal terms for the actual account. Revocation stops future access
but cannot erase copies already received; Mantecato promises no universal provider
DPA, training exclusion or retention policy.

Activity stores only owner/connection, known operation, optional site UUID,
timestamp and outcome. No prompts, analytics arguments/results, credentials or
IP addresses are recorded. Consent stores a version and canonical-text hash.
Activity is shown on demand, ten entries per cursor page, with no polling.

Schedule and monitor the offline job independently of web startup:

```bash
python manage.py run_daily_maintenance --rollup-runtime 900 --ai-runtime 120
# Optional inspection/individual cleanup:
python manage.py cleanup_ai_connections --dry-run
python manage.py cleanup_ai_connections --max-runtime 120 --batch-size 500
```

The orchestrator always attempts AI cleanup even when visitor rollup is busy or
fails, and emits separate outcomes. Cleanup batches remove expired requests and
credentials, audit older than 90 days, soft-deleted users' grants, long-inactive
connections and unused clients. Valid credentials and pending consent requests
are protected. Eligible rows skipped because another transaction holds their
locks produce a `busy` outcome, not `completed`; committed batches are retained
and the next run resumes. Incomplete cleanup exits with status 2 and should be
monitored/retried. Expiry/revocation enforcement works without cron, but timely
record deletion requires a working scheduler. `/railway.rollup.toml` now runs
both jobs; selecting it provisions nothing. See [Railway](RAILWAY.md#e-daily-maintenance-required).

## Validation and rollback

Test only against isolated PostgreSQL and synthetic accounts. Local tests exercise
real SDK OAuth discovery/PKCE, CSRF consent, initialize/notifications/tools,
multiple ASGI workers, refresh replay, tenant boundaries, SSRF, scoped results and
legacy collector/script/preflight. These are not authorized provider-account
trials or representative constrained-resource staging evidence.

Before public rollout, measure HTTP percentiles, CPU/RSS, database connections,
locks and temporary I/O under concurrent MCP, ingestion and maintenance on the
intended resource limits. Restore-test the backup and monitor the first 24 hours.
For rollback disable AI access first, preserve the additive tables, and restore
the previous runtime/revision if needed. Do not drop authentication tables or
alter analytics retention as an emergency workaround.
