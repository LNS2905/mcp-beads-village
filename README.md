# Beads Village

Multi-agent MCP server combining **Beads** (issue tracking) + **Agent Mail** (coordination).

```
npx beads-village
```

## Quick Start

### 1. Add to MCP config

**Claude Desktop**

File: 
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

**Cursor**

File: Settings > MCP > Add Server

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

**VS Code / Amp**

File: `.vscode/settings.json` or User Settings

```json
{
  "amp.mcpServers": {
    "beads-village": {
      "command": "npx",
      "args": ["beads-village"]
    }
  }
}
```

**Claude Code CLI**

```bash
claude mcp add --transport stdio beads-village --scope user -- npx beads-village
```

### 2. Use in agent

```
Agent: init()
Agent: claim()
Agent: reserve(paths=["src/auth.py"])
Agent: [do work...]
Agent: done(id="bd-42", msg="implemented auth")
```

---

## Workflow

```
+-------+     +-------+     +---------+     +------+     +------+
| init  | --> | claim | --> | reserve | --> | work | --> | done |
+-------+     +-------+     +---------+     +------+     +------+
                                                            |
                                                            v
                                                      [ RESTART ]
```

**Best Practice**: 1 task = 1 session. Restart agent after `done()`.

---

## Tools

### Core (4)

| Tool | Description | Example |
|------|-------------|---------|
| `init` | Join workspace | `init()` or `init(ws="/path")` |
| `claim` | Get next task | `claim()` |
| `done` | Complete task | `done(id="bd-42", msg="fixed bug")` |
| `add` | Create issue | `add(title="Fix login", typ="bug", pri=1)` |

### Query (3)

| Tool | Description | Example |
|------|-------------|---------|
| `ls` | List issues | `ls(status="open", limit=10)` |
| `ready` | Unblocked tasks | `ready(limit=5)` |
| `show` | Issue details | `show(id="bd-42")` |

### File Locks (3)

| Tool | Description | Example |
|------|-------------|---------|
| `reserve` | Lock files | `reserve(paths=["src/api.py"], ttl=600)` |
| `release` | Unlock files | `release()` |
| `reservations` | View locks | `reservations()` |

### Messaging (3)

| Tool | Description | Example |
|------|-------------|---------|
| `msg` | Send message | `msg(subj="help", body="stuck on X")` |
| `inbox` | Read messages | `inbox(n=5, unread=true)` |
| `status` | Workspace info | `status()` |

### Maintenance (3)

| Tool | Description | Example |
|------|-------------|---------|
| `sync` | Git sync | `sync()` |
| `cleanup` | Delete old issues | `cleanup(days=2)` |
| `doctor` | Fix database | `doctor()` |

---

## Multi-Agent Architecture

```
  Agent 1              Agent 2              Agent 3
  (Frontend)           (Backend)            (Mobile)
      |                    |                    |
      v                    v                    v
  worktree-1           worktree-2           worktree-3
      |                    |                    |
      +--------------------+--------------------+
                           |
                           v
              +---------------------------+
              |     Shared via Git        |
              |  .beads/   (tasks)        |
              |  .mail/    (messages)     |
              |  .reservations/ (locks)   |
              +---------------------------+
```

---

## Response Format

Token-optimized short field names:

| Field | Meaning |
|-------|---------|
| `id` | Issue ID |
| `t` | Title |
| `p` | Priority (0-4) |
| `s` | Status |
| `f` | From (sender) |
| `b` | Body |
| `ts` | Timestamp |

**Priority levels**: 0=critical, 1=high, 2=normal, 3=low, 4=backlog

---

## Installation Options

```bash
# Option 1: npx (recommended)
npx beads-village

# Option 2: npm global
npm install -g beads-village

# Option 3: pip
pip install beads-village
```

**Requirements**:
- Python 3.8+
- Node.js 16+ (for npx)
- [Beads CLI](https://github.com/beads-project/beads) (optional, for issue tracking)

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `BEADS_AGENT` | `agent-{pid}` | Agent name |
| `BEADS_WS` | Current dir | Workspace path |

---

## Example Session

```python
# Initialize
init()
# {"ok":1,"agent":"agent-1","ws":"/project"}

# Claim a task
claim()
# {"id":"bd-42","t":"Add OAuth login","p":1,"s":"in_progress"}

# Reserve files before editing
reserve(paths=["src/auth.py", "src/oauth.py"])
# {"granted":["src/auth.py","src/oauth.py"],"conflicts":[]}

# Found related work? Create issue
add(title="Add refresh token logic", typ="task", pri=2)
# {"id":"bd-43","t":"Add refresh token logic","p":2}

# Complete task
done(id="bd-42", msg="OAuth login implemented")
# {"ok":1,"done":1,"hint":"restart session"}
```

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `bd CLI not found` | `go install github.com/beads-project/beads/cmd/bd@latest` |
| `Python not found` | Install Python 3.8+ |
| Stale reservations | Run `init()` to cleanup expired |
| >200 open issues | Run `cleanup(days=2)` |

---

## Performance

| Operation | Speed |
|-----------|-------|
| Path normalization | 0.01ms |
| Reserve file | 2ms |
| Send message | 1ms |
| Read inbox | 22ms |
| MCP protocol | <0.01ms |

---

## Cross-Platform

| Platform | Status |
|----------|--------|
| Windows | Supported |
| macOS | Supported |
| Linux | Supported |

All paths use forward slashes (`/`) in responses.

---

## License

MIT

## Links

- [Beads CLI](https://github.com/beads-project/beads)
- [Best Practices](https://steve-yegge.medium.com/beads-best-practices-2db636b9760c)
