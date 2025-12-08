"""Beads Village MCP - Multi-agent workflow with Beads + Agent Mail.

Combines:
- Beads (Steve Yegge): Git-native issue tracker for AI agents
- Agent Mail concepts: File reservations + messaging for coordination

Best practices from https://steve-yegge.medium.com/beads-best-practices-2db636b9760c
"""

import asyncio
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional, Set, List, Any

# ============================================================================
# CONFIG
# ============================================================================

AGENT = os.environ.get("BEADS_AGENT", f"agent-{os.getpid()}")

# Current workspace - can be changed via init(ws=...)
# Each workspace has its own .beads/, .mail/, .reservations/
WS = os.environ.get("BEADS_WS", os.getcwd())

# ============================================================================
# STATE
# ============================================================================

@dataclass
class State:
    """Agent session state."""
    issue: Optional[str] = None
    start: datetime = field(default_factory=datetime.now)
    done: int = 0
    reserved_files: Set[str] = field(default_factory=set)

S = State()

# ============================================================================
# HELPERS
# ============================================================================

def bd_sync(*args, timeout: float = 30.0) -> dict:
    """Run bd CLI command synchronously.
    
    Runs in current WS directory - each workspace has its own beads database.
    """
    try:
        cmd = ["bd", *args]
        # Add --json if command supports it
        json_cmds = {"list", "ready", "show", "stats", "doctor", "cleanup"}
        if args and args[0] in json_cmds:
            cmd.append("--json")
        
        # Run bd in current workspace
        result = subprocess.run(
            cmd,
            capture_output=True,
            timeout=timeout,
            cwd=WS,
        )
        if result.returncode != 0:
            stderr = result.stderr.decode()[:200] if result.stderr else ""
            return {"error": stderr or "command failed"}
        
        stdout = result.stdout.decode().strip() if result.stdout else ""
        if not stdout:
            return {"ok": 1}
        
        try:
            return json.loads(stdout)
        except json.JSONDecodeError:
            return {"output": stdout}
    except subprocess.TimeoutExpired:
        return {"error": "timeout"}
    except FileNotFoundError:
        return {"error": "bd CLI not found - install beads first"}
    except Exception as e:
        return {"error": str(e)[:100]}


async def bd(*args, timeout: float = 30.0) -> dict:
    """Run bd CLI command (async wrapper)."""
    return bd_sync(*args, timeout=timeout)


def ensure_dir(base: str, name: str) -> str:
    """Ensure directory exists and return path."""
    d = os.path.join(base, name)
    os.makedirs(d, exist_ok=True)
    return d


def mail_dir() -> str:
    """Mail directory - in current workspace."""
    return ensure_dir(WS, ".mail")


def reservation_dir() -> str:
    """Reservation directory - in current workspace."""
    return ensure_dir(WS, ".reservations")


def j(data: Any) -> str:
    """Compact JSON serialization."""
    return json.dumps(data, separators=(',', ':'), ensure_ascii=False)


def path_hash(path: str) -> str:
    """Generate short hash for file path."""
    return hashlib.sha1(path.encode()).hexdigest()[:12]


def to_posix_path(path: str) -> str:
    """Convert path to POSIX format (forward slashes) for cross-platform consistency."""
    return path.replace("\\", "/")


def normalize_path(path: str) -> str:
    """Normalize and validate path is within workspace.
    
    Prevents path traversal attacks by ensuring path stays within WS.
    Returns relative path in POSIX format (forward slashes) for cross-platform consistency.
    
    Raises:
        ValueError: If path is outside workspace
    """
    clean_path = path.replace("\\", "/")
    
    if os.path.isabs(clean_path):
        abs_path = os.path.normpath(clean_path)
    else:
        abs_path = os.path.normpath(os.path.join(WS, clean_path))
    
    ws_abs = os.path.abspath(WS)
    
    if not (abs_path.startswith(ws_abs + os.sep) or abs_path == ws_abs):
        raise ValueError(f"Path outside workspace: {path}")
    
    rel_path = os.path.relpath(abs_path, WS)
    return to_posix_path(rel_path)


