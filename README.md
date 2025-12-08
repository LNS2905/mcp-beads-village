# Beads Village

Multi-agent MCP server for **task coordination** and **file locking** between AI agents.

Combines [Beads](https://github.com/steveyegge/beads) (issue tracking) + Agent Mail (messaging) to enable multiple agents to work on the same codebase without conflicts.

## Use Cases

- **Multi-agent development**: Multiple AI agents working on different parts of a codebase
- **Task queue management**: Agents claim and complete tasks from a shared queue
- **File conflict prevention**: Lock files before editing to prevent merge conflicts
- **Cross-agent communication**: Send messages between agents for coordination

## Installation

```bash
# Option 1: npx (recommended)
npx beads-village

# Option 2: npm global
npm install -g beads-village

# Option 3: pip
pip install beads-village
```

**Requirements**: Python 3.8+, Node.js 16+ (for npx)

## Configuration

### Claude Desktop

`%APPDATA%\Claude\claude_desktop_config.json` (Windows) or `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS)

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

### VS Code / Amp

`.vscode/settings.json`

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

### Cursor

Settings > MCP > Add Server with same config as above.

## How It Works

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

All agents share task queue, messages, and file locks through Git-synced directories.

## Workflow

```
init() → claim() → reserve() → [work] → done() → RESTART
```

1. **init()** - Join workspace
2. **claim()** - Get next available task
3. **reserve()** - Lock files before editing
4. **[work]** - Do the actual work
5. **done()** - Complete task, release locks
6. **RESTART** - Start new session (recommended)

### Example Session

```python
init()
# {"ok":1,"agent":"agent-1","ws":"/project"}

claim()
# {"id":"bd-42","t":"Add OAuth login","p":1,"s":"in_progress"}

reserve(paths=["src/auth.py"])
# {"granted":["src/auth.py"],"conflicts":[]}

# ... do work ...

done(id="bd-42", msg="OAuth implemented")
# {"ok":1,"done":1,"hint":"restart session"}
```

## Best Practices

| Practice | Why |
|----------|-----|
| **One task per session** | Restart after `done()` for clean state |
| **Always reserve before editing** | Prevents merge conflicts |
| **File issues for side-discoveries** | `add(title="...", typ="bug")` immediately |
| **Keep <200 open issues** | Run `cleanup(days=2)` regularly |
| **Use short TTLs** | Don't block others (default 10 min) |

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `bd CLI not found` | `go install github.com/beads-project/beads/cmd/bd@latest` |
| Stale reservations | Run `init()` to cleanup expired |
| >200 open issues | Run `cleanup(days=2)` |

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `BEADS_AGENT` | `agent-{pid}` | Agent name |
| `BEADS_WS` | Current dir | Workspace path |

## Links

- [Beads CLI](https://github.com/steveyegge/beads)
- [Best Practices Article](https://steve-yegge.medium.com/beads-best-practices-2db636b9760c)

## License

MIT
