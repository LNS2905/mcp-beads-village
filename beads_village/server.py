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

# Daemon client for faster operations (optional)
try:
    from .bd_daemon_client import BdDaemonClient, is_daemon_available, DaemonError, DaemonNotRunningError
    from .agent_registry import get_registry, AgentInfo
except ImportError:
    # Running as standalone script (not as package)
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from bd_daemon_client import BdDaemonClient, is_daemon_available, DaemonError, DaemonNotRunningError
    from agent_registry import get_registry, AgentInfo

# ============================================================================
# CONFIG
# ============================================================================

AGENT = os.environ.get("BEADS_AGENT", f"agent-{os.getpid()}")

# Current workspace - can be changed via init(ws=...)
# Each workspace has its own .beads/, .mail/, .reservations/
WS = os.environ.get("BEADS_WS", os.getcwd())

# Team/Project identifier - groups related workspaces together
# Agents in the same team can see each other's broadcasts
# Different teams are completely isolated
# Default: "default" (all agents in same team)
# Can be changed via init(team=...) at runtime
TEAM = os.environ.get("BEADS_TEAM", "default")

# Base directory for all team data
BEADS_VILLAGE_BASE = os.environ.get(
    "BEADS_VILLAGE_BASE",
    os.path.join(os.path.expanduser("~"), ".beads-village")
)

# Global mail hub - shared across workspaces IN THE SAME TEAM
# Default: ~/.beads-village/{team}/mail
def _get_team_mail_dir(team: str = None):
    """Get mail directory for a team."""
    t = team or TEAM
    return os.path.join(BEADS_VILLAGE_BASE, t, "mail")

# Agent registry - tracks active agents IN THE SAME TEAM
def _get_team_registry_dir(team: str = None):
    """Get agent registry directory for a team."""
    t = team or TEAM
    return os.path.join(BEADS_VILLAGE_BASE, t, "agents")

def get_available_teams() -> List[str]:
    """List all available teams (directories in ~/.beads-village/)."""
    teams = []
    if os.path.isdir(BEADS_VILLAGE_BASE):
        for name in os.listdir(BEADS_VILLAGE_BASE):
            team_dir = os.path.join(BEADS_VILLAGE_BASE, name)
            if os.path.isdir(team_dir):
                teams.append(name)
    return sorted(teams)

# Prefer daemon over CLI for faster operations (set BEADS_USE_DAEMON=0 to disable)
USE_DAEMON = os.environ.get("BEADS_USE_DAEMON", "1") == "1"

# Daemon client instance (lazy initialized)
_daemon_client: Optional[BdDaemonClient] = None

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
    role: Optional[str] = None  # Agent role: fe, be, mobile, devops, qa, etc.
    is_leader: bool = False  # Leader can assign tasks to other agents
    team: str = "default"  # Current team name
    current_task: Optional[str] = None  # Current task ID for registry

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
        # Add --json if command supports it and not already present
        json_cmds = {"list", "ready", "show", "stats", "doctor", "cleanup", "create"}
        if args and args[0] in json_cmds and "--json" not in args:
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


def _get_daemon_client() -> Optional[BdDaemonClient]:
    """Get or create daemon client for current workspace.
    
    Returns:
        BdDaemonClient if daemon is available and enabled, None otherwise
    """
    global _daemon_client
    
    if not USE_DAEMON:
        return None
    
    if not is_daemon_available(WS):
        return None
    
    if _daemon_client is None or _daemon_client.working_dir != WS:
        _daemon_client = BdDaemonClient(working_dir=WS, actor=AGENT)
    
    return _daemon_client


async def bd(*args, timeout: float = 30.0) -> dict:
    """Run bd command - uses daemon if available, falls back to CLI.
    
    The daemon is ~10x faster than CLI for repeated operations.
    """
    # Try daemon first if enabled
    daemon = _get_daemon_client()
    if daemon:
        try:
            return await _bd_via_daemon(daemon, args)
        except (DaemonError, DaemonNotRunningError):
            # Fall back to CLI
            pass
    
    # Fall back to CLI
    return bd_sync(*args, timeout=timeout)


