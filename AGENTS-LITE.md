# Beads Village MCP - Quick Reference

## Workflow

### Leader Agent
```
init(team, leader=true, start_tui=true) → add(tags=["role"]) → assign(id,role) → monitor
```

### Worker Agent
```
init(team, role="fe/be/mobile") → claim() → reserve(paths) → work → done(id,msg) → restart
```

## Dashboard

```bash
python -m beads_village.dashboard [workspace]   # Manual launch
init(leader=true, start_tui=true)              # Auto-launch for leader
village_tui()                                  # Launch from MCP
```

## Core Tools (21 total)

| Tool | Use | Key Args |
|------|-----|----------|
| `init` | Join workspace (FIRST) | `ws`, `team`, `role`, `leader`, `start_tui` |
| `claim` | Get next task (filtered by role) | - |
| `done` | Complete task | `id`, `msg` |
| `add` | Create issue | `title`, `desc`, `typ`, `pri`, `tags` |
| `assign` | Assign to role (leader only) | `id`, `role` |

## Query Tools

| Tool | Use |
|------|-----|
| `ls` | List issues (status=open/closed/ready/all) |
| `show` | Get issue details (id) |

## File Locking

| Tool | Use |
|------|-----|
| `reserve` | Lock files (paths[], ttl, reason) |
| `release` | Unlock files |
| `reservations` | Check locks |

## Messaging

| Tool | Use |
|------|-----|
| `msg` | Send message (subj, to, global=true for broadcast) |
| `inbox` | Get messages |

## Status & Discovery

| Tool | Use |
|------|-----|
| `status` | Workspace overview (include_agents=true for discovery, include_bv=true for bv status) |

## Maintenance

| Tool | Use |
|------|-----|
| `sync` | Git sync |
| `cleanup` | Remove old issues (days) |
| `doctor` | Fix database |

## Dashboard & Graph Tools

| Tool | Use |
|------|-----|
| `village_tui` | Launch unified dashboard (works without bv) |
| `bv_insights` | Graph analysis (requires bv) |
| `bv_plan` | Parallel execution tracks (requires bv) |
| `bv_priority` | Priority recommendations (requires bv) |
| `bv_diff` | Compare git revisions (requires bv) |

## Response Fields

`id`=ID, `t`=title, `p`=priority(0-4), `s`=status, `f`=from, `b`=body, `tags`=role tags

## Priority

0=critical, 1=high, 2=normal, 3=low, 4=backlog

## Types

task, bug, feature, epic, chore

## Role Tags

`fe`=frontend, `be`=backend, `mobile`, `devops`, `qa`

## Rules

1. Always `init()` first
2. Leader: `init(leader=true)` to assign tasks
3. Worker: `init(role="fe/be/...")` to auto-filter tasks
4. Always `reserve()` before editing files
5. Create issues for work >2min
6. Restart session after `done()`

## Tool Consolidation (v1.3.0)

| Old Tool | New Usage |
|----------|-----------|
| `broadcast` | `msg(subj, body, global=true, to="all")` |
| `discover` | `status(include_agents=true)` |
| `ready` | `ls(status="ready")` |
| `bv_status` | `status(include_bv=true)` |
| `bv_tui` | `village_tui` |

## Example: Multi-Agent Setup

```python
# Leader creates tasks
init(team="proj", leader=true, start_tui=true)
add(title="Login API", tags=["be"])
add(title="Login form", tags=["fe"])

# BE agent claims BE tasks
init(team="proj", role="be")
claim()  # Gets "Login API"

# FE agent claims FE tasks  
init(team="proj", role="fe")
claim()  # Gets "Login form"

# Team-wide announcement (replaces broadcast)
msg(subj="API Ready", body="Login endpoint live", global=true, to="all")

# Find teammates (replaces discover)
status(include_agents=true)

# Get claimable tasks (replaces ready)
ls(status="ready")
```
