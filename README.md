# Beads Village

[![npm version](https://img.shields.io/npm/v/beads-village.svg)](https://www.npmjs.com/package/beads-village)
[![npm downloads](https://img.shields.io/npm/dm/beads-village.svg)](https://www.npmjs.com/package/beads-village)

Multi-agent MCP server for **task coordination** and **file locking** between AI agents.

Combines [Beads](https://github.com/steveyegge/beads) (issue tracking) + built-in Agent Mail (messaging) to enable multiple agents to work on the same codebase without conflicts.

> 💡 **Note:** Messaging is built-in. No external mail server required. Inspired by [MCP Agent Mail](https://github.com/Dicklesworthstone/mcp_agent_mail) concept.

## Use Cases

- **Multi-agent development**: Multiple AI agents working on different parts of a codebase
- **Task queue management**: Agents claim and complete tasks from a shared queue
- **File conflict prevention**: Lock files before editing to prevent merge conflicts
- **Cross-agent communication**: Send messages between agents for coordination

---

## Quick Start

### 1. Install Prerequisites

```bash
pip install beads    # Required: Beads CLI
node --version       # Required: Node.js 16+
```

### 2. Install Beads Village

```bash
npx beads-village    # Recommended
# or: npm install -g beads-village
# or: pip install beads-village
```

### 3. Configure Your IDE/Agent

<details>
<summary><strong>Claude Desktop</strong></summary>

Edit `claude_desktop_config.json`:
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`
- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`

```json
{
  "mcpServers": {
    "beads-village": {
      "command": "npx",
      "args": ["beads-village"]
    }
  }
}
```
</details>

<details>
<summary><strong>Claude Code (CLI)</strong></summary>

```bash
claude mcp add beads-village -- npx beads-village
```

Or create `.mcp.json` in project root:
```json
{
  "mcpServers": {
    "beads-village": {
      "command": "npx",
      "args": ["beads-village"]
    }
  }
}
```
</details>

<details>
<summary><strong>Cursor</strong></summary>

Create `.cursor/mcp.json`:
```json
{
  "mcpServers": {
    "beads-village": {
      "command": "npx",
      "args": ["beads-village"]
    }
  }
}
```
</details>

<details>
<summary><strong>GitHub Copilot (VS Code)</strong></summary>

Add to VS Code `settings.json`:
```json
{
  "github.copilot.chat.mcp.servers": {
    "beads-village": {
      "command": "npx",
      "args": ["beads-village"]
    }
  }
}
```
</details>

<details>
<summary><strong>More IDEs (OpenCode, Cline, Roo Code, Zed, Continue...)</strong></summary>

See **[📖 Full Setup Guide](docs/SETUP.md)** for complete configuration instructions for all supported IDEs and agents.

</details>

---

## Workflow

```
init() → claim() → reserve() → [work] → done() → RESTART
```

| Step | Description |
|------|-------------|
| `init()` | Join workspace (call FIRST) |
| `claim()` | Get next task |
| `reserve()` | Lock files before editing |
| `done()` | Complete task, release locks |
| RESTART | New session for next task |

📖 **[Detailed Workflow Guide](docs/WORKFLOW.md)** - Patterns, examples, best practices

---

## Documentation Guide

Choose the right documentation for your AI model:

| Document | Best For | Size |
|----------|----------|------|
| **[AGENTS-LITE.md](AGENTS-LITE.md)** | High-capability models (Claude 3.5+, GPT-4+, Gemini Pro) with limited context | ~1.5KB |
| **[AGENTS.md](AGENTS.md)** | All models, comprehensive reference with examples | ~16KB |
| **[docs/SETUP.md](docs/SETUP.md)** | Setup instructions for all IDEs/agents | ~6KB |
| **[docs/WORKFLOW.md](docs/WORKFLOW.md)** | Workflow patterns and best practices | ~5KB |

### When to Use Which

```
┌─────────────────────────────────────────────────────────────┐
│                    Model Capability                          │
├─────────────────────────────────────────────────────────────┤
│  HIGH (Claude 3.5+, GPT-4o, Gemini 1.5 Pro)                 │
│  └─→ Use AGENTS-LITE.md (minimal tokens, maximum signal)    │
│                                                              │
│  MEDIUM (Claude 3 Haiku, GPT-4o-mini, smaller models)       │
│  └─→ Use AGENTS.md (detailed examples needed)               │
│                                                              │
│  LARGE CONTEXT (128K+ tokens available)                      │
│  └─→ Use AGENTS.md (comprehensive reference)                │
│                                                              │
│  LIMITED CONTEXT (<32K tokens)                               │
│  └─→ Use AGENTS-LITE.md (save tokens for code)              │
└─────────────────────────────────────────────────────────────┘
```

---

## Tools Overview

| Category | Tools | Description |
|----------|-------|-------------|
| **Lifecycle** | `init`, `claim`, `done` | Task workflow |
| **Issues** | `add`, `assign`, `ls`, `show` | Task management (`ls` supports `status="ready"`) |
| **Files** | `reserve`, `release`, `reservations` | Conflict prevention |
| **Messages** | `msg`, `inbox` | Agent communication (`msg` with `global=true` for broadcast) |
| **Status** | `status` | Team visibility (use `include_agents=true` for discovery) |
| **Maintenance** | `sync`, `cleanup`, `doctor` | Housekeeping |
| **Graph Analysis** | `bv_insights`, `bv_plan`, `bv_priority`, `bv_diff` | Requires optional `bv` binary |
| **Dashboard** | `village_tui` | Launch visual TUI dashboard |

---

## Beads Viewer Integration (Optional)

The dashboard works **without `bv`**. Install `bv` only if you need advanced graph analysis.

### Dashboard Features (Built-in, no bv needed)

| Panel | Description |
|-------|-------------|
| **Teams** | Click to filter agents by team |
| **Agents** | Shows online/offline status, current task |
| **Tasks Board** | Kanban view (Open/In Progress/Blocked/Closed) |
| **Task Detail** | Click any task for full details + activity |
| **File Locks** | Active file reservations with TTL |
| **Messages** | Recent broadcasts and done notifications |
| **Filter Recipes** | Quick filters: All, Actionable, Blocked, High Impact, Stale |

### Graph Insights (Requires `bv`)

| Feature | Without bv | With bv |
|---------|------------|---------|
| Keystones, Bottlenecks | ❌ | ✅ |
| PageRank, Betweenness | ❌ | ✅ |
| Cycle Detection | ❌ | ✅ |
| Parallel Execution Plan | ❌ | ✅ |

### Launch Dashboard

```bash
# Run dashboard for current directory
python -m beads_village.dashboard

# Run dashboard for specific workspace
python -m beads_village.dashboard "C:\path\to\workspace"

# Auto-start when leader inits
init(leader=True, start_tui=True)
```

### Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `1-8` | Focus different panels |
| `Tab` | Navigate between panels |
| `j/k` | Scroll up/down |
| `r` | Refresh data |
| `t` | Toggle dark/light theme |
| `q` | Quit |

### Alternative: bv Binary (Go)

For advanced graph analysis, install the optional `bv` binary:

### Installation

```bash
# Option 1: Go install (recommended)
go install github.com/Dicklesworthstone/beads_viewer/cmd/bv@latest

# Option 2: Download binary from releases
# https://github.com/Dicklesworthstone/beads_viewer/releases
```

### New Tools (when bv available)

| Tool | Description |
|------|-------------|
| `bv_insights` | Graph analysis (PageRank, Betweenness, bottlenecks, cycles) |
| `bv_plan` | Parallel execution tracks for multi-agent work |
| `bv_priority` | Priority recommendations based on graph metrics |
| `bv_diff` | Compare changes between git revisions |

> **Note:** `bv_tui` and `bv_status` have been merged into `village_tui` and `status(include_bv=true)`

### Usage Examples

```python
# Get graph insights for AI decision making
bv_insights()

# Get priority recommendations
bv_priority(limit=5)

# Launch unified TUI dashboard
village_tui()

# Auto-start TUI when leader inits
init(leader=True, start_tui=True)

# Check bv availability via status
status(include_bv=True)
```

### Architecture with bv

```
┌─────────────────────────────────────────────────────────────┐
│                     MCP Beads Village                        │
├─────────────────────────────────────────────────────────────┤
│  Core Tools              │  bv Tools (optional)             │
│  ──────────              │  ─────────────────               │
│  init, claim, done       │  bv_insights (graph metrics)     │
│  reserve, release        │  bv_plan (execution tracks)      │
│  msg, inbox, broadcast   │  bv_priority (recommendations)   │
│  ls, show, add           │  bv_tui (dashboard)              │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                     bv Binary (Go)                           │
│  - 9 Graph algorithms: PageRank, Betweenness, HITS, etc.    │
│  - Robot mode: Pre-computed JSON for AI agents              │
│  - TUI mode: Kanban, graph viz, insights dashboard          │
└─────────────────────────────────────────────────────────────┘
```

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Shared via Git                          │
│  .beads/        .mail/           .reservations/             │
│  (tasks)        (messages)       (file locks)               │
└─────────────────────────────────────────────────────────────┘
        ▲               ▲                  ▲
        │               │                  │
   ┌────┴────┐    ┌─────┴────┐      ┌──────┴─────┐
   │ Agent 1 │    │ Agent 2  │      │  Agent 3   │
   │ (FE)    │    │ (BE)     │      │  (Mobile)  │
   └─────────┘    └──────────┘      └────────────┘
```

---

## Configuration Summary

| Client | Config Location | Config Key |
|--------|-----------------|------------|
| Claude Desktop | `claude_desktop_config.json` | `mcpServers` |
| Claude Code | `.mcp.json` | `mcpServers` |
| Cursor | `.cursor/mcp.json` | `mcpServers` |
| GitHub Copilot | `settings.json` | `github.copilot.chat.mcp.servers` |
| Amp Code | `.amp/settings.json` | `amp.mcpServers` |
| Kilo Code | `settings.json` | `kilocode.mcpServers` |
| Windsurf | `~/.windsurf/mcp.json` | `mcpServers` |
| OpenCode | `opencode.json` | `mcpServers` |
| Cline | Cline settings | `mcpServers` |
| Roo Code | Roo settings | `mcpServers` |
| Zed | Zed settings | `context_servers` |
| Continue | `config.yaml` | `mcpServers` |

📖 **[Complete Setup Instructions](docs/SETUP.md)**

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `BEADS_AGENT` | `agent-{pid}` | Agent name |
| `BEADS_WS` | Current dir | Workspace path |
| `BEADS_TEAM` | `default` | Team name |
| `BEADS_USE_DAEMON` | `1` | Use daemon if available |

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| `bd: command not found` | `pip install beads` |
| MCP server not starting | Check Node.js 16+ |
| Tools not appearing | Restart IDE after config |

```bash
# Verify installation
bd --version
node --version
npx beads-village --help
```

---

## Links

- [Beads CLI](https://github.com/steveyegge/beads) - Git-native issue tracker
- [Beads Best Practices](https://steve-yegge.medium.com/beads-best-practices-2db636b9760c)
- [MCP Agent Mail](https://github.com/Dicklesworthstone/mcp_agent_mail) - Inspiration for messaging concept
- [Model Context Protocol](https://modelcontextprotocol.io/)

---

## Changelog

<details>
<summary><strong>v1.3.2</strong> - Dashboard Launch Fix (Windows)</summary>

**Bug Fixes:**
- Fixed `village_tui` tool not launching dashboard correctly on Windows
- Improved command escaping for paths with spaces

</details>

<details>
<summary><strong>v1.3.1</strong> - CLI Flag Fix</summary>

**Bug Fixes:**
- Fixed `--tag` flag error in `add` tool - now uses correct `--labels` flag for `bd create`
- Fixed `--tag` flag error in `assign` tool - now uses correct `--add-label` flag for `bd update`
- Fixed daemon fallback detection for `--labels` and `--add-label` flags

</details>

<details>
<summary><strong>v1.3.0</strong> - Tool Consolidation & Dashboard Enhancements</summary>

**Tool Consolidation (26 → 21 tools):**
- `broadcast` merged into `msg(global=true, to="all")`
- `discover` merged into `status(include_agents=true)`
- `ready` merged into `ls(status="ready")`
- `bv_status` merged into `status(include_bv=true)`
- `bv_tui` merged into `village_tui`

**Dashboard Enhancements:**
- Added **Graph Insights** panel (Keystones, Influencers, Cycles)
- Added **Filter Recipes** panel (All, Actionable, Blocked, High Impact, Stale)
- Dashboard works without `bv` binary (graph insights require bv)
- Improved scrollbar and alignment
- Status icons for issues (○ open, ◐ in_progress, ✕ blocked, ✓ closed)
</details>

<details>
<summary><strong>v1.2.0</strong> - Textual Dashboard & Optimizations</summary>

- **Built-in Textual Dashboard** - `python -m beads_village.dashboard` for monitoring
- **Auto-start TUI** - `init(leader=true, start_tui=true)` launches dashboard automatically
- **Stateless team discovery** - Dashboard reads agents from `.mail` messages (no registry file needed)
- **Cross-workspace task lookup** - Task details fetched from correct workspace
- **I/O optimization** - Mail messages cached, reducing disk reads by 80%
- **UX improvements** - Click navigation: Teams → Agents → Tasks → Task Detail
</details>

<details>
<summary><strong>v1.1.2</strong> - Role-Based Task Assignment</summary>

- **Leader/Worker agents** - `init(leader=true)` for leaders, `init(role="fe")` for workers
- **Role tags on tasks** - `add(tags=["fe"])` to assign tasks to specific roles
- **Auto-filtered claim** - Workers only see tasks matching their role
- **assign() tool** - Leaders can explicitly assign tasks to roles
</details>

<details>
<summary><strong>v1.1.1</strong> - Token Optimization</summary>

- **Tool descriptions reduced by ~50%**
- **Instructions reduced by ~80%**
- **Added AGENTS-LITE.md** - 1.3KB quick reference
</details>

---

## License

MIT
