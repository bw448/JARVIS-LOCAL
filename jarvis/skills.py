"""
Skills system for JARVIS LOCAL.
Inspired by Aivy OS skills architecture.
Provides markdown-based skill definitions that enhance AI capabilities.
"""

from __future__ import annotations

import json
import re
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Mapping


@dataclass(slots=True)
class SkillMetadata:
    """Skill metadata from SKILL.md frontmatter."""
    name: str
    description: str = ""
    tags: List[str] = field(default_factory=list)
    tools_required: List[str] = field(default_factory=list)
    version: str = "1.0.0"
    author: str = ""
    category: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "tags": self.tags,
            "tools_required": self.tools_required,
            "version": self.version,
            "author": self.author,
            "category": self.category,
        }


@dataclass(slots=True)
class Skill:
    """A loaded skill with metadata and content."""
    metadata: SkillMetadata
    content: str  # The SKILL.md content (instructions)
    path: Path

    @property
    def name(self) -> str:
        return self.metadata.name

    def to_dict(self) -> Dict[str, Any]:
        return {
            **self.metadata.to_dict(),
            "path": str(self.path),
            "content_length": len(self.content),
        }


def _parse_frontmatter(content: str) -> tuple[Dict[str, Any], str]:
    """Parse YAML-like frontmatter from markdown content."""
    if not content.startswith("---"):
        return {}, content

    try:
        end_idx = content.index("---", 3)
        frontmatter_str = content[3:end_idx].strip()
        body = content[end_idx + 3:].strip()

        # Simple key-value parser (no full YAML dependency needed)
        metadata: Dict[str, Any] = {}
        current_key = None
        current_value = []

        for line in frontmatter_str.split("\n"):
            line = line.rstrip()
            if not line:
                continue

            # Check for key: value
            match = re.match(r'^(\w+):\s*(.*)', line)
            if match:
                if current_key:
                    metadata[current_key] = _parse_value("\n".join(current_value))
                current_key = match.group(1)
                current_value = [match.group(2)] if match.group(2) else []
            elif current_key:
                current_value.append(line)

        if current_key:
            metadata[current_key] = _parse_value("\n".join(current_value))

        return metadata, body
    except (ValueError, IndexError):
        return {}, content


def _parse_value(value: str) -> Any:
    """Parse a frontmatter value."""
    value = value.strip()

    # List value [item1, item2]
    if value.startswith("[") and value.endswith("]"):
        items = value[1:-1].split(",")
        return [item.strip().strip("'\"") for item in items if item.strip()]

    # Boolean
    if value.lower() in ("true", "yes"):
        return True
    if value.lower() in ("false", "no"):
        return False

    # Number
    try:
        if "." in value:
            return float(value)
        return int(value)
    except ValueError:
        pass

    # String (remove quotes if present)
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        return value[1:-1]

    return value


