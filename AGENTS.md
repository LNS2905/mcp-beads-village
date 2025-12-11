# AGENTS.md - Beads Village

## AI Agent Guide for Multi-Agent Task Coordination

This guide helps AI agents use Beads Village MCP correctly for task management and multi-agent coordination.

---

## ⚡ Quick Start (MUST DO FIRST)

### Standard Agent
```
1. init()              → Join workspace, get agent ID
2. claim()             → Get next ready task
3. reserve(paths=[...]) → Lock files before editing
4. [do work]           → Make changes
5. done(id="...", msg="...") → Complete task
6. RESTART SESSION     → One task = one session (best practice)
```

### With Role-Based Assignment
```
# Leader agent (creates and assigns tasks)
1. init(leader=true, start_tui=true) → Join as leader, auto-launch dashboard
2. add(title="...", tags=["fe"]) → Create task with role tag
3. assign(id="bd-42", role="fe") → Assign to role (optional)

# Worker agent (claims tasks by role)
1. init(role="fe")              → Join with role (fe/be/mobile/devops/qa)
2. claim()                      → Auto-filtered to your role
3. reserve(paths=[...])         → Lock files
4. [do work]                    → Make changes
5. done(id="...", msg="...")    → Complete task
```

**CRITICAL**: Always call `init()` BEFORE any other Beads tool!

---

## 📊 Dashboard (Human Monitoring)

Launch the Textual dashboard to monitor agents, tasks, and messages:

```bash
# Manual launch
python -m beads_village.dashboard [workspace_path]

# Auto-launch when leader inits
init(leader=true, start_tui=true)

# Launch from MCP tool
village_tui()
```

### Dashboard Panels
| Panel | Description |
|-------|-------------|
| Teams | Click to filter agents by team |
| Agents | Online status, current task |
| Tasks Board | Kanban (Open/In Progress/Blocked/Closed) |
| Task Detail | Click task for full details + activity |
| File Locks | Active reservations with TTL |
| Messages | Recent broadcasts and done notifications |
| Graph Insights | Keystones, Influencers, Cycles (requires bv) |
| Filter Recipes | All, Actionable, Blocked, High Impact, Stale |

---

## 🔄 Tool Consolidation (v1.3.0)

The following tools have been consolidated to reduce the total from 26 to 21:

| Old Tool | New Usage | Description |
|----------|-----------|-------------|
| `broadcast` | `msg(subj, body, global=true, to="all")` | Team-wide announcement |
| `discover` | `status(include_agents=true)` | Find teammates |
| `ready` | `ls(status="ready")` | Get claimable tasks |
| `bv_status` | `status(include_bv=true)` | Check bv availability |
| `bv_tui` | `village_tui` | Unified dashboard |

---

## 🎯 Decision Tree: Which Tool to Use?

### Starting a Session
```
Q: Am I starting work?
├─ Yes → init() first, ALWAYS
│   ├─ Am I the leader/coordinator? → init(leader=true, start_tui=true)
│   ├─ Do I have a specialty? → init(role="fe/be/mobile/devops/qa")
│   └─ General agent → init()
└─ Already called init() → proceed to claim() or ls(status="ready")
```

### Getting Work
```
Q: What task should I work on?
├─ Worker with role → claim() (auto-filters by your role)
├─ Want next priority task → claim()
├─ Want to see options first → ls(status="ready", limit=5)
├─ Looking for specific task → ls(status="open") or show(id="...")
└─ No tasks available → add(title="...", desc="...")
```

### Creating/Assigning Tasks (Leader)
```
Q: How do I create tasks for the team?
├─ Create for specific role → add(title="...", tags=["fe"]) 
├─ Create and assign → add(...) then assign(id="bd-42", role="be")
├─ Create unassigned → add(title="...", desc="...")
└─ Reassign existing → assign(id="bd-42", role="mobile")
```