async def _bd_via_daemon(daemon: BdDaemonClient, args: tuple) -> dict:
    """Execute bd command via daemon client.
    
    Maps CLI-style args to daemon RPC calls.
    """
    if not args:
        return {"error": "no command specified"}
    
    cmd = args[0]
    
    if cmd == "init":
        # Init doesn't go through daemon
        raise DaemonNotRunningError("init must use CLI")
    
    elif cmd == "ready":
        limit = 5
        # Parse --limit from args
        for i, arg in enumerate(args):
            if arg == "--limit" and i + 1 < len(args):
                try:
                    limit = int(args[i + 1])
                except ValueError:
                    pass
        
        issues = await daemon.ready(limit=limit)
        return issues if isinstance(issues, list) else [issues] if issues else []
    
    elif cmd == "list":
        status = None
        limit = 10
        for i, arg in enumerate(args):
            if arg == "--status" and i + 1 < len(args):
                status = args[i + 1]
            elif arg == "--limit" and i + 1 < len(args):
                try:
                    limit = int(args[i + 1])
                except ValueError:
                    pass
        
        issues = await daemon.list_issues(status=status, limit=limit)
        return issues if isinstance(issues, list) else [issues] if issues else []
    
    elif cmd == "show" and len(args) > 1:
        issue_id = args[1]
        return await daemon.show(issue_id)
    
    elif cmd == "create":
        # Parse create args
        title = args[1] if len(args) > 1 else ""
        issue_type = "task"
        priority = 2
        description = ""
        deps = []
        has_labels = False
        
        i = 2
        while i < len(args):
            arg = args[i]
            if arg in ("-t", "--type") and i + 1 < len(args):
                issue_type = args[i + 1]
                i += 2
            elif arg in ("-p", "--priority") and i + 1 < len(args):
                try:
                    priority = int(args[i + 1])
                except ValueError:
                    pass
                i += 2
            elif arg in ("-d", "--description") and i + 1 < len(args):
                description = args[i + 1]
                i += 2
            elif arg == "--deps" and i + 1 < len(args):
                deps.append(args[i + 1])
                i += 2
            elif arg in ("--labels", "-l") and i + 1 < len(args):
                # --labels is comma-separated for create command
                has_labels = True
                i += 2
            elif arg == "--json":
                i += 1  # Skip
            else:
                i += 1
        
        # If labels are used, fall back to CLI (daemon may not support labels yet)
        if has_labels:
            raise DaemonNotRunningError("Labels not supported by daemon, falling back to CLI")
        
        return await daemon.create(
            title=title,
            issue_type=issue_type,
            priority=priority,
            description=description,
            deps=deps if deps else None,
        )
    
    elif cmd == "update" and len(args) > 1:
        issue_id = args[1]
        status = None
        priority = None
        has_labels = False
        
        for i, arg in enumerate(args):
            if arg == "--status" and i + 1 < len(args):
                status = args[i + 1]
            elif arg in ("-p", "--priority") and i + 1 < len(args):
                try:
                    priority = int(args[i + 1])
                except ValueError:
                    pass
            elif arg in ("--add-label", "--remove-label", "--set-labels"):
                # Any label-related flag means we need CLI fallback
                has_labels = True
        
        # If labels are used, fall back to CLI (daemon may not support labels yet)
        if has_labels:
            raise DaemonNotRunningError("Labels not supported by daemon, falling back to CLI")
        
        return await daemon.update(issue_id, status=status, priority=priority)
    
    elif cmd == "close" and len(args) > 1:
        issue_id = args[1]
        reason = "Completed"
        for i, arg in enumerate(args):
            if arg == "--reason" and i + 1 < len(args):
                reason = args[i + 1]
        
        return await daemon.close(issue_id, reason=reason)
    
    elif cmd == "sync":
        return await daemon.sync()
    
    elif cmd == "stats":
        return await daemon.stats()
    
    elif cmd == "dep" and len(args) > 3 and args[1] == "add":
        from_id = args[2]
        to_id = args[3]
        dep_type = "blocks"
        for i, arg in enumerate(args):
            if arg == "--type" and i + 1 < len(args):
                dep_type = args[i + 1]
        
        await daemon.add_dependency(from_id, to_id, dep_type)
        return {"ok": 1}
    
    else:
        # Command not supported by daemon, fall back to CLI
        raise DaemonNotRunningError(f"Command '{cmd}' not supported by daemon")


def ensure_dir(base: str, name: str) -> str:
    """Ensure directory exists and return path."""
    d = os.path.join(base, name)
    os.makedirs(d, exist_ok=True)
    return d


def global_mail_dir() -> str:
    """Global mail directory - shared across ALL workspaces IN CURRENT TEAM.
    
    Messages sent here are visible to agents in any workspace within the team.
    Used for cross-workspace coordination.
    """
    d = _get_team_mail_dir(TEAM)
    os.makedirs(d, exist_ok=True)
    return d


def agent_registry_dir() -> str:
    """Agent registry directory - tracks active agents IN CURRENT TEAM.
    
    Each agent registers with: agent_id, workspace, capabilities, last_seen.
    """
    d = _get_team_registry_dir(TEAM)
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
                   thread_id: str = "", importance: str = "normal",
                   global_broadcast: bool = False) -> dict:
    """Send message to other agents.
    
    Args:
        subj: Message subject
        body: Message body
        to: Recipient ('all' for broadcast, or specific agent ID)
        thread_id: Thread ID for grouping messages
        importance: 'low', 'normal', or 'high'
        global_broadcast: If True, send to global mail hub (visible to ALL agents across ALL workspaces)
    """
    msg = {
        "f": AGENT,
        "t": to,
        "s": subj,
        "b": body,
        "ts": datetime.now().isoformat(),
        "thread": thread_id or S.issue or "",
        "imp": importance,
        "issue": S.issue,
        "ws": WS,  # Include source workspace
    }
    ts = datetime.now().timestamp()
    unique = uuid.uuid4().hex[:6]
    
    # Choose directory: local workspace or global hub
    target_dir = global_mail_dir() if global_broadcast else mail_dir()
    p = os.path.join(target_dir, f"{ts:.6f}_{unique}.json")
    
    with open(p, "w", encoding="utf-8") as f:
        json.dump(msg, f)
    
    return {"sent": 1, "global": global_broadcast}


async def recv_msgs(n: int = 5, unread_only: bool = False, 
                    include_global: bool = True) -> List[dict]:
    """Receive messages from other agents.
    
    Args:
        n: Maximum messages to return
        unread_only: Only return unread messages
        include_global: Also check global mail hub for cross-workspace messages
    """
    msgs = []
    
    # Collect from directories
    dirs_to_check = [mail_dir()]
    if include_global:
        dirs_to_check.append(global_mail_dir())
    
    for d in dirs_to_check:
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
                    
                    # Mark if from global hub
                    if d == global_mail_dir():
                        m["_global"] = True
                    
                    msgs.append(m)
                except (json.JSONDecodeError, OSError):
                    pass
        except OSError:
            pass
        
        # Update read timestamp for this directory
        if msgs:
            try:
                with open(read_file, "w", encoding="utf-8") as f:
                    f.write(str(datetime.now().timestamp()))
            except OSError:
                pass
    
    # Sort by timestamp and return last n
    msgs.sort(key=lambda x: x.get("ts", ""))
    return msgs[-n:]


