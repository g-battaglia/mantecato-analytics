# Mantecato — scoped, read-only AI connections

**Draft release notes.** This change is unreleased; implementation is tracked in
[PR #11](https://github.com/g-battaglia/mantecato-analytics/pull/11).
No release version/tag or publication date is assigned by this document.

## Highlights

Connect an external AI assistant to aggregate analytics without giving it admin
access. The new **Settings → AI connections** workbench brings provider setup,
explicit permission approval, connection management and recent activity into
one place. Remote MCP/OAuth is available when a valid canonical public URL is
configured; no global enable flag is required. Without configuration, remote
access is unavailable and collection continues normally. Each client still needs
explicit site-scoped approval.

Provider-specific guides cover Claude, ChatGPT, Gemini, Grok and generic remote
MCP clients. Availability depends on the provider's account, plan, region and
workspace rules. Guides and identification marks are not endorsements or proof
of account-specific interoperability.

## What's new

### A clearer connection setup

Choose an assistant and see one guide at a time. Copy the MCP server address from
its dedicated panel, or use the separate personal-token and agent-assisted setup
flows. Keyboard controls, responsive layouts and light/dark themes are included.
Provider identification SVGs are served locally, with pinned public-source
provenance and retained licensing; no new icon package or frontend framework.

### Explicit, revocable access

OAuth authorization-code flow uses S256 PKCE, short-lived access tokens and
rotating refresh credentials. Personal Bearer tokens are site-scoped, shown
once, with 30-day default expiry, a 1–90-day finite range or explicit **Never
expires**. No-expiry personal tokens remain revocable and subject to live
account/site/scope checks, are included in active-grant quotas and are not
age-cleaned while valid. OAuth credentials still expire and rotate. Credentials are persisted only
as type-separated HMAC digests.

You explicitly choose sites and read scopes. New sites are never automatically
included, even for administrators. Every tool call checks the grant against
current access and checks again before returning results. Permissions can only
be reduced in place; expansion requires new approval. Revocation, expiry,
password changes and account deletion invalidate AI access.

The inventory opens by default when credentials exist, with personal/OAuth
filters and clearly visible name, creation, last use, expiry and state. Revocation
is directly available outside the permission editor, including for expired or
account-invalidated entries. Token values remain show-once, not recoverable.

Authorization is not verification: a connection becomes verified only after a
successful authenticated MCP operation.

### Read-only remote MCP

The exact endpoint `/mcp` uses the official MCP v1 SDK, stateless JSON-only
Streamable HTTP and existing bounded analytics services. Eight tools cover
approved sites, analytics capabilities, connection verification, metrics, time
series, comparisons, traffic-quality diagnostics and dimension discovery.

No raw visitor records, admin tools, arbitrary SQL or bulk export. Mantecato does
not store model-provider API keys, host a chat system or call model providers.
The independent CLI, REST API keys and local stdio MCP remain separate and
compatible; a new `mai_` credential cannot replace a legacy REST key.

### Metadata-only activity and offline cleanup

Activity stores known operations/outcomes, connection/owner, optional site UUID
and timestamp—not prompts, query arguments/results, credentials or IPs.
The daily offline job removes expired authentication records and activity older
than 90 days. Enforcement of expiry/revocation is immediate; timely physical
cleanup requires an operational scheduler.

`run_daily_maintenance` attempts visitor and AI jobs independently with separate
budgets/outcomes. Neither job runs inside HTTP collection or web startup.

## Security and runtime fixes

Callback validation rejects reserved OAuth response parameters even when empty
or URL-encoded. CIMD fetching validates all resolved addresses and pins public
connections while preserving TLS/SNI identity, with bounded DNS/HTTP and JSON
budgets and no redirects or proxy use.

Native Gunicorn 26 ASGI is configured with bounded connections, keep-alive off,
explicit HTTP/1 connection-closure signalling and ORM cleanup on request
finalization/cancellation. An MCP-only HTTPS scheme adapter accepts a single exact
forwarded HTTPS value only from environment-allowlisted proxy IPs/CIDRs; it does
not rewrite Host/client IP or change collector/Django paths.

Further concurrency regressions cover skipped locked cleanup rows and revocation
racing with family deletion: cleanup reports incomplete `busy` outcomes while
retaining progress, and already-removed credentials revoke idempotently.
Unexpected service/JSON failures are audited as unavailable, never completed.

OAuth rate-limit keys use the existing hardened client-IP resolver only for an
explicitly configured trusted proxy topology. Otherwise they use the socket peer,
not spoofable permissive forwarding headers. Limits remain per-worker best-effort,
not global quotas. Daily-job privacy documentation consistently identifies
`run_daily_maintenance`, and HTTP integration tests skip unsupported environments
before fixture writes/worker startup while supporting the `DATABASE_URL` fallback.

## Upgrade and activation requirements

The release adds four authentication/audit models through additive Django
migrations. There is no analytics-schema migration or change to counting formulas,
monthly deduplication, 396-day visitor-digest retention, bot filtering, GPC/DNT or
the tracker heartbeat.

Before upgrade, restore-test a backup and review rollback. Apply migrations once
and use the documented ASGI runtime settings; `CONN_MAX_AGE` is forced to zero
under ASGI. Before configuring the public URL, verify daily cleanup, restrictive
hosts/CSRF, proxy trust, representative resource-capped staging and rollback.
On ASGI, an already-configured valid public URL makes MCP/OAuth available on
upgrade; existing valid grants remain usable without a separate enable flag.
Configure the **environment variable** `FORWARDED_ALLOW_IPS` with the
actual trusted proxy IPs/CIDRs; do not guess a platform range or blindly use `*`.
Django's `USE_SECURE_PROXY_SSL_HEADER` alone does not configure MCP HTTPS.

During an authorized staging/activation check, an unauthenticated POST through
the canonical public HTTPS `/mcp` endpoint must return a 401 challenge, not
`404 ai_access_unavailable`. An absent/invalid public URL intentionally returns
404 without affecting the rest of the application. A health/login check
alone does not validate the MCP path. Verify provider account availability and
real interoperability separately.

External services may retain the results they read; revocation cannot recall
those copies. Paths, titles and event names may contain sensitive data. Review
the receiving service's sharing, training and retention settings before approval.

See [AI connections](../AI-CONNECTIONS.md), [Railway operations](../RAILWAY.md)
and [performance and recovery](../PERFORMANCE.md). Local synthetic tests and
scoped accessibility checks are not a production SLA or whole-product certification.

## Publication gate

Keep these notes as a draft until PR review is resolved and an operator approves
the release revision, version/tag, backup/rollback and staging evidence. A code
release must clearly state that a configured public URL makes MCP/OAuth
available; it does not provision cron, approve clients or certify provider accounts. Publish the matching announcement only after the
release is actually available.
