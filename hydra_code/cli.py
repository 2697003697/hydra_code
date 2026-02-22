"""
Main CLI entry point for Hydra Code.
"""

import argparse
import asyncio
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table

from .chat import ChatSession
from .config import (
    Config,
    create_sample_config,
    get_config_path,
    load_config,
    save_config,
)
from .codebase import get_smart_context
from .orchestration import ModelRole, get_role_definition
from .i18n import I18N, Language, get_i18n, set_language, t
from . import stats
from .ui import ui

console = Console()


def print_banner():
    ui.print_banner()


def print_help():
    help_text = f"""
[bold]{t("help_commands")}:[/bold]
  [cyan]/help[/cyan]        - {t("cmd_help")}
  [cyan]/new[/cyan]         - 重启程序
  [cyan]/roles[/cyan]       - {t("cmd_roles")}
  [cyan]/config[/cyan]      - {t("cmd_config")}
  [cyan]/clear[/cyan]       - {t("cmd_clear")}
  [cyan]/context[/cyan]     - {t("cmd_context")}
  [cyan]/status[/cyan]      - {t("cmd_status")}
  [cyan]/memory[/cyan]      - 记忆统计
  [cyan]/fast [dim][-y][/dim][/cyan]  - Fast 模型
  [cyan]/pro [dim][-y][/dim][/cyan]   - Pro 模型
  [cyan]/sonnet [dim][-y][/dim][/cyan]- Sonnet 模型
  [cyan]/opus [dim][-y][/dim][/cyan]  - Opus 模型
  [cyan]/parallel [dim][-y][/dim][/cyan]- 并行协作
  [cyan]/leader [role][/cyan]   - Leader 模式 (默认: opus)
  [cyan]/auto[/cyan]        - 自动判断
  [cyan]/stats[/cyan]       - API统计
  [cyan]/lang[/cyan]        - {t("cmd_lang")}
  [cyan]/model[/cyan]       - {t("cmd_model")}
  [cyan]/yes[/cyan]         - {t("cmd_yes")}
  [cyan]/exit[/cyan]        - {t("cmd_exit")}

[bold]模式说明:[/bold]
  [yellow]Fast[/yellow]    - 快速响应，适合简单任务
  [yellow]Pro[/yellow]     - 平衡性能，适合中等任务
  [yellow]Sonnet[/yellow]  - 高质量，适合复杂任务
  [yellow]Opus[/yellow]    - 最强能力，适合困难任务
  [yellow]Parallel[/yellow]- 多模型并行协作
  [yellow]Leader[/yellow]  - 主从协作模式
  [yellow]Auto[/yellow]    - 自动选择模式
"""
    console.print(Panel(help_text, title="[bold blue] Help [/bold blue]", border_style="blue"))


def get_role_name(role: ModelRole) -> str:
    role_names = {
        ModelRole.FAST: t("role_fast"),
        ModelRole.PRO: t("role_pro"),
        ModelRole.SONNET: t("role_sonnet"),
        ModelRole.OPUS: t("role_opus"),
    }
    return role_names.get(role, role.value)


def get_role_description(role: ModelRole) -> str:
    role_descs = {
        ModelRole.FAST: t("role_fast_desc"),
        ModelRole.PRO: t("role_pro_desc"),
        ModelRole.SONNET: t("role_sonnet_desc"),
        ModelRole.OPUS: t("role_opus_desc"),
    }
    return role_descs.get(role, "")


def print_roles(config: Config):
    table = Table(title=t("roles_title"), show_header=True, header_style="bold cyan")
    table.add_column(t("role_config"), style="yellow")
    table.add_column(t("help_roles")[:-1], style="green")
    table.add_column("Model", style="green")
    
    for role in ModelRole:
        role_def = get_role_definition(role)
        
        _, _, model_name, _, max_tokens = config.get_role_config(role.value)
        if not model_name:
            model_name = t("not_configured")
        
        info = model_name
        if max_tokens:
            info += f"\n(Max Tokens: {max_tokens})"

        table.add_row(
            f"{get_role_name(role)}\n({role.value})",
            get_role_description(role),
            info,
        )
    
    console.print(table)


def show_config(config: Config):
    config_text = f"""
[bold]{t("config_title")}:[/bold]
  {t("config_file")}: [cyan]{get_config_path()}[/cyan]
  {t("default_role")}: [cyan]{config.default_role}[/cyan]
  {t("current_language")}: [cyan]{config.language}[/cyan]
  Max tokens: [cyan]{config.max_tokens}[/cyan]
  Temperature: [cyan]{config.temperature}[/cyan]
  Auto-approve: [cyan]{config.auto_approve}[/cyan]
  Single model mode: [cyan]{config.single_model_mode}[/cyan]
  {t("working_directory")}: [cyan]{config.working_directory or Path.cwd()}[/cyan]

[bold]{t("role_config")}:[/bold]
"""
    for role in ModelRole:
        _, _, model_name, _, max_tokens = config.get_role_config(role.value)
        if not model_name:
            model_name = t("not_configured")
        config_text += f"  {get_role_name(role)} ({role.value}): {model_name}"
        if max_tokens:
            config_text += f" (Max Tokens: {max_tokens})"
        config_text += "\n"

    console.print(Panel(config_text, title=t("config_title"), border_style="cyan"))