# ============================================================================
# AGENT REGISTRY FUNCTIONS
# ============================================================================

def register_agent(capabilities: List[str] = None) -> dict:
    """Register this agent in the team registry.
    
    Other agents in the same team can discover us and see what workspace we're in.
    """
    reg_file = os.path.join(agent_registry_dir(), f"{AGENT}.json")
    
    registration = {
        "agent": AGENT,
        "ws": WS,
        "team": TEAM,
        "capabilities": capabilities or ["general"],
        "registered": datetime.now().isoformat(),
        "last_seen": datetime.now().isoformat(),
    }
    
    with open(reg_file, "w", encoding="utf-8") as f:
        json.dump(registration, f)
    
    return registration


def update_agent_heartbeat() -> None:
    """Update last_seen timestamp for this agent."""
    reg_file = os.path.join(agent_registry_dir(), f"{AGENT}.json")
    
    if os.path.exists(reg_file):
        try:
            with open(reg_file, encoding="utf-8") as f:
                reg = json.load(f)
            reg["last_seen"] = datetime.now().isoformat()
            with open(reg_file, "w", encoding="utf-8") as f:
                json.dump(reg, f)
        except (json.JSONDecodeError, OSError):
            pass


def get_active_agents(max_age_minutes: int = 30) -> List[dict]:
    """Get list of active agents across all workspaces.
    
    Args:
        max_age_minutes: Consider agent inactive if not seen within this time
    """
    agents = []
    cutoff = datetime.now() - timedelta(minutes=max_age_minutes)
    
    try:
        for fname in os.listdir(agent_registry_dir()):
            if not fname.endswith(".json"):
                continue
            try:
                with open(os.path.join(agent_registry_dir(), fname), encoding="utf-8") as f:
                    reg = json.load(f)
                last_seen = datetime.fromisoformat(reg.get("last_seen", "2000-01-01"))
                if last_seen > cutoff:
                    agents.append(reg)
            except (json.JSONDecodeError, OSError, ValueError):
                pass
    except OSError:
        pass
    
    return agents


