"""
Memory system for JARVIS LOCAL.
Inspired by Aivy OS memory architecture.
Provides conversation memory, core memory, and long-term knowledge storage.
"""

from __future__ import annotations

import json
import hashlib
import time
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Mapping
from datetime import datetime


@dataclass
class MemoryEntry:
    """A single memory entry."""
    id: str
    content: str
    category: str  # "conversation", "fact", "preference", "task"
    timestamp: float
    importance: float = 0.5  # 0.0 to 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    access_count: int = 0
    last_accessed: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "content": self.content,
            "category": self.category,
            "timestamp": self.timestamp,
            "importance": self.importance,
            "metadata": self.metadata,
            "access_count": self.access_count,
            "last_accessed": self.last_accessed,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "MemoryEntry":
        return cls(
            id=str(data.get("id", "")),
            content=str(data.get("content", "")),
            category=str(data.get("category", "conversation")),
            timestamp=float(data.get("timestamp", 0.0)),
            importance=float(data.get("importance", 0.5)),
            metadata=dict(data.get("metadata", {})),
            access_count=int(data.get("access_count", 0)),
            last_accessed=float(data.get("last_accessed", 0.0)),
        )


class MemoryStore:
    """
    Memory store with core memory (always in context) and long-term memory (searchable).
    
    Architecture (inspired by Aivy OS):
    - core_memory: Always-loaded key facts (owner name, preferences, etc.)
    - short_term: Recent conversation context (last N turns)
    - long_term: Searchable knowledge base with importance scoring
    """

    def __init__(self, data_dir: Optional[Path] = None, max_core: int = 30, max_short_term: int = 50):
        self._lock = threading.RLock()
        self._data_dir = data_dir or Path.home() / ".jarvis" / "memory"
        self._data_dir.mkdir(parents=True, exist_ok=True)

        self._max_core = max_core
        self._max_short_term = max_short_term

        # Core memory - always in context
        self._core: Dict[str, MemoryEntry] = {}
        # Short-term conversation memory
        self._short_term: List[MemoryEntry] = []
        # Long-term searchable memory
        self._long_term: Dict[str, MemoryEntry] = {}

        # Load persisted memory
        self._load()

    def _load(self):
        """Load memory from disk."""
        try:
            core_file = self._data_dir / "core_memory.json"
            if core_file.exists():
                data = json.loads(core_file.read_text(encoding="utf-8"))
                self._core = {k: MemoryEntry.from_dict(v) for k, v in data.items()}

            short_file = self._data_dir / "short_term.json"
            if short_file.exists():
                data = json.loads(short_file.read_text(encoding="utf-8"))
                self._short_term = [MemoryEntry.from_dict(item) for item in data]

            long_file = self._data_dir / "long_term.json"
            if long_file.exists():
                data = json.loads(long_file.read_text(encoding="utf-8"))
                self._long_term = {k: MemoryEntry.from_dict(v) for k, v in data.items()}
        except (json.JSONDecodeError, OSError) as e:
            print(f"[Memory] Warning: Failed to load memory: {e}")

    def _save(self):
        """Persist memory to disk."""
        try:
            core_file = self._data_dir / "core_memory.json"
            core_file.write_text(
                json.dumps({k: v.to_dict() for k, v in self._core.items()}, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )

            short_file = self._data_dir / "short_term.json"
            short_file.write_text(
                json.dumps([item.to_dict() for item in self._short_term[-self._max_short_term:]], ensure_ascii=False, indent=2),
                encoding="utf-8"
            )

            long_file = self._data_dir / "long_term.json"
            long_file.write_text(
                json.dumps({k: v.to_dict() for k, v in self._long_term.items()}, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
        except OSError as e:
            print(f"[Memory] Warning: Failed to save memory: {e}")

    def _generate_id(self, content: str) -> str:
        """Generate a deterministic ID for content."""
        return hashlib.md5(content.encode("utf-8")).hexdigest()[:12]

    # --- Core Memory (always in context) ---

    def set_core(self, key: str, content: str, importance: float = 0.8) -> None:
        """Set a core memory entry (always included in context)."""
        with self._lock:
            entry = MemoryEntry(
                id=key,
                content=content,
                category="core",
                timestamp=time.time(),
                importance=importance,
            )
            self._core[key] = entry
            # Enforce limit
            if len(self._core) > self._max_core:
                # Remove least important
                sorted_keys = sorted(self._core.keys(), key=lambda k: self._core[k].importance)
                for k in sorted_keys[:len(self._core) - self._max_core]:
                    del self._core[k]
            self._save()

    def get_core(self, key: str) -> Optional[str]:
        """Get a core memory entry."""
        with self._lock:
            entry = self._core.get(key)
            if entry:
                entry.access_count += 1
                entry.last_accessed = time.time()
                return entry.content
            return None

    def get_all_core(self) -> Dict[str, str]:
        """Get all core memory entries."""
        with self._lock:
            return {k: v.content for k, v in self._core.items()}

    def delete_core(self, key: str) -> bool:
        """Delete a core memory entry."""
        with self._lock:
            if key in self._core:
                del self._core[key]
                self._save()
                return True
            return False

    # --- Short-term Memory (recent conversation) ---

    def add_conversation(self, role: str, content: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        """Add a conversation turn to short-term memory."""
        with self._lock:
            entry = MemoryEntry(
                id=self._generate_id(f"{role}:{content}"),
                content=content,
                category="conversation",
                timestamp=time.time(),
                importance=0.3,
                metadata={"role": role, **(metadata or {})},
            )
            self._short_term.append(entry)
            # Trim to limit
            if len(self._short_term) > self._max_short_term:
                self._short_term = self._short_term[-self._max_short_term:]
            self._save()

    def get_recent_conversation(self, count: int = 10) -> List[Dict[str, str]]:
        """Get recent conversation turns."""
        with self._lock:
            recent = self._short_term[-count:]
            return [
                {"role": e.metadata.get("role", "user"), "content": e.content}
                for e in recent
            ]

    def clear_conversation(self) -> None:
        """Clear short-term conversation memory."""
        with self._lock:
            self._short_term.clear()
            self._save()

    # --- Long-term Memory (searchable knowledge) ---

    def remember(self, content: str, category: str = "fact", importance: float = 0.6, metadata: Optional[Dict[str, Any]] = None) -> str:
        """Store a long-term memory entry."""
        with self._lock:
            entry_id = self._generate_id(content)
            entry = MemoryEntry(
                id=entry_id,
                content=content,
                category=category,
                timestamp=time.time(),
                importance=importance,
                metadata=metadata or {},
            )
            self._long_term[entry_id] = entry
            self._save()
            return entry_id

    def recall(self, query: str, limit: int = 5) -> List[MemoryEntry]:
        """Search long-term memory by keyword similarity."""
        with self._lock:
            if not self._long_term:
                return []

            # Simple keyword matching (can be enhanced with embeddings later)
            query_lower = query.lower()
            query_words = set(query_lower.split())

            scored: List[tuple[float, MemoryEntry]] = []
            for entry in self._long_term.values():
                content_lower = entry.content.lower()
                # Calculate relevance score
                word_matches = sum(1 for w in query_words if w in content_lower)
                if word_matches > 0:
                    # Combine keyword match with importance and recency
                    recency = 1.0 / (1.0 + (time.time() - entry.timestamp) / 86400)  # Decay over days
                    score = (word_matches / len(query_words)) * 0.5 + entry.importance * 0.3 + recency * 0.2
                    scored.append((score, entry))

            # Sort by score descending
            scored.sort(key=lambda x: x[0], reverse=True)

            # Update access stats
            results = []
            for _, entry in scored[:limit]:
                entry.access_count += 1
                entry.last_accessed = time.time()
                results.append(entry)

            return results

    def forget(self, entry_id: str) -> bool:
        """Delete a long-term memory entry."""
        with self._lock:
            if entry_id in self._long_term:
                del self._long_term[entry_id]
                self._save()
                return True
            return False

    def get_memory_stats(self) -> Dict[str, Any]:
        """Get memory statistics."""
        with self._lock:
            return {
                "core_count": len(self._core),
                "core_limit": self._max_core,
                "short_term_count": len(self._short_term),
                "short_term_limit": self._max_short_term,
                "long_term_count": len(self._long_term),
                "total_entries": len(self._core) + len(self._short_term) + len(self._long_term),
            }

    def build_context_prompt(self) -> str:
        """Build a memory context prompt for the AI."""
        with self._lock:
            parts = []

            # Core memory
            if self._core:
                core_lines = []
                for key, entry in sorted(self._core.items(), key=lambda x: x[1].importance, reverse=True):
                    core_lines.append(f"- {key}: {entry.content}")
                parts.append("【核心记忆】\n" + "\n".join(core_lines))

            # Recent conversation context
            if self._short_term:
                recent = self._short_term[-5:]  # Last 5 turns
                conv_lines = []
                for entry in recent:
                    role = entry.metadata.get("role", "user")
                    role_label = "用户" if role == "user" else "助手"
                    conv_lines.append(f"{role_label}: {entry.content[:200]}")
                parts.append("【近期对话】\n" + "\n".join(conv_lines))

            return "\n\n".join(parts) if parts else ""


# Global singleton
_memory_store: Optional[MemoryStore] = None
_memory_lock = threading.Lock()


def get_memory_store(data_dir: Optional[Path] = None) -> MemoryStore:
    """Get the global memory store instance."""
    global _memory_store
    if _memory_store is None:
        with _memory_lock:
            if _memory_store is None:
                _memory_store = MemoryStore(data_dir=data_dir)
    return _memory_store