### Before Editing Files
```
Q: Am I about to edit files?
├─ Yes → reservations() first to check conflicts
│   ├─ No conflicts → reserve(paths=[...], reason="bd-xxx")
│   └─ Conflicts exist → WAIT or coordinate via msg()
└─ Just reading → No reservation needed
```

### Communicating with Other Agents
```
Q: Who needs this message?
├─ Agents in THIS workspace only → msg(subj="...", to="all")
├─ ALL agents in my TEAM (across workspaces) → msg(subj="...", body="...", global=true, to="all")
├─ Specific agent in team → msg(subj="...", to="agent-id", global=true)
└─ Find who's available → status(include_agents=true)
```

### Completing Work
```
Q: Is the task done?
├─ Yes, fully complete → done(id="...", msg="what I did")
├─ Blocked by something → Add blocker issue, switch tasks
├─ Found side work (>2 min) → add(title="...", typ="bug/task")
└─ Need to pause → release() files, don't call done()
```

---

## ⚠️ Common Mistakes & How to Avoid Them

### ❌ Mistake 1: Not calling init() first
```
# WRONG - will fail
claim()  → ERROR: workspace not initialized

# CORRECT
init()   → {"ok":1, "agent":"agent-123", "ws":"/path", "team":"default"}
claim()  → works!
```

### ❌ Mistake 2: Editing files without reservation
```
# WRONG - may cause conflicts with other agents
[edit src/auth.py directly]

# CORRECT
reservations()  → check for conflicts first
reserve(paths=["src/auth.py"], reason="bd-42")
[now safe to edit]
```

### ❌ Mistake 3: Creating issues without description
```
# WRONG - no context for future
add(title="Fix bug")

# CORRECT - includes context
add(
    title="Fix auth bug",
    desc="Login fails with 500 when password has special chars. Found during bd-42.",
    typ="bug",
    pri=1
)
```

### ❌ Mistake 4: Not releasing files when switching tasks
```
# WRONG - blocks other agents
reserve(paths=["src/api.py"])
[decide to work on something else]
claim()  # files still locked!

# CORRECT
reserve(paths=["src/api.py"])
[decide to switch]
release()  # free the files
claim()
```

### ❌ Mistake 5: Using old tools that have been consolidated
```
# OLD - these tools no longer exist
broadcast(subj="API ready")
discover()
ready()

# NEW - use consolidated tools
msg(subj="API ready", body="POST /auth/login is live", global=true, to="all")
status(include_agents=true)
ls(status="ready")
```

### ❌ Mistake 6: Forgetting to sync
```
# WRONG - working on stale data
[make changes]
[other agent's changes are lost]

# CORRECT
sync()  → get latest from git
[make changes]
done()  → auto-syncs
```

---

## 🔄 Workflow Patterns

### Pattern 1: Standard Task Completion
```python
# 1. Initialize
init()

# 2. Get task
claim()  
# Returns: {"id":"bd-42", "t":"Add login", "p":1, "s":"in_progress"}

# 3. Reserve files
reserve(paths=["src/auth.py", "src/login.py"], reason="bd-42", ttl=600)
# Returns: {"granted":["src/auth.py","src/login.py"], "conflicts":[]}

# 4. Do the work
[implement the feature]

# 5. Complete
done(id="bd-42", msg="Implemented login with JWT tokens")
# Returns: {"ok":1, "done":1, "hint":"restart session"}

# 6. RESTART SESSION for next task
```

