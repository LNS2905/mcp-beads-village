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
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional, Set, List, Dict, Any

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
    p = os.path.join(mail_dir(), f"{ts:.6f}.json")
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
            read_ts = float(open(read_file).read().strip())
        except:
            pass
    
    try:
        files = sorted(os.listdir(d))
        for f in files[-50:]:  # Check last 50 files
            if not f.endswith(".json") or f.startswith("."):
                continue
            try:
                fp = os.path.join(d, f)
                with open(fp, encoding="utf-8") as file:
                    m = json.load(file)
                
                # Filter by recipient
                if m.get("t") not in ["all", AGENT]:
                    continue
                
                # Filter unread if requested
                if unread_only:
                    file_ts = float(f.replace(".json", ""))
                    if file_ts <= read_ts:
                        continue
                
                msgs.append(m)
            except:
                pass
    except:
        pass
    
    # Mark as read
    if msgs:
        with open(read_file, "w") as f:
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
        for f in os.listdir(d):
            if not f.endswith(".json"):
                continue
            fp = os.path.join(d, f)
            try:
                with open(fp) as file:
                    res = json.load(file)
                if datetime.fromisoformat(res["expires"]) < now:
                    os.remove(fp)
                    cleaned += 1
            except:
                pass
    except:
        pass
    
    return cleaned


def get_active_reservations() -> List[dict]:
    """Get all active (non-expired) reservations."""
    cleanup_expired_reservations()
    now = datetime.now()
    d = reservation_dir()
    active = []
    
    try:
        for f in os.listdir(d):
            if not f.endswith(".json"):
                continue
            try:
                with open(os.path.join(d, f)) as fp:
                    res = json.load(fp)
                if datetime.fromisoformat(res["expires"]) > now:
                    active.append(res)
            except:
                pass
    except:
        pass
    
    return active


def check_reservation_conflict(path: str) -> Optional[dict]:
    """Check if path conflicts with existing reservation."""
    cleanup_expired_reservations()
    now = datetime.now()
    res_file = os.path.join(reservation_dir(), f"{path_hash(path)}.json")
    
    if os.path.exists(res_file):
        try:
            with open(res_file) as f:
                existing = json.load(f)
            if datetime.fromisoformat(existing["expires"]) > now:
                if existing["agent"] != AGENT:
                    return existing
        except:
            pass
    
    return None


# ============================================================================
# TOOL IMPLEMENTATIONS
# ============================================================================

