# Beads Village

MCP wrapper kết hợp **Beads** + **Agent Mail** cho multi-agent workflow.

Dựa trên best practices từ [Steve Yegge](https://steve-yegge.medium.com/beads-best-practices-2db636b9760c).

## Kiến trúc

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   Agent 1       │     │   Agent 2       │     │   Agent 3       │
│   worktree-1    │     │   worktree-2    │     │   worktree-3    │
└────────┬────────┘     └────────┬────────┘     └────────┬────────┘
         │                       │                       │
         └───────────────────────┼───────────────────────┘
                                 │
            ┌────────────────────▼────────────────────┐
            │       Shared via Git                     │
            │  📋 .beads/beads.jsonl  (Task Graph)    │
            │  📧 .mail/              (Messages)       │
            │  🔒 .reservations/      (File Locks)     │
            └─────────────────────────────────────────┘
```

## Cài đặt

```bash
# Prerequisites: Install beads CLI
# https://github.com/beads-project/beads

# Install this package
cd mcp-beads-village
pip install -e .
```

## Cấu hình MCP

### Amp/Antigravity

Thêm vào `settings.json`:

```json
{
  "amp.mcpServers": {
    "beads-village": {
      "command": "python",
      "args": ["-m", "beads_village.server"],
      "cwd": "C:\\Working\\mcp-beads-village",
      "env": {
        "BEADS_AGENT": "amp-agent-1",
        "BEADS_WS": "${workspaceFolder}"
      }
    }
  }
}
```

### Claude Desktop

Copy vào `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "beads-village": {
      "command": "python",
      "args": ["-m", "beads_village.server"],
      "cwd": "C:\\Working\\mcp-beads-village"
    }
  }
}
```

## Tools

### Core Workflow

| Tool | Mô tả |
|------|-------|
| `init` | Khởi tạo Beads + Mail trong project |
| `claim` | Lấy và claim task tiếp theo (auto-sync) |
| `done` | Đóng task, release reservations, sync |
| `add` | Tạo issue mới (cho việc >2 phút) |

### Issue Management

| Tool | Mô tả |
|------|-------|
| `ls` | Liệt kê issues theo status |
| `ready` | Xem issues không có blocker |
| `show` | Chi tiết 1 issue |

### Maintenance

| Tool | Mô tả |
|------|-------|
| `cleanup` | Xóa issues cũ (chạy mỗi vài ngày) |
| `doctor` | Kiểm tra và sửa beads health |
| `sync` | Sync với git |

### File Reservations (Multi-agent)

| Tool | Mô tả |
|------|-------|
| `reserve` | Claim files trước khi edit |
| `release` | Nhả files khi xong |
| `reservations` | Xem ai đang giữ files nào |

### Messaging

| Tool | Mô tả |
|------|-------|
| `msg` | Gửi message cho agents khác |
| `inbox` | Đọc messages |
| `status` | Xem trạng thái village |

## Workflow

### Single Agent

```
1. init         → Khởi tạo workspace
2. claim        → Lấy task tiếp theo
3. [work]       → Làm việc
4. add          → File issues cho việc phát hiện thêm
5. done         → Hoàn thành task
6. RESTART      → Khởi động lại session
```

### Multi-Agent

```
Agent 1:                      Agent 2:
─────────                     ─────────
init                          init
claim (task-1)                claim (task-2)
reserve(["src/a.py"])         reserve(["src/b.py"])
[edit src/a.py]               [edit src/b.py]
release                       release
done                          done
```

## Best Practices (Steve Yegge)

1. **1 task = 1 session** - Restart agent sau mỗi task hoàn thành
2. **File issues cho việc >2 phút** - Đừng để mất track
3. **Giữ <200 issues mở** - Chạy `cleanup` thường xuyên
4. **Plan ngoài Beads** - Dùng tool khác để plan, rồi import thành epics
5. **Agents claim work** - Không assign, để agents tự claim
6. **Run `doctor` regularly** - Kiểm tra health

## Response Fields (Token-optimized)

| Field | Meaning |
|-------|---------|
| `id` | Issue ID |
| `t` | Title |
| `p` | Priority (0=critical, 4=backlog) |
| `s` | Status |
| `f` | From (sender) |
| `b` | Body |
| `ts` | Timestamp |
| `imp` | Importance |

## Multi-Agent Setup với Git Worktrees

```bash
# Main repo
cd my-project
bd init

# Tạo worktrees cho mỗi agent
git worktree add ../agent-1 -b work-1
git worktree add ../agent-2 -b work-2
git worktree add ../agent-3 -b work-3

# Mỗi agent chạy trong worktree riêng với BEADS_AGENT khác nhau
# Beads sync qua git
# Messages và reservations sync qua shared folder hoặc git
```

## Environment Variables

| Variable | Default | Mô tả |
|----------|---------|-------|
| `BEADS_AGENT` | `agent-{pid}` | Tên agent unique |
| `BEADS_WS` | Current dir | Workspace directory (where bd runs) |
| `BEADS_SHARED` | Same as WS | Shared directory for .mail/ and .reservations/ |

### Multi-Agent Setup

Với git worktrees, mỗi agent có workspace riêng nhưng cần share `.mail/` và `.reservations/`:

```bash
# Main repo structure:
my-project/           ← BEADS_SHARED (all agents point here)
├── .beads/          ← Beads data (syncs via git)
├── .mail/           ← Messages (shared via BEADS_SHARED)
├── .reservations/   ← File locks (shared via BEADS_SHARED)
└── src/

# Worktrees:
../agent-1/          ← BEADS_WS for agent 1
../agent-2/          ← BEADS_WS for agent 2
```

Config cho mỗi agent:
```json
{
  "env": {
    "BEADS_AGENT": "agent-1",
    "BEADS_WS": "/path/to/agent-1",
    "BEADS_SHARED": "/path/to/my-project"
  }
}
```

## File Reservation System

Hệ thống reservation giúp tránh xung đột khi nhiều agents edit cùng files:

```python
# Agent 1 claims files
reserve(paths=["src/auth.py", "src/utils.py"], ttl=600, reason="implementing login")

# Agent 2 tries to claim same file
reserve(paths=["src/auth.py"])
# → {"granted": [], "conflicts": [{"path": "src/auth.py", "holder": "agent-1", ...}]}

# Agent 1 finishes and releases
release()  # Releases all owned reservations
```

- **TTL**: Reservations expire after TTL seconds (default 10 min)
- **Auto-release**: `done()` automatically releases all reservations
- **Graceful degradation**: Conflicts are reported, not enforced

## Troubleshooting

### bd CLI not found

```bash
# Install beads
go install github.com/beads-project/beads/cmd/bd@latest
```

### Permission denied on Windows

Run terminal as Administrator hoặc check antivirus settings.

### Stale reservations

Reservations auto-expire. Hoặc chạy `init` để cleanup expired.

## License

MIT