### Pattern 2: Leader-Worker Role-Based Assignment
```python
# === LEADER AGENT (orchestrator/coordinator) ===
init(team="ecommerce", leader=true, start_tui=true)
# Returns: {"ok":1, "agent":"agent-001", "ws":"...", "team":"ecommerce", "leader":true}

# Create tasks with role tags
add(
    title="Implement /auth/login endpoint",
    desc="JWT-based auth. Return token in 'token' field.",
    typ="feature",
    pri=1,
    tags=["be"]  # Tagged for backend
)
# Returns: {"id":"bd-10", "t":"Implement /auth/login endpoint", "tags":["be"]}

add(
    title="Create login form component",
    desc="Use POST /auth/login. Display errors.",
    typ="feature",
    pri=1,
    tags=["fe"]  # Tagged for frontend
)
# Returns: {"id":"bd-11", "t":"Create login form component", "tags":["fe"]}

add(
    title="E2E tests for login flow",
    desc="Test happy path and error cases.",
    typ="task",
    pri=2,
    tags=["qa"]  # Tagged for QA
)
# Returns: {"id":"bd-12", "t":"E2E tests for login flow", "tags":["qa"]}

# Optionally explicitly assign (if not using tags)
assign(id="bd-15", role="mobile")
# Returns: {"ok":1, "id":"bd-15", "role":"mobile"}


# === BE WORKER AGENT ===
init(team="ecommerce", role="be")
# Returns: {"ok":1, "agent":"agent-be", "ws":"/api", "team":"ecommerce", "role":"be"}

claim()  # Auto-filtered to tasks tagged "be"
# Returns: {"id":"bd-10", "t":"Implement /auth/login endpoint", "p":1, "s":"in_progress"}

reserve(paths=["src/auth/login.py"], reason="bd-10")
[implement endpoint]
done(id="bd-10", msg="Login API ready with JWT auth")
msg(subj="Auth API Ready", body="POST /auth/login - returns JWT in 'token' field", global=true, to="all")


# === FE WORKER AGENT ===
init(team="ecommerce", role="fe")
# Returns: {"ok":1, "agent":"agent-fe", "ws":"/web", "team":"ecommerce", "role":"fe"}

claim()  # Auto-filtered to tasks tagged "fe"
# Returns: {"id":"bd-11", "t":"Create login form component", "p":1, "s":"in_progress"}

inbox()  # Check for updates from BE
# [{"f":"agent-be", "s":"Auth API Ready", "b":"POST /auth/login - returns JWT", "global":true}]

reserve(paths=["src/components/Login.tsx"], reason="bd-11")
[implement form]
done(id="bd-11", msg="Login form complete, uses /auth/login API")


# === QA WORKER AGENT ===
init(team="ecommerce", role="qa")
claim()  # Only sees tasks tagged "qa"
# Returns: {"id":"bd-12", "t":"E2E tests for login flow", ...}
```

### Pattern 3: Finding Side Issues During Work
```python
# While working on bd-42, discover a bug
add(
    title="Password validation missing",
    desc="Found during login implementation (bd-42). No validation for min length.",
    typ="bug",
    pri=2,
    tags=["be"],     # Assign to backend
    parent="bd-42"   # Link to parent task
)
# Returns: {"id":"bd-43", "t":"Password validation missing", "tags":["be"]}

# Continue with original task
done(id="bd-42", msg="Login done. Filed bd-43 for password validation.")
```

### Pattern 4: Cross-Workspace Coordination (BE/FE)
```python
# === BE Agent in /api workspace ===
init()
claim()  # Gets "Implement /auth/login endpoint"
[implement API]
done(id="bd-10", msg="Login API ready")
msg(subj="Auth API Ready", body="POST /auth/login - returns JWT token in 'token' field", global=true, to="all")

# === FE Agent in /web workspace ===
init()
inbox()  # Sees broadcast from BE agent
# [{"f":"agent-be", "s":"Auth API Ready", "ws":"/api", "global":true}]

status(include_agents=true)  # See who's working (replaces discover)
# {"agents":[{"agent":"agent-be","ws":"/api"}, {"agent":"agent-fe","ws":"/web"}]}

# Can switch to BE workspace to see their task details
init(ws="/api")
show(id="bd-10")  # Read API implementation details

# Switch back and create FE task
init(ws="/web")
add(title="Login form", desc="Uses /auth/login from BE", typ="feature")
```

### Pattern 5: Handling Conflicts
```python
# Check before reserving
reservations()
# Returns: [{"path":"src/api.py", "agent":"agent-2", "expires":"..."}]

# File is locked by another agent - DO NOT force edit!
# Option 1: Wait and check again
# Option 2: Message the agent
msg(subj="Need src/api.py", body="Working on bd-50, need to modify api.py", to="agent-2")

# Option 3: Work on something else
claim()  # Get different task
```

