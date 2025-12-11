"""
Beads Village Dashboard - Main Textual Application

Flow: Teams -> Agents -> Tasks -> Task Detail
"""
import asyncio
import json
import subprocess
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical, ScrollableContainer, Container
from textual.widgets import Header, Footer, Static, Label, Rule, Button
from textual.binding import Binding
from textual.message import Message
from textual import work
from textual.reactive import reactive
from pathlib import Path
import os

from .watcher import DashboardWatcher


# ============================================================================
# Clickable Cards
# ============================================================================

class TeamCard(Static):
    """Clickable team card"""
    can_focus = True
    
    class Selected(Message):
        """Message when team is selected"""
        def __init__(self, team_name: str, team_data: dict) -> None:
            self.team_name = team_name
            self.team_data = team_data
            super().__init__()
    
    def __init__(self, team_name: str, team_data: dict, **kwargs) -> None:
        self.team_name = team_name
        self.team_data = team_data
        active = team_data.get('active', 0)
        total = team_data.get('total', 0)
        super().__init__(f"📋 [b]{team_name}[/b]\n   {active}/{total} online", **kwargs)
    
    def on_click(self) -> None:
        self.post_message(self.Selected(self.team_name, self.team_data))
    
    def key_enter(self) -> None:
        self.post_message(self.Selected(self.team_name, self.team_data))


class AgentCard(Static):
    """Clickable agent card"""
    can_focus = True
    
    class Selected(Message):
        """Message when agent is selected"""
        def __init__(self, agent_id: str, agent_data: dict) -> None:
            self.agent_id = agent_id
            self.agent_data = agent_data
            super().__init__()
    
    def __init__(self, agent_id: str, agent_data: dict, **kwargs) -> None:
        self.agent_id = agent_id
        self.agent_data = agent_data
        
        status = agent_data.get('status', 'offline')
        status_icon = {'online': '🟢', 'working': '🟡', 'offline': '⚫'}.get(status, '⚫')
        role = agent_data.get('role', '')
        role_str = f" [{role}]" if role else ""
        leader = " ⭐" if agent_data.get('is_leader') else ""
        current = agent_data.get('current_task', '')
        task_str = f"\n   → {current}" if current else ""
        
        super().__init__(f"{status_icon} [b]{agent_id}[/b]{role_str}{leader}{task_str}", **kwargs)
    
    def on_click(self) -> None:
        self.post_message(self.Selected(self.agent_id, self.agent_data))
    
    def key_enter(self) -> None:
        self.post_message(self.Selected(self.agent_id, self.agent_data))


class TaskCard(Static):
    """Clickable task card that can be selected with Enter key"""
    can_focus = True
    
    class Selected(Message):
        """Message when task card is selected"""
        def __init__(self, task_id: str, task_data: dict) -> None:
            self.task_id = task_id
            self.task_data = task_data
            super().__init__()
    
    def __init__(self, task_id: str, task_data: dict, **kwargs) -> None:
        self.task_id = task_id
        self.task_data = task_data
        # Display content
        title = task_data.get('title', 'No title')[:35]
        priority = task_data.get('priority', 2)
        priority_icons = {0: '🔴', 1: '🟠', 2: '🟡', 3: '🟢', 4: '⚪'}
        p_icon = priority_icons.get(priority, '⚪')
        super().__init__(f"{p_icon} [b]{task_id}[/b]\n{title}", **kwargs)
    
    def on_click(self) -> None:
        """Handle click event"""
        self.post_message(self.Selected(self.task_id, self.task_data))
    
    def key_enter(self) -> None:
        """Handle Enter key"""
        self.post_message(self.Selected(self.task_id, self.task_data))



class TeamsWidget(ScrollableContainer):
    """Widget showing list of teams - clickable and scrollable"""
    can_focus = True
    
    def compose(self) -> ComposeResult:
        yield Label("📋 Teams (click to select)", classes="widget-title")
        yield ScrollableContainer(id="teams-list")


class AgentsWidget(ScrollableContainer):
    """Widget showing agents in selected team - clickable and scrollable"""
    can_focus = True
    
    def compose(self) -> ComposeResult:
        yield Label("🤖 Agents", classes="widget-title")
        yield Static("[dim]Select a team first[/]", id="agents-header")
        yield ScrollableContainer(id="agents-list")


class AgentTasksWidget(ScrollableContainer):
    """Widget showing tasks completed by selected agent - scrollable"""
    can_focus = True
    
    def compose(self) -> ComposeResult:
        yield Label("📝 Agent Tasks", classes="widget-title")
        yield Static("[dim]Select an agent to see their tasks[/]", id="agent-tasks-header")
        yield ScrollableContainer(id="agent-tasks-list")


class TaskColumn(ScrollableContainer):
    """Focusable scrollable column for tasks"""
    can_focus = True