def try_atomic_reserve(path: str, reservation: dict) -> tuple:
    """Atomically try to create reservation file.
    
    Uses temp file + rename pattern for atomicity.
    On Windows, os.replace() is used which is atomic.
    
    Returns:
        (success: bool, existing_reservation: Optional[dict])
    """
    res_file = os.path.join(reservation_dir(), f"{path_hash(path)}.json")
    now = datetime.now()
    
    if os.path.exists(res_file):
        try:
            with open(res_file, encoding="utf-8") as f:
                existing = json.load(f)
            if datetime.fromisoformat(existing["expires"]) > now:
                if existing["agent"] != AGENT:
                    return False, existing
        except (json.JSONDecodeError, OSError, KeyError, ValueError):
            pass
    
    fd = None
    tmp_path = None
    try:
        fd, tmp_path = tempfile.mkstemp(dir=reservation_dir(), suffix=".tmp")
        with os.fdopen(fd, 'w', encoding="utf-8") as f:
            fd = None
            json.dump(reservation, f)
        
        os.replace(tmp_path, res_file)
        tmp_path = None
        return True, None
    except OSError:
        return False, None
    finally:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


# ============================================================================
# MAIL FUNCTIONS
# ============================================================================

async def send_msg(subj: str, body: str = "", to: str = "all", 
                   thread_id: str = "", importance: str = "normal") -> dict:
    """Send message to other agents."""
    msg = {
        "f": AGENT,
        "t": to,
        "s": subj,
        "b": body,
        "ts": datetime.now().isoformat(),
        "thread": thread_id or S.issue or "",
        "imp": importance,
        "issue": S.issue
    }
    ts = datetime.now().timestamp()
    unique = uuid.uuid4().hex[:6]
    p = os.path.join(mail_dir(), f"{ts:.6f}_{unique}.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump(msg, f)
    return {"sent": 1}


async def recv_msgs(n: int = 5, unread_only: bool = False) -> List[dict]:
    """Receive messages from other agents."""
    d = mail_dir()
    msgs = []
    read_file = os.path.join(d, f".read_{AGENT}")
    read_ts = 0.0
    
    if os.path.exists(read_file):
        try:
            with open(read_file, encoding="utf-8") as f:
                read_ts = float(f.read().strip())
        except (OSError, ValueError):
            read_ts = 0.0
    
    try:
        files = sorted(os.listdir(d))
        for fname in files[-50:]:
            if not fname.endswith(".json") or fname.startswith("."):
                continue
            try:
                fp = os.path.join(d, fname)
                with open(fp, encoding="utf-8") as file:
                    m = json.load(file)
                
                if m.get("t") not in ["all", AGENT]:
                    continue
                
                if unread_only:
                    ts_part = fname.replace(".json", "").split("_")[0]
                    try:
                        file_ts = float(ts_part)
                        if file_ts <= read_ts:
                            continue
                    except ValueError:
                        pass
                
                msgs.append(m)
            except (json.JSONDecodeError, OSError):
                pass
    except OSError:
        pass
    
    if msgs:
        with open(read_file, "w", encoding="utf-8") as f:
            f.write(str(datetime.now().timestamp()))
    
    return msgs[-n:]


# ============================================================================
# RESERVATION FUNCTIONS
# ============================================================================

def cleanup_expired_reservations():
    """Remove expired reservations."""
    now = datetime.now()
    d = reservation_dir()
    cleaned = 0
    
    try:
        for fname in os.listdir(d):
            if not fname.endswith(".json"):
                continue
            fp = os.path.join(d, fname)
            try:
                with open(fp, encoding="utf-8") as file:
                    res = json.load(file)
                if datetime.fromisoformat(res["expires"]) < now:
                    os.remove(fp)
                    cleaned += 1
            except (json.JSONDecodeError, OSError, KeyError, ValueError):
                pass
    except OSError:
        pass
    
    return cleaned


def get_active_reservations() -> List[dict]:
    """Get all active (non-expired) reservations."""
    cleanup_expired_reservations()
    now = datetime.now()
    d = reservation_dir()
    active = []
    
    try:
        for fname in os.listdir(d):
            if not fname.endswith(".json"):
                continue
            try:
                with open(os.path.join(d, fname), encoding="utf-8") as fp:
                    res = json.load(fp)
                if datetime.fromisoformat(res["expires"]) > now:
                    active.append(res)
            except (json.JSONDecodeError, OSError, KeyError, ValueError):
                pass
    except OSError:
        pass
    
    return active


def check_reservation_conflict(path: str) -> Optional[dict]:
    """Check if path conflicts with existing reservation."""
    cleanup_expired_reservations()
    now = datetime.now()
    res_file = os.path.join(reservation_dir(), f"{path_hash(path)}.json")
    
    if os.path.exists(res_file):
        try:
            with open(res_file, encoding="utf-8") as f:
                existing = json.load(f)
            if datetime.fromisoformat(existing["expires"]) > now:
                if existing["agent"] != AGENT:
                    return existing
        except (json.JSONDecodeError, OSError, KeyError, ValueError):
            pass
    
    return None


# ============================================================================
# TOOL IMPLEMENTATIONS
# ============================================================================

async def tool_init(args: dict) -> str:
    """Initialize/join a beads workspace with actionable errors.

    Each workspace (BE/FE/Mobile) has its own isolated:
    - .beads/ (task database)
    - .mail/ (messages between agents in this workspace)
    - .reservations/ (file locks)

    Args:
        ws: Workspace directory to join. Each workspace is independent.
    """
    global WS

    # Switch to specified workspace
    if args.get("ws"):
        WS = os.path.abspath(args["ws"])

    # Ensure workspace directory exists
    if not os.path.isdir(WS):
        return j({
            "error": f"workspace not found: {WS}",
            "hint": "Provide a valid directory path with ws parameter, or ensure current directory exists."
        })

    # Init beads in this workspace
    result = await bd("init")
    if result.get("error"):
        err_msg = str(result.get("error", ""))
        if "already" not in err_msg.lower():
            return j({
                "error": err_msg,
                "hint": "Ensure 'bd' CLI is installed: go install github.com/beads-project/beads/cmd/bd@latest"
            })

    # Ensure mail and reservation dirs
    mail_dir()
    reservation_dir()

    # Clean up any expired reservations
    cleanup_expired_reservations()

    # Announce agent joining this workspace
    await send_msg("join", f"Agent {AGENT} joined workspace")

    return j({
        "ok": 1,
        "agent": AGENT,
        "ws": WS,
        "hint": "Workspace ready. Use 'claim' to get a task, or 'ready' to see available tasks."
    })


async def tool_claim(_args: dict) -> str:
    """Claim next ready task (highest priority first) with actionable errors."""
    # Sync first to get latest state
    await bd("sync")

    # Get ready issues
    r = await bd("ready")

    if isinstance(r, dict) and r.get("error"):
        return j({
            "error": r["error"],
            "hint": "Run 'init' first to initialize workspace, or 'doctor' to fix issues."
        })

    if not r or (isinstance(r, list) and len(r) == 0):
        return j({
            "ok": 0,
            "msg": "no ready tasks",
            "hint": "No tasks available to claim. Use 'add' to create new tasks, or 'ls' to see all issues."
        })

    # Get first ready issue
    issue = r[0] if isinstance(r, list) else r
    issue_id = issue.get("id", "")

    # Update status (agents claim, not assigned per Steve's article)
    await bd("update", issue_id, "--status", "in_progress")

    # Track in session state
    S.issue = issue_id

    # Notify other agents
    await send_msg(f"claimed:{issue_id}", issue.get("title", ""), importance="high")

    return j({
        "id": issue_id,
        "t": issue.get("title", ""),
        "p": issue.get("priority", 2),
        "s": "in_progress",
        "hint": "Task claimed. Use 'reserve' before editing files, then 'done' when complete."
    })


async def tool_done(args: dict) -> str:
    """Close task and sync with actionable errors."""
    issue_id = args.get("id", S.issue)
    if not issue_id:
        return j({
            "error": "no issue id",
            "hint": "Provide an issue ID, or use 'claim' first to set current task."
        })

    msg = args.get("msg", "completed")

    # Close issue
    r = await bd("close", issue_id, "--reason", msg)
    if isinstance(r, dict) and r.get("error"):
        return j({
            "error": r["error"],
            "hint": f"Failed to close issue '{issue_id}'. Use 'show' to verify issue exists."
        })

    # Release any file reservations
    if S.reserved_files:
        for path in list(S.reserved_files):
            res_file = os.path.join(reservation_dir(), f"{path_hash(path)}.json")
            if os.path.exists(res_file):
                try:
                    os.remove(res_file)
                except Exception:
                    pass
        S.reserved_files.clear()

    # Sync to share with other agents
    await bd("sync")

    # Notify
    await send_msg(f"done:{issue_id}", msg, importance="high")

    S.issue = None
    S.done += 1

    return j({
        "ok": 1,
        "done": S.done,
        "hint": "Task completed. Restart session for best performance (1 task = 1 session pattern)."
    })


async def tool_add(args: dict) -> str:
    """Create new issue (file issues for anything >2 min) with actionable errors."""
    title = args.get("title", "")
    if not title:
        return j({
            "error": "title required",
            "hint": "Provide a clear, actionable title. Example: 'Fix login timeout on slow networks'"
        })

    typ = args.get("typ", "task")
    if typ not in ("task", "bug", "epic", "story"):
        return j({
            "error": f"invalid type: {typ}",
            "hint": "Valid types: 'task' (default), 'bug', 'epic', 'story'"
        })

    pri = args.get("pri", 2)
    if not isinstance(pri, int) or pri < 0 or pri > 4:
        return j({
            "error": f"invalid priority: {pri}",
            "hint": "Priority must be 0-4. 0=critical, 1=high, 2=normal (default), 3=low, 4=backlog"
        })

    parent = args.get("parent", S.issue)  # Default to current issue

    # Create issue
    r = await bd("create", title, "-t", typ, "-p", str(pri))

    if isinstance(r, dict) and r.get("error"):
        return j({
            "error": r["error"],
            "hint": "Failed to create issue. Run 'init' to initialize workspace first."
        })

    new_id = r.get("id", "")

    if not new_id:
        return j({
            "error": "failed to create issue",
            "details": r,
            "hint": "Check if workspace is initialized with 'status'"
        })

    # Link to parent if specified
    if parent and new_id:
        await bd("dep", "add", new_id, parent, "--type", "discovered-from")

    return j({
        "id": new_id,
        "t": title,
        "p": pri,
        "typ": typ,
        "parent": parent,
        "hint": f"Issue created. Use 'show {new_id}' to see details."
    })


async def tool_ls(args: dict) -> str:
    """List issues with pagination."""
    status = args.get("status", "open")
    limit = min(args.get("limit", 10), 50)  # Cap at 50
    offset = args.get("offset", 0)

    r = await bd("list", "--status", status)

    if isinstance(r, dict) and r.get("error"):
        return j({
            "error": r["error"],
            "hint": "Try running 'doctor' to fix database issues, or 'init' to initialize workspace"
        })

    if not isinstance(r, list):
        return j({
            "items": [],
            "total": 0,
            "count": 0,
            "offset": offset,
            "has_more": False
        })

    total = len(r)
    paginated = r[offset:offset + limit]

    items = [{
        "id": i.get("id", ""),
        "t": i.get("title", ""),
        "p": i.get("priority", 2),
        "s": i.get("status", "")
    } for i in paginated]

    return j({
        "items": items,
        "total": total,
        "count": len(items),
        "offset": offset,
        "has_more": offset + limit < total,
        "next_offset": offset + limit if offset + limit < total else None
    })


async def tool_ready(args: dict) -> str:
    """Get ready issues (no blockers) with pagination."""
    limit = min(args.get("limit", 5), 20)  # Cap at 20

    r = await bd("ready")

    if isinstance(r, dict) and r.get("error"):
        return j({
            "error": r["error"],
            "hint": "Try running 'sync' to fetch latest state, or 'doctor' to fix issues"
        })

    if not isinstance(r, list):
        return j({
            "items": [],
            "total": 0,
            "count": 0,
            "has_more": False
        })

    total = len(r)
    paginated = r[:limit]

    items = [{
        "id": i.get("id", ""),
        "t": i.get("title", ""),
        "p": i.get("priority", 2)
    } for i in paginated]

    return j({
        "items": items,
        "total": total,
        "count": len(items),
        "has_more": limit < total
    })


async def tool_show(args: dict) -> str:
    """Get issue details with actionable error messages."""
    issue_id = args.get("id", "")
    if not issue_id:
        return j({
            "error": "id required",
            "hint": "Provide an issue ID. Use 'ls' or 'ready' to find available issues."
        })

    r = await bd("show", issue_id)

    if isinstance(r, dict) and r.get("error"):
        return j({
            "error": r["error"],
            "hint": f"Issue '{issue_id}' not found. Use 'ls' to list available issues."
        })

    return j(r)


async def tool_cleanup(args: dict) -> str:
    """Cleanup old closed issues (run every few days)."""
    days = args.get("days", 2)
    
    r = await bd("cleanup", "--days", str(days))
    await bd("sync")
    
    return j({
        "ok": 1,
        "days": days,
        "cleaned": r.get("deleted", r.get("cleaned", 0))
    })


async def tool_doctor(_args: dict) -> str:
    """Check and fix beads health."""
    r = await bd("doctor", "--fix")
    return j(r)


async def tool_sync(_args: dict) -> str:
    """Sync beads with git."""
    r = await bd("sync")
    return j({"ok": 1, "result": r})


# ============================================================================
# FILE RESERVATION TOOLS
# ============================================================================

async def tool_reserve(args: dict) -> str:
    """Reserve files/paths for exclusive editing.
    
    Use this before editing files to prevent conflicts with other agents.
    Reservations expire after TTL seconds.
    Uses atomic file creation to prevent race conditions.
    """
    paths = args.get("paths", [])
    if isinstance(paths, str):
        paths = [paths]
    
    if not paths:
        return j({"error": "paths required", "hint": "Provide list of file paths to reserve"})
    
    ttl = args.get("ttl", 600)
    reason = args.get("reason", S.issue or "editing")
    
    conflicts = []
    grants = []
    errors = []
    now = datetime.now()
    expires = now + timedelta(seconds=ttl)
    
    for path in paths:
        try:
            normalized = normalize_path(path)
        except ValueError as e:
            errors.append({"path": path, "error": str(e)})
            continue
        
        reservation = {
            "path": normalized,
            "agent": AGENT,
            "reason": reason,
            "created": now.isoformat(),
            "expires": expires.isoformat()
        }
        
        success, existing = try_atomic_reserve(normalized, reservation)
        
        if success:
            grants.append(normalized)
            S.reserved_files.add(normalized)
        elif existing:
            conflicts.append({
                "path": normalized,
                "holder": existing["agent"],
                "reason": existing.get("reason", ""),
                "expires": existing["expires"]
            })
        else:
            errors.append({"path": normalized, "error": "failed to reserve"})
    
    result = {
        "granted": grants,
        "conflicts": conflicts,
        "expires": expires.isoformat() if grants else None
    }
    if errors:
        result["errors"] = errors
    
    return j(result)


async def tool_release(args: dict) -> str:
    """Release file reservations."""
    paths = args.get("paths", [])
    
    if not paths:
        paths = list(S.reserved_files)
    
    if isinstance(paths, str):
        paths = [paths]
    
    released = []
    
    for path in paths:
        try:
            normalized = normalize_path(path)
        except ValueError:
            normalized = path
        
        res_file = os.path.join(reservation_dir(), f"{path_hash(normalized)}.json")
        if os.path.exists(res_file):
            try:
                with open(res_file, encoding="utf-8") as f:
                    res = json.load(f)
                if res.get("agent") == AGENT:
                    os.remove(res_file)
                    released.append(normalized)
            except (json.JSONDecodeError, OSError):
                pass
        S.reserved_files.discard(path)
        S.reserved_files.discard(normalized)
    
    return j({"released": released})


async def tool_reservations(_args: dict) -> str:
    """List active file reservations."""
    active = get_active_reservations()
    
    items = [{
        "path": r.get("path", ""),
        "agent": r.get("agent", ""),
        "reason": r.get("reason", ""),
        "expires": r.get("expires", "")
    } for r in active]
    
    return j(items)


# ============================================================================
# MESSAGING TOOLS
# ============================================================================

async def tool_msg(args: dict) -> str:
    """Send message to other agents."""
    subj = args.get("subj", "")
    if not subj:
        return j({"error": "subj required"})
    
    body = args.get("body", "")
    to = args.get("to", "all")
    thread_id = args.get("thread", S.issue or "")
    importance = args.get("importance", "normal")
    
    await send_msg(subj, body, to, thread_id, importance)
    
    return j({"ok": 1})


async def tool_inbox(args: dict) -> str:
    """Get messages from other agents."""
    n = args.get("n", 5)
    unread = args.get("unread", False)
    
    msgs = await recv_msgs(n, unread)
    
    items = [{
        "f": m.get("f", ""),
        "s": m.get("s", ""),
        "b": m.get("b", "")[:100],
        "ts": m.get("ts", ""),
        "imp": m.get("imp", "normal")
    } for m in msgs]
    
    return j(items)


async def tool_status(_args: dict) -> str:
    """Get village status overview."""
    # Get open issues count
    lst = await bd("list", "--status", "open")
    open_count = len(lst) if isinstance(lst, list) else 0
    
    # Get active reservations
    reservations = get_active_reservations()
    
    # Session duration
    mins = (datetime.now() - S.start).total_seconds() / 60
    
    return j({
        "agent": AGENT,
        "open": open_count,
        "warn": open_count > 200,
        "current": S.issue,
        "reserved": len(S.reserved_files),
        "active_agents": len(set(r.get("agent", "") for r in reservations)),
        "min": round(mins, 1),
        "done": S.done
    })


# ============================================================================
# TOOL REGISTRY
# ============================================================================

TOOLS = {
    # Core workflow
    "init": {
        "fn": tool_init,
        "desc": "Initialize or join a Beads workspace for multi-agent task coordination. Creates .beads/, .mail/, and .reservations/ directories. Call this first before using other tools. Returns agent ID and workspace path.",
        "input": {
            "type": "object",
            "properties": {
                "ws": {
                    "type": "string",
                    "description": "Absolute path to workspace directory. Each workspace has isolated task database, messages, and file locks. Defaults to current directory if not specified."
                }
            },
            "required": []
        },
        "annotations": {
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True
        }
    },
    "claim": {
        "fn": tool_claim,
        "desc": "Claim the next available ready task (highest priority first, no blockers). Automatically syncs with git, marks task as in_progress, and notifies other agents. Returns task details including id, title, priority. Use this to get work assigned.",
        "input": {
            "type": "object",
            "properties": {},
            "required": []
        },
        "annotations": {
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True
        }
    },
    "done": {
        "fn": tool_done,
        "desc": "Mark a task as completed and sync changes. Automatically releases all file reservations held by this agent. Notifies other agents of completion. After calling done, restart session for best performance (1 task = 1 session pattern).",
        "input": {
            "type": "object",
            "properties": {
                "id": {
                    "type": "string",
                    "description": "Issue ID to close. If not specified, uses the currently claimed task from this session."
                },
                "msg": {
                    "type": "string",
                    "description": "Completion message describing what was done. Example: 'Implemented login feature with OAuth2'"
                }
            },
            "required": ["id"]
        },
        "annotations": {
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True
        }
    },
    "add": {
        "fn": tool_add,
        "desc": "Create a new issue/task. Use this for any work that takes >2 minutes to avoid losing track. Issues are automatically linked to current task as 'discovered-from'. Supports task, bug, epic, and story types.",
        "input": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Clear, actionable title. Example: 'Fix authentication timeout on slow networks'"
                },
                "typ": {
                    "type": "string",
                    "description": "Issue type: 'task' (default), 'bug', 'epic', or 'story'"
                },
                "pri": {
                    "type": "integer",
                    "description": "Priority 0-4. 0=critical (drop everything), 1=high, 2=normal (default), 3=low, 4=backlog"
                },
                "parent": {
                    "type": "string",
                    "description": "Parent issue ID to link as dependency. Defaults to current task if in a session."
                }
            },
            "required": ["title"]
        },
        "annotations": {
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True
        }
    },

    # Issue queries
    "ls": {
        "fn": tool_ls,
        "desc": "List issues with filtering and pagination. Returns id, title, priority, status for each issue. Use status='open' for active work, 'closed' for completed, 'all' for everything.",
        "input": {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "description": "Filter by status: 'open' (default), 'closed', 'in_progress', or 'all'"
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum issues to return (default: 10, max: 50)"
                },
                "offset": {
                    "type": "integer",
                    "description": "Skip first N issues for pagination (default: 0)"
                }
            },
            "required": []
        },
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True
        }
    },
    "ready": {
        "fn": tool_ready,
        "desc": "Get issues that are ready to work on (no blocking dependencies). These are the tasks that can be claimed immediately. Sorted by priority (0=highest). Use this to see available work.",
        "input": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Maximum issues to return (default: 5, max: 20)"
                }
            },
            "required": []
        },
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True
        }
    },
    "show": {
        "fn": tool_show,
        "desc": "Get full details of a specific issue including title, description, status, priority, dependencies, comments, and history. Use this to understand task requirements before starting work.",
        "input": {
            "type": "object",
            "properties": {
                "id": {
                    "type": "string",
                    "description": "Issue ID to retrieve (e.g., 'abc123')"
                }
            },
            "required": ["id"]
        },
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True
        }
    },

    # Maintenance
    "cleanup": {
        "fn": tool_cleanup,
        "desc": "Remove old closed issues to keep the database lean. Run every few days to maintain <200 open issues. Syncs changes to git after cleanup. Returns count of deleted issues.",
        "input": {
            "type": "object",
            "properties": {
                "days": {
                    "type": "integer",
                    "description": "Delete issues closed more than N days ago (default: 2)"
                }
            },
            "required": []
        },
        "annotations": {
            "readOnlyHint": False,
            "destructiveHint": True,
            "idempotentHint": True,
            "openWorldHint": True
        }
    },
    "doctor": {
        "fn": tool_doctor,
        "desc": "Check and repair Beads database health. Fixes orphaned dependencies, invalid states, and data inconsistencies. Run periodically or when experiencing issues. Returns health report with fixes applied.",
        "input": {
            "type": "object",
            "properties": {},
            "required": []
        },
        "annotations": {
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True
        }
    },
    "sync": {
        "fn": tool_sync,
        "desc": "Synchronize Beads database with git repository. Pulls latest changes from other agents and pushes local changes. Use after making changes or before claiming new work.",
        "input": {
            "type": "object",
            "properties": {},
            "required": []
        },
        "annotations": {
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True
        }
    },

    # File reservations
    "reserve": {
        "fn": tool_reserve,
        "desc": "Reserve files for exclusive editing to prevent conflicts with other agents. Check reservations before editing shared files. Reservations auto-expire after TTL. Returns granted paths and any conflicts with other agents.",
        "input": {
            "type": "object",
            "properties": {
                "paths": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "File paths to reserve. Example: ['src/auth.py', 'src/utils.py']"
                },
                "ttl": {
                    "type": "integer",
                    "description": "Time-to-live in seconds (default: 600 = 10 minutes). Reservation expires after this time."
                },
                "reason": {
                    "type": "string",
                    "description": "Reason for reservation. Example: 'implementing OAuth login flow'"
                }
            },
            "required": ["paths"]
        },
        "annotations": {
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": False
        }
    },
    "release": {
        "fn": tool_release,
        "desc": "Release file reservations so other agents can edit them. Call when done editing files. If no paths specified, releases all reservations held by this agent. Reservations are also auto-released when calling done().",
        "input": {
            "type": "object",
            "properties": {
                "paths": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Specific file paths to release. If empty, releases all reservations held by this agent."
                }
            },
            "required": []
        },
        "annotations": {
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False
        }
    },
    "reservations": {
        "fn": tool_reservations,
        "desc": "List all active file reservations across all agents. Shows who is editing which files and when reservations expire. Use this to check for potential conflicts before editing.",
        "input": {
            "type": "object",
            "properties": {},
            "required": []
        },
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False
        }
    },

    # Messaging
    "msg": {
        "fn": tool_msg,
        "desc": "Send a message to other agents in the workspace. Use for coordination, asking questions, or sharing status updates. Messages are stored in .mail/ and visible to all agents or specific recipients.",
        "input": {
            "type": "object",
            "properties": {
                "subj": {
                    "type": "string",
                    "description": "Message subject. Example: 'Need help with auth module'"
                },
                "body": {
                    "type": "string",
                    "description": "Message body with details"
                },
                "to": {
                    "type": "string",
                    "description": "Recipient agent ID, or 'all' for broadcast (default: 'all')"
                },
                "thread": {
                    "type": "string",
                    "description": "Thread ID for grouping related messages. Defaults to current issue ID."
                },
                "importance": {
                    "type": "string",
                    "description": "Message priority: 'low', 'normal' (default), or 'high'"
                }
            },
            "required": ["subj"]
        },
        "annotations": {
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": False
        }
    },
    "inbox": {
        "fn": tool_inbox,
        "desc": "Retrieve messages from other agents. Returns sender, subject, body snippet, timestamp, and importance. Check inbox periodically for coordination messages and updates.",
        "input": {
            "type": "object",
            "properties": {
                "n": {
                    "type": "integer",
                    "description": "Maximum messages to return (default: 5)"
                },
                "unread": {
                    "type": "boolean",
                    "description": "If true, only return unread messages (default: false)"
                }
            },
            "required": []
        },
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False
        }
    },

    # Status
    "status": {
        "fn": tool_status,
        "desc": "Get overview of workspace status including: open issue count (warn if >200), current task, reserved files count, active agents count, session duration, and completed tasks. Use to understand workspace state.",
        "input": {
            "type": "object",
            "properties": {},
            "required": []
        },
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True
        }
    },
}