### Pattern 6: Handling Blocked Tasks
```python
claim()  # Gets a task
# Discover it's blocked by something

# 1. Create blocker issue
add(
    title="Need database schema update",
    desc="bd-42 blocked until users table has email column",
    typ="task",
    pri=1
)

# 2. Don't complete the blocked task - release and move on
release()
# Task stays in_progress - another agent can pick it up later or you can resume

# 3. Optionally claim different work
claim()
```

---

## 📊 Tool Quick Reference

### Lifecycle Tools
| Tool | When to Use | Key Args | Returns |
|------|-------------|----------|---------|
| `init` | Start of EVERY session | `ws`, `team`, `role`, `leader` | `{ok, agent, ws, team, role}` |
| `claim` | Get next task to work on | - (auto-filters by role if set) | `{id, t, p, s}` or `{ok:0, msg}` |
| `done` | Task complete | `id`, `msg` | `{ok, done, hint}` |

### Issue Management
| Tool | When to Use | Key Args | Returns |
|------|-------------|----------|---------|
| `add` | Create new issue | `title`, `desc`, `typ`, `pri`, `tags` | `{id, t, p, typ, tags}` |
| `assign` | Assign task to role (leader only) | `id`, `role` | `{ok, id, role}` |
| `ls` | List issues | `status` (open/closed/ready/all), `limit` | `[{id, t, p, s, tags}...]` |
| `show` | Get issue details | `id` | Full issue object |

### File Locking
| Tool | When to Use | Key Args | Returns |
|------|-------------|----------|---------|
| `reserve` | Before editing files | `paths[]`, `reason`, `ttl` | `{granted, conflicts}` |
| `release` | Done editing / switching | `paths[]` (optional) | `{released}` |
| `reservations` | Check what's locked | - | `[{path, agent, expires}...]` |

### Messaging
| Tool | When to Use | Key Args | Returns |
|------|-------------|----------|---------|
| `msg` | Send message or broadcast | `subj`, `body`, `to`, `global` | `{sent}` |
| `inbox` | Check messages | `n`, `unread`, `global` | `[{f, s, b, ts}...]` |

**Broadcasting (replaces old `broadcast` tool):**
```python
msg(subj="API Ready", body="Login endpoint live", global=true, to="all")
```

### Status & Discovery
| Tool | When to Use | Key Args | Returns |
|------|-------------|----------|---------|
| `status` | Workspace overview | `include_agents`, `include_bv` | `{team, agents, issues...}` |

**Finding teammates (replaces old `discover` tool):**
```python
status(include_agents=true)
# Returns: {"agents":[{"agent":"agent-be","ws":"/api","role":"be"}, ...]}
```

### Maintenance
| Tool | When to Use | Key Args | Returns |
|------|-------------|----------|---------|
| `sync` | Force git sync | - | `{ok}` |
| `cleanup` | Remove old closed issues | `days` | `{deleted}` |
| `doctor` | Fix database issues | - | Health report |

### Dashboard & Graph Tools
| Tool | When to Use | Returns |
|------|-------------|---------|
| `village_tui` | Launch unified dashboard | `{ok, message}` |
| `bv_insights` | Graph analysis (requires bv) | Bottlenecks, keystones, cycles |
| `bv_plan` | Parallel execution tracks | Issue tracks |
| `bv_priority` | Priority recommendations | Ranked issues |
| `bv_diff` | Compare git revisions | Issue changes |

---

## 🔍 Beads Viewer Tools (Optional)

If `bv` binary is installed, additional graph analysis tools are available:

### bv_insights()
Get pre-computed graph metrics:
- **Bottlenecks**: Issues with high betweenness centrality
- **Keystones**: Critical path issues with zero slack
- **Cycles**: Circular dependency detection
- **Hubs/Authorities**: HITS algorithm results

### bv_priority(limit=5)
Get priority recommendations ranked by impact score.

