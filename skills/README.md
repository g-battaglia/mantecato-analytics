# Mantecato agent skills

These skills follow the [Agent Skills format](https://agentskills.io/specification)
and can be installed with the [skills.sh CLI](https://skills.sh/). Each directory
contains a self-contained `SKILL.md`. There are no wrappers or executable scripts.

| Skill | When to use it |
|---|---|
| [mantecato-cli](mantecato-cli/SKILL.md) | Query analytics with the installed `mantecato` command |
| [mantecato-install](mantecato-install/SKILL.md) | Install or upgrade the server, connect a tracker, or install a client |
| [mantecato-mcp](mantecato-mcp/SKILL.md) | Configure a stdio MCP host and use the native read-only tools |

Installing a skill adds instructions to an agent. It does not install the Python
packages, configure credentials, create infrastructure or start a server.

## Install from GitHub

These skills are on `develop`. From the project where the agent should use them,
select that branch explicitly:

```bash
npx skills add https://github.com/g-battaglia/mantecato-analytics/tree/develop --list
npx skills add https://github.com/g-battaglia/mantecato-analytics/tree/develop --skill mantecato-cli
```

Choose the other skills when needed:

```bash
npx skills add https://github.com/g-battaglia/mantecato-analytics/tree/develop --skill mantecato-install
npx skills add https://github.com/g-battaglia/mantecato-analytics/tree/develop --skill mantecato-mcp
```

After these files are merged into the default branch, the shorter source
`g-battaglia/mantecato-analytics` works too. It does not select `develop` implicitly.

Add `-g` for a user-wide installation, or `--agent <agent-name>` to select a specific
supported agent. Without `-g`, installation is scoped to the current project.
The root `skills/` directory in this repository is the distribution source, not a
user's global agent configuration directory.

## Test or install from a local checkout

Before the changes are pushed, use the checkout's absolute path:

```bash
npx skills add /absolute/path/to/mantecato-analytics --list
npx skills add /absolute/path/to/mantecato-analytics --skill mantecato-cli
```

`--list` discovers skills without installing them. Remote installation reads the
GitHub repository, not uncommitted local files. Compatibility with the CLI does
not mean the skills are already listed or ranked on skills.sh.

## Maintenance

Keep names equal to their directory names and include `name` and `description`
in YAML frontmatter. Each skill must work when installed alone; avoid dependencies
on files outside its directory. Verify commands against the corresponding client
and deployment configuration. Do not add secrets, production website defaults or
machine-specific paths.

All skills use the repository's Apache-2.0 license.
