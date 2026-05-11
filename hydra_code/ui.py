"""
 UI 组件风格。
"""

from typing import Optional, Deque
from collections import deque
from rich.console import Console, Group, RenderableType
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.syntax import Syntax
from rich.text import Text
from rich.box import ROUNDED
from rich.spinner import Spinner
from rich.table import Table
from .todo import TodoList, TaskStatus

console = Console()


class TodoListRenderer:
    """Renders a simple Todo List."""
    def __init__(self, todo_list: TodoList):
        self.todo_list = todo_list
        
    def __rich__(self) -> RenderableType:
        table = Table(box=None, show_header=False, padding=(0, 2))
        table.add_column("Status", width=3)
        table.add_column("Task")
        
        for item in self.todo_list.items:
            status_icon = "○"  # Pending
            style = "dim"
            
            if item.status == TaskStatus.IN_PROGRESS:
                status_icon = "●"
                style = "yellow"
            elif item.status == TaskStatus.COMPLETED:
                status_icon = "✓"
                style = "green"
            elif item.status == TaskStatus.FAILED:
                status_icon = "✗"
                style = "red"
            elif item.status == TaskStatus.SKIPPED:
                status_icon = "-"
                style = "dim"
                
            table.add_row(Text(status_icon, style=style), Text(item.content, style=style))
            
        return Panel(
            table,
            title=f"[bold]{self.todo_list.title}[/bold]",
            border_style="cyan",
            box=ROUNDED,
            padding=(0, 1)
        )


class ParallelMonitor:
    """Renders parallel execution status with scrolling logs."""
    def __init__(self):
        self.logs: Deque[str] = deque(maxlen=3)
        self.tasks: dict[str, str] = {}
        self.spinner = Spinner("dots", style="cyan")
        self.title = "Parallel Execution"

    def add_log(self, message: str):
        self.logs.append(message)

    def update_task(self, name: str, status: str):
        self.tasks[name] = status

    def __rich__(self) -> RenderableType:
        # 1. Task Status Table
        task_table = Table(box=None, show_header=False, padding=(0, 2))
        task_table.add_column("Status", width=3)
        task_table.add_column("Task")
        task_table.add_column("State", style="dim")
        
        sorted_tasks = sorted(self.tasks.items())
        for name, status in sorted_tasks:
            if "Completed" in status or "Done" in status:
                icon = Text("✓", style="green")
            elif "Failed" in status:
                icon = Text("✗", style="red")
            else:
                icon = self.spinner
                
            task_table.add_row(icon, name, status)
            
        # 2. Log Panel (last 3 lines)
        log_content = "\n".join(self.logs) if self.logs else "[dim]Waiting for logs...[/dim]"
        log_panel = Panel(
            Text(log_content, style="dim"),
            title=f"[cyan]{self.title}[/cyan]",
            border_style="cyan dim",
            box=ROUNDED,
            height=5, # 3 lines content + 2 border
            padding=(0, 1)
        )
        
        return Group(
            Panel(task_table, title="[bold]Active Tasks[/bold]", border_style="blue", box=ROUNDED),
            log_panel
        )