### bv_plan()
Get parallel execution tracks for multi-agent coordination.

### village_tui()
Launch unified TUI dashboard for human monitoring. Works without bv, but graph insights require bv.

**Check bv availability:**
```python
status(include_bv=true)
# Returns: {"bv_available": true, "bv_version": "1.0.0", ...}
```

---

## 🏷️ Issue Types & When to Use

| Type | Use For | Example |
|------|---------|---------|
| `task` | General work (DEFAULT) | "Refactor auth module" |
| `bug` | Something broken | "Login fails on Safari" |
| `feature` | New functionality | "Add OAuth2 support" |
| `epic` | Large work with sub-tasks | "User authentication system" |
| `story` | User-facing capability | "As a user, I can reset password" |
| `chore` | Maintenance | "Update npm dependencies" |

## 🎯 Priority Levels

| Priority | Meaning | When to Use |
|----------|---------|-------------|
| **0** | Critical | Production down, security breach |
| **1** | High | Blocking other work |
| **2** | Medium | Normal priority (DEFAULT) |
| **3** | Low | Nice to have |
| **4** | Backlog | Future consideration |

---

## 👥 Role-Based Task Assignment

Role-based assignment enables efficient task distribution in multi-agent teams. Leaders create and assign tasks, workers automatically receive tasks matching their specialty.

### Roles

| Role | Description | Typical Files |
|------|-------------|---------------|
| `fe` | Frontend | `*.tsx`, `*.vue`, `*.css`, `src/components/` |
| `be` | Backend | `*.py`, `*.go`, `*.java`, `src/api/`, `src/services/` |
| `mobile` | Mobile apps | `*.swift`, `*.kt`, `android/`, `ios/` |
| `devops` | Infrastructure | `Dockerfile`, `*.yaml`, `terraform/`, `.github/` |
| `qa` | Testing/QA | `*.test.*`, `*.spec.*`, `e2e/`, `tests/` |

### Leader Agents

Leaders orchestrate work by creating and assigning tasks:

```python
# Initialize as leader
init(team="my-project", leader=true, start_tui=true)
# Returns: {"ok":1, "agent":"agent-001", "leader":true, ...}

# Create tasks with role tags
add(title="Build user API", desc="CRUD for /users", tags=["be"])
add(title="User profile page", desc="Display user info", tags=["fe"])
add(title="Setup CI pipeline", desc="GitHub Actions", tags=["devops"])

# Explicitly assign/reassign tasks
assign(id="bd-42", role="mobile")
# Returns: {"ok":1, "id":"bd-42", "role":"mobile"}
```

### Worker Agents

Workers automatically receive tasks matching their role:

```python
# Initialize with role
init(team="my-project", role="fe")
# Returns: {"ok":1, "agent":"agent-fe", "role":"fe", ...}

# claim() automatically filters by role
claim()  # Only returns tasks tagged "fe"
# Returns: {"id":"bd-11", "t":"User profile page", "tags":["fe"], ...}

# ls(status="ready") also respects role
ls(status="ready")  # Shows only "fe" tasks available
```

### Task Tags

Tags connect tasks to roles:

```python
# Single role
add(title="API endpoint", tags=["be"])

# Multiple roles (any can claim)
add(title="API contract review", tags=["be", "fe"])

# No tags = anyone can claim
add(title="Update README", desc="General task")
```

### How Filtering Works

1. **Leader creates task** with `tags=["fe"]`
2. **Worker with `role="fe"`** calls `claim()`
3. **System filters** to only show tasks where:
   - Task has no tags (unassigned), OR
   - Task tags include the worker's role
4. **Worker receives** matching task

### Best Practices

- **Leaders**: Always add `tags` when creating role-specific tasks
- **Workers**: Initialize with your specialty role for automatic filtering
- **Mixed work**: Workers can still see untagged tasks (general work)
- **Reassignment**: Use `assign()` to move tasks between roles

---

## 🤝 Team Setup

### What is a Team?

