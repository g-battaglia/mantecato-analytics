# AI Agent Setup Guide

Mantecato is designed to be queried by AI agents. This guide covers setup for every supported platform.

## Prerequisites

1. Mantecato installed and configured (`npm install`, `.env` set up, Prisma client generated)
2. An API key generated from the web UI (Settings > API Keys)
3. The `DATABASE_URL` and `MANTECATO_API_KEY` environment variables set

## How It Works

Mantecato exposes analytics data through two interfaces that AI agents can use:

### MCP Server (41 tools)

The [Model Context Protocol](https://modelcontextprotocol.io/) server exposes typed tools that agents call directly. The agent receives structured JSON responses — no output parsing needed.

```
Agent                          Mantecato MCP Server
  │                                  │
  ├─ call get_stats(site, period) ──→│
  │                                  ├─ query PostgreSQL
  │←── { pageviews: 8420, ... } ─────┤
  │                                  │
  ├─ call get_pages(site, ...) ─────→│
  │←── [{ url: "/", views: 1200 }] ──┤
```

**Pros:** Typed schemas, structured responses, no shell needed.
**Cons:** Requires MCP configuration per editor/tool.

### CLI Agent (38 commands)

The agent runs shell commands via `npx tsx src/cli/index.ts <command>`. It reads the terminal output (table, JSON, or CSV) and reasons about it.

```
Agent                          Shell
  │                              │
  ├─ exec: npx tsx src/cli/     │
  │   index.ts stats --site     │
  │   mysite.com --format json ─→│
  │                              ├─ query PostgreSQL
  │←── {"pageviews": 8420, ...} ─┤
```

**Pros:** Works anywhere a shell is available, no MCP config needed.
**Cons:** Agent must parse output, slightly higher latency.

Both approaches query the same database through the same query modules and return identical data.

---

## OpenCode

### What's included in the repo

| File | What it does |
|------|-------------|
| `.opencode/agents/site-analyst.md` | Custom agent that uses the CLI for deep analytics. Select it from the agent picker. |
| `.opencode/skills/traffic-report/SKILL.md` | Skill for generating comprehensive traffic reports |
| `.opencode/skills/content-audit/SKILL.md` | Skill for auditing content performance |
| `.opencode/skills/funnel-analysis/SKILL.md` | Skill for analyzing conversion funnels |

### Using the CLI agent

The site-analyst agent is available automatically when you open the project:

```bash
cd /path/to/mantecato
opencode
```

Select **site-analyst** from the agent picker. Then ask:

```
"Analyze kerykeion.net traffic for the last 30 days"
"Which pages have the highest bounce rate?"
"Compare this month vs last month for all my sites"
```

The agent will run CLI commands, cross-reference data across dimensions, and deliver structured reports.

### Using skills

Skills are loaded automatically. You can reference them in any conversation:

```
"Use the traffic-report skill to analyze kerykeion.net"
"Run a content audit for mysite.com for the last 90 days"
"Analyze the signup funnel: /, /pricing, /signup, /welcome"
```

### Adding MCP (optional)

If you also want MCP tools available (in addition to the CLI agent), add to `~/.config/opencode/config.json`:

```json
{
  "mcpServers": {
    "mantecato": {
      "command": "npx",
      "args": ["tsx", "src/mcp/server.ts"],
      "cwd": "/path/to/mantecato",
      "env": {
        "DATABASE_URL": "postgresql://user:pass@host/dbname",
        "MANTECATO_API_KEY": "mtk_your-key-here"
      }
    }
  }
}
```

---

## Claude Code

### What's included in the repo

| File | What it does |
|------|-------------|
| `CLAUDE.md` | Project instructions: full CLI reference, analysis methodology, output format |
| `.claude/commands/traffic-report.md` | `/project:traffic-report` slash command |
| `.claude/commands/content-audit.md` | `/project:content-audit` slash command |
| `.claude/commands/funnel-analysis.md` | `/project:funnel-analysis` slash command |

### Using Claude Code with the CLI

Claude Code reads `CLAUDE.md` automatically:

```bash
cd /path/to/mantecato
claude
```

Then ask analytics questions directly:

```
"Analyze traffic for kerykeion.net over the last 30 days"
"What are the top traffic sources and how do they compare to last month?"
"Show me the bounce rate by device type for US visitors"
```

Claude Code will run `npx tsx src/cli/index.ts <command>` with appropriate options.

### Using slash commands

Slash commands provide structured analysis workflows:

```
/project:traffic-report kerykeion.net 30d
/project:content-audit kerykeion.net 90d
/project:funnel-analysis kerykeion.net /,/pricing,/signup
```

Each command runs a multi-step analysis: gathering data, cross-referencing dimensions, and producing a formatted report.

### Adding MCP (optional)

```bash
# Add MCP server to Claude Code
claude mcp add mantecato \
  -e DATABASE_URL="postgresql://user:pass@host/dbname" \
  -e MANTECATO_API_KEY="mtk_your-key-here" \
  -- npx tsx /path/to/mantecato/src/mcp/server.ts
```

Or add to `~/.claude.json`:

```json
{
  "mcpServers": {
    "mantecato": {
      "command": "npx",
      "args": ["tsx", "/path/to/mantecato/src/mcp/server.ts"],
      "env": {
        "DATABASE_URL": "postgresql://user:pass@host/dbname",
        "MANTECATO_API_KEY": "mtk_your-key-here"
      }
    }
  }
}
```

---

## Claude Desktop

Claude Desktop supports MCP only (no CLI access).

Add to `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or `%APPDATA%\Claude\claude_desktop_config.json` (Windows):

```json
{
  "mcpServers": {
    "mantecato": {
      "command": "npx",
      "args": ["tsx", "/path/to/mantecato/src/mcp/server.ts"],
      "env": {
        "DATABASE_URL": "postgresql://user:pass@host/dbname",
        "MANTECATO_API_KEY": "mtk_your-key-here"
      }
    }
  }
}
```

Restart Claude Desktop. Then ask:

```
"List all my tracked sites"
"Show me the top pages for kerykeion.net in the last 7 days"
"Run a funnel analysis: homepage → docs → examples"
```

---

## Cline

### What's included in the repo

| File | What it does |
|------|-------------|
| `.clinerules` | Project instructions: CLI reference, analysis methodology |

### Using Cline with the CLI

Cline reads `.clinerules` automatically when you open the project:

```
"Analyze traffic for kerykeion.net"
"Run a content performance audit for the last 90 days"
```

### Adding MCP

In VS Code, open Cline settings and add an MCP server:

```json
{
  "mcpServers": {
    "mantecato": {
      "command": "npx",
      "args": ["tsx", "/path/to/mantecato/src/mcp/server.ts"],
      "env": {
        "DATABASE_URL": "postgresql://user:pass@host/dbname",
        "MANTECATO_API_KEY": "mtk_your-key-here"
      }
    }
  }
}
```

---

## Cursor

### What's included in the repo

| File | What it does |
|------|-------------|
| `.cursorrules` | Project instructions: CLI reference, analysis methodology |

### Using Cursor with the CLI

Cursor reads `.cursorrules` automatically. Ask analytics questions in Composer or Chat:

```
"Analyze my site's traffic trends"
"Which sources send the highest quality traffic?"
```

### Adding MCP

In Cursor settings, go to Features > MCP Servers and add:

```json
{
  "mcpServers": {
    "mantecato": {
      "command": "npx",
      "args": ["tsx", "/path/to/mantecato/src/mcp/server.ts"],
      "env": {
        "DATABASE_URL": "postgresql://user:pass@host/dbname",
        "MANTECATO_API_KEY": "mtk_your-key-here"
      }
    }
  }
}
```

---

## Docker-based MCP

If you prefer not to install Node.js locally, run the MCP server via Docker:

```json
{
  "mcpServers": {
    "mantecato": {
      "command": "docker",
      "args": [
        "compose", "-f", "/path/to/mantecato/docker-compose.yaml",
        "--profile", "mcp", "run", "--rm", "-i", "mcp"
      ],
      "env": {
        "DATABASE_URL": "postgresql://user:pass@host/dbname",
        "MANTECATO_API_KEY": "mtk_your-key-here"
      }
    }
  }
}
```

This works with any MCP client (OpenCode, Claude Desktop, Cursor, etc.).

---

## Example Workflows

### Traffic report

```
You:   "Give me a full traffic report for kerykeion.net, last 30 days"

Agent: 1. Runs stats --period 30d (overall metrics)
       2. Runs compare --period 30d (period-over-period deltas)
       3. Runs top-pages --limit 20 (content performance)
       4. Runs sources --limit 20 (traffic sources)
       5. Runs channels (channel breakdown)
       6. Runs devices (device split)
       7. Runs geo --limit 10 (geographic breakdown)
       8. Cross-references bounce rates by source × device
       9. Delivers structured report with executive summary,
          key metrics, findings, and recommendations
```

### Diagnosing a traffic drop

```
You:   "Traffic dropped this week. What happened?"

Agent: 1. Runs compare --period this_week (confirms the drop)
       2. Runs timeseries --period 14d --granularity day (finds the exact day)
       3. Runs pages --period this_week --format json (finds which pages dropped)
       4. Runs sources --period this_week --format json (finds which sources dropped)
       5. Runs pages --period last_week --format json (baseline comparison)
       6. Identifies: "Organic traffic to /blog/popular-post dropped 60% on Tuesday.
          Google may have deindexed it. The page's bounce rate also spiked from
          35% to 78%, suggesting a content or loading issue."
```

### Funnel optimization

```
You:   "Analyze the signup funnel and tell me where we're losing people"

Agent: 1. Runs funnel --steps "/,/pricing,/signup,/welcome"
       2. Runs page-detail --url /pricing (where's the biggest drop-off)
       3. Runs devices --filter url_path:eq:/pricing (mobile vs desktop conversion)
       4. Runs sources --filter url_path:eq:/signup (which sources convert best)
       5. Reports: "The /pricing → /signup step has a 72% drop-off rate.
          Mobile users drop off at 84% vs 61% desktop. Users from Google Ads
          convert at 2x the rate of organic. Recommendation: optimize pricing
          page for mobile, reallocate ad budget toward Google Ads."
```

---

## Customization

All agent configurations are plain text files in the repo. You can:

- **Edit agent instructions** in `.opencode/agents/`, `CLAUDE.md`, `.clinerules`, `.cursorrules`
- **Add new skills** in `.opencode/skills/` (OpenCode) or `.claude/commands/` (Claude Code)
- **Adjust permissions** — the OpenCode agent is read-only by default (no file editing, restricted bash). Modify the frontmatter in `site-analyst.md` to change this.
- **Create specialized agents** — e.g., an SEO-focused agent that only uses page and source commands, or a revenue agent that focuses on conversion and revenue metrics.

### Writing a custom OpenCode skill

Create `.opencode/skills/my-skill/SKILL.md`:

```markdown
---
description: One-line description of what this skill does
---

## Instructions for the skill

Step 1: ...
Step 2: ...
```

### Writing a custom Claude Code slash command

Create `.claude/commands/my-command.md`:

```markdown
Analyze $ARGUMENTS using the Mantecato CLI.

Steps:
1. Run `npx tsx src/cli/index.ts ...`
2. ...
```

Use `$ARGUMENTS` as a placeholder for user input.
