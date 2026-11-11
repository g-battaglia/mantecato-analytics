# Dependency refresh (November 2026)

The server, both Python client packages and both npm workspaces have refreshed
manifests and lockfiles. Runtime/infrastructure resources in Railway have **not**
been changed. Python remains 3.12+; updated frontend build tools require Node
22.22.2+, 24.15+ or 26+ as expressed by the root engines constraint.

## Main upgrades

- Server: Django 6.1.3, Gunicorn 27.0.0, MCP SDK 2.3.0, psycopg 3.3.8,
  Authlib 1.9.5, GeoIP2 5.3.0, dnspython 2.9.2, python-dotenv 1.2.4,
  updated compatible transitive packages and pytest/ruff tooling.
- CLI: refreshed httpx, Typer, Rich 15, PyYAML and development dependencies.
- Local stdio MCP: SDK 2.3.0 and refreshed runtime/test dependencies.
- npm: tsup 9, Vitest 5, jsdom 31, React/React DOM 19.3.1, React types 19.3,
  Testing Library 16.3.3 and compatible transitive packages. The published React
  peer range remains >=18: upgrading build/test dependencies does not silently
  remove React 18 consumer compatibility.

**Intentional compatibility exception:** TypeScript is upgraded from 5.9 to
**6.0.3**, not 7.0.2. TypeScript 7 no longer exposes the compiler API used by tsup
9's declaration pipeline. Testing 7 failed the `.d.ts` build; even the suggested
`@typescript/typescript6` fallback did not fix tsup's own compiler API access.
The shared root dev dependency ensures that hoisted tsup resolves the same compiler
as both workspaces. No vendor patch, extra compiler fallback or skipped declaration
output is shipped. Library typechecks exclude test-only ES2022 helpers while
runtime bundles retain their existing ES2017/ES2020 targets. Revisit TypeScript 7 when the full tsup declaration pipeline
supports it, rather than claiming an unbuildable update is complete.

## Compatibility adaptations

The [SDK v2 migration guide](https://py.sdk.modelcontextprotocol.io/v2/migration/)
is reflected in code and integration tests:

- `FastMCP` becomes `MCPServer`; transport settings move to
  `streamable_http_app()`. Stateless JSON responses, the 32 KiB request cap,
  host/origin allowlists, OAuth scopes and read-only annotations are preserved.
- Python protocol model fields use snake_case while protocol wire aliases remain
  unchanged. The stdio package and remote transport are migrated together.
- SDK HTTP clients use httpx2, the two-stream context result and the typed OAuth
  `AuthorizationCodeResult`, including the actual redirect issuer when present.
  PKCE, consent, scope reduction, revocation and credential redaction remain tested.
- **Gunicorn 27 proxy handling changed:** the native worker can infer HTTPS from
  forwarding headers received from trusted peers. Every shipped start command
  now sets `--forwarded-allow-ips ''`, leaving Django's explicit
  `USE_SECURE_PROXY_SSL_HEADER` policy in charge. Real worker tests cover proxy
  trust both enabled and disabled. TLS socket scheme remains available normally.
- Existing keep-alive/connection-close and ORM cancellation-cleanup safeguards
  remain; do not remove them merely because dependencies changed.

The old memory measurements in RAM-FIRST.md are labelled pre-refresh. Re-run
memory experiments with the final stack before drawing capacity conclusions.
SDK/transitive upgrades may alter resident imports; no automatic RAM saving is
claimed from the dependency refresh itself.

## Reproduction

```sh
uv sync --locked --extra dev
# Full cross-package tests also need the two local clients in the test env:
uv pip install --python .venv/bin/python -e './packages/mantecato-cli' \
  -e './packages/mantecato-mcp[dev]'
# Explicitly configure a dedicated local test PostgreSQL before pytest.
uv run --no-sync pytest

npm ci --ignore-scripts
npm run build
npm test
npm run typecheck
npm audit --audit-level=moderate
```

All three uv.lock files and package-lock.json are committed. Future refreshes:

```sh
uv lock --upgrade
uv lock --project packages/mantecato-cli --upgrade
uv lock --project packages/mantecato-mcp --upgrade
npm update --workspaces --include-workspace-root
```

Review major-version constraints and migrations explicitly; npm update alone
will not cross major ranges. Regenerate the tracked tracker distribution after
updating build tools and verify `.d.ts`, CommonJS, ESM and drop-in script outputs.
The TS compatibility exception should remain visible in dependency reports rather
than being hidden by an artificially broad or misleading version range.