A **team** groups related agents (BE, FE, Mobile, etc.) working on the same project. Agents in the same team can:
- See each other via `status(include_agents=true)`
- Send broadcasts via `msg(global=true, to="all")`
- Receive team messages via `inbox()`

Agents in **different teams** are completely isolated - they cannot see or message each other.

### How to Create/Join a Team

**Teams are created automatically** when the first agent joins. Use `init(team="...")` to join:

```python
# Join/create team "my-project"
init(team="my-project")
# Returns: {"ok":1, "agent":"agent-001", "ws":"...", "team":"my-project", "available_teams":["default","my-project"]}

# Now agent is in team "my-project"
status(include_agents=true)  # See other agents in this team
msg(subj="Hello", body="I joined!", global=true, to="all")  # Send to all team members
```

### See Available Teams

```python
init()
# Response includes: "available_teams": ["abc", "default", "ecommerce"]

# Or check status
status()
# Returns: {"team":"current-team", ...}
```

### Join Specific Team

**Scenario**: User says "join team abc"

```python
init(team="abc")
# Returns: {
#   "ok": 1,
#   "agent": "agent-003",
#   "ws": "C:\\Projects\\mobile",
#   "team": "abc",                    # ✓ Joined team abc
#   "available_teams": ["abc", "default", "xyz"]
# }

# Verify - can see other agents in team abc
status(include_agents=true)
# Returns: {"team":"abc", "agents":[
#   {"agent":"agent-001", "ws":"C:\\Projects\\api"},
#   {"agent":"agent-002", "ws":"C:\\Projects\\web"},
#   {"agent":"agent-003", "ws":"C:\\Projects\\mobile"}  # You
# ]}
```

### Switching Between Teams

Agent can work with multiple teams in the same session:

```python
# Currently in team alpha, need to check team beta
init(team="beta")
inbox()  # See messages from team beta
status(include_agents=true)  # See agents in team beta

# Return to team alpha
init(team="alpha")
msg(subj="Done", body="Finished checking beta", global=true, to="all")
```

**Note**: When switching teams, the agent will:
- Auto-register in the new team
- Send join announcement to the new team
- `msg(global=true)`, `inbox()`, `status(include_agents=true)` will scope to the new team

### Example: Setting Up a 3-Agent Team

```python
# Agent 1 (Backend, workspace /api)
init(team="ecommerce")
# → joins team "ecommerce", team is created automatically

# Agent 2 (Frontend, workspace /web)  
init(team="ecommerce")
# → joins existing team "ecommerce"

# Agent 3 (Mobile, workspace /mobile)
init(team="ecommerce")
# → joins existing team "ecommerce"

# All 3 agents can now:
status(include_agents=true)   # See each other
msg(global=true, to="all")    # Send to all
inbox()                        # Receive team messages
```

### Default Team

If no team is specified, agent joins team `default`:

```python
init()  # No team parameter
# Returns: {"ok":1, ..., "team":"default"}
```

⚠️ **Warning**: All agents without specified team go to `default` - may see each other's broadcasts even if working on different projects!

### Team Isolation Architecture

```
~/.beads-village/
├── ecommerce/            # Team A
│   ├── mail/             # Team A broadcasts only
│   └── agents/           # Team A agent registry
├── internal-tools/       # Team B (completely isolated)
│   ├── mail/
│   └── agents/
└── default/              # Default team (all unassigned agents)
    ├── mail/
    └── agents/
```

### Scope Comparison

| Scope | Directory | Who Sees | Use Case |
|-------|-----------|----------|----------|
| **Local** | `/workspace/.mail/` | Only agents in THIS workspace | Workspace-specific coordination |
| **Team** | `~/.beads-village/{team}/mail/` | All agents in same team | Cross-workspace announcements |

### Common Team Patterns

#### Pattern 1: Single Project with Multiple Repos
```python
# All repos for same project share a team
init(team="project-alpha")  # Agent in /alpha-api
init(team="project-alpha")  # Agent in /alpha-web
init(team="project-alpha")  # Agent in /alpha-mobile
```