# ============================================================================
# MCP PROTOCOL HANDLER
# ============================================================================

async def handle_request(req: dict) -> Optional[dict]:
    """Handle JSON-RPC request."""
    method = req.get("method", "")
    params = req.get("params", {})
    req_id = req.get("id")
    
    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "beads-village", "version": "2.0"},
                "instructions": """Beads Village MCP - Multi-agent issue tracking and coordination.

WORKFLOW (follow this order):
1. init()              - Initialize workspace (REQUIRED first step)
2. claim()             - Get next ready task (auto-assigns to you)
3. reserve(paths=[...]) - Lock files before editing (prevents conflicts)
4. [do your work]      - Implement the task
5. add(title="...")    - Create issues for any work >2 minutes found
6. done(id="...", msg="...") - Complete task, release locks, sync
7. RESTART SESSION     - Best practice: 1 task = 1 session

IMPORTANT RULES:
- ALWAYS run init() before using other tools
- ALWAYS reserve files before editing them
- ALWAYS create issues for discovered work (don't lose track)
- After done(), restart session for best performance
- Keep <200 open issues, run cleanup() every few days

MULTI-AGENT COORDINATION:
- reserve(paths=["src/api.py"]) before editing
- Check reservations() to see what others are editing
- Use msg(subj="...", body="...") to communicate
- Check inbox() periodically for messages

PRIORITY LEVELS: 0=critical, 1=high, 2=normal, 3=low, 4=backlog
ISSUE TYPES: task, bug, epic, story

RESPONSE FORMAT (token-optimized):
- id=issue ID, t=title, p=priority, s=status
- f=from, b=body, ts=timestamp

MULTI-WORKSPACE:
- Each codebase = separate workspace
- init(ws="/path/to/repo") to join specific workspace
- Report workspace path so other agents can join same workspace"""
            }
        }
    
    elif method == "notifications/initialized":
        return None
    
    elif method == "tools/list":
        tools = []
        for k, v in TOOLS.items():
            tool_def = {
                "name": k,
                "description": v["desc"],
                "inputSchema": v["input"]
            }
            # Include annotations if present
            if "annotations" in v:
                tool_def["annotations"] = v["annotations"]
            tools.append(tool_def)
        return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": tools}}
    
    elif method == "tools/call":
        name = params.get("name", "")
        args = params.get("arguments", {})

        if name in TOOLS:
            try:
                result = await TOOLS[name]["fn"](args)
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [{"type": "text", "text": result}]
                    }
                }
            except Exception as e:
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [{
                            "type": "text",
                            "text": j({
                                "error": str(e),
                                "hint": f"Tool '{name}' failed. Try 'doctor' to check workspace health."
                            })
                        }],
                        "isError": True
                    }
                }

        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {
                "code": -32601,
                "message": f"Unknown tool: {name}. Available tools: {', '.join(TOOLS.keys())}"
            }
        }

    elif method == "ping":
        return {"jsonrpc": "2.0", "id": req_id, "result": {}}
    
    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {"code": -32601, "message": f"Unknown method: {method}"}
    }


def run_server():
    """Run MCP server on stdio."""
    import warnings
    warnings.filterwarnings("ignore")
    
    # Windows binary mode
    if sys.platform == "win32":
        import msvcrt
        msvcrt.setmode(sys.stdin.fileno(), os.O_BINARY)
        msvcrt.setmode(sys.stdout.fileno(), os.O_BINARY)
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        while True:
            line = sys.stdin.buffer.readline()
            if not line:
                break
            
            try:
                req = json.loads(line.decode().strip())
            except json.JSONDecodeError:
                continue
            
            resp = loop.run_until_complete(handle_request(req))
            
            if resp:
                out = json.dumps(resp) + "\n"
                sys.stdout.buffer.write(out.encode())
                sys.stdout.buffer.flush()
    finally:
        loop.run_until_complete(loop.shutdown_asyncgens())
        loop.close()


def main():
    run_server()


if __name__ == "__main__":
    main()
