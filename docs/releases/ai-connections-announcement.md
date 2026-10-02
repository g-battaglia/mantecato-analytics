# Introducing read-only AI connections for Mantecato

> **Announcement draft—not published.** Prepared for the next approved GitHub
> release. Publish only after the reviewed release is available; do not describe
> an unmerged PR as a shipped feature. No version/tag has been assigned here.

Mantecato is adding a way to bring your website analytics into an AI assistant
without handing over admin access.

The new **AI connections** page lets you choose an assistant, approve specific
sites and read-only permissions, and manage that access from one place. The
redesigned setup shows one guide at a time, recognizable locally served provider
marks and a dedicated server-address panel, with keyboard and mobile support.

The remote MCP endpoint exposes bounded aggregate analytics: metrics, time series,
comparisons, traffic-quality diagnostics and dimension discovery. It does not
expose raw visitor records, arbitrary SQL or administrative operations.

OAuth uses PKCE and rotating credentials. Clients without OAuth can use an
site-scoped personal token, shown once: 30 days by default, or an explicit
**Never expires** option. The inventory lists token names, last use, expiry and
status with a directly visible revocation action. You can revoke or reduce access,
and adding another website never silently expands an existing grant. No-expiry
tokens remain subject to live account/site checks; OAuth credentials stay short-lived.

Mantecato remains a self-hosted analytics server, not an AI chat service. It
stores no model-provider API keys and makes no calls to model providers. The
existing CLI, REST API keys and local stdio MCP keep working independently.

Setup guides are included for Claude, ChatGPT, Gemini, Grok and other remote MCP
clients. Provider availability varies by account and workspace; these guides do
not imply endorsement or certified interoperability with every account.

AI access is **off by default**. Operators must verify HTTPS/proxy trust, backups,
daily cleanup, staging and rollback before enabling it. Your assistant may retain
the results it reads, so check its data-sharing and retention settings before
connecting. Revocation stops future access; it cannot recall existing copies.

Read the [setup and security guide](../AI-CONNECTIONS.md) and
[release notes](ai-connections-release-notes.md). Feedback on the setup flow,
client compatibility and documentation is welcome in
[GitHub Issues](https://github.com/g-battaglia/mantecato-analytics/issues).

---

## Maintainer publishing notes

Suggested headline: **Bring Mantecato analytics to your assistant—with scoped,
read-only access**.

For a GitHub Release, copy the announcement paragraphs above (excluding the draft
notice and this section) and pair them with the release notes for the approved
revision. Replace relative guide links with absolute URLs pinned to the approved
release tag; confirm the final version and publication date without inventing them.
Do not advertise production availability or account-specific provider support
without corresponding verification.

A GitHub Discussions “Announcements” post is another possible destination, but
Discussions must first be enabled and an appropriate category selected by the
maintainer. Do not enable repository features or create a public announcement as
part of preparing this draft. Keep screenshots synthetic and credential-free.