#### Pattern 2: Multiple Independent Projects
```python
# Each project is isolated
init(team="project-alpha")  # Alpha agents
init(team="project-beta")   # Beta agents (cannot see Alpha)
```

#### Pattern 3: Shared Library Development
```python
# Core team works on shared libs
init(team="platform-core")  # Agent in /shared-lib

# Consuming teams are separate
init(team="app-team-a")     # Agent in /app-a (isolated from core)
init(team="app-team-b")     # Agent in /app-b (isolated from core)
```

#### Pattern 4: Role-Based Team with Leader
```python
# Leader sets up the team and creates tasks
init(team="ecommerce", leader=true, start_tui=true)
add(title="Payment API", tags=["be"])
add(title="Checkout UI", tags=["fe"])
add(title="Payment flow tests", tags=["qa"])

# Workers join with their roles
init(team="ecommerce", role="be")   # BE agent
init(team="ecommerce", role="fe")   # FE agent
init(team="ecommerce", role="qa")   # QA agent

# Each worker's claim() only returns matching tasks
```

---

## 🔧 Error Handling

### Common Errors & Solutions

| Error | Cause | Solution |
|-------|-------|----------|
| `workspace not found` | Invalid path in init() | Check path exists |
| `bd CLI not found` | Beads not installed | `pip install beads` |
| `no ready tasks` | No claimable work | Use `add()` to create tasks or `ls()` to see all |
| `file reserved by agent-X` | Conflict | Wait, message agent, or work on different files |
| `timeout` | Slow git operation | Run `sync()` manually, check network |

### When Things Go Wrong
```python
# Check system health
doctor()

# Force sync with git
sync()

# Clean up old issues (if >200 open)
cleanup(days=2)

# Check messages for coordination issues
inbox(unread=True)
```

---

## ✅ Best Practices Checklist

### Before Starting
- [ ] Call `init()` first (with `role` or `leader` as appropriate)
- [ ] Check `inbox()` for updates from other agents
- [ ] Run `ls(status="ready")` to see available tasks (filtered by your role if set)

### During Work
- [ ] Always `reserve()` before editing files
- [ ] Create issues for side-discoveries with `add(..., desc="...", tags=[...])`
- [ ] Keep reservations short (TTL 600s = 10 min default)
- [ ] Check `reservations()` before editing new files

### When Completing
- [ ] Use descriptive `msg` in `done()` - explain what was done
- [ ] `msg(global=true, to="all")` for important completions to team
- [ ] Restart session after `done()` for clean state

### Maintenance (Every Few Days)
- [ ] Run `cleanup(days=2)` to remove old closed issues
- [ ] Run `doctor()` to fix any database issues
- [ ] Keep <200 open issues for performance

---

## 📝 Response Field Reference

| Field | Meaning | Example |
|-------|---------|---------|
| `id` | Issue ID | `"bd-42"` |
| `t` | Title | `"Fix auth bug"` |
| `p` | Priority | `1` (high) |
| `s` | Status | `"in_progress"` |
| `f` | From (sender) | `"agent-be"` |
| `b` | Body | `"Login API ready..."` |
| `ts` | Timestamp | `"2024-01-15T10:30:00"` |
| `ws` | Workspace | `"/projects/api"` |
| `team` | Team name | `"my-project"` |
| `role` | Agent role | `"fe"` |
| `leader` | Is leader agent | `true` |
| `tags` | Role tags on issue | `["be", "fe"]` |
| `global` | From team hub | `true` |
| `imp` | Importance | `"high"` |

---

## 🚀 Example Complete Session

