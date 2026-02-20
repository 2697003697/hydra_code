"""
Smart context management for large codebases.
Implements lazy loading and intelligent context building.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from datetime import datetime


@dataclass
class FileInfo:
    path: str
    language: str
    size: int
    lines: int
    content: str = ""
    loaded: bool = False


@dataclass
class WorkHistory:
    tasks: list[dict] = field(default_factory=list)
    files_created: list[str] = field(default_factory=list)
    files_modified: list[str] = field(default_factory=list)
    commands_run: list[str] = field(default_factory=list)
    
    def add_task(self, description: str, result, success: bool):
        if isinstance(result, dict):
            result_str = result.get("description", str(result))[:500]
        elif isinstance(result, str):
            result_str = result[:500]
        else:
            result_str = str(result)[:500] if result else ""
        
        self.tasks.append({
            "time": datetime.now().isoformat(),
            "description": description,
            "result": result_str,
            "success": success,
        })
    
    def add_file_created(self, path: str):
        if path not in self.files_created:
            self.files_created.append(path)
    
    def add_file_modified(self, path: str):
        if path not in self.files_modified:
            self.files_modified.append(path)
    
    def add_command(self, cmd: str):
        self.commands_run.append(cmd)
    
    def get_summary(self) -> str:
        lines = []
        
        if self.tasks:
            lines.append("## 已完成的任务")
            for i, task in enumerate(self.tasks[-5:], 1):
                status = "✓" if task["success"] else "✗"
                lines.append(f"{status} {task['description']}")
        
        if self.files_created:
            lines.append(f"\n## 创建的文件: {', '.join(self.files_created)}")
        
        if self.files_modified:
            lines.append(f"\n## 修改的文件: {', '.join(self.files_modified)}")
        
        return "\n".join(lines) if lines else ""


LANGUAGE_EXTENSIONS = {
    ".py": "Python",
    ".js": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript React",
    ".jsx": "JavaScript React",
    ".java": "Java",
    ".go": "Go",
    ".rs": "Rust",
    ".c": "C",
    ".cpp": "C++",
    ".h": "C Header",
    ".hpp": "C++ Header",
    ".cs": "C#",
    ".rb": "Ruby",
    ".php": "PHP",
    ".swift": "Swift",
    ".kt": "Kotlin",
    ".html": "HTML",
    ".css": "CSS",
    ".scss": "SCSS",
    ".json": "JSON",
    ".yaml": "YAML",
    ".yml": "YAML",
    ".xml": "XML",
    ".toml": "TOML",
    ".md": "Markdown",
    ".txt": "Text",
    ".sh": "Shell",
    ".sql": "SQL",
}

IGNORE_DIRS = {
    ".git", ".svn", ".hg", "__pycache__", "node_modules",
    "venv", ".venv", "env", ".env", "build", "dist",
    "target", "out", "bin", "obj", ".idea", ".vscode",
    ".tox", ".pytest_cache", ".mypy_cache", "egg-info",
}

PRIORITY_EXTENSIONS = {
    ".py": 1, ".js": 2, ".ts": 2, ".tsx": 2, ".jsx": 2,
    ".json": 3, ".yaml": 3, ".yml": 3, ".md": 4, ".html": 5, ".css": 5,
}

MAX_FILE_SIZE = 30000
MAX_CONTEXT_SIZE = 80000


class SmartContext:
    def __init__(self, root_path: Path, work_history: Optional[WorkHistory] = None):
        self.root_path = root_path.resolve()
        self.work_history = work_history
        self.files: list[FileInfo] = []
        self.file_index: dict[str, FileInfo] = {}
        self.total_size = 0
        self._scanned = False
    
    def scan(self, max_files: int = 200):
        if self._scanned:
            return
        
        all_files = []
        
        for root, dirs, files in os.walk(self.root_path):
            dirs[:] = [d for d in dirs if d not in IGNORE_DIRS and not d.startswith(".")]
            
            for file in files:
                file_path = Path(root) / file
                ext = file_path.suffix.lower()
                language = LANGUAGE_EXTENSIONS.get(ext, "")
                
                if not language:
                    continue
                
                try:
                    rel_path = str(file_path.relative_to(self.root_path))
                    size = file_path.stat().st_size
                    lines = self._count_lines(file_path)
                    
                    info = FileInfo(
                        path=rel_path,
                        language=language,
                        size=size,
                        lines=lines,
                    )
                    all_files.append(info)
                except Exception:
                    continue
        
        all_files.sort(key=lambda x: (PRIORITY_EXTENSIONS.get(Path(x.path).suffix, 10), -x.size))
        
        self.files = all_files[:max_files]
        self.file_index = {f.path: f for f in self.files}
        self._scanned = True
    
    def _count_lines(self, file_path: Path) -> int:
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                return sum(1 for _ in f)
        except Exception:
            return 0
    
    def read_file(self, file_path: str) -> str:
        if file_path in self.file_index:
            info = self.file_index[file_path]
            if info.loaded:
                return info.content
            
            full_path = self.root_path / file_path
            try:
                with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read(MAX_FILE_SIZE + 1)
                    if len(content) > MAX_FILE_SIZE:
                        content = content[:MAX_FILE_SIZE] + "\n... (文件过大，已截断)"
                    info.content = content
                    info.loaded = True
                    return content
            except Exception as e:
                return f"# 无法读取: {e}"
        return ""
    
    def search_files(self, pattern: str) -> list[str]:
        pattern_lower = pattern.lower()
        matches = []
        for f in self.files:
            if pattern_lower in f.path.lower():
                matches.append(f.path)
        return matches[:20]
    
    def search_content(self, pattern: str, max_results: int = 10) -> list[tuple[str, str]]:
        results = []
        pattern_lower = pattern.lower()
        
        for f in self.files:
            if len(results) >= max_results:
                break
            
            content = self.read_file(f.path)
            if not content:
                continue
            
            lines = content.split("\n")
            for i, line in enumerate(lines):
                if pattern_lower in line.lower():
                    start = max(0, i - 2)
                    end = min(len(lines), i + 3)
                    context = "\n".join(lines[start:end])
                    results.append((f.path, context))
                    if len(results) >= max_results:
                        break
        
        return results
    
    def get_lightweight_context(self) -> str:
        lines = [
            f"# 工作区: {self.root_path.name}",
            f"路径: {self.root_path}",
            f"文件数: {len(self.files)}",
            "",
            "## 文件列表",
        ]
        
        for f in self.files[:30]:
            lines.append(f"- {f.path} ({f.language}, {f.lines}行, {f.size//1024}KB)")
        
        if len(self.files) > 30:
            lines.append(f"... 还有 {len(self.files) - 30} 个文件")
        
        if self.work_history:
            history = self.work_history.get_summary()
            if history:
                lines.append("")
                lines.append("## 工作历史")
                lines.append(history)
        
        return "\n".join(lines)
    
    def get_full_context(self, max_size: int = MAX_CONTEXT_SIZE) -> str:
        lines = [self.get_lightweight_context()]
        lines.append("")
        lines.append("## 文件内容")
        
        current_size = len("\n".join(lines))
        
        priority_files = []
        
        if self.work_history:
            for f in self.work_history.files_created[-5:]:
                if f in self.file_index:
                    priority_files.append(f)
            for f in self.work_history.files_modified[-5:]:
                if f in self.file_index and f not in priority_files:
                    priority_files.append(f)
        
        for f in self.files[:10]:
            if f.path not in priority_files:
                priority_files.append(f.path)
        
        loaded_count = 0
        for path in priority_files:
            if current_size > max_size:
                break
            
            content = self.read_file(path)
            if not content:
                continue
            
            file_section = f"\n### {path}\n```{self.file_index[path].language.lower()}\n{content}\n```\n"
            
            if current_size + len(file_section) > max_size:
                break
            
            lines.append(file_section)
            current_size += len(file_section)
            loaded_count += 1
        
        if loaded_count < len(priority_files):
            remaining = len(priority_files) - loaded_count
            lines.append(f"\n... 还有 {remaining} 个文件未加载")
        
        return "\n".join(lines)
    
    def get_files_for_task(self, task_description: str) -> str:
        keywords = self._extract_keywords(task_description)
        
        relevant_files = set()
        
        for keyword in keywords:
            for f in self.files:
                path_lower = f.path.lower()
                if keyword.lower() in path_lower:
                    relevant_files.add(f.path)
        
        if self.work_history:
            for f in self.work_history.files_created[-3:]:
                relevant_files.add(f)
            for f in self.work_history.files_modified[-3:]:
                relevant_files.add(f)
        
        lines = [self.get_lightweight_context()]
        lines.append("")
        lines.append("## 相关文件")
        
        current_size = len("\n".join(lines))
        
        for path in list(relevant_files)[:10]:
            if path not in self.file_index:
                continue
            
            content = self.read_file(path)
            if not content:
                continue
            
            file_section = f"\n### {path}\n```{self.file_index[path].language.lower()}\n{content}\n```\n"
            
            if current_size + len(file_section) > MAX_CONTEXT_SIZE:
                break
            
            lines.append(file_section)
            current_size += len(file_section)
        
        return "\n".join(lines)
    
    def _extract_keywords(self, text: str) -> list[str]:
        import re
        words = re.findall(r'\b[a-zA-Z_][a-zA-Z0-9_]*\b', text)
        
        stopwords = {'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been',
                     'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will',
                     'would', 'could', 'should', 'may', 'might', 'must', 'shall',
                     'can', 'need', 'dare', 'ought', 'used', 'to', 'of', 'in',
                     'for', 'on', 'with', 'at', 'by', 'from', 'as', 'into',
                     'through', 'during', 'before', 'after', 'above', 'below',
                     'between', 'under', 'again', 'further', 'then', 'once',
                     'here', 'there', 'when', 'where', 'why', 'how', 'all',
                     'each', 'few', 'more', 'most', 'other', 'some', 'such',
                     'no', 'nor', 'not', 'only', 'own', 'same', 'so', 'than',
                     'too', 'very', 'just', 'and', 'but', 'if', 'or', 'because',
                     'until', 'while', 'this', 'that', 'these', 'those', 'what',
                     'which', 'who', 'whom', 'this', 'that', 'am', 'it', 'its'}
        
        keywords = [w for w in words if w.lower() not in stopwords and len(w) > 2]
        return keywords[:10]


def get_smart_context(root_path: Path, work_history: Optional[WorkHistory] = None) -> SmartContext:
    ctx = SmartContext(root_path, work_history)
    ctx.scan()
    return ctx