async def tool_init(args: dict) -> str:
    """Initialize/join a beads workspace.
    
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
        return j({"error": f"workspace not found: {WS}"})
    
    # Init beads in this workspace
    result = await bd("init")
    if result.get("error") and "already" not in str(result.get("error", "")).lower():
        pass  # May already be initialized
    
    # Ensure mail and reservation dirs
    mail_dir()
    reservation_dir()
    
    # Clean up any expired reservations
    cleanup_expired_reservations()
    
    # Announce agent joining this workspace
    await send_msg("join", f"Agent {AGENT} joined workspace")
    
    return j({"ok": 1, "agent": AGENT, "ws": WS})


async def tool_claim(args: dict) -> str:
    """Claim next ready task (highest priority first)."""
    # Sync first to get latest state
    await bd("sync")
    
    # Get ready issues
    r = await bd("ready")
    
    if not r:
        return j({"ok": 0, "msg": "no ready tasks"})
    
    if isinstance(r, dict) and r.get("error"):
        return j(r)
    
    if isinstance(r, list) and len(r) == 0:
        return j({"ok": 0, "msg": "no ready tasks"})
    
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
        "s": "in_progress"
    })


async def tool_done(args: dict) -> str:
    """Close task and sync."""
    issue_id = args.get("id", S.issue)
    if not issue_id:
        return j({"error": "no issue id"})
    
    msg = args.get("msg", "completed")
    
    # Close issue
    await bd("close", issue_id, "--reason", msg)
    
    # Release any file reservations
    if S.reserved_files:
        for path in list(S.reserved_files):
            res_file = os.path.join(reservation_dir(), f"{path_hash(path)}.json")
            if os.path.exists(res_file):
                try:
                    os.remove(res_file)
                except:
                    pass
        S.reserved_files.clear()
    
    # Sync to share with other agents
    await bd("sync")
    
    # Notify
    await send_msg(f"done:{issue_id}", msg, importance="high")
    
    S.issue = None
    S.done += 1
    
    return j({"ok": 1, "done": S.done, "hint": "restart session for best performance"})


async def tool_add(args: dict) -> str:
    """Create new issue (file issues for anything >2 min)."""
    title = args.get("title", "")
    if not title:
        return j({"error": "title required"})
    
    typ = args.get("typ", "task")
    pri = args.get("pri", 2)
    parent = args.get("parent", S.issue)  # Default to current issue
    
    # Create issue
    r = await bd("create", title, "-t", typ, "-p", str(pri))
    new_id = r.get("id", "")
    
    if not new_id:
        return j({"error": "failed to create", "details": r})
    
    # Link to parent if specified
    if parent and new_id:
        await bd("dep", "add", new_id, parent, "--type", "discovered-from")
    
    return j({"id": new_id, "t": title, "p": pri, "typ": typ})


async def tool_ls(args: dict) -> str:
    """List issues."""
    status = args.get("status", "open")
    limit = args.get("limit", 10)
    
    r = await bd("list", "--status", status)
    
    if not isinstance(r, list):
        return j([])
    
    items = [{
        "id": i.get("id", ""),
        "t": i.get("title", ""),
        "p": i.get("priority", 2),
        "s": i.get("status", "")
    } for i in r[:limit]]
    
    return j(items)


async def tool_ready(args: dict) -> str:
    """Get ready issues (no blockers)."""
    limit = args.get("limit", 5)
    
    r = await bd("ready")
    
    if not isinstance(r, list):
        return j([])
    
    items = [{
        "id": i.get("id", ""),
        "t": i.get("title", ""),
        "p": i.get("priority", 2)
    } for i in r[:limit]]
    
    return j(items)


async def tool_show(args: dict) -> str:
    """Get issue details."""
    issue_id = args.get("id", "")
    if not issue_id:
        return j({"error": "id required"})
    
    return j(await bd("show", issue_id))


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


async def tool_doctor(args: dict) -> str:
    """Check and fix beads health."""
    r = await bd("doctor", "--fix")
    return j(r)


async def tool_sync(args: dict) -> str:
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
    """
    paths = args.get("paths", [])
    if isinstance(paths, str):
        paths = [paths]
    
    if not paths:
        return j({"error": "paths required"})
    
    ttl = args.get("ttl", 600)  # 10 min default
    reason = args.get("reason", S.issue or "editing")
    
    conflicts = []
    grants = []
    now = datetime.now()
    expires = now + timedelta(seconds=ttl)
    
    for path in paths:
        # Check for conflict
        conflict = check_reservation_conflict(path)
        if conflict:
            conflicts.append({
                "path": path,
                "holder": conflict["agent"],
                "reason": conflict.get("reason", ""),
                "expires": conflict["expires"]
            })
            continue
        
        # Grant reservation
        reservation = {
            "path": path,
            "agent": AGENT,
            "reason": reason,
            "created": now.isoformat(),
            "expires": expires.isoformat()
        }
        
        res_file = os.path.join(reservation_dir(), f"{path_hash(path)}.json")
        with open(res_file, "w") as f:
            json.dump(reservation, f)
        
        grants.append(path)
        S.reserved_files.add(path)
    
    return j({
        "granted": grants,
        "conflicts": conflicts,
        "expires": expires.isoformat() if grants else None
    })


async def tool_release(args: dict) -> str:
    """Release file reservations."""
    paths = args.get("paths", [])
    
    # If no paths specified, release all our reservations
    if not paths:
        paths = list(S.reserved_files)
    
    if isinstance(paths, str):
        paths = [paths]
    
    released = []
    
    for path in paths:
        res_file = os.path.join(reservation_dir(), f"{path_hash(path)}.json")
        if os.path.exists(res_file):
            try:
                # Only release if we own it
                with open(res_file) as f:
                    res = json.load(f)
                if res.get("agent") == AGENT:
                    os.remove(res_file)
                    released.append(path)
            except:
                pass
        S.reserved_files.discard(path)
    
    return j({"released": released})


async def tool_reservations(args: dict) -> str:
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