### Standard Session
```python
# === Starting a new work session ===
Agent: I'll initialize beads village and see what work is available.

init()
# {"ok":1, "agent":"agent-001", "ws":"C:\\project", "team":"default"}

inbox(unread=True)
# [{"f":"agent-002", "s":"Auth API Ready", "b":"POST /auth/login deployed", "global":true}]

Agent: I see the auth API is ready. Let me claim the next task.

claim()
# {"id":"bd-50", "t":"Add login form", "p":1, "s":"in_progress"}

Agent: Got the login form task. I'll reserve the files I need.

reserve(paths=["src/components/Login.tsx", "src/api/auth.ts"], reason="bd-50")
# {"granted":["src/components/Login.tsx","src/api/auth.ts"], "conflicts":[]}

Agent: Files reserved. Now implementing...
[implements login form]

Agent: While implementing, I noticed we need form validation. I'll file that.

add(
    title="Add form validation to login",
    desc="Need client-side validation for email format and password length. Found during bd-50.",
    typ="task",
    pri=2,
    tags=["fe"],    # Tag for frontend
    parent="bd-50"
)
# {"id":"bd-51", "t":"Add form validation to login", "p":2, "tags":["fe"]}

Agent: Login form complete. Marking done and announcing to team.

done(id="bd-50", msg="Login form implemented using auth API. Filed bd-51 for validation.")
# {"ok":1, "done":1, "hint":"restart session for best performance"}

msg(subj="Login Form Ready", body="FE login at /login - uses POST /auth/login", global=true, to="all")
# {"sent":1, "global":true}

Agent: Task complete. Restarting session as recommended.
```

### Role-Based Session (FE Worker)
```python
# === FE Agent starting work ===
Agent: I'm a frontend developer. Let me join the team with my role.

init(team="ecommerce", role="fe")
# {"ok":1, "agent":"agent-fe", "ws":"C:\\web", "team":"ecommerce", "role":"fe"}

inbox(unread=True)
# [{"f":"agent-be", "s":"User API Ready", "b":"GET/POST /users available", "global":true}]

Agent: Backend API is ready. Let me see what FE tasks are available.

ls(status="ready")
# [{"id":"bd-20", "t":"User profile page", "p":1, "tags":["fe"]},
#  {"id":"bd-21", "t":"User settings form", "p":2, "tags":["fe"]}]

Agent: I'll claim the highest priority FE task.

claim()
# {"id":"bd-20", "t":"User profile page", "p":1, "s":"in_progress", "tags":["fe"]}

reserve(paths=["src/pages/Profile.tsx"], reason="bd-20")
[implements profile page]

done(id="bd-20", msg="Profile page complete with user API integration")
# {"ok":1, "done":1, "hint":"restart session"}
```

### Leader Session (Task Orchestration)
```python
# === Leader setting up sprint work ===
Agent: I'm the team lead. Let me create and assign tasks for the sprint.

init(team="ecommerce", leader=true, start_tui=true)
# {"ok":1, "agent":"agent-lead", "ws":"C:\\project", "team":"ecommerce", "leader":true}

Agent: Creating tasks for the checkout feature.

add(
    title="Checkout API endpoint",
    desc="POST /checkout - process payment and create order",
    typ="feature",
    pri=1,
    tags=["be"]
)
# {"id":"bd-30", "t":"Checkout API endpoint", "tags":["be"]}

add(
    title="Checkout page UI",
    desc="Cart summary, payment form, order confirmation",
    typ="feature",
    pri=1,
    tags=["fe"]
)
# {"id":"bd-31", "t":"Checkout page UI", "tags":["fe"]}

add(
    title="Checkout E2E tests",
    desc="Full checkout flow testing",
    typ="task",
    pri=2,
    tags=["qa"]
)
# {"id":"bd-32", "t":"Checkout E2E tests", "tags":["qa"]}

Agent: Tasks created. Workers will automatically receive tasks matching their roles.

status(include_agents=true)
# {"team":"ecommerce", "agents":[
#   {"agent":"agent-be", "ws":"/api", "role":"be"},
#   {"agent":"agent-fe", "ws":"/web", "role":"fe"},
#   {"agent":"agent-qa", "ws":"/tests", "role":"qa"}
# ]}

msg(subj="Sprint Started", body="Checkout feature tasks created. Claim your work!", global=true, to="all")
# {"sent":1, "global":true}
```