class SkillManager:
    """
    Manages skills loaded from SKILL.md files.
    
    Skills are loaded from a skills directory. Each skill is a folder containing:
    - SKILL.md: The skill definition with frontmatter and instructions
    - Optional supporting files
    """

    def __init__(self, skills_dir: Optional[Path] = None):
        self._lock = threading.RLock()
        self._skills_dir = skills_dir
        self._skills: Dict[str, Skill] = {}
        self._registry_file: Optional[Path] = None

        if skills_dir:
            self._registry_file = skills_dir / "_registry.json"
            self._load_skills()

    def _load_skills(self):
        """Load all skills from the skills directory."""
        if not self._skills_dir or not self._skills_dir.exists():
            return

        for skill_dir in self._skills_dir.iterdir():
            if not skill_dir.is_dir():
                continue
            if skill_dir.name.startswith(("_", ".")):
                continue

            skill_md = skill_dir / "SKILL.md"
            if not skill_md.exists():
                continue

            try:
                self._load_skill(skill_dir, skill_md)
            except Exception as e:
                print(f"[Skills] Warning: Failed to load skill {skill_dir.name}: {e}")

    def _load_skill(self, skill_dir: Path, skill_md: Path):
        """Load a single skill from its directory."""
        content = skill_md.read_text(encoding="utf-8")
        metadata_dict, body = _parse_frontmatter(content)

        name = metadata_dict.get("name", skill_dir.name)
        metadata = SkillMetadata(
            name=name,
            description=str(metadata_dict.get("description", "")),
            tags=metadata_dict.get("tags", []) if isinstance(metadata_dict.get("tags"), list) else [],
            tools_required=metadata_dict.get("tools_required", []) if isinstance(metadata_dict.get("tools_required"), list) else [],
            version=str(metadata_dict.get("version", "1.0.0")),
            author=str(metadata_dict.get("author", "")),
            category=str(metadata_dict.get("category", "")),
        )

        skill = Skill(
            metadata=metadata,
            content=body,
            path=skill_dir,
        )

        with self._lock:
            self._skills[name] = skill

    def get_skill(self, name: str) -> Optional[Skill]:
        """Get a skill by name."""
        with self._lock:
            return self._skills.get(name)

    def list_skills(self) -> List[Dict[str, Any]]:
        """List all available skills."""
        with self._lock:
            return [skill.to_dict() for skill in self._skills.values()]

    def search_skills(self, query: str) -> List[Skill]:
        """Search skills by query (name, description, tags)."""
        with self._lock:
            query_lower = query.lower()
            results = []

            for skill in self._skills.values():
                # Match name
                if query_lower in skill.name.lower():
                    results.append(skill)
                    continue

                # Match description
                if query_lower in skill.metadata.description.lower():
                    results.append(skill)
                    continue

                # Match tags
                if any(query_lower in tag.lower() for tag in skill.metadata.tags):
                    results.append(skill)
                    continue

            return results

    def get_skill_context(self, skill_names: Optional[List[str]] = None) -> str:
        """Build skill context for the AI prompt."""
        with self._lock:
            if skill_names:
                skills = [self._skills[n] for n in skill_names if n in self._skills]
            else:
                skills = list(self._skills.values())

            if not skills:
                return ""

            parts = ["【可用技能】"]
            for skill in skills:
                parts.append(f"\n### {skill.name}")
                if skill.metadata.description:
                    parts.append(f"说明: {skill.metadata.description}")
                parts.append(skill.content[:2000])  # Limit per skill

            return "\n".join(parts)

    def add_skill(self, name: str, content: str, description: str = "", tags: Optional[List[str]] = None) -> bool:
        """Add a new skill dynamically."""
        if not self._skills_dir:
            return False

        with self._lock:
            skill_dir = self._skills_dir / name
            skill_dir.mkdir(parents=True, exist_ok=True)

            # Build SKILL.md content with frontmatter
            frontmatter_lines = ["---"]
            frontmatter_lines.append(f"name: {name}")
            if description:
                frontmatter_lines.append(f"description: {description}")
            if tags:
                frontmatter_lines.append(f"tags: [{', '.join(tags)}]")
            frontmatter_lines.append("---")
            frontmatter_lines.append("")

            full_content = "\n".join(frontmatter_lines) + "\n" + content
            skill_md = skill_dir / "SKILL.md"
            skill_md.write_text(full_content, encoding="utf-8")

            # Load the new skill
            self._load_skill(skill_dir, skill_md)
            self._save_registry()
            return True

    def _save_registry(self):
        """Save skill registry to disk."""
        if not self._registry_file:
            return

        registry = {}
        for name, skill in self._skills.items():
            registry[name] = {
                "id": name,
                "name": name,
                "description": skill.metadata.description,
                "tags": skill.metadata.tags,
                "tools_required": skill.metadata.tools_required,
                "path": str(skill.path),
                "skill_type": "prompt",
                "version": skill.metadata.version,
            }

        try:
            self._registry_file.write_text(
                json.dumps(registry, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
        except OSError as e:
            print(f"[Skills] Warning: Failed to save registry: {e}")


# Built-in skills
BUILTIN_SKILLS = {
    "code-development": """# 代码操作规范

## 关键原则
- 修改文件前必须先读取
- 使用精确编辑而非覆盖整个文件
- 最小改动原则：只改要求的内容

## 文件操作
- 读取文件后再编辑
- 保持原有代码风格
- 不添加未要求的注释或重构
""",
    "web-research": """# 网络研究

## 搜索策略
1. 使用精确关键词
2. 验证多个来源
3. 注意信息时效性

## 信息整理
- 记录来源URL
- 区分事实和观点
- 标注信息日期
""",
    "data-analysis": """# 数据分析

## 分析流程
1. 数据清洗和预处理
2. 探索性数据分析
3. 统计分析和建模
4. 可视化展示

## 工具使用
- pandas 用于数据处理
- matplotlib/seaborn 用于可视化
- 注意数据类型和缺失值
""",
}


# Global singleton
_skill_manager: Optional[SkillManager] = None
_skill_lock = threading.Lock()


def get_skill_manager(skills_dir: Optional[Path] = None) -> SkillManager:
    """Get the global skill manager instance."""
    global _skill_manager
    if _skill_manager is None:
        with _skill_lock:
            if _skill_manager is None:
                _skill_manager = SkillManager(skills_dir=skills_dir)
    return _skill_manager