async def tool_status(args: dict) -> str:
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
        "desc": "Init/join workspace",
        "input": {
            "type": "object", 
            "properties": {
                "ws": {"type": "string", "description": "Workspace directory to join"}
            }, 
            "required": []
        }
    },
    "claim": {
        "fn": tool_claim,
        "desc": "Claim next ready task",
        "input": {"type": "object", "properties": {}, "required": []}
    },
    "done": {
        "fn": tool_done,
        "desc": "Close task",
        "input": {
            "type": "object",
            "properties": {
                "id": {"type": "string"},
                "msg": {"type": "string"}
            },
            "required": ["id"]
        }
    },
    "add": {
        "fn": tool_add,
        "desc": "Create issue",
        "input": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "typ": {"type": "string"},
                "pri": {"type": "integer"},
                "parent": {"type": "string"}
            },
            "required": ["title"]
        }
    },
    
    # Issue queries
    "ls": {
        "fn": tool_ls,
        "desc": "List issues",
        "input": {
            "type": "object",
            "properties": {
                "status": {"type": "string"},
                "limit": {"type": "integer"}
            },
            "required": []
        }
    },
    "ready": {
        "fn": tool_ready,
        "desc": "Get ready issues",
        "input": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer"}
            },
            "required": []
        }
    },
    "show": {
        "fn": tool_show,
        "desc": "Get issue details",
        "input": {
            "type": "object",
            "properties": {
                "id": {"type": "string"}
            },
            "required": ["id"]
        }
    },
    
    # Maintenance
    "cleanup": {
        "fn": tool_cleanup,
        "desc": "Cleanup old issues",
        "input": {
            "type": "object",
            "properties": {
                "days": {"type": "integer"}
            },
            "required": []
        }
    },
    "doctor": {
        "fn": tool_doctor,
        "desc": "Check beads health",
        "input": {"type": "object", "properties": {}, "required": []}
    },
    "sync": {
        "fn": tool_sync,
        "desc": "Sync with git",
        "input": {"type": "object", "properties": {}, "required": []}
    },
    
    # File reservations
    "reserve": {
        "fn": tool_reserve,
        "desc": "Reserve files for editing",
        "input": {
            "type": "object",
            "properties": {
                "paths": {"type": "array", "items": {"type": "string"}},
                "ttl": {"type": "integer"},
                "reason": {"type": "string"}
            },
            "required": ["paths"]
        }
    },
    "release": {
        "fn": tool_release,
        "desc": "Release file reservations",
        "input": {
            "type": "object",
            "properties": {
                "paths": {"type": "array", "items": {"type": "string"}}
            },
            "required": []
        }
    },
    "reservations": {
        "fn": tool_reservations,
        "desc": "List active reservations",
        "input": {"type": "object", "properties": {}, "required": []}
    },
    
    # Messaging
    "msg": {
        "fn": tool_msg,
        "desc": "Send message",
        "input": {
            "type": "object",
            "properties": {
                "subj": {"type": "string"},
                "body": {"type": "string"},
                "to": {"type": "string"},
                "thread": {"type": "string"},
                "importance": {"type": "string"}
            },
            "required": ["subj"]
        }
    },
    "inbox": {
        "fn": tool_inbox,
        "desc": "Get messages",
        "input": {
            "type": "object",
            "properties": {
                "n": {"type": "integer"},
                "unread": {"type": "boolean"}
            },
            "required": []
        }
    },
    
    # Status
    "status": {
        "fn": tool_status,
        "desc": "Village status",
        "input": {"type": "object", "properties": {}, "required": []}
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
                "instructions": """Beads Village MCP - Issue tracking for AI agents.

WORKFLOW: init -> claim -> reserve -> [work] -> add -> done -> RESTART

WORKSPACE:
  init()                    # Create in current dir
  init(ws="/path/to/repo")  # Join specific workspace
  REPORT ws path after init so other agents can join

TOOLS:
  claim         Get next ready task
  add(title)    Create issue (for work >2min)
  done(id,msg)  Complete task
  ls/ready      List issues
  reserve/release  File locks (multi-agent)
  cleanup/doctor   Maintenance

MULTI-REPO: Each codebase = separate workspace. Switch with init(ws="...")"""
            }
        }
    
    elif method == "notifications/initialized":
        return None
    
    elif method == "tools/list":
        tools = [{
            "name": k,
            "description": v["desc"],
            "inputSchema": v["input"]
        } for k, v in TOOLS.items()]
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
                        "content": [{"type": "text", "text": j({"error": str(e)})}],
                        "isError": True
                    }
                }
        
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": -32601, "message": f"Unknown tool: {name}"}
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