def discover_workspaces() -> List[dict]:
    """Discover all workspaces from registered agents in the same team.
    
    Returns unique workspaces with their active agent counts.
    """
    agents = get_active_agents()
    ws_map = {}
    
    for agent in agents:
        ws = agent.get("ws", "")
        if ws:
            if ws not in ws_map:
                ws_map[ws] = {"ws": ws, "agents": [], "count": 0, "team": TEAM}
            ws_map[ws]["agents"].append(agent.get("agent", "unknown"))
            ws_map[ws]["count"] += 1
    
    return list(ws_map.values())


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
        team: Team/project name to join. Can switch teams at runtime.
        role: Agent role (fe/be/mobile/devops/qa/etc). Used for task filtering.
        leader: If True, this agent can assign tasks to others.
        start_tui: If True and leader, auto-launch bv TUI dashboard for human monitoring.
    """
    global WS, TEAM

    # Switch to specified workspace
    if args.get("ws"):
        WS = os.path.abspath(args["ws"])

    # Switch to specified team (allows runtime team switching!)
    if args.get("team"):
        TEAM = args["team"]
    
    # Set agent role for task filtering
    if args.get("role"):
        S.role = args["role"].lower().strip()
    
    # Set leader flag
    if args.get("leader"):
        S.is_leader = bool(args["leader"])

    # Ensure workspace directory exists
    if not os.path.isdir(WS):
        # List available teams as hint
        available_teams = get_available_teams()
        return j({
            "error": f"workspace not found: {WS}",
            "hint": "Provide a valid directory path with ws parameter, or ensure current directory exists.",
            "available_teams": available_teams
        })

    # Init beads in this workspace
    result = await bd("init")
    if result.get("error"):
        err_msg = str(result.get("error", ""))
        if "already" not in err_msg.lower():
            return j({
                "error": err_msg,
                "hint": "Ensure 'bd' CLI is installed: go install github.com/steveyegge/beads/cmd/bd@latest"
            })

    # Ensure mail and reservation dirs
    mail_dir()
    reservation_dir()

    # Clean up any expired reservations
    cleanup_expired_reservations()
    
    # Register agent in global registry (for cross-workspace discovery)
    # Include role in capabilities for other agents to see
    capabilities = ["general"]
    if S.role:
        capabilities.append(S.role)
    if S.is_leader:
        capabilities.append("leader")
    register_agent(capabilities=capabilities)
    
    # Register agent in new agent registry for tracking
    S.team = TEAM  # Store team in state
    registry = get_registry(WS)
    agent_info = AgentInfo(
        agent_id=AGENT,
        team=S.team,
        role=S.role,
        workspace=WS,
        is_leader=S.is_leader,
        current_task=S.current_task
    )
    registry.register(agent_info)

    # Announce agent joining this workspace (local)
    role_info = f" (role={S.role})" if S.role else ""
    leader_info = " [LEADER]" if S.is_leader else ""
    await send_msg("join", f"Agent {AGENT}{role_info}{leader_info} joined workspace {WS}")
    
    # Also announce globally so other workspaces know
    await send_msg("join", f"Agent {AGENT}{role_info}{leader_info} joined workspace {WS}", global_broadcast=True)

    # Get available teams for user reference
    available_teams = get_available_teams()

    # Auto-start TUI if leader and start_tui is True
    tui_started = False
    if S.is_leader and args.get("start_tui"):
        try:
            import subprocess
            import sys
            # Start Textual dashboard in background process
            subprocess.Popen(
                [sys.executable, "-m", "beads_village.dashboard", WS],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0
            )
            tui_started = True
        except Exception:
            pass  # Silently ignore if dashboard can't start

    return j({
        "ok": 1,
        "agent": AGENT,
        "ws": WS,
        "team": TEAM,
        "role": S.role,
        "is_leader": S.is_leader,
        "tui_started": tui_started,
        "available_teams": available_teams,
        "hint": "Workspace ready. Use 'claim' to get a task, or 'ready' to see available tasks."
    })


async def tool_claim(_args: dict) -> str:
    """Claim next ready task (highest priority first) with actionable errors.
    
    If agent has a role set, will prioritize tasks with matching tags.
    Tasks with tags that don't match agent's role are filtered out.
    """
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

    # Filter by role if agent has one
    issues = r if isinstance(r, list) else [r]
    
    if S.role:
        # Filter: only tasks with matching tag OR tasks without any tag
        matching_issues = []
        for issue in issues:
            tags = issue.get("tags", []) or []
            # Accept if: no tags, or our role is in tags
            if not tags or S.role in [t.lower() for t in tags]:
                matching_issues.append(issue)
        
        if not matching_issues:
            return j({
                "ok": 0,
                "msg": f"no tasks for role '{S.role}'",
                "hint": f"No tasks with tag '{S.role}' or untagged tasks. Use 'ready' to see all available tasks.",
                "total_ready": len(issues)
            })
        issues = matching_issues

    # Get first matching issue
    issue = issues[0]
    issue_id = issue.get("id", "")

    # Update status (agents claim, not assigned per Steve's article)
    await bd("update", issue_id, "--status", "in_progress")

    # Track in session state
    S.issue = issue_id
    S.current_task = issue_id
    
    # Update agent registry with current task
    registry = get_registry(WS)
    registry.update_task(AGENT, issue_id)

    # Notify other agents
    role_info = f" [{S.role}]" if S.role else ""
    await send_msg(f"claimed:{issue_id}", f"{issue.get('title', '')}{role_info}", importance="high")

    return j({
        "id": issue_id,
        "t": issue.get("title", ""),
        "p": issue.get("priority", 2),
        "s": "in_progress",
        "tags": issue.get("tags", []),
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
    S.current_task = None
    S.done += 1
    
    # Update agent registry - clear current task
    registry = get_registry(WS)
    registry.update_task(AGENT, None)

    return j({
        "ok": 1,
        "done": S.done,
        "hint": "Task completed. Restart session for best performance (1 task = 1 session pattern)."
    })


async def tool_add(args: dict) -> str:
    """Create new issue (file issues for anything >2 min) with actionable errors.
    
    IMPORTANT: Always provide a meaningful description with context about:
    - Why this issue exists (problem statement or need)
    - What needs to be done (scope and approach)
    - How you discovered it (if applicable)
    
    Use tags to assign tasks to specific roles (fe, be, mobile, devops, qa, etc).
    Agents with matching roles will automatically pick up these tasks.
    """
    title = args.get("title", "")
    if not title:
        return j({
            "error": "title required",
            "hint": "Provide a clear, actionable title. Example: 'Fix login timeout on slow networks'"
        })

    typ = args.get("typ", "task")
    if typ not in ("task", "bug", "feature", "epic", "chore"):
        return j({
            "error": f"invalid type: {typ}",
            "hint": "Valid types: 'task' (default), 'bug', 'feature', 'epic', 'chore'"
        })

    pri = args.get("pri", 2)
    if not isinstance(pri, int) or pri < 0 or pri > 4:
        return j({
            "error": f"invalid priority: {pri}",
            "hint": "Priority must be 0-4. 0=critical, 1=high, 2=normal (default), 3=low, 4=backlog"
        })

    description = args.get("desc", "")
    deps = args.get("deps", [])
    parent = args.get("parent", S.issue)  # Default to current issue
    tags = args.get("tags", [])  # Role tags: fe, be, mobile, devops, qa, etc.
    
    # Normalize tags to lowercase
    if isinstance(tags, str):
        tags = [tags]
    tags = [t.lower().strip() for t in tags if t]

    # Build command arguments
    cmd_args = ["create", title, "-t", typ, "-p", str(pri), "--json"]
    
    # Add description if provided
    if description:
        cmd_args.extend(["--description", description])
    
    # Add tags as labels (bd CLI uses --labels/-l, not --tag)
    if tags:
        cmd_args.extend(["--labels", ",".join(tags)])
    
    # Add dependencies if provided (format: "discovered-from:bd-123" or just "bd-123")
    if deps:
        for dep in deps:
            cmd_args.extend(["--deps", dep])
    
    # Create issue
    r = await bd(*cmd_args)

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

    # Link to parent if specified and no deps provided (for backward compatibility)
    if parent and new_id and not deps:
        await bd("dep", "add", new_id, parent, "--type", "discovered-from")

    return j({
        "id": new_id,
        "t": title,
        "p": pri,
        "typ": typ,
        "tags": tags,
        "desc": description[:100] + "..." if len(description) > 100 else description,
        "parent": parent if not deps else None,
        "deps": deps,
        "hint": f"Issue created. Use 'show {new_id}' to see details."
    })


async def tool_assign(args: dict) -> str:
    """Assign a task to a specific role or agent (leader only).
    
    Leaders can use this to explicitly assign tasks to specific roles.
    This adds/updates the tags on the issue.
    
    Args:
        id: Issue ID to assign
        role: Role to assign to (fe, be, mobile, devops, qa, etc)
        notify: If True, broadcast assignment notification (default: True)
    """
    if not S.is_leader:
        return j({
            "error": "permission denied",
            "hint": "Only leaders can assign tasks. Use init(leader=true) to become a leader."
        })
    
    issue_id = args.get("id", "")
    if not issue_id:
        return j({
            "error": "id required",
            "hint": "Provide the issue ID to assign"
        })
    
    role = args.get("role", "")
    if not role:
        return j({
            "error": "role required",
            "hint": "Provide a role to assign to (fe, be, mobile, devops, qa, etc)"
        })
    
    role = role.lower().strip()
    notify = args.get("notify", True)
    
    # Get current issue to verify it exists
    issue = await bd("show", issue_id)
    if isinstance(issue, dict) and issue.get("error"):
        return j({
            "error": issue["error"],
            "hint": f"Issue '{issue_id}' not found. Use 'ls' to see available issues."
        })
    
    # Add label to issue (bd CLI uses --add-label, not --tag)
    r = await bd("update", issue_id, "--add-label", role)
    if isinstance(r, dict) and r.get("error"):
        # Fallback: try alternative approach if update --add-label not supported
        # We can store assignment in description or use a workaround
        pass
    
    # Notify team about assignment
    if notify:
        title = issue.get("title", issue_id) if isinstance(issue, dict) else issue_id
        await send_msg(
            f"assigned:{issue_id}",
            f"Task '{title}' assigned to role: {role}",
            importance="high",
            global_broadcast=True
        )
    
    return j({
        "ok": 1,
        "id": issue_id,
        "assigned_to": role,
        "hint": f"Task assigned to '{role}'. Agents with this role will see it when they claim()."
    })


async def tool_ls(args: dict) -> str:
    """List issues with pagination.
    
    Consolidated tool that supports:
    - status: open|closed|in_progress|ready|all
    - status='ready' returns issues with no blockers (replaces separate 'ready' tool)
    """
    status = args.get("status", "open")
    limit = min(args.get("limit", 10), 50)  # Cap at 50
    offset = args.get("offset", 0)

    # Handle 'ready' status specially - uses bd ready command
    if status == "ready":
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
                "offset": offset,
                "has_more": False
            })
        
        total = len(r)
        paginated = r[offset:offset + limit]
        
        items = [{
            "id": i.get("id", ""),
            "t": i.get("title", ""),
            "p": i.get("priority", 2),
            "s": "ready"  # Mark as ready
        } for i in paginated]
        
        return j({
            "items": items,
            "total": total,
            "count": len(items),
            "offset": offset,
            "has_more": offset + limit < total,
            "next_offset": offset + limit if offset + limit < total else None
        })

    # Normal status filtering
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
    global_broadcast = args.get("global", False)
    
    result = await send_msg(subj, body, to, thread_id, importance, global_broadcast)
    
    return j({"ok": 1, "global": global_broadcast})


async def tool_inbox(args: dict) -> str:
    """Get messages from other agents."""
    n = args.get("n", 5)
    unread = args.get("unread", False)
    include_global = args.get("global", True)  # Default: include global messages
    
    msgs = await recv_msgs(n, unread, include_global)
    
    items = [{
        "f": m.get("f", ""),
        "s": m.get("s", ""),
        "b": m.get("b", "")[:100],
        "ts": m.get("ts", ""),
        "imp": m.get("imp", "normal"),
        "ws": m.get("ws", ""),  # Source workspace
        "global": m.get("_global", False),  # Is from global hub
    } for m in msgs]
    
    return j(items)


async def tool_status(args: dict) -> str:
    """Get village status overview.
    
    Consolidated tool that includes:
    - Basic workspace status (always)
    - Agent/team discovery (include_agents=true)
    - bv tool availability (include_bv=true)
    
    Replaces: discover, bv_status (now merged here)
    """
    include_agents = args.get("include_agents", False)
    include_bv = args.get("include_bv", False)
    
    # Update our heartbeat
    update_agent_heartbeat()
    
    # Get open issues count
    lst = await bd("list", "--status", "open")
    open_count = len(lst) if isinstance(lst, list) else 0
    
    # Get active reservations (local workspace)
    reservations = get_active_reservations()
    
    # Session duration
    mins = (datetime.now() - S.start).total_seconds() / 60
    
    result = {
        "agent": AGENT,
        "ws": WS,
        "team": TEAM,
        "open": open_count,
        "warn": open_count > 200,
        "current": S.issue,
        "reserved": len(S.reserved_files),
        "local_agents": len(set(r.get("agent", "") for r in reservations)),
        "min": round(mins, 1),
        "done": S.done
    }
    
    # Include agent/team discovery info (replaces discover tool)
    if include_agents:
        all_agents = get_active_agents()
        workspaces = discover_workspaces()
        result["agents"] = [{
            "agent": a.get("agent", ""),
            "ws": a.get("ws", ""),
            "capabilities": a.get("capabilities", []),
            "last_seen": a.get("last_seen", ""),
        } for a in all_agents]
        result["workspaces"] = workspaces
        result["team_agents"] = len(all_agents)
        result["total_workspaces"] = len(workspaces)
    else:
        # Just include counts for quick overview
        all_agents = get_active_agents()
        workspaces = discover_workspaces()
        result["team_agents"] = len(all_agents)
        result["workspaces"] = len(workspaces)
    
    # Include bv tool status (replaces bv_status tool)
    if include_bv:
        bv = _get_bv()
        if bv.is_available:
            result["bv"] = {
                "available": True,
                "version": bv.get_version(),
                "path": bv.get_bv_path()
            }
        else:
            result["bv"] = {
                "available": False,
                "hint": "Install bv: go install github.com/Dicklesworthstone/beads_viewer/cmd/bv@latest"
            }
    
    return j(result)


# ============================================================================
# TOOL REGISTRY
# ============================================================================

TOOLS = {
    # Core workflow
    "init": {
        "fn": tool_init,
        "desc": "Join workspace. MUST call first. Returns agent ID, workspace, team.",
        "input": {
            "type": "object",
            "properties": {
                "ws": {"type": "string", "description": "Workspace path (default: cwd)"},
                "team": {"type": "string", "description": "Team name to join (default: 'default')"},
                "role": {"type": "string", "description": "Agent role (fe/be/mobile/devops/qa). Used for task filtering."},
                "leader": {"type": "boolean", "description": "If true, agent can assign tasks to others."},
                "start_tui": {"type": "boolean", "description": "If true and leader, auto-launch bv TUI dashboard."}
            },
            "required": []
        },
        "annotations": {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True}
    },
    "claim": {
        "fn": tool_claim,
        "desc": "Claim next ready task. Filters by role if set. Auto-syncs, marks in_progress.",
        "input": {"type": "object", "properties": {}, "required": []},
        "annotations": {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": True}
    },
    "done": {
        "fn": tool_done,
        "desc": "Complete task. Auto-releases files, syncs. Restart session after.",
        "input": {
            "type": "object",
            "properties": {
                "id": {"type": "string", "description": "Issue ID to close"},
                "msg": {"type": "string", "description": "What was done"}
            },
            "required": ["id"]
        },
        "annotations": {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True}
    },
    "add": {
        "fn": tool_add,
        "desc": "Create issue. Use tags to assign to roles (fe/be/mobile/etc).",
        "input": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Actionable title"},
                "desc": {"type": "string", "description": "Why/what/how context"},
                "typ": {"type": "string", "description": "task|bug|feature|epic|chore"},
                "pri": {"type": "integer", "description": "0=critical,1=high,2=normal,3=low,4=backlog"},
                "tags": {"type": "array", "items": {"type": "string"}, "description": "Role tags: fe,be,mobile,devops,qa"},
                "deps": {"type": "array", "items": {"type": "string"}, "description": "type:id format"},
                "parent": {"type": "string", "description": "Parent issue ID"}
            },
            "required": ["title"]
        },
        "annotations": {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": True}
    },
    "assign": {
        "fn": tool_assign,
        "desc": "Assign task to role (leader only). Adds tag and notifies team.",
        "input": {
            "type": "object",
            "properties": {
                "id": {"type": "string", "description": "Issue ID to assign"},
                "role": {"type": "string", "description": "Role to assign: fe,be,mobile,devops,qa"},
                "notify": {"type": "boolean", "description": "Broadcast notification (default: true)"}
            },
            "required": ["id", "role"]
        },
        "annotations": {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True}
    },
    # Issue queries
    "ls": {
        "fn": tool_ls,
        "desc": "List issues. Use status='ready' for claimable tasks (no blockers).",
        "input": {
            "type": "object",
            "properties": {
                "status": {"type": "string", "description": "open|closed|in_progress|ready|all"},
                "limit": {"type": "integer", "description": "Max results (default:10)"},
                "offset": {"type": "integer", "description": "Skip N issues"}
            },
            "required": []
        },
        "annotations": {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True}
    },
    "show": {
        "fn": tool_show,
        "desc": "Get full issue details.",
        "input": {
            "type": "object",
            "properties": {"id": {"type": "string", "description": "Issue ID"}},
            "required": ["id"]
        },
        "annotations": {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True}
    },
    # Maintenance
    "cleanup": {
        "fn": tool_cleanup,
        "desc": "Remove old closed issues. Run every few days.",
        "input": {
            "type": "object",
            "properties": {"days": {"type": "integer", "description": "Delete closed >N days (default:2)"}},
            "required": []
        },
        "annotations": {"readOnlyHint": False, "destructiveHint": True, "idempotentHint": True, "openWorldHint": True}
    },
    "doctor": {
        "fn": tool_doctor,
        "desc": "Check/repair database health.",
        "input": {"type": "object", "properties": {}, "required": []},
        "annotations": {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True}
    },
    "sync": {
        "fn": tool_sync,
        "desc": "Sync with git. Pull/push changes.",
        "input": {"type": "object", "properties": {}, "required": []},
        "annotations": {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True}
    },
    # File reservations
    "reserve": {
        "fn": tool_reserve,
        "desc": "Lock files for editing. Prevents conflicts.",
        "input": {
            "type": "object",
            "properties": {
                "paths": {"type": "array", "items": {"type": "string"}, "description": "Files to lock"},
                "ttl": {"type": "integer", "description": "Seconds until expiry (default:600)"},
                "reason": {"type": "string", "description": "Why reserving"}
            },
            "required": ["paths"]
        },
        "annotations": {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": False}
    },
    "release": {
        "fn": tool_release,
        "desc": "Unlock files. Auto-released on done().",
        "input": {
            "type": "object",
            "properties": {"paths": {"type": "array", "items": {"type": "string"}, "description": "Files to unlock (empty=all)"}},
            "required": []
        },
        "annotations": {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False}
    },
    "reservations": {
        "fn": tool_reservations,
        "desc": "List active file locks. Check before editing.",
        "input": {"type": "object", "properties": {}, "required": []},
        "annotations": {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False}
    },
    # Messaging
    "msg": {
        "fn": tool_msg,
        "desc": "Send message. Use global=true + to='all' for team-wide broadcast.",
        "input": {
            "type": "object",
            "properties": {
                "subj": {"type": "string", "description": "Subject"},
                "body": {"type": "string", "description": "Message body"},
                "to": {"type": "string", "description": "Recipient or 'all'"},
                "thread": {"type": "string", "description": "Thread ID"},
                "importance": {"type": "string", "description": "low|normal|high"},
                "global": {"type": "boolean", "description": "Send to all workspaces"}
            },
            "required": ["subj"]
        },
        "annotations": {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": False}
    },
    "inbox": {
        "fn": tool_inbox,
        "desc": "Get messages. Includes global by default.",
        "input": {
            "type": "object",
            "properties": {
                "n": {"type": "integer", "description": "Max messages (default:5)"},
                "unread": {"type": "boolean", "description": "Unread only"},
                "global": {"type": "boolean", "description": "Include cross-workspace"}
            },
            "required": []
        },
        "annotations": {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False}
    },
    # Status (consolidated: replaces discover, bv_status)
    "status": {
        "fn": tool_status,
        "desc": "Workspace overview. Use include_agents=true for team discovery, include_bv=true for bv status.",
        "input": {
            "type": "object",
            "properties": {
                "include_agents": {"type": "boolean", "description": "Include detailed agent/workspace info (replaces discover)"},
                "include_bv": {"type": "boolean", "description": "Include bv tool availability (replaces bv_status)"}
            },
            "required": []
        },
        "annotations": {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True}
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
                "instructions": """Beads Village MCP - Multi-agent task coordination (21 tools).