class TaskDetailWidget(Vertical):
    """Widget showing task details inline (replaces modal)"""
    can_focus = True
    
    class BackRequested(Message):
        """Message when back button is pressed"""
        pass
    
    def __init__(self, task_id: str, task_data: dict, activity: list, **kwargs) -> None:
        super().__init__(**kwargs)
        self.task_id = task_id
        self.task_data = task_data
        self.activity = activity
    
    def compose(self) -> ComposeResult:
        task = self.task_data
        
        # Status colors
        status_colors = {
            'open': '$success',
            'in_progress': '$warning', 
            'blocked': '$error',
            'closed': '$text-muted'
        }
        status = task.get('status', 'open')
        status_color = status_colors.get(status, '$text')
        
        priority_names = {0: 'Critical', 1: 'High', 2: 'Normal', 3: 'Low', 4: 'Backlog'}
        priority = priority_names.get(task.get('priority', 2), 'Unknown')
        
        yield Button("← Back to Board", id="back-to-board", variant="default")
        
        with ScrollableContainer(id="task-detail-scroll"):
            yield Label(f"📋 Task: {self.task_id}", id="inline-task-header")
            yield Rule()
            
            # Title
            yield Static(f"[b]Title:[/b] {task.get('title', 'N/A')}", classes="detail-section")
            
            # Status & Priority
            yield Static(f"[b]Status:[/b] [{status_color}]{status}[/] | [b]Priority:[/b] {priority}", classes="detail-section")
            
            # Assignee - get from task data or from activity (who done it)
            assignee = task.get('assignee', task.get('assigned_to', None))
            if not assignee and self.activity:
                # Find who completed THIS specific task from done messages
                for act in self.activity:
                    subj = act.get('s', act.get('subject', ''))
                    if subj == f'done:{self.task_id}':
                        assignee = act.get('f', act.get('from', None))
                        break
            assignee_display = assignee if assignee else '[dim]Unassigned[/]'
            # Use appropriate label based on status
            label = "Completed by" if status == 'closed' else "Assignee"
            yield Static(f"[b]{label}:[/b] {assignee_display}", classes="detail-section")
            
            # Type
            issue_type = task.get('issue_type', task.get('type', 'task'))
            yield Static(f"[b]Type:[/b] {issue_type}", classes="detail-section")
            
            # Dates
            created = task.get('created_at', 'N/A')[:19] if task.get('created_at') else 'N/A'
            updated = task.get('updated_at', 'N/A')[:19] if task.get('updated_at') else 'N/A'
            yield Static(f"[b]Created:[/b] {created}\n[b]Updated:[/b] {updated}", classes="detail-section")
            
            # Description
            desc = task.get('description', 'No description')
            yield Static(f"[b]Description:[/b]\n{desc}", classes="detail-section")
            
            yield Rule()
            yield Label("🔔 Agent Activity", id="activity-section-header")
            
            if self.activity:
                for act in self.activity[:10]:
                    agent = act.get('f', 'unknown')
                    body = act.get('b', act.get('body', 'No message'))
                    ts = act.get('ts', '')[:19] if act.get('ts') else ''
                    yield Static(
                        f"[dim]{ts}[/]\n[b]{agent}:[/b] {body}",
                        classes="activity-item"
                    )
            else:
                yield Static("[dim]No activity recorded[/]")
    
    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "back-to-board":
            self.post_message(self.BackRequested())


class TasksBoardWidget(Static):
    """Widget showing tasks in Kanban style or task detail"""
    
    show_detail = reactive(False)
    
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.current_task_id = None
        self.current_task_data = None
        self.current_activity = None
    
    def compose(self) -> ComposeResult:
        yield Label("📝 Tasks Board", classes="widget-title", id="board-title")
        with Vertical(id="board-container"):
            with Horizontal(id="kanban-board"):
                with Vertical(classes="kanban-column"):
                    yield Label("Open", classes="column-header open")
                    yield TaskColumn(id="tasks-open")
                with Vertical(classes="kanban-column"):
                    yield Label("In Progress", classes="column-header in-progress")
                    yield TaskColumn(id="tasks-in-progress")
                with Vertical(classes="kanban-column"):
                    yield Label("Blocked", classes="column-header blocked")
                    yield TaskColumn(id="tasks-blocked")
                with Vertical(classes="kanban-column"):
                    yield Label("Closed", classes="column-header closed")
                    yield TaskColumn(id="tasks-closed")
        yield Vertical(id="detail-container")
    
    async def show_task_detail(self, task_id: str, task_data: dict, activity: list) -> None:
        """Switch to task detail view"""
        self.current_task_id = task_id
        self.current_task_data = task_data
        self.current_activity = activity
        
        # Hide board, show detail
        board = self.query_one("#board-container")
        detail = self.query_one("#detail-container")
        
        board.display = False
        detail.display = True
        detail.remove_children()
        
        # Create widget and mount (await for proper layout)
        widget = TaskDetailWidget(task_id, task_data, activity)
        await detail.mount(widget)
        detail.refresh(layout=True)
        
        # Update title
        title = self.query_one("#board-title", Label)
        title.update(f"📋 Task: {task_id}")
    
    def show_board(self) -> None:
        """Switch back to board view"""
        board = self.query_one("#board-container")
        detail = self.query_one("#detail-container")
        
        board.display = True
        detail.display = False
        detail.remove_children()
        
        # Update title
        title = self.query_one("#board-title", Label)
        title.update("📝 Tasks Board")