class LeaderMonitor:
    """Renders leader-worker execution status with task tracking and activity log."""
    def __init__(self):
        self.logs: Deque[str] = deque(maxlen=5)
        self.tasks: dict[str, dict] = {}  # task_id -> {desc, worker, status}
        self.current_round: int = 0
        self.max_rounds: int = 15
        self.leader_role: str = "Leader"
        self.phase: str = "Initializing"
        self.spinner = Spinner("dots", style="cyan")
        self.start_time: float = 0.0

    def add_log(self, message: str):
        self.logs.append(message)

    def update_round(self, current: int, max_rounds: int = 15):
        self.current_round = current
        self.max_rounds = max_rounds

    def set_phase(self, phase: str):
        self.phase = phase

    def add_task(self, task_id: str, desc: str, worker: str, status: str = "pending"):
        self.tasks[task_id] = {"desc": desc, "worker": worker, "status": status}

    def update_task(self, task_id: str, status: str):
        if task_id in self.tasks:
            self.tasks[task_id]["status"] = status

    def __rich__(self) -> RenderableType:
        import time
        elapsed = int(time.time() - self.start_time) if self.start_time else 0
        elapsed_str = f"{elapsed // 60}m {elapsed % 60}s" if elapsed >= 60 else f"{elapsed}s"

        # Header
        progress = f"Round {self.current_round}/{self.max_rounds}" if self.current_round > 0 else "Starting..."
        header_text = f"[bold]{self.leader_role}[/bold]  {progress}  [dim]({elapsed_str})[/dim]"
        if self.phase:
            header_text += f"\n[dim]{self.phase}[/dim]"

        # Task table
        task_table = Table(box=None, show_header=True, padding=(0, 1))
        task_table.add_column("", width=3)
        task_table.add_column("Task", ratio=3)
        task_table.add_column("Worker", ratio=1)
        task_table.add_column("Status", ratio=1)

        for tid, info in sorted(self.tasks.items()):
            status = info["status"]
            if status in ("completed", "reviewed"):
                icon = Text("✓", style="green")
                status_style = "green"
            elif status == "failed":
                icon = Text("✗", style="red")
                status_style = "red"
            elif status == "running":
                icon = self.spinner
                status_style = "yellow"
            else:
                icon = Text("○", style="dim")
                status_style = "dim"

            desc_short = info["desc"][:50] + ("..." if len(info["desc"]) > 50 else "")
            task_table.add_row(icon, desc_short, info["worker"], Text(status, style=status_style))

        # Log panel
        log_content = "\n".join(self.logs) if self.logs else "[dim]Waiting...[/dim]"
        log_panel = Panel(
            Text.from_ansi(log_content) if any("\x1b" in l for l in self.logs) else Text(log_content, style="dim"),
            title="[cyan]Activity[/cyan]",
            border_style="cyan dim",
            box=ROUNDED,
            height=7,
            padding=(0, 1)
        )

        # Combine
        if self.tasks:
            content = Group(
                Text.from_markup(header_text),
                task_table,
                log_panel
            )
        else:
            content = Group(
                Text.from_markup(header_text),
                log_panel
            )

        return Panel(
            content,
            title="[bold cyan]Leader Mode[/bold cyan]",
            border_style="cyan",
            box=ROUNDED,
            padding=(0, 1)
        )


class StreamRenderer:
    """Renders streaming output with thinking and content blocks."""
    def __init__(self):
        self.thinking_lines: list[str] = [""]
        self.thinking_total_chars: int = 0
        self.content_buffer: list[str] = []
        self.tool_status: Optional[str] = None
        self.tool_args_buffer: list[str] = []
        self.status_text: Optional[str] = None
        self.tool_status_map: dict[str, str] = {}  # tool_name -> status

    def update_thinking(self, chunk: str):
        if not chunk:
            return
        self.thinking_total_chars += len(chunk)

        # Append chunk to the last line
        self.thinking_lines[-1] += chunk

        # If the last line contains newlines, split it
        if '\n' in self.thinking_lines[-1]:
            parts = self.thinking_lines[-1].split('\n')
            self.thinking_lines.pop() # Remove the incomplete last line
            self.thinking_lines.extend(parts)

        # Keep only the last 50 lines to prevent memory/performance issues
        if len(self.thinking_lines) > 50:
            self.thinking_lines = self.thinking_lines[-50:]

    def update_content(self, chunk: str):
        self.content_buffer.append(chunk)

    def update_tool(self, tool_name: str, args_chunk: str):
        self.tool_status = tool_name
        self.tool_args_buffer.append(args_chunk)

    def update_status(self, text: str):
        self.status_text = text

    def update_tool_status(self, tool_name: str, status: str, args: str = None):
        if status.lower() in ("done", "failed", "completed"):
            self.tool_status_map.pop(tool_name, None)
        else:
            display = f"{tool_name}: {status}"
            if args:
                display += f" ({str(args)[:30]})"
            self.tool_status_map[tool_name] = display
        
    def __rich__(self) -> RenderableType:
        renderables = []
        
        # Render Thinking Block
        if self.thinking_total_chars > 0:
            # If we have content, collapse the thinking block
            if self.content_buffer:
                thinking_text = f"Thinking process completed ({self.thinking_total_chars} chars)."
                thinking_panel = Panel(
                    Text(thinking_text, style="dim"),
                    title="[yellow]🤔 Thinking[/yellow]",
                    border_style="yellow dim",
                    box=ROUNDED,
                    title_align="left",
                    padding=(0, 1)
                )
                renderables.append(thinking_panel)
            else:
                # While thinking, show the last few lines (scrolling window)
                # Filter out empty strings except maybe the last one if typing
                visible_lines = [line for line in self.thinking_lines if line]
                
                # Take last 20 non-empty lines
                if len(visible_lines) > 20:
                    display_text = "...\n" + "\n".join(visible_lines[-20:])
                else:
                    display_text = "\n".join(visible_lines)
                    
                if display_text:
                    thinking_panel = Panel(
                        display_text,
                        title="[yellow]🤔 Thinking[/yellow]",
                        border_style="yellow",
                        box=ROUNDED,
                        title_align="left",
                        padding=(0, 1)
                    )
                    renderables.append(thinking_panel)
            
        # Render Content
        if self.content_buffer:
            if renderables:
                renderables.append(Text(" "))
            content_text = "".join(self.content_buffer)
            renderables.append(Markdown(content_text))
            
        # Render Tool Status
        if self.tool_status:
            if renderables:
                renderables.append(Text(" "))

            tool_msg = f"Preparing tool call: {self.tool_status}..."

            total_chars = sum(len(c) for c in self.tool_args_buffer)
            if total_chars > 0:
                tool_msg += f" ({total_chars} chars received)"

            renderables.append(Panel(
                Text(tool_msg, style="cyan dim"),
                border_style="cyan dim",
                box=ROUNDED,
                padding=(0, 1)
            ))

        # Render active tool statuses (from update_tool_status)
        if self.tool_status_map:
            if renderables:
                renderables.append(Text(" "))
            tool_lines = "\n".join(self.tool_status_map.values())
            renderables.append(Panel(
                Text(tool_lines, style="cyan"),
                title="[cyan]Tools[/cyan]",
                border_style="cyan dim",
                box=ROUNDED,
                padding=(0, 1)
            ))

        # Render status line
        if self.status_text:
            if renderables:
                renderables.append(Text(" "))
            renderables.append(Text(f"  {self.status_text}", style="dim cyan"))

        return Group(*renderables)


