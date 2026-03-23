# AI Agent Setup

Mantecato works with any AI coding agent that can run terminal commands or connect via MCP. This guide covers setup for each supported platform.

## Before You Start

1. Mantecato installed and running (see the [README](../README.md#get-started))
2. An API key generated from the web UI (**Settings > API Keys**)
3. Your `DATABASE_URL` and `MANTECATO_API_KEY` ready

## How It Works

There are two ways an AI agent can talk to Mantecato:

**CLI** — The agent runs shell commands like `npx tsx src/cli/index.ts stats --site mysite.com` and reads the output. Works with any agent that has terminal access. No extra configuration needed — just open the project folder.

**MCP** — The agent calls structured tools directly via [Model Context Protocol](https://modelcontextprotocol.io/). Returns typed JSON, no output parsing. Requires adding Mantecato to your editor's MCP configuration.

Both methods query the same data and return the same results. Most agents work great with CLI alone. MCP is optional and adds tighter integration.

---

## Platform Setup

### OpenCode

**Included in the repo:**
- `.opencode/agents/site-analyst.md` — a dedicated analytics agent
- `.opencode/skills/traffic-report/SKILL.md` — traffic report workflow
- `.opencode/skills/content-audit/SKILL.md` — content audit workflow
- `.opencode/skills/funnel-analysis/SKILL.md` — funnel analysis workflow

**How to use:**

```bash
cd /path/to/mantecato
opencode
```

Select **site-analyst** from the agent picker, then ask questions:

```
"Analyze kerykeion.net traffic for the last 30 days"
"Which pages have the highest bounce rate?"
"Compare this month vs last month for all my sites"
```

The skills are loaded automatically — you can reference them from any agent:

```
"Use the traffic-report skill to analyze kerykeion.net"
"Run a content audit for mysite.com for the last 90 days"
```

**Add MCP (optional):** Add to `~/.config/opencode/config.json`:

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

### Claude Code

**Included in the repo:**
- `CLAUDE.md` — full CLI reference and analysis methodology (loaded automatically)
- `.claude/commands/traffic-report.md` — `/project:traffic-report` slash command
- `.claude/commands/content-audit.md` — `/project:content-audit` slash command
- `.claude/commands/funnel-analysis.md` — `/project:funnel-analysis` slash command

**How to use:**

```bash
cd /path/to/mantecato
claude
```

Ask questions directly or use slash commands:

```
"Analyze traffic for kerykeion.net over the last 30 days"
"Show me the bounce rate by device type for US visitors"

/project:traffic-report kerykeion.net 30d
/project:content-audit kerykeion.net 90d
/project:funnel-analysis kerykeion.net /,/pricing,/signup
```

**Add MCP (optional):**

```bash
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

### Claude Desktop

Claude Desktop supports MCP only (no terminal access).

Add to your config file:
- **macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows:** `%APPDATA%\Claude\claude_desktop_config.json`

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

Restart Claude Desktop, then ask:

```
"List all my tracked sites"
"Show me the top pages for kerykeion.net in the last 7 days"
"Run a funnel analysis: homepage → docs → examples"
```

---

### OpenClaw

**Included in the repo:**
- `.openclaw/skills/traffic-report/SKILL.md` — traffic report workflow
- `.openclaw/skills/content-audit/SKILL.md` — content audit workflow
- `.openclaw/skills/funnel-analysis/SKILL.md` — funnel analysis workflow

**How to use:**

Copy the skills to your OpenClaw skills directory:

```bash
cp -r /path/to/mantecato/.openclaw/skills/* ~/.openclaw/skills/
```

Or add the project's skill directory to your `~/.openclaw/openclaw.json`:

```json
{
  "skills": {
    "load": {
      "extraDirs": ["/path/to/mantecato/.openclaw/skills"]
    }
  }
}
```

Then ask OpenClaw questions or invoke skills directly:

```
"Analyze kerykeion.net traffic for the last 30 days"
"Run a content audit for mysite.com"
"Analyze the signup funnel: /, /pricing, /signup, /welcome"
```

**Add MCP (optional):** Add to `~/.openclaw/openclaw.json`:

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

### Cline

**Included in the repo:** `.clinerules` with CLI reference and analysis methodology.

Open the project in VS Code with Cline installed. Ask analytics questions directly.

**Add MCP (optional):** In Cline settings, add an MCP server with the [standard MCP config](#mcp-configuration-reference).

---

### Cursor

**Included in the repo:** `.cursorrules` with CLI reference and analysis methodology.

Open the project in Cursor. Ask analytics questions in Composer or Chat.

**Add MCP (optional):** Go to **Settings > Features > MCP Servers** and add the [standard MCP config](#mcp-configuration-reference).

---

## MCP Configuration Reference

All MCP-compatible tools use the same configuration. Replace the paths and credentials with your own:

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

### Docker alternative

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

---

## Example Workflows

### Traffic report

```
You:   "Give me a full traffic report for kerykeion.net, last 30 days"

Agent: 1. Gets overall metrics and period-over-period comparison
       2. Finds top pages, traffic sources, channels
       3. Checks device and geographic breakdown
       4. Cross-references bounce rates by source and device
       5. Delivers a structured report with findings and recommendations
```

### Diagnosing a traffic drop

```
You:   "Traffic dropped this week. What happened?"

Agent: 1. Confirms the drop with a period comparison
       2. Finds the exact day it started via time series
       3. Identifies which pages and sources dropped
       4. Reports: "Organic traffic to /blog/popular-post dropped 60% on
          Tuesday. The page's bounce rate spiked from 35% to 78%."
```

### Funnel optimization

```
You:   "Analyze the signup funnel and tell me where we're losing people"

Agent: 1. Runs funnel analysis for /, /pricing, /signup, /welcome
       2. Checks mobile vs desktop conversion at each step
       3. Compares traffic sources by conversion rate
       4. Reports: "The /pricing → /signup step has a 72% drop-off.
          Mobile users drop at 84% vs 61% desktop. Google Ads converts
          at 2x organic. Optimize pricing page for mobile."
```

---

## Customization

All agent configurations are plain text files you can edit:

- **Agent instructions:** `.opencode/agents/`, `CLAUDE.md`, `.clinerules`, `.cursorrules`
- **Skills and commands:** `.opencode/skills/` (OpenCode), `.claude/commands/` (Claude Code)
- **Permissions:** The OpenCode site-analyst agent is read-only by default. Edit the frontmatter in `site-analyst.md` to change this.

### Create a custom OpenCode skill

Add a file at `.opencode/skills/my-skill/SKILL.md`:

```markdown
---
description: One-line description of what this skill does
---

## Instructions

Step 1: ...
Step 2: ...
```

### Create a custom Claude Code slash command

Add a file at `.claude/commands/my-command.md`:

```markdown
Analyze $ARGUMENTS using the Mantecato CLI.

Steps:
1. Run `npx tsx src/cli/index.ts ...`
2. ...
```

Use `$ARGUMENTS` as a placeholder for user input.