class LocksWidget(ScrollableContainer):
    """Widget showing file locks - scrollable"""
    can_focus = True
    
    def compose(self) -> ComposeResult:
        yield Label("🔒 File Locks", classes="widget-title")
        yield Static("No active locks", id="locks-content")


class MessagesWidget(ScrollableContainer):
    """Widget showing recent messages - scrollable"""
    can_focus = True
    
    def compose(self) -> ComposeResult:
        yield Label("💬 Messages", classes="widget-title")
        yield Static("Loading messages...", id="messages-list")


class InsightsWidget(ScrollableContainer):
    """Widget showing graph insights from bv - bottlenecks, keystones, cycles"""
    can_focus = True
    
    def compose(self) -> ComposeResult:
        yield Label("📊 Graph Insights [dim](current workspace)[/]", classes="widget-title")
        yield Button("Refresh", id="btn-refresh-insights", variant="default")
        yield Static("Loading insights...", id="insights-content")
    
    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-refresh-insights":
            self.post_message(self.RefreshRequested())
    
    class RefreshRequested(Message):
        """Message when refresh is requested"""
        pass


class RecipesWidget(ScrollableContainer):
    """Widget showing filter recipes - actionable, blocked, stale, etc."""
    can_focus = True
    
    RECIPES = [
        ("default", "📋 All"),
        ("actionable", "⚡ Actionable"),
        ("blocked", "🚫 Blocked"),
        ("high-impact", "🎯 High Impact"),
        ("stale", "💤 Stale"),
    ]
    
    def compose(self) -> ComposeResult:
        yield Label("🎛️ Filter Recipes [dim](current workspace)[/]", classes="widget-title")
        with Horizontal(classes="recipe-buttons"):
            for key, name in self.RECIPES:
                yield Button(name, id=f"recipe-{key}", variant="default", classes="recipe-btn")
        yield ScrollableContainer(id="recipe-results")
    
    class RecipeSelected(Message):
        """Message when a recipe is selected"""
        def __init__(self, recipe: str) -> None:
            self.recipe = recipe
            super().__init__()
    
    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id.startswith("recipe-"):
            recipe = event.button.id.replace("recipe-", "")
            self.post_message(self.RecipeSelected(recipe))