def show_context(working_dir: Path):
    console.print(f"\n[dim]{t("analyzing_codebase")}[/dim]")
    context = get_smart_context(working_dir)
    console.print(Panel(context.get_lightweight_context(), title=t("codebase_context"), border_style="green"))


def show_models(config: Config):
    """Show available models and current assignments."""
    table = Table(title=t("model_title"), show_header=True, header_style="bold cyan")
    table.add_column("Model Name", style="yellow")
    table.add_column("Provider", style="green")
    table.add_column("Details", style="white")

    if not config.models:
        console.print("[yellow]No models defined in config.models[/yellow]")
        return

    for name, model in config.models.items():
        info = f"Model: {model.model_name}"
        if model.description:
            info += f"\nDesc: {model.description}"
        if model.base_url:
            info += f"\nURL: {model.base_url}"
        if model.max_tokens:
            info += f"\nMax Tokens: {model.max_tokens}"
        
        table.add_row(name, model.provider, info)
    
    console.print(table)
    console.print(f"\n[dim]{t('model_usage')}[/dim]")


async def run_interactive(config: Config):
    i18n = get_i18n()
    if config.language == "en":
        i18n.set_language(Language.EN)
    else:
        i18n.set_language(Language.ZH)

    print_banner()

    working_dir = Path(config.working_directory) if config.working_directory else Path.cwd()
    
    console.print(f"[dim blue]│[/dim blue] Working Directory: [cyan]{working_dir}[/cyan]")
    console.print(f"[dim blue]│[/dim blue] Type [yellow]/help[/yellow] for commands")
    console.print(f"[dim blue]╰────────────────────────────────────────────────────[/dim blue]\n")

    session = ChatSession(config, str(working_dir))

    while True:
        try:
            console.print()
            user_input = Prompt.ask("[bold green]>[/bold green]").strip()

            if not user_input:
                continue

            if user_input.startswith("/"):
                parts = user_input.split(maxsplit=1)
                command = parts[0].lower()

                if command in ("/exit", "/quit", "/q"):
                    console.print(f"\n[dim blue]╭────────────────────────────────────────────────────[/dim blue]")
                    console.print(f"[dim blue]│[/dim blue] [cyan]Goodbye! 👋[/cyan]")
                    console.print(f"[dim blue]╰────────────────────────────────────────────────────[/dim blue]")
                    break
                elif command == "/new":
                    console.print(f"[cyan]Restarting...[/cyan]")
                    import subprocess
                    import sys
                    if sys.platform == "win32":
                        subprocess.Popen(["start", "cmd", "/k", sys.executable, "-m", "aicli"], shell=True)
                    else:
                        subprocess.Popen([sys.executable, "-m", "aicli"])
                    break
                elif command == "/help":
                    print_help()
                elif command == "/roles":
                    print_roles(config)
                elif command == "/config":
                    show_config(config)
                elif command == "/clear":
                    session.clear_history()
                    console.print(f"[green]{t("cleared")}[/green]")
                elif command == "/context":
                    show_context(working_dir)
                elif command == "/model":
                    parts = user_input.split()
                    if len(parts) == 1:
                        show_models(config)
                    elif len(parts) >= 2 and parts[1] == "list":
                        show_models(config)
                    elif len(parts) == 4 and parts[1] == "use":
                        role_name = parts[2].lower()
                        model_name = parts[3]
                        
                        valid_roles = [r.value for r in ModelRole]
                        if role_name not in valid_roles:
                            console.print(f"[red]Invalid role: {role_name}. Valid roles: {', '.join(valid_roles)}[/red]")
                            continue
                            
                        if model_name not in config.models:
                            console.print(f"[red]Model '{model_name}' not found in config.[/red]")
                            continue
                            
                        # Update config
                        config.role_configs[role_name].use_model = model_name
                        save_config(config)
                        
                        console.print(f"[green]Role '{role_name}' switched to use model '{model_name}'.[/green]")
                        
                        # Re-initialize session to clear cached clients
                        session = ChatSession(config, str(working_dir))
                    else:
                         console.print(f"[yellow]{t('model_usage')}[/yellow]")
                elif command == "/lang":
                    new_lang = i18n.toggle_language()
                    config.language = new_lang.value
                    console.print(f"[green]{t("language_switched")}[/green]")
                elif command == "/yes":
                    config.auto_approve = not config.auto_approve
                    msg = t("auto_approve_enabled") if config.auto_approve else t("auto_approve_disabled")
                    console.print(f"[green]{msg}[/green]")
                elif command == "/status":
                    status = session.get_collaboration_status()
                    if status.get("status") != "unavailable":
                        phase = status.get("phase", "unknown")
                        iteration = status.get("iteration", 0)
                        pending = status.get("pending_messages", 0)
                        memory = status.get("memory", {})
                        
                        agents_info = "\n".join(
                            f"  • {a['role']} ({a['model']}): {t('busy') if a['busy'] else t('idle')}"
                            for a in status.get("agents", [])
                        )
                        
                        memory_info = ""
                        if memory:
                            memory_info = f"\n\n记忆: {memory.get('message_count', 0)}条消息, ~{memory.get('total_tokens', 0)}tokens"
                        
                        console.print(Panel(
                            f"{t('phase')}: {phase}\n"
                            f"{t('iteration')}: {iteration}\n"
                            f"{t('pending_messages')}: {pending}\n\n"
                            f"{t('agents')}:\n{agents_info}"
                            f"{memory_info}",
                            title=t("collaboration_status"),
                            border_style="green",
                        ))
                    else:
                        console.print(f"[yellow]{t("collaboration_not_active")}[/yellow]")
                elif command == "/memory":
                    session.show_memory_stats()
                elif command in ["/fast", "/pro", "/sonnet", "/opus", "/parallel", "/leader", "/auto"]:
                    mode = command[1:]
                    
                    # Parse args
                    leader_role = None
                    console.print(f"[dim]Debug: parts={parts}, command={command}[/dim]")
                    if len(parts) > 1:
                        args = parts[1].split()
                        if "-y" in args or "--yes" in args:
                            config.auto_approve = True
                            console.print(f"[dim]{t('auto_approve_enabled')}[/dim]")
                        
                        # Extract leader role for /leader command
                        if command == "/leader":
                            for arg in args:
                                if not arg.startswith("-"):
                                    leader_role = arg
                                    break
                    
                    session.set_mode(mode, leader_role=leader_role)
                elif command == "/stats":
                    s = stats.get_stats()
                    console.print(Panel(s.get_summary(), title="[yellow]API调用统计[/yellow]", border_style="yellow"))
                else:
                    console.print(f"[red]{t("unknown_command")}: {command}[/red]")
                    console.print(f"[dim]{t("type_help")}[/dim]")
            else:
                await session.process_message(user_input)

        except KeyboardInterrupt:
            console.print(f"\n[cyan]{t("use_exit")}[/cyan]")
        except EOFError:
            break


