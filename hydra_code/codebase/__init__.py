"""
Codebase understanding and indexing module.
Provides smart context management for better AI understanding.
"""

from .context import (
    SmartContext,
    WorkHistory,
    FileInfo,
    get_smart_context,
    LANGUAGE_EXTENSIONS,
    IGNORE_DIRS,
    PRIORITY_EXTENSIONS,
)

__all__ = [
    "SmartContext",
    "WorkHistory",
    "FileInfo",
    "get_smart_context",
    "LANGUAGE_EXTENSIONS",
    "IGNORE_DIRS",
    "PRIORITY_EXTENSIONS",
]