WORKFLOW: init() → claim() → reserve() → work → done() → restart session

RULES: init first | reserve before edit | add issues for >2min work

RESPONSE: id=ID, t=title, p=pri(0-4), s=status, f=from, b=body

TEAMS: init(team="x") to join | msg(global=true,to="all") for broadcast

CONSOLIDATED: broadcast→msg(global=true) | discover→status(include_agents=true) | ready→ls(status="ready")"""
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


# ============================================================================
# Beads Viewer Integration Tools (optional - requires bv binary)
# ============================================================================

from beads_village.bv_manager import get_bv_manager, BvManager


def _get_workspace() -> str:
    """Get current workspace path"""
    return WS


def _get_bv() -> BvManager:
    """Get BvManager for current workspace"""
    return get_bv_manager(str(_get_workspace()))


async def tool_bv_insights(_args: dict) -> str:
    """Graph analysis: bottlenecks, keystones, cycles, PageRank, Betweenness.
    
    Returns pre-computed graph metrics for AI decision making.
    Requires bv binary (install: go install github.com/Dicklesworthstone/beads_viewer/cmd/bv@latest)
    """
    bv = _get_bv()
    if not bv.is_available:
        return j({'error': 'bv not available', 'hint': 'Install bv for graph analysis'})
    return j(bv.get_insights())


async def tool_bv_plan(_args: dict) -> str:
    """Parallel execution plan with tracks.
    
    Returns issue tracks that can be worked on in parallel.
    Uses Union-Find algorithm to detect independent work streams.
    """
    bv = _get_bv()
    if not bv.is_available:
        return j({'error': 'bv not available', 'hint': 'Install bv for execution planning'})
    return j(bv.get_plan())


async def tool_bv_priority(args: dict) -> str:
    """Priority recommendations based on graph analysis.
    
    Ranks issues by impact score combining:
    - PageRank (30%): Recursive importance
    - Betweenness (30%): Bottleneck detection  
    - BlockerRatio (20%): How many issues unblocked
    - Staleness (10%): Time since last update
    - Priority (10%): Manual priority setting
    
    Args:
        limit: Max issues to return (default 5)
    """
    limit = args.get("limit", 5)
    bv = _get_bv()
    if not bv.is_available:
        return j({'error': 'bv not available', 'hint': 'Install bv for priority recommendations'})
    return j(bv.get_priority(limit))


async def tool_bv_diff(args: dict) -> str:
    """Compare issue changes between git revisions.
    
    Args:
        since: Start revision (commit SHA, tag, branch, or date like '3 days ago')
        as_of: End revision (default: current state)
    
    Examples:
        bv_diff(since='HEAD~5')  # Changes in last 5 commits
        bv_diff(since='v1.0.0')  # Changes since tag
        bv_diff(since='3 days ago')  # Changes in last 3 days
    """
    since = args.get("since")
    as_of = args.get("as_of")
    bv = _get_bv()
    if not bv.is_available:
        return j({'error': 'bv not available', 'hint': 'Install bv for diff analysis'})
    return j(bv.get_diff(since, as_of))


async def tool_bv_tui(args: dict) -> str:
    """Launch Beads Viewer TUI dashboard in new terminal.
    
    Opens interactive TUI for human operators to view:
    - Kanban board (Open/In Progress/Blocked/Closed)
    - Dependency graph visualization
    - Insights dashboard (bottlenecks, keystones, cycles)
    - Actionable view (what to work on next)
    
    Args:
        recipe: Filter preset (default, actionable, recent, blocked, high-impact, stale)
    """
    recipe = args.get("recipe")
    bv = _get_bv()
    if not bv.is_available:
        return j({'error': 'bv not available', 'hint': 'Install bv for TUI dashboard'})
    return j(bv.start_tui(recipe))


async def tool_bv_status(_args: dict) -> str:
    """Check bv availability and version.
    
    Returns bv binary status and version info.
    """
    bv = _get_bv()
    if not bv.is_available:
        return j({
            'available': False,
            'hint': 'Install bv: go install github.com/Dicklesworthstone/beads_viewer/cmd/bv@latest'
        })
    return j({
        'available': True,
        'version': bv.get_version(),
        'path': bv.get_bv_path()
    })


# Add bv tools to TOOLS registry
TOOLS.update({
    # Beads Viewer Integration
    "bv_insights": {
        "fn": tool_bv_insights,
        "desc": "Graph analysis: bottlenecks, keystones, cycles, PageRank, Betweenness.",
        "input": {"type": "object", "properties": {}, "required": []},
        "annotations": {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True}
    },
    "bv_plan": {
        "fn": tool_bv_plan,
        "desc": "Parallel execution plan with tracks.",
        "input": {"type": "object", "properties": {}, "required": []},
        "annotations": {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True}
    },
    "bv_priority": {
        "fn": tool_bv_priority,
        "desc": "Priority recommendations based on graph analysis.",
        "input": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Max issues to return (default 5)"}
            },
            "required": []
        },
        "annotations": {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True}
    },
    "bv_diff": {
        "fn": tool_bv_diff,
        "desc": "Compare issue changes between git revisions.",
        "input": {
            "type": "object",
            "properties": {
                "since": {"type": "string", "description": "Start revision (commit SHA, tag, branch, or date)"},
                "as_of": {"type": "string", "description": "End revision (default: current state)"}
            },
            "required": []
        },
        "annotations": {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True}
    },
    # NOTE: bv_tui removed - use village_tui instead (unified dashboard with all features)
    # NOTE: bv_status removed - use status(include_bv=true) instead
})


# ============================================================================
# Village Dashboard Tool
# ============================================================================

async def tool_village_tui(args: dict) -> str:
    """Launch Beads Village Dashboard TUI.
    
    Shows:
    - Teams and agents online
    - Tasks board (Kanban view)
    - File locks and messages
    - Real-time updates
    """
    import subprocess
    import sys
    import shutil
    
    python_exe = sys.executable
    workspace = WS
    
    # Check if textual is installed
    try:
        import textual
    except ImportError:
        return j({
            'error': 'textual not installed',
            'hint': 'Install with: pip install textual'
        })
    
    try:
        if sys.platform == 'win32':
            # Windows: use cmd /c with command and pause
            cmd = f'start "Beads Village Dashboard" cmd /c ""{python_exe}" -m beads_village.dashboard "{workspace}" & pause"'
            subprocess.Popen(cmd, shell=True, cwd=workspace)
        elif sys.platform == 'darwin':
            # macOS: use osascript to open Terminal
            # Escape quotes properly for AppleScript
            escaped_ws = workspace.replace('"', '\\"')
            escaped_py = python_exe.replace('"', '\\"')
            script = f'cd "{escaped_ws}" && "{escaped_py}" -m beads_village.dashboard "{escaped_ws}"'
            subprocess.Popen([
                'osascript', '-e',
                f'tell application "Terminal" to do script "{script}"'
            ])
        else:
            # Linux: try common terminal emulators
            terminals = ['gnome-terminal', 'xterm', 'konsole', 'xfce4-terminal', 'alacritty', 'kitty']
            launched = False
            for term in terminals:
                if shutil.which(term):
                    if term == 'gnome-terminal':
                        subprocess.Popen(
                            [term, '--', python_exe, '-m', 'beads_village.dashboard', workspace],
                            start_new_session=True
                        )
                    elif term in ('alacritty', 'kitty'):
                        subprocess.Popen(
                            [term, '-e', python_exe, '-m', 'beads_village.dashboard', workspace],
                            start_new_session=True
                        )
                    elif term == 'konsole':
                        subprocess.Popen(
                            [term, '-e', python_exe, '-m', 'beads_village.dashboard', workspace],
                            start_new_session=True
                        )
                    else:
                        # xterm, xfce4-terminal
                        subprocess.Popen(
                            [term, '-e', f'{python_exe} -m beads_village.dashboard "{workspace}"'],
                            cwd=workspace,
                            start_new_session=True
                        )
                    launched = True
                    break
            
            if not launched:
                return j({
                    'error': 'No terminal emulator found',
                    'hint': 'Install gnome-terminal, xterm, konsole, xfce4-terminal, alacritty, or kitty'
                })
        
        return j({'ok': 1, 'message': 'Village Dashboard launched in new terminal'})
        
    except Exception as e:
        return j({'error': str(e), 'hint': 'Failed to launch dashboard'})


# Add village_tui to TOOLS registry
TOOLS.update({
    "village_tui": {
        "fn": tool_village_tui,
        "desc": "Launch Beads Village Dashboard TUI in new terminal. Shows teams, agents, tasks, locks, messages with live updates.",
        "input": {
            "type": "object",
            "properties": {},
            "required": []
        },
        "annotations": {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": False, "openWorldHint": True}
    }
})


if __name__ == "__main__":
    main()