def main():
    parser = argparse.ArgumentParser(description="Hydra Code - AI Code Assistant")
    parser.add_argument(
        "--config",
        "-c",
        action="store_true",
        help="Show current configuration",
    )
    parser.add_argument(
        "--init",
        action="store_true",
        help="Create a sample configuration file",
    )
    parser.add_argument(
        "--directory",
        "-d",
        type=str,
        help="Working directory",
    )
    parser.add_argument(
        "--lang",
        "-l",
        type=str,
        choices=["zh", "en"],
        help="Language (zh/en)",
    )
    parser.add_argument(
        "--yes",
        "-y",
        action="store_true",
        help="Auto-approve all actions",
    )
    parser.add_argument(
        "--roles",
        action="store_true",
        help="List available roles",
    )
    parser.add_argument(
        "prompt",
        nargs="?",
        help="Single prompt to execute (non-interactive mode)",
    )

    args = parser.parse_args()

    if args.lang:
        i18n = get_i18n()
        if args.lang == "en":
            i18n.set_language(Language.EN)
        else:
            i18n.set_language(Language.ZH)

    if args.init:
        create_sample_config()
        console.print(f"[green]{t("created_config")} {get_config_path()}[/green]")
        console.print(f"[dim]{t("edit_config")}[/dim]")
        return

    config = load_config()

    if args.lang:
        config.language = args.lang

    i18n = get_i18n()
    if config.language == "en":
        i18n.set_language(Language.EN)
    else:
        i18n.set_language(Language.ZH)

    if args.yes:
        config.auto_approve = True
        console.print(f"[dim]{t('auto_approve_enabled')}[/dim]")

    if args.config:
        show_config(config)
        return

    if args.roles:
        print_roles(config)
        return

    if args.directory:
        config.working_directory = args.directory

    configured_roles = config.get_configured_roles()
    if not configured_roles:
        console.print(f"[red]{t("no_api_keys")}[/red]")
        console.print(f"[dim]{t("run_init")}[/dim]")
        return

    if args.prompt:
        working_dir = Path(config.working_directory) if config.working_directory else Path.cwd()
        session = ChatSession(config, str(working_dir))
        asyncio.run(session.process_message(args.prompt))
    else:
        asyncio.run(run_interactive(config))


if __name__ == "__main__":
    main()
