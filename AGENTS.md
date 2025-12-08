# AGENTS.md - Beads Village

## Multi-Agent Issue Tracking & Coordination

This project uses **Beads Village** (Beads + Agent Mail) for task management.

### Quick Start

**BEFORE starting work**, initialize:

```
mcp__beads_village__init
```

---

## Workflow

### Standard Flow (1 task per session)

```
1. claim     → Get next ready task (auto-syncs, notifies others)
2. reserve   → Claim files you'll edit (prevents conflicts)
3. [work]    → Do the actual work
4. add       → File issues for anything >2 min found during work
5. release   → Release file reservations (or skip - done() does this)
6. done      → Complete task (syncs, notifies, releases all)
7. RESTART   → Start new session for best performance
```

### Multi-Agent Coordination

```
# Before editing files, reserve them:
reserve(paths=["src/api.py", "src/models.py"], reason="bd-123")

# Check if files are available:
reservations()

# When done, release (or let done() handle it):
release()
```

---

## Quick Reference

### Core Workflow

| Action | Tool | Example |
|--------|------|---------|
| Initialize | `init` | `init()` |
| Get task | `claim` | `claim()` → auto picks highest priority ready |
| Complete | `done` | `done(id="bd-123", msg="implemented")` |
| Create issue | `add` | `add(title="Fix bug", typ="bug", pri=1)` |

### Issue Queries

| Action | Tool | Example |
|--------|------|---------|
| List issues | `ls` | `ls(status="open", limit=10)` |
| Ready issues | `ready` | `ready(limit=5)` |
| Show details | `show` | `show(id="bd-123")` |

### Maintenance (run regularly!)

| Action | Tool | When |
|--------|------|------|
| Cleanup old | `cleanup` | Every few days |
| Health check | `doctor` | Weekly or after issues |
| Force sync | `sync` | After major changes |

### File Reservations

| Action | Tool | Example |
|--------|------|---------|
| Reserve files | `reserve` | `reserve(paths=["src/*.py"], ttl=600)` |
| Release files | `release` | `release()` or `release(paths=["src/x.py"])` |
| View reservations | `reservations` | `reservations()` |

### Messaging

| Action | Tool | Example |
|--------|------|---------|
| Send message | `msg` | `msg(subj="help", body="stuck on X", to="all")` |
| Check inbox | `inbox` | `inbox(n=5, unread=True)` |
| Village status | `status` | `status()` |

---

## Response Fields (Token-optimized)

| Field | Meaning |
|-------|---------|
| `id` | Issue ID |
| `t` | Title |
| `p` | Priority (0=critical, 1=high, 2=medium, 3=low, 4=backlog) |
| `s` | Status (open, in_progress, blocked, closed) |
| `f` | From (message sender) |
| `b` | Body |
| `ts` | Timestamp |
| `imp` | Importance (normal, high, urgent) |

---

## Best Practices

### From Steve Yegge's Article

1. **One task per session** - Restart agent after `done()`
2. **File issues for anything >2 minutes** - Don't lose track
3. **Keep <200 open issues** - Run `cleanup` every few days
4. **Plan outside Beads** - Use external tool, then import as epics
5. **Agents claim work** - Use `claim`, don't pre-assign
6. **Run `doctor` regularly** - Fixes common issues

### Multi-Agent Tips

1. **Always reserve before editing** - Prevents merge conflicts
2. **Use short TTLs** - Don't block others (default 10 min)
3. **Check inbox periodically** - Other agents may need help
4. **Sync after major work** - Keep everyone updated

---

## Issue Types

| Type | Use For |
|------|---------|
| `task` | General work item (default) |
| `bug` | Defect to fix |
| `feature` | New functionality |
| `epic` | Large work with sub-issues |
| `chore` | Maintenance, cleanup |

---

## Priority Levels

| Priority | Meaning | When to Use |
|----------|---------|-------------|
| 0 | Critical | Production down, security issue |
| 1 | High | Blocking other work |
| 2 | Medium | Normal priority (default) |
| 3 | Low | Nice to have |
| 4 | Backlog | Future consideration |

---

## Multi-Workspace Setup (BE/FE/Mobile)

Each codebase has its **own isolated workspace**. Agents can switch between workspaces.

### Creating a Workspace

When user asks to "create a beads workspace", run:

```
init(ws="/absolute/path/to/codebase")
```

**IMPORTANT**: After creating, report the workspace path to user:

```
✅ Beads workspace created!
📁 Workspace: C:\Projects\my-app-be
🤖 Agent: agent-be-1

To assign another agent to this workspace, use:
init(ws="C:\Projects\my-app-be")
```

### Switching Workspaces

To view tasks from another workspace (e.g., see what BE team did):

```
init(ws="C:\Projects\my-app-be")  # Switch to BE workspace
ls()                              # See BE tasks
```

Then switch back to your workspace:

```
init(ws="C:\Projects\my-app-fe")  # Switch back to FE
```

### Example: Cross-Team Workflow

```
=== Agent BE ===
User: "Create a beads workspace for this BE project"
Agent: 
  → init()
  → Response: {"ok":1,"agent":"agent-be","ws":"C:\\Projects\\my-app-be"}
  → "✅ Workspace created at: C:\Projects\my-app-be"

User: "Create tasks for auth APIs"
Agent:
  → add(title="POST /auth/login", typ="feature", pri=1)
  → add(title="POST /auth/register", typ="feature", pri=1)
  → add(title="POST /auth/refresh-token", typ="feature", pri=2)

=== Agent FE ===
User: "Join the BE workspace at C:\Projects\my-app-be to see their tasks"
Agent:
  → init(ws="C:\\Projects\\my-app-be")
  → ls()
  → Shows: [login API ✓, register API, refresh-token API]

User: "Now create FE workspace and add tasks based on BE APIs"
Agent:
  → init(ws="C:\\Projects\\my-app-fe")
  → "✅ Workspace created at: C:\Projects\my-app-fe"
  → add(title="Login form (uses /auth/login)", typ="feature", pri=1)
  → add(title="Register form (uses /auth/register)", typ="feature", pri=1)
```

---

## Example Session

```
Agent: I'll start by initializing the beads village.
→ init()
{"ok":1,"agent":"amp-agent-1","ws":"C:\\project"}

Agent: Let me claim the next available task.
→ claim()
{"id":"bd-42","t":"Implement user authentication","p":1,"s":"in_progress"}

Agent: I'll reserve the files I need to edit.
→ reserve(paths=["src/auth.py", "src/user.py"], reason="bd-42")
{"granted":["src/auth.py","src/user.py"],"conflicts":[],"expires":"..."}

Agent: While working, I found we also need password reset.
→ add(title="Add password reset flow", typ="feature", pri=2)
{"id":"bd-43","t":"Add password reset flow","p":2,"typ":"feature"}

Agent: Authentication is complete. Marking done.
→ done(id="bd-42", msg="Implemented JWT auth with refresh tokens")
{"ok":1,"done":1,"hint":"restart session for best performance"}

Agent: Task complete. Restarting session as recommended.
```
