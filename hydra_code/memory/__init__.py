"""
Intelligent conversation memory management.
Implements sliding window, summarization, and key information extraction.
"""

import re
import json
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime
from enum import Enum


class MessageType(Enum):
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"
    SYSTEM = "system"
    SUMMARY = "summary"


@dataclass
class MemoryMessage:
    role: MessageType
    content: str
    timestamp: str = ""
    token_count: int = 0
    importance: int = 0
    tool_calls: list = field(default_factory=list)
    tool_call_id: str = ""
    
    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()
        if self.token_count == 0:
            self.token_count = self._estimate_tokens()
    
    def _estimate_tokens(self) -> int:
        return len(self.content) // 4 + len(self.content.split())


@dataclass
class KeyDecision:
    content: str
    timestamp: str
    related_files: list[str] = field(default_factory=list)


@dataclass
class ConversationMemory:
    max_messages: int = 20
    max_tokens: int = 8000
    summary_threshold: int = 10
    
    messages: list[MemoryMessage] = field(default_factory=list)
    summaries: list[str] = field(default_factory=list)
    key_decisions: list[KeyDecision] = field(default_factory=list)
    files_created: list[str] = field(default_factory=list)
    files_modified: list[str] = field(default_factory=list)
    current_task: str = ""
    
    def add_message(self, role: MessageType, content: str, importance: int = 0, **kwargs) -> MemoryMessage:
        msg = MemoryMessage(
            role=role,
            content=content,
            importance=importance,
            **kwargs
        )
        
        if importance == 0:
            if role == MessageType.USER:
                msg.importance = 10
            elif role == MessageType.TOOL:
                msg.importance = 3
        
        self.messages.append(msg)
        
        self._extract_key_info(content, role)
        
        self._maybe_compress()
        
        return msg
    
    def _extract_key_info(self, content: str, role: MessageType):
        create_patterns = [
            r'创建[了]?\s*(?:文件|项目|模块)\s*([a-zA-Z0-9_\-\./\\]+\.[a-zA-Z0-9]+)',
            r'新建[了]?\s*(?:文件|项目|模块)\s*([a-zA-Z0-9_\-\./\\]+\.[a-zA-Z0-9]+)',
            r'write_file.*?([^\s]+\.(?:py|js|ts|html|css|json))',
        ]
        
        for pattern in create_patterns:
            matches = re.findall(pattern, content, re.IGNORECASE)
            for match in matches:
                if isinstance(match, tuple):
                    match = match[0]
                if match and match not in self.files_created:
                    self.files_created.append(match)
        
        modify_patterns = [
            r'修改[了]?\s*(?:文件|代码|函数)\s*([a-zA-Z0-9_\-\./\\]+\.[a-zA-Z0-9]+)',
            r'更新[了]?\s*(?:文件|代码)\s*([a-zA-Z0-9_\-\./\\]+\.[a-zA-Z0-9]+)',
            r'edit_file.*?([^\s]+\.(?:py|js|ts|html|css|json))',
        ]
        
        for pattern in modify_patterns:
            matches = re.findall(pattern, content, re.IGNORECASE)
            for match in matches:
                if isinstance(match, tuple):
                    match = match[0]
                if match and match not in self.files_modified:
                    self.files_modified.append(match)
        
        if role == MessageType.ASSISTANT:
            decision_patterns = [
                r'(?:决定|方案|解决|实现)[:：]\s*(.+)',
                r'(?:关键|重要|注意)[:：]\s*(.+)',
            ]
            
            for pattern in decision_patterns:
                matches = re.findall(pattern, content)
                for match in matches:
                    if len(match) > 10:
                        self.key_decisions.append(KeyDecision(
                            content=match[:200],
                            timestamp=datetime.now().isoformat(),
                        ))
    
    def _maybe_compress(self):
        total_tokens = sum(m.token_count for m in self.messages)
        
        if len(self.messages) > self.max_messages or total_tokens > self.max_tokens:
            self._compress_old_messages()
    
    def _compress_old_messages(self):
        keep_recent = self.max_messages // 2
        
        old_messages = self.messages[:-keep_recent]
        recent_messages = self.messages[-keep_recent:]
        
        summary = self._summarize_messages(old_messages)
        
        if summary:
            self.summaries.append(summary)
        
        important_old = [m for m in old_messages if m.importance >= 8]
        
        self.messages = important_old + recent_messages
    
    def _summarize_messages(self, messages: list[MemoryMessage]) -> str:
        if not messages:
            return ""
        
        user_msgs = [m.content for m in messages if m.role == MessageType.USER]
        assistant_msgs = [m.content[:200] for m in messages if m.role == MessageType.ASSISTANT]
        
        parts = []
        
        if user_msgs:
            parts.append(f"用户请求: {user_msgs[-1][:100]}...")
        
        if assistant_msgs:
            parts.append(f"助手响应: {len(assistant_msgs)} 条")
        
        if self.files_created:
            parts.append(f"创建文件: {', '.join(self.files_created[-5:])}")
        
        if self.files_modified:
            parts.append(f"修改文件: {', '.join(self.files_modified[-5:])}")
        
        return " | ".join(parts) if parts else ""
    
    def get_context_for_model(self, max_tokens: int = 4000) -> list[dict]:
        result = []
        current_tokens = 0
        
        if self.summaries:
            summary_text = f"[历史摘要] {self.summaries[-1]}"
            result.append({"role": "system", "content": summary_text})
            current_tokens += len(summary_text) // 4
        
        if self.key_decisions:
            decisions_text = "[关键决策]\n" + "\n".join([
                f"- {d.content[:100]}" for d in self.key_decisions[-3:]
            ])
            result.append({"role": "system", "content": decisions_text})
            current_tokens += len(decisions_text) // 4
        
        files_context = []
        if self.files_created:
            files_context.append(f"已创建: {', '.join(self.files_created[-5:])}")
        if self.files_modified:
            files_context.append(f"已修改: {', '.join(self.files_modified[-5:])}")
        
        if files_context:
            text = "[文件操作] " + " | ".join(files_context)
            result.append({"role": "system", "content": text})
            current_tokens += len(text) // 4
        
        chat_messages = []
        for msg in reversed(self.messages):
            msg_tokens = msg.token_count
            
            if current_tokens + msg_tokens > max_tokens:
                # Critical check: Are we splitting a tool-assistant pair?
                # If the first message in our current context is a tool output,
                # and the message we are about to skip is the assistant call,
                # we MUST include it to avoid protocol errors (orphan tool outputs).
                is_parent_assistant = (
                    chat_messages and 
                    chat_messages[0]['role'] == 'tool' and
                    msg.role == MessageType.ASSISTANT and 
                    msg.tool_calls
                )
                
                if not is_parent_assistant:
                    break
            
            role_map = {
                MessageType.USER: "user",
                MessageType.ASSISTANT: "assistant",
                MessageType.TOOL: "tool",
                MessageType.SYSTEM: "system",
            }
            
            msg_dict = {
                "role": role_map.get(msg.role, "user"),
                "content": msg.content,
            }
            
            if msg.tool_calls:
                msg_dict["tool_calls"] = msg.tool_calls
            if msg.tool_call_id:
                msg_dict["tool_call_id"] = msg.tool_call_id
            
            chat_messages.insert(0, msg_dict)
            current_tokens += msg_tokens
            
        # Safety cleanup: Ensure we don't start with a tool message
        # This handles cases where we broke in the middle of a tool chain
        # or couldn't fit the assistant even with the soft limit logic above
        while chat_messages and chat_messages[0]['role'] == 'tool':
            chat_messages.pop(0)
            
        return result + chat_messages
    
    def get_compact_history(self) -> str:
        lines = []
        
        if self.summaries:
            lines.append(f"## 历史摘要\n{self.summaries[-1]}")
        
        if self.key_decisions:
            lines.append("\n## 关键决策")
            for d in self.key_decisions[-5:]:
                lines.append(f"- {d.content[:100]}")
        
        if self.files_created or self.files_modified:
            lines.append("\n## 文件操作")
            if self.files_created:
                lines.append(f"创建: {', '.join(self.files_created)}")
            if self.files_modified:
                lines.append(f"修改: {', '.join(self.files_modified)}")
        
        recent = self.messages[-5:]
        if recent:
            lines.append("\n## 最近对话")
            for msg in recent:
                role_name = {
                    MessageType.USER: "用户",
                    MessageType.ASSISTANT: "助手",
                    MessageType.TOOL: "工具",
                }.get(msg.role, "未知")
                lines.append(f"{role_name}: {msg.content[:100]}...")
        
        return "\n".join(lines)
    
    def clear(self):
        self.messages.clear()
        self.summaries.clear()
        self.key_decisions.clear()
        self.files_created.clear()
        self.files_modified.clear()
    
    def get_stats(self) -> dict:
        return {
            "message_count": len(self.messages),
            "total_tokens": sum(m.token_count for m in self.messages),
            "summary_count": len(self.summaries),
            "key_decisions": len(self.key_decisions),
            "files_created": len(self.files_created),
            "files_modified": len(self.files_modified),
        }


def create_memory(max_messages: int = 20, max_tokens: int = 8000) -> ConversationMemory:
    return ConversationMemory(
        max_messages=max_messages,
        max_tokens=max_tokens,
    )
