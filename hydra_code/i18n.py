"""
Internationalization (i18n) support for Hydra Code.
Supports Chinese and English languages.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class Language(Enum):
    ZH = "zh"
    EN = "en"


@dataclass
class I18N:
    lang: Language = Language.ZH

    MESSAGES: dict[str, dict[Language, str]] = None

    def __post_init__(self):
        self.MESSAGES = {
            "banner": {
                Language.ZH: """
[bold cyan]╔═══════════════════════════════════════════════════════╗
║         [bold white]Hydra Code[/bold white] - AI 代码助手                ║
║         动态多模型协作系统                              ║
╚═══════════════════════════════════════════════════════╝[/bold cyan]
""",
                Language.EN: """
[bold cyan]╔═══════════════════════════════════════════════════════╗
║         [bold white]Hydra Code[/bold white] - AI Code Assistant             ║
║       Dynamic Multi-Model Collaboration System         ║
╚═══════════════════════════════════════════════════════╝[/bold cyan]
""",
            },
            "help_title": {
                Language.ZH: "帮助",
                Language.EN: "Help",
            },
            "help_commands": {
                Language.ZH: "可用命令",
                Language.EN: "Available Commands",
            },
            "help_collaboration": {
                Language.ZH: "动态协作功能",
                Language.EN: "Dynamic Collaboration Features",
            },
            "help_roles": {
                Language.ZH: "角色定义",
                Language.EN: "Role Definitions",
            },
            "help_protocol": {
                Language.ZH: "协作协议",
                Language.EN: "Collaboration Protocol",
            },
            "cmd_help": {
                Language.ZH: "显示帮助信息",
                Language.EN: "Show help message",
            },
            "cmd_roles": {
                Language.ZH: "显示角色配置",
                Language.EN: "Show role configurations",
            },
            "cmd_config": {
                Language.ZH: "显示当前配置",
                Language.EN: "Show current configuration",
            },
            "cmd_clear": {
                Language.ZH: "清空对话历史",
                Language.EN: "Clear conversation history",
            },
            "cmd_context": {
                Language.ZH: "显示代码库上下文",
                Language.EN: "Show codebase context",
            },
            "cmd_status": {
                Language.ZH: "显示协作状态",
                Language.EN: "Show collaboration status",
            },
            "cmd_lang": {
                Language.ZH: "切换语言",
                Language.EN: "Switch language",
            },
            "cmd_yes": {
                Language.ZH: "切换自动确认模式",
                Language.EN: "Toggle auto-approve mode",
            },
            "auto_approve_enabled": {
                Language.ZH: "自动确认模式已启用",
                Language.EN: "Auto-approve mode enabled",
            },
            "auto_approve_disabled": {
                Language.ZH: "自动确认模式已禁用",
                Language.EN: "Auto-approve mode disabled",
            },
            "cmd_exit": {
                Language.ZH: "退出 CLI",
                Language.EN: "Exit the CLI",
            },
            "config_file": {
                Language.ZH: "配置文件",
                Language.EN: "Config file",
            },
            "default_role": {
                Language.ZH: "默认角色",
                Language.EN: "Default role",
            },
            "working_directory": {
                Language.ZH: "工作目录",
                Language.EN: "Working directory",
            },
            "role_config": {
                Language.ZH: "角色配置",
                Language.EN: "Role Configuration",
            },
            "not_configured": {
                Language.ZH: "未配置",
                Language.EN: "Not configured",
            },
            "config_title": {
                Language.ZH: "配置",
                Language.EN: "Configuration",
            },
            "roles_title": {
                Language.ZH: "角色配置",
                Language.EN: "Role Configuration",
            },
            "role_fast": {
                Language.ZH: "Fast",
                Language.EN: "Fast",
            },
            "role_pro": {
                Language.ZH: "Pro",
                Language.EN: "Pro",
            },
            "role_sonnet": {
                Language.ZH: "Sonnet",
                Language.EN: "Sonnet",
            },
            "role_opus": {
                Language.ZH: "Opus",
                Language.EN: "Opus",
            },
            "role_fast_desc": {
                Language.ZH: "任务分析与分发，快速响应",
                Language.EN: "Task analysis & routing, quick responses",
            },
            "role_pro_desc": {
                Language.ZH: "项目规划与核心代码编写",
                Language.EN: "Code architecture & core development",
            },
            "role_sonnet_desc": {
                Language.ZH: "深度推理与问题解决",
                Language.EN: "Deep reasoning & problem solving",
            },
            "role_opus_desc": {
                Language.ZH: "工具调用与中文任务",
                Language.EN: "Tool calls & Chinese tasks",
            },
            "goodbye": {
                Language.ZH: "再见！",
                Language.EN: "Goodbye!",
            },
            "use_exit": {
                Language.ZH: "使用 /exit 退出",
                Language.EN: "Use /exit to quit",
            },
            "cleared": {
                Language.ZH: "对话已清空",
                Language.EN: "Conversation cleared",
            },
            "unknown_command": {
                Language.ZH: "未知命令",
                Language.EN: "Unknown command",
            },
            "type_help": {
                Language.ZH: "输入 /help 查看可用命令",
                Language.EN: "Type /help for available commands",
            },
            "no_api_keys": {
                Language.ZH: "没有配置任何 API 密钥",
                Language.EN: "No API keys configured",
            },
            "run_init": {
                Language.ZH: "运行 'hydra --init' 创建配置文件",
                Language.EN: "Run 'hydra --init' to create a config file",
            },
            "created_config": {
                Language.ZH: "已创建示例配置文件",
                Language.EN: "Created sample config at",
            },
            "edit_config": {
                Language.ZH: "请编辑文件并添加您的 API 密钥",
                Language.EN: "Please edit the file and add your API keys",
            },
            "analyzing_codebase": {
                Language.ZH: "分析代码库...",
                Language.EN: "Analyzing codebase...",
            },
            "codebase_context": {
                Language.ZH: "代码库上下文",
                Language.EN: "Codebase Context",
            },
            "collaboration_status": {
                Language.ZH: "协作状态",
                Language.EN: "Collaboration Status",
            },
            "collaboration_not_active": {
                Language.ZH: "协作系统未激活",
                Language.EN: "Collaboration system not active",
            },
            "phase": {
                Language.ZH: "阶段",
                Language.EN: "Phase",
            },
            "iteration": {
                Language.ZH: "迭代",
                Language.EN: "Iteration",
            },
            "pending_messages": {
                Language.ZH: "待处理消息",
                Language.EN: "Pending messages",
            },
            "agents": {
                Language.ZH: "代理",
                Language.EN: "Agents",
            },
            "busy": {
                Language.ZH: "忙碌",
                Language.EN: "busy",
            },
            "idle": {
                Language.ZH: "空闲",
                Language.EN: "idle",
            },
            "language_switched": {
                Language.ZH: "语言已切换为中文",
                Language.EN: "Language switched to English",
            },
            "current_language": {
                Language.ZH: "当前语言",
                Language.EN: "Current language",
            },
            "you": {
                Language.ZH: "你",
                Language.EN: "You",
            },
            "working_dir": {
                Language.ZH: "工作目录",
                Language.EN: "Working directory",
            },
            "dynamic_collab": {
                Language.ZH: "动态协作: 已启用",
                Language.EN: "Dynamic collaboration: Enabled",
            },
            "type_help_hint": {
                Language.ZH: "输入 /help 查看可用命令",
                Language.EN: "Type /help for available commands",
            },
            "start_collab": {
                Language.ZH: "开始协作处理复杂任务...",
                Language.EN: "Starting collaboration for complex task...",
            },
            "max_iterations": {
                Language.ZH: "达到最大迭代次数，整合当前结果",
                Language.EN: "Max iterations reached, consolidating results",
            },
            "request_help": {
                Language.ZH: "请求帮助",
                Language.EN: "requesting help",
            },
            "share_discovery": {
                Language.ZH: "分享发现",
                Language.EN: "sharing discovery",
            },
            "delegate_task": {
                Language.ZH: "委派任务给",
                Language.EN: "delegating task to",
            },
            "handoff": {
                Language.ZH: "移交给",
                Language.EN: "handing off to",
            },
            "progress": {
                Language.ZH: "进度",
                Language.EN: "progress",
            },
            "task_complete": {
                Language.ZH: "标记任务完成",
                Language.EN: "marked task complete",
            },
            "processing": {
                Language.ZH: "处理中...",
                Language.EN: "processing...",
            },
            "no_model": {
                Language.ZH: "没有可用的模型来回答问题",
                Language.EN: "No available model to answer the question",
            },
            "error_occurred": {
                Language.ZH: "发生错误",
                Language.EN: "Error occurred",
            },
        }

    def t(self, key: str) -> str:
        msg = self.MESSAGES.get(key, {})
        return msg.get(self.lang, key)

    def set_language(self, lang: Language):
        self.lang = lang

    def toggle_language(self) -> Language:
        if self.lang == Language.ZH:
            self.lang = Language.EN
        else:
            self.lang = Language.ZH
        return self.lang


_i18n: Optional[I18N] = None


def get_i18n() -> I18N:
    global _i18n
    if _i18n is None:
        _i18n = I18N()
    return _i18n


def set_language(lang: Language):
    get_i18n().set_language(lang)


def t(key: str) -> str:
    return get_i18n().t(key)