class LiveStreamSession:
    """Context manager for a live streaming session."""
    def __init__(self):
        self.renderer = StreamRenderer()
        self.live = Live(self.renderer, console=console, refresh_per_second=10, transient=False)
        
    def __enter__(self):
        self.live.start()
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.live.stop()
        
    def update_thinking(self, chunk: str):
        self.renderer.update_thinking(chunk)
        
    def update_content(self, chunk: str):
        self.renderer.update_content(chunk)

    def update_tool(self, tool_name: str, args_chunk: str):
        self.renderer.update_tool(tool_name, args_chunk)

    def update_status(self, text: str):
        self.renderer.update_status(text)

    def update_tool_status(self, tool_name: str, status: str, args: str = None):
        self.renderer.update_tool_status(tool_name, status, args)


class ClaudeStyleUI:
    def __init__(self):
        self._thinking_lines: list[str] = []
        self._current_tool: Optional[str] = None
    
    def create_live_session(self) -> LiveStreamSession:
        return LiveStreamSession()
    
    def create_parallel_monitor(self, title: str = "Parallel Execution") -> "ParallelMonitor":
        monitor = ParallelMonitor()
        monitor.title = title
        return monitor

    def create_leader_monitor(self, leader_role: str = "Leader", max_rounds: int = 15) -> "LeaderMonitor":
        monitor = LeaderMonitor()
        monitor.leader_role = leader_role
        monitor.max_rounds = max_rounds
        return monitor

    def print_banner(self):
        banner = r"""
[bold blue]╭─────────────────────────────────────────────────────────────────╮[/bold blue]
[bold blue]│[/bold blue]                                                                 [bold blue]│ [/bold blue]
[bold blue]│[/bold blue]    [bold cyan]  _    _           _              _____          _       [/bold cyan]    [bold blue]│[/bold blue]
[bold blue]│[/bold blue]    [bold cyan] | |  | |         | |            / ____|        | |      [/bold cyan]    [bold blue]│[/bold blue]
[bold blue]│[/bold blue]    [bold cyan] | |__| |_   _  __| |_ __ __ _  | |     ___   __| | ___  [/bold cyan]    [bold blue]│[/bold blue]
[bold blue]│[/bold blue]    [bold cyan] |  __  | | | |/ _` | '__/ _` | | |    / _ \ / _` |/ _ \ [/bold cyan]    [bold blue]│[/bold blue]
[bold blue]│[/bold blue]    [bold cyan] | |  | | |_| | (_| | | | (_| | | |___| (_) | (_| |  __/ [/bold cyan]    [bold blue]│[/bold blue]
[bold blue]│[/bold blue]    [bold cyan] |_|  |_|\__, |\__,_|_|  \__,_|  \_____\___/ \__,_|\___| [/bold cyan]    [bold blue]│[/bold blue]
[bold blue]│[/bold blue]    [bold cyan]          __/ |                                          [/bold cyan]    [bold blue]│[/bold blue]
[bold blue]│[/bold blue]    [bold cyan]         |___/                                           [/bold cyan]    [bold blue]│[/bold blue]
[bold blue]│[/bold blue]                                                                 [bold blue]│[/bold blue]
[bold blue]│[/bold blue]    [bold white]Hydra Code - Dynamic Multi-Model AI Coding Assistant[/bold white]         [bold blue]│[/bold blue]
[bold blue]│[/bold blue]                                                                 [bold blue]│[/bold blue]
[bold blue]╰─────────────────────────────────────────────────────────────────╯[/bold blue]
"""
        console.print(banner)
    
    def print_user_input(self, text: str):
        console.print()
        console.print(f"[green]╭─ User Input ─{'─' * 45}[/green]")
        console.print(f"[green]│[/green] {text[:100]}")
        console.print(f"[green]╰──────────────────────────────────────────────────[/green]")
    
    def print_thinking(self, thought: str):
        if not self._thinking_lines:
            console.print(f"[yellow]╭─ 🤔 Thinking ─{'─' * 44}[/yellow]")
        self._thinking_lines.append(thought)
        console.print(f"[yellow]│[/yellow] [dim]{thought}[/dim]")
        
    def start_thinking(self):
        self._thinking_lines = []
        console.print(f"[yellow]╭─ 🤔 Thinking ─{'─' * 44}[/yellow]")
        
    def end_thinking(self):
        console.print(f"[yellow]╰──────────────────────────────────────────────────[/yellow]")
    
    def clear_thinking(self):
        if self._thinking_lines:
            self.end_thinking()
        self._thinking_lines = []
    
    def print_tool_start(self, tool_name: str, args: dict):
        self._current_tool = tool_name
        
        display_args = ""
        missing_warning = ""
        
        if args:
            if tool_name == "write_file":
                if "file_path" in args:
                    display_args = f" {args['file_path']}"
                else:
                    missing_warning = " [red](missing file_path)[/red]"
            elif tool_name == "read_file" and "file_path" in args:
                display_args = f" {args['file_path']}"
            elif tool_name == "edit_file" and "file_path" in args:
                display_args = f" {args['file_path']}"
            elif tool_name == "list_directory" and "path" in args:
                display_args = f" {args['path']}"
            elif tool_name == "create_directory" and "directory_path" in args:
                display_args = f" {args['directory_path']}"
            elif tool_name == "run_command" and "command" in args:
                cmd = args["command"]
                display_args = f" {cmd[:40]}{'...' if len(cmd) > 40 else ''}"
            else:
                key_items = []
                for k, v in list(args.items())[:2]:
                    v_str = str(v)[:25] + "..." if len(str(v)) > 25 else str(v)
                    key_items.append(f"{k}={v_str}")
                display_args = " " + " ".join(key_items) if key_items else ""
        
        display_args = display_args[:50] if display_args else ""
        line_width = max(50, len(tool_name) + len(display_args) + 5)
        console.print()
        console.print(f"[cyan]╭─ {tool_name}{display_args}{missing_warning} {'─' * max(10, line_width - len(tool_name) - len(display_args))}[/cyan]")
    
    def print_tool_output(self, output: str, success: bool = True):
        lines = output.split("\n")[:20]
        for line in lines:
            if line.strip():
                console.print(f"[dim]│[/dim] {line[:100]}{'...' if len(line) > 100 else ''}")
        
        status = "[green]✓[/green]" if success else "[red]✗[/red]"
        tool_name = self._current_tool or "done"
        console.print(f"[cyan]╰─ {status} {tool_name}[/cyan]")
        self._current_tool = None
    
    def print_tool_result(self, tool_name: str, success: bool, output: str = ""):
        status_icon = "✓" if success else "✗"
        status_color = "green" if success else "red"
        
        if output:
            lines = [l for l in output.split("\n")[:8] if l.strip()]
            for line in lines:
                console.print(f"[dim]│[/dim] {line[:90]}")
        
        console.print(f"[cyan]╰─ [{status_color}]{status_icon}[/{status_color}] {tool_name}[/cyan]")
        self._current_tool = None
    
    def print_code_writing(self, file_path: str, code: str, language: str = ""):
        ext = file_path.split(".")[-1] if "." in file_path else ""
        lang = language or ext or "text"
        
        lines = code.split("\n")
        total_lines = len(lines)
        
        display_height = 12
        
        if total_lines <= display_height:
            display_lines = lines
            start_line = 1
        else:
            display_lines = lines[-display_height:]
            start_line = total_lines - display_height + 1
        
        console.print(f"[magenta]╭─ Writing: {file_path} ({total_lines} lines) {'─' * max(10, 40 - len(file_path) - len(str(total_lines)))}[/magenta]")
        
        if total_lines > display_height:
            console.print(f"[dim]│[/dim] [dim]  ... ({total_lines - display_height} lines above)[/dim]")
        
        for i, line in enumerate(display_lines, start=start_line):
            line_num = f"{i:4d}"
            truncated_line = line[:80] if len(line) > 80 else line
            console.print(f"[dim]│[/dim] [dim]{line_num}[/dim]  {truncated_line}")
        
        console.print(f"[magenta]╰─ ✓ {file_path}[/magenta]")
    
    def print_assistant_response(self, content: str):
        console.print()
        console.print(f"[blue]╭─ Assistant ─{'─' * 48}[/blue]")
        lines = content.split("\n")
        for line in lines[:30]:
            console.print(f"[blue]│[/blue] {line[:90]}")
        if len(lines) > 30:
            console.print(f"[blue]│[/blue] ... ({len(lines) - 30} more lines)")
        console.print(f"[blue]╰──────────────────────────────────────────────────[/blue]")
    
    def print_phase(self, phase: str, description: str = ""):
        phase_icons = {
            "架构设计": "🏗️",
            "并行实现": "⚡",
            "整合验证": "🔗",
            "完成": "✅",
            "quick_routing": "⚡",
            "planning": "📋",
            "execution": "🔧",
            "completed": "✅",
            "并行协作": "🚀",
        }
        icon = phase_icons.get(phase, "▶")
        
        console.print()
        console.print(f"[bold blue]╭─ {icon} {phase} ─{'─' * (45 - len(phase))}[/bold blue]")
        if description:
            console.print(f"[bold blue]│[/bold blue] [dim]{description}[/dim]")
        console.print(f"[bold blue]╰──────────────────────────────────────────────────[/bold blue]")
    
    def print_module_status(self, modules: list[dict]):
        console.print(f"[cyan]╭─ Modules ─{'─' * 48}[/cyan]")
        for m in modules:
            status_icon = "[green]✓[/green]" if m.get("completed") else "[yellow]▶[/yellow]" if m.get("in_progress") else "[dim]○[/dim]"
            console.print(f"[cyan]│[/cyan] {status_icon} [white]{m.get('name', '')}[/white] [dim]({m.get('role', '')})[/dim]")
        console.print(f"[cyan]╰──────────────────────────────────────────────────[/cyan]")
    
    def print_confirm(self, message: str = "Continue?") -> bool:
        from rich.prompt import Confirm
        return Confirm.ask(f"[bold yellow]{message}[/bold yellow]")
    
    def print_progress(self, current: int, total: int, task: str = ""):
        bar_width = 30
        filled = int(bar_width * current / total) if total > 0 else 0
        bar = "█" * filled + "░" * (bar_width - filled)
        percent = int(100 * current / total) if total > 0 else 0
        
        console.print(f"\r[dim]│[/dim] [{bar}] {percent}% {task[:30]}", end="")
        if current == total:
            console.print()
    
    def print_error(self, error: str):
        console.print()
        console.print(f"[red]╭─ ✗ Error ─{'─' * 48}[/red]")
        lines = error.split("\n")[:10]
        for line in lines:
            console.print(f"[red]│[/red] {line[:90]}")
        console.print(f"[red]╰──────────────────────────────────────────────────[/red]")
    
    def print_stats(self, stats_data: dict):
        console.print()
        console.print(f"[yellow]╭─ 📊 Statistics ─{'─' * 42}[/yellow]")
        for k, v in stats_data.items():
            console.print(f"[yellow]│[/yellow] [cyan]{k}:[/cyan] {v}")
        console.print(f"[yellow]╰──────────────────────────────────────────────────[/yellow]")
    
    def print_input_prompt(self):
        console.print()
        console.print("[bold green]>[/bold green] ", end="")


ui = ClaudeStyleUI()