class BeadsVillageDashboard(App):
    """Beads Village Dashboard - Monitor agents, tasks, locks, and messages"""
    
    TITLE = "Beads Village Dashboard"
    SUB_TITLE = "Multi-Agent Coordination"
    
    CSS = '''
    Screen {
        layout: grid;
        grid-size: 3;
        grid-columns: 1fr 2fr 1fr;
    }
    
    #left-panel {
        height: 100%;
        border: solid $primary;
        padding: 1;
    }
    
    #center-panel {
        height: 100%;
        border: solid $secondary;
        padding: 1;
    }
    
    #right-panel {
        height: 100%;
        border: solid $primary;
        padding: 1;
    }
    
    .widget-title {
        text-style: bold;
        color: $accent;
        margin-bottom: 1;
    }
    
    #kanban-board {
        height: 100%;
    }
    
    .kanban-column {
        width: 1fr;
        height: 100%;
        border: solid $surface;
        margin: 0 1;
        padding: 1;
    }
    
    .column-header {
        text-style: bold;
        text-align: center;
        margin-bottom: 1;
    }
    
    .column-header.open { color: $success; }
    .column-header.in-progress { color: $warning; }
    .column-header.blocked { color: $error; }
    .column-header.closed { color: $primary-darken-2; }
    
    .task-card {
        background: $surface;
        padding: 1;
        margin-bottom: 1;
        border: solid $primary-darken-1;
    }
    
    .task-card:focus {
        border: double $accent;
        background: $primary-background;
    }
    
    .task-card:hover {
        background: $surface-lighten-1;
    }
    
    .team-card, .agent-card {
        background: $surface;
        padding: 1;
        margin-bottom: 1;
        border: solid $primary-darken-1;
    }
    
    .team-card:focus, .agent-card:focus {
        border: double $accent;
        background: $primary-background;
    }
    
    .team-card:hover, .agent-card:hover {
        background: $surface-lighten-1;
    }
    
    .team-card.selected, .agent-card.selected {
        border: double $success;
        background: $success 20%;
    }
    
    #teams-list, #agents-list, #agent-tasks-list {
        height: auto;
        max-height: 100%;
        min-height: 3;
    }
    
    .agent-online { color: $success; }
    .agent-working { color: $warning; }
    .agent-offline { color: $text-muted; }
    
    .lock-warning { color: $error; }
    .lock-ok { color: $success; }
    
    .message-high { color: $error; }
    .message-normal { color: $text; }
    .message-low { color: $text-muted; }
    
    /* Focus styles */
    TeamsWidget:focus, AgentsWidget:focus, TasksBoardWidget:focus, 
    LocksWidget:focus, MessagesWidget:focus {
        border: double $accent;
    }
    
    .focusable:focus-within {
        border: double $accent;
    }
    
    /* Board/Detail toggle containers */
    #board-container {
        height: 100%;
    }
    
    #detail-container {
        display: none;
        height: 1fr;
        width: 100%;
        padding: 1;
    }
    
    TaskDetailWidget {
        height: 1fr;
        width: 100%;
    }
    
    #task-detail-scroll {
        height: 1fr;
        width: 100%;
    }
    
    #back-to-board {
        margin-bottom: 1;
    }
    
    #inline-task-header {
        text-style: bold;
        color: $accent;
        margin-bottom: 1;
    }
    
    #activity-section-header {
        text-style: bold;
        color: $warning;
        margin-top: 1;
    }
    
    .detail-section {
        margin-bottom: 1;
    }
    
    .activity-item {
        background: $surface-darken-1;
        padding: 1;
        margin-bottom: 1;
        border-left: thick $success;
    }
    
    /* Insights and Recipes widgets */
    #btn-refresh-insights {
        margin-bottom: 1;
    }
    
    #insights-content {
        height: auto;
        max-height: 10;
    }
    
    .recipe-buttons {
        height: 3;
        margin-bottom: 1;
    }
    
    .recipe-btn {
        min-width: 10;
        margin: 0 1;
    }
    
    #recipe-results {
        height: 1fr;
        min-height: 10;
        scrollbar-gutter: stable;
        overflow-y: auto;
        padding-left: 1;
    }
    
    .recipe-item {
        padding: 0 1;
        margin-bottom: 0;
    }
    
    InsightsWidget {
        height: auto;
        max-height: 18;
    }
    
    RecipesWidget {
        height: 1fr;
        min-height: 15;
    }
    '''
    
    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("r", "refresh", "Refresh"),
        Binding("t", "toggle_dark", "Theme"),
        Binding("tab", "focus_next", "Next"),
        Binding("shift+tab", "focus_previous", "Prev"),
        Binding("1", "focus_teams", "Teams"),
        Binding("2", "focus_agents", "Agents"),
        Binding("3", "focus_tasks_open", "Open"),
        Binding("4", "focus_tasks_progress", "InProg"),
        Binding("5", "focus_tasks_blocked", "Block"),
        Binding("6", "focus_tasks_closed", "Closed"),
        Binding("7", "focus_locks", "Locks"),
        Binding("8", "focus_messages", "Msgs"),
        Binding("j", "scroll_down", "Down"),
        Binding("k", "scroll_up", "Up"),
    ]
    
    def __init__(self, workspace: str = None):
        super().__init__()
        self.workspace = workspace or os.getcwd()
        self.watcher = None
        # Selection state
        self.selected_team = None
        self.selected_agent = None
        self.all_teams = {}  # team_name -> {active, total, agents: []}
        self.all_agents = []  # list of agent objects
    
    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="left-panel"):
            yield TeamsWidget()
            yield Rule()
            yield AgentsWidget()
            yield Rule()
            yield AgentTasksWidget()
        with Vertical(id="center-panel"):
            yield TasksBoardWidget()
        with Vertical(id="right-panel"):
            yield LocksWidget()
            yield Rule()
            yield MessagesWidget()
            yield Rule()
            yield InsightsWidget()
            yield Rule()
            yield RecipesWidget()
        yield Footer()
    
    def on_mount(self) -> None:
        """Called when app is mounted"""
        self.refresh_data()
        self.start_watcher()
    
    def start_watcher(self) -> None:
        """Start file watcher for live updates"""
        async def on_change(changed_files):
            self.refresh_data()
        
        self.watcher = DashboardWatcher(
            workspace=self.workspace,
            on_change=on_change,
            poll_interval=2.0
        )
        asyncio.create_task(self.watcher.start())
    
    def on_unmount(self) -> None:
        """Called when app is unmounted"""
        if self.watcher:
            self.watcher.stop()
    
    @work(exclusive=True)
    async def refresh_data(self) -> None:
        """Refresh all widget data"""
        # Load .mail messages once and cache for all methods
        self._cached_messages = self._load_all_messages()
        
        await self.load_teams()
        await self.load_agents()
        await self.load_tasks()
        await self.load_locks()
        await self.load_messages()
        await self.load_insights()
        await self.load_recipes("default")
    
    def _load_all_messages(self) -> list:
        """Load all .mail messages once (for caching)"""
        messages = []
        mail_dir = Path(self.workspace) / '.mail'
        if not mail_dir.exists():
            return messages
        
        for msg_file in sorted(mail_dir.glob('*.json'), reverse=True)[:200]:
            try:
                with open(msg_file, 'r') as f:
                    msg = json.load(f)
                    messages.append(msg)
            except Exception:
                pass
        return messages
    
    async def load_teams(self) -> None:
        """Load teams from agent registry AND .mail messages (stateless)"""
        try:
            teams = {}
            
            # Method 1: Try agent registry first
            try:
                from beads_village.agent_registry import get_registry
                registry = get_registry(self.workspace)
                all_agents = registry.get_all_agents()
                self.all_agents = all_agents
                
                for agent in all_agents:
                    team = agent.team
                    if team not in teams:
                        teams[team] = {'active': 0, 'total': 0, 'agents': []}
                    teams[team]['total'] += 1
                    teams[team]['agents'].append(agent)
                    if agent.is_online:
                        teams[team]['active'] += 1
            except Exception:
                self.all_agents = []
            
            # Method 2: Also scan cached .mail for join messages (stateless fallback)
            import re
            agents_from_mail = {}  # agent_id -> {team, role, is_leader, last_seen}
            
            for msg in getattr(self, '_cached_messages', []):
                subj = msg.get('s', msg.get('subject', ''))
                if subj == 'join':
                    body = msg.get('b', msg.get('body', ''))
                    sender = msg.get('f', msg.get('from', ''))
                    ts = msg.get('ts', '')
                    
                    # Parse: "Agent xxx (role=be) [LEADER] joined workspace yyy"
                    if sender and sender not in agents_from_mail:
                        is_leader = '[LEADER]' in body
                        role = None
                        team = 'default'
                        
                        # Extract role using regex
                        role_match = re.search(r'\(role=(\w+)\)', body)
                        if role_match:
                            role = role_match.group(1)
                        
                        # Extract team from thread
                        thread = msg.get('thread', '')
                        if thread:
                            team = thread.split('-')[0] if '-' in thread else thread
                        
                        agents_from_mail[sender] = {
                            'agent_id': sender,
                            'team': team,
                            'role': role,
                            'is_leader': is_leader,
                            'last_seen': ts,
                            'current_task': msg.get('issue', None),
                            'status': 'offline'
                        }
                
            # Merge mail-based agents into teams
            for agent_id, agent_data in agents_from_mail.items():
                team = agent_data['team']
                if team not in teams:
                    teams[team] = {'active': 0, 'total': 0, 'agents': []}
                
                # Check if already in teams from registry
                existing_ids = [a.agent_id if hasattr(a, 'agent_id') else a.get('agent_id') 
                               for a in teams[team].get('agents', [])]
                if agent_id not in existing_ids:
                    # Create a simple object-like dict
                    from types import SimpleNamespace
                    agent_obj = SimpleNamespace(
                        agent_id=agent_id,
                        team=team,
                        role=agent_data.get('role'),
                        is_leader=agent_data.get('is_leader', False),
                        current_task=agent_data.get('current_task'),
                        status='offline',
                        is_online=False
                    )
                    teams[team]['total'] += 1
                    teams[team]['agents'].append(agent_obj)
            
            self.all_teams = teams
            
            # Update teams list with clickable cards
            container = self.query_one("#teams-list", ScrollableContainer)
            container.remove_children()
            
            if not teams:
                container.mount(Static("[dim]No teams found[/]"))
            else:
                for team_name, team_data in teams.items():
                    card = TeamCard(team_name, team_data, classes="team-card")
                    if team_name == self.selected_team:
                        card.add_class("selected")
                    container.mount(card)
                    
        except Exception as e:
            container = self.query_one("#teams-list", ScrollableContainer)
            container.remove_children()
            container.mount(Static(f"Error: {e}"))
    
    async def load_agents(self) -> None:
        """Load agents filtered by selected team"""
        try:
            container = self.query_one("#agents-list", ScrollableContainer)
            header = self.query_one("#agents-header", Static)
            container.remove_children()
            
            if not self.selected_team:
                header.update("[dim]← Select a team first[/]")
                return
            
            header.update(f"[b]Team: {self.selected_team}[/]")
            
            # Get agents for selected team
            team_data = self.all_teams.get(self.selected_team, {})
            agents = team_data.get('agents', [])
            
            if not agents:
                container.mount(Static("[dim]No agents in this team[/]"))
                return
            
            for agent in agents:
                agent_data = {
                    'status': agent.status,
                    'role': agent.role,
                    'is_leader': agent.is_leader,
                    'current_task': agent.current_task,
                    'team': agent.team,
                }
                card = AgentCard(agent.agent_id, agent_data, classes="agent-card")
                if agent.agent_id == self.selected_agent:
                    card.add_class("selected")
                container.mount(card)
                
        except Exception as e:
            container = self.query_one("#agents-list", ScrollableContainer)
            container.remove_children()
            container.mount(Static(f"Error: {e}"))
    
    async def load_agent_tasks(self) -> None:
        """Load tasks completed by selected agent"""
        try:
            container = self.query_one("#agent-tasks-list", ScrollableContainer)
            header = self.query_one("#agent-tasks-header", Static)
            container.remove_children()
            
            if not self.selected_agent:
                header.update("[dim]← Select an agent to see their tasks[/]")
                return
            
            header.update(f"[b]Tasks by: {self.selected_agent}[/]")
            
            task_ids = set()
            
            # 1. Get current task from agent data
            for agent in self.all_agents:
                if agent.agent_id == self.selected_agent and agent.current_task:
                    task_ids.add(agent.current_task)
            
            # 2. Find done messages from this agent (match by agent_id anywhere in sender)
            activity = self.get_agent_activity(self.selected_agent)
            
            for msg in activity:
                subj = msg.get('s', msg.get('subject', ''))
                if subj.startswith('done:'):
                    task_id = subj.replace('done:', '').strip()
                    task_ids.add(task_id)
            
            # 3. Also check all done messages to find any referencing this agent
            all_done_tasks = self.get_all_done_tasks()
            
            if not task_ids:
                container.mount(Static("[dim]No tasks found for this agent[/]"))
                return
            
            # Get task details for each task ID
            for task_id in list(task_ids)[:10]:  # Limit to 10
                # Try to get workspace from done message for this task
                task_workspace = None
                for msg in activity:
                    subj = msg.get('s', msg.get('subject', ''))
                    if subj == f'done:{task_id}':
                        task_workspace = msg.get('ws', None)
                        break
                
                task_data = self.get_task_by_id(task_id, workspace=task_workspace)
                if task_data:
                    card = TaskCard(task_id, task_data, classes="task-card")
                    container.mount(card)
                else:
                    # Create minimal task data so TaskCard is still clickable
                    minimal_data = {'id': task_id, 'title': task_id, 'priority': 2, 'status': 'unknown'}
                    card = TaskCard(task_id, minimal_data, classes="task-card")
                    container.mount(card)
                    
        except Exception as e:
            container = self.query_one("#agent-tasks-list", ScrollableContainer)
            container.remove_children()
            container.mount(Static(f"Error: {e}"))
    
    def get_all_done_tasks(self) -> set:
        """Get all task IDs from done messages (uses cached messages)"""
        task_ids = set()
        
        for msg in getattr(self, '_cached_messages', []):
            subj = msg.get('s', msg.get('subject', ''))
            if subj.startswith('done:'):
                task_id = subj.replace('done:', '').strip()
                task_ids.add(task_id)
        
        return task_ids
    
    def get_agent_activity(self, agent_id: str) -> list:
        """Get all messages from a specific agent (uses cached messages)"""
        activity = []
        
        for msg in getattr(self, '_cached_messages', []):
            sender = msg.get('f', msg.get('from', ''))
            if agent_id in sender:
                activity.append(msg)
        
        return activity[:50]  # Return last 50 activities
    
    def get_task_by_id(self, task_id: str, workspace: str = None) -> dict:
        """Get task details by ID using bd show"""
        try:
            cwd = workspace or self.workspace
            result = subprocess.run(
                ['bd', 'show', task_id, '--json'],
                capture_output=True,
                text=True,
                cwd=cwd,
                timeout=5
            )
            if result.returncode == 0:
                data = json.loads(result.stdout)
                # bd show returns a list, get first item
                if isinstance(data, list) and len(data) > 0:
                    return data[0]
                elif isinstance(data, dict):
                    return data
        except Exception:
            pass
        return None
    
    def on_team_card_selected(self, event: TeamCard.Selected) -> None:
        """Handle team selection"""
        self.selected_team = event.team_name
        self.selected_agent = None  # Reset agent selection
        
        # Refresh agents and agent tasks
        self.run_worker(self.load_teams())
        self.run_worker(self.load_agents())
        self.run_worker(self.load_agent_tasks())
    
    def on_agent_card_selected(self, event: AgentCard.Selected) -> None:
        """Handle agent selection - show their tasks"""
        self.selected_agent = event.agent_id
        
        # Refresh to show selected state and load agent tasks
        self.run_worker(self.load_agents())
        self.run_worker(self.load_agent_tasks())
    
    async def load_tasks(self) -> None:
        """Load tasks from beads"""
        try:
            import subprocess
            import json
            
            result = subprocess.run(
                ['bd', 'list', '--json', '--limit', '50'],
                capture_output=True,
                text=True,
                cwd=self.workspace,
                timeout=10
            )
            
            if result.returncode != 0:
                return
            
            tasks = json.loads(result.stdout)
            
            # Group by status
            by_status = {
                'open': [],
                'in_progress': [],
                'blocked': [],
                'closed': []
            }
            
            for task in tasks:
                status = task.get('status', 'open')
                # Normalize status variations
                if status in ('in-progress', 'in_progress', 'inprogress'):
                    status = 'in_progress'
                elif status not in by_status:
                    status = 'open'  # Default unknown statuses to open
                by_status[status].append(task)
            
            # Update each column
            for status, tasks_list in by_status.items():
                container_id = f"#tasks-{status.replace('_', '-')}"
                try:
                    container = self.query_one(container_id, TaskColumn)
                    container.remove_children()
                    
                    for task in tasks_list[:10]:  # Limit to 10 per column
                        task_id = task.get('id', '?')
                        card = TaskCard(task_id, task, classes="task-card")
                        container.mount(card)
                    
                    if not tasks_list:
                        container.mount(Static("(empty)", classes="task-card"))
                except Exception:
                    pass
                    
        except Exception as e:
            pass
    
    def get_task_activity(self, task_id: str) -> list:
        """Get activity/done messages related to a task (uses cached messages)"""
        activity = []
        
        for msg in getattr(self, '_cached_messages', []):
            subject = msg.get('s', msg.get('subject', ''))
            body = msg.get('b', msg.get('body', ''))
            
            # Match "done:task-id" pattern or task_id in body
            if f'done:{task_id}' in subject or task_id in body or task_id in subject:
                activity.append(msg)
        
        return activity[:20]  # Return last 20 activities
    
    def on_task_card_selected(self, event: TaskCard.Selected) -> None:
        """Handle task card selection - show detail in center panel"""
        task_id = event.task_id
        task_data = event.task_data
        
        # Load activity for this task
        activity = self.get_task_activity(task_id)
        
        # Show detail in TasksBoardWidget instead of modal (run async)
        board_widget = self.query_one(TasksBoardWidget)
        self.run_worker(board_widget.show_task_detail(task_id, task_data, activity))
    
    def on_task_detail_widget_back_requested(self, event: TaskDetailWidget.BackRequested) -> None:
        """Handle back button in task detail - return to board view"""
        board_widget = self.query_one(TasksBoardWidget)
        board_widget.show_board()
    
    async def load_locks(self) -> None:
        """Load file locks"""
        try:
            import json
            from datetime import datetime
            
            locks_dir = Path(self.workspace) / '.reservations'
            if not locks_dir.exists():
                return
            
            content = []
            now = datetime.now().timestamp()
            
            for lock_file in locks_dir.glob('*.json'):
                try:
                    with open(lock_file, 'r') as f:
                        lock = json.load(f)
                    
                    path = lock.get('path', lock_file.stem)
                    agent = lock.get('agent', 'unknown')
                    expires = lock.get('expires', 0)
                    
                    ttl = int(expires - now)
                    if ttl < 0:
                        continue  # Expired
                    
                    ttl_class = 'lock-warning' if ttl < 60 else 'lock-ok'
                    content.append(f"[{ttl_class}]• {Path(path).name}[/]\n  └─ {agent} ({ttl}s)")
                except Exception:
                    pass
            
            if not content:
                content = ["No active locks"]
            
            widget = self.query_one("#locks-content", Static)
            widget.update("\n".join(content))
        except Exception as e:
            widget = self.query_one("#locks-content", Static)
            widget.update(f"Error: {e}")
    
    async def load_messages(self) -> None:
        """Load recent messages (uses cached messages)"""
        try:
            messages = getattr(self, '_cached_messages', [])[:10]
            
            # Update messages list (now a Static inside MessagesWidget)
            content_lines = []
            for msg in messages:
                importance = msg.get('importance', msg.get('imp', 'normal'))
                importance_class = f"message-{importance}"
                # Handle both old format (subject) and new format (s)
                subj = msg.get('subject', msg.get('s', 'No subject'))[:40]
                sender = msg.get('from', msg.get('f', 'unknown'))
                content_lines.append(f"[{importance_class}][b]{subj}[/b][/]\nFrom: {sender}\n")
            
            if not content_lines:
                content_lines = ["No messages"]
            
            widget = self.query_one("#messages-list", Static)
            widget.update("\n".join(content_lines))
                
        except Exception as e:
            pass
    
    async def load_insights(self) -> None:
        """Load graph insights from bv (bottlenecks, keystones, cycles, pagerank)"""
        try:
            widget = self.query_one("#insights-content", Static)
            
            # Try to load bv manager
            try:
                from beads_village.bv_manager import BvManager
                bv = BvManager(self.workspace)
                
                if not bv.is_available:
                    widget.update("[dim]bv not installed[/]\nInstall: go install github.com/Dicklesworthstone/beads_viewer/cmd/bv@latest")
                    return
                
                insights = bv.get_insights()
                
                if insights.get("error"):
                    widget.update(f"[error]Error: {insights['error']}[/]")
                    return
                
                content = []
                
                # Bottlenecks - bv returns "Bottlenecks" with capital B
                bottlenecks = insights.get("Bottlenecks", insights.get("bottlenecks", []))
                if bottlenecks:
                    content.append("[b]🚧 Bottlenecks[/]")
                    for b in bottlenecks[:3]:
                        bid = b.get('ID', b.get('id', ''))[:15]
                        content.append(f"  • {bid}")
                
                # Keystones - bv returns "Keystones" with capital K
                keystones = insights.get("Keystones", insights.get("keystones", []))
                if keystones:
                    content.append("[b]🔑 Keystones[/]")
                    for k in keystones[:3]:
                        kid = k.get('ID', k.get('id', ''))[-8:]  # Show last 8 chars (unique part)
                        content.append(f"  • ...{kid}")
                
                # Influencers (PageRank) - bv returns "Influencers"
                influencers = insights.get("Influencers", insights.get("pagerank", []))
                if influencers:
                    content.append("[b]📈 Top Influencers[/]")
                    for p in influencers[:3]:
                        pid = p.get('ID', p.get('id', ''))[-8:]  # Show last 8 chars
                        val = p.get('Value', p.get('score', 0))
                        content.append(f"  • ...{pid} ({val:.3f})")
                
                # Cycles - bv returns "Cycles"
                cycles = insights.get("Cycles", insights.get("cycles", []))
                if cycles:
                    content.append(f"[b]🔄 Cycles: {len(cycles)}[/]")
                
                # Stats - node count
                stats = insights.get("Stats", {})
                if stats:
                    node_count = stats.get("NodeCount", 0)
                    edge_count = stats.get("EdgeCount", 0)
                    content.append(f"[dim]Nodes: {node_count} | Edges: {edge_count}[/]")
                
                if not content:
                    content = ["[dim]No insights (graph empty)[/]"]
                
                widget.update("\n".join(content))
                
            except ImportError:
                widget.update("[dim]bv_manager not available[/]")
                
        except Exception as e:
            pass
    
    async def load_recipes(self, recipe: str = "default") -> None:
        """Load issues filtered by recipe"""
        try:
            container = self.query_one("#recipe-results", ScrollableContainer)
            container.remove_children()
            
            # Load issues
            issues = self._load_issues_for_recipes()
            
            # Apply filter
            from datetime import datetime, timedelta
            
            if recipe == "actionable":
                # Open issues without blockers
                filtered = [i for i in issues if i.get("status") == "open" and not self._has_blockers(i)]
            elif recipe == "blocked":
                # Blocked status OR has blockers
                filtered = [i for i in issues if i.get("status") == "blocked" or self._has_blockers(i)]
            elif recipe == "high-impact":
                # High priority (0 or 1), not closed
                filtered = [i for i in issues if i.get("priority", 2) <= 1 and i.get("status") != "closed"]
            elif recipe == "stale":
                # Not updated in 7+ days, not closed
                week_ago = (datetime.now() - timedelta(days=7)).isoformat()
                filtered = [i for i in issues if i.get("updated_at", "") < week_ago and i.get("status") != "closed"]
            else:  # default - show ALL issues including closed (to show something)
                filtered = issues
            
            if not filtered:
                container.mount(Static("[dim]No issues match this filter[/]"))
                return
            
            for issue in filtered[:15]:  # Show more items with scroll
                pri = issue.get("priority", 2)
                pri_icon = ["🔥", "⚡", "📌", "📋", "📝"][min(pri, 4)]
                status = issue.get("status", "open")
                status_icon = {"open": "○", "in_progress": "◐", "blocked": "✕", "closed": "✓"}.get(status, "○")
                title = issue.get("title", "No title")[:35]
                issue_id = issue.get("id", "")[-6:]  # Show last 6 chars
                container.mount(Static(f"{pri_icon} {status_icon} ...{issue_id} {title}", classes="recipe-item"))
                
        except Exception as e:
            pass
    
    def _load_issues_for_recipes(self) -> list:
        """Load issues from .beads/issues.jsonl"""
        issues = []
        issues_file = Path(self.workspace) / '.beads' / 'issues.jsonl'
        
        if issues_file.exists():
            try:
                with open(issues_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            try:
                                issues.append(json.loads(line))
                            except json.JSONDecodeError:
                                pass
            except Exception:
                pass
        
        return issues
    
    def _has_blockers(self, issue: dict) -> bool:
        """Check if issue has blockers"""
        for dep in issue.get("dependencies", []):
            if dep.get("type") == "blocked_by":
                return True
        return False
    
    def on_insights_widget_refresh_requested(self, event: InsightsWidget.RefreshRequested) -> None:
        """Handle insights refresh request"""
        asyncio.create_task(self.load_insights())
    
    def on_recipes_widget_recipe_selected(self, event: RecipesWidget.RecipeSelected) -> None:
        """Handle recipe selection"""
        asyncio.create_task(self.load_recipes(event.recipe))
    
    def action_refresh(self) -> None:
        """Handle refresh action"""
        self.refresh_data()
    
    def action_toggle_dark(self) -> None:
        """Toggle dark mode"""
        self.dark = not self.dark
    
    def action_focus_teams(self) -> None:
        """Focus on teams widget"""
        self.query_one(TeamsWidget).focus()
    
    def action_focus_agents(self) -> None:
        """Focus on agents widget"""
        self.query_one(AgentsWidget).focus()
    
    def action_focus_tasks_open(self) -> None:
        """Focus on Open tasks column"""
        self.query_one("#tasks-open", TaskColumn).focus()
    
    def action_focus_tasks_progress(self) -> None:
        """Focus on In Progress tasks column"""
        self.query_one("#tasks-in-progress", TaskColumn).focus()
    
    def action_focus_tasks_blocked(self) -> None:
        """Focus on Blocked tasks column"""
        self.query_one("#tasks-blocked", TaskColumn).focus()
    
    def action_focus_tasks_closed(self) -> None:
        """Focus on Closed tasks column"""
        self.query_one("#tasks-closed", TaskColumn).focus()
    
    def action_focus_locks(self) -> None:
        """Focus on locks widget"""
        self.query_one(LocksWidget).focus()
    
    def action_focus_messages(self) -> None:
        """Focus on messages widget"""
        self.query_one(MessagesWidget).focus()
    
    def action_scroll_down(self) -> None:
        """Scroll focused widget down"""
        focused = self.focused
        if focused and hasattr(focused, 'scroll_down'):
            focused.scroll_down()
    
    def action_scroll_up(self) -> None:
        """Scroll focused widget up"""
        focused = self.focused
        if focused and hasattr(focused, 'scroll_up'):
            focused.scroll_up()


def main(workspace: str = None):
    """Run the dashboard"""
    app = BeadsVillageDashboard(workspace=workspace)
    app.run()


if __name__ == "__main__":
    import sys
    workspace = sys.argv[1] if len(sys.argv) > 1 else None
    main(workspace)
