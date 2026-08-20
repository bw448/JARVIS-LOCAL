"""
增强集成模块 - v0.9.0
集成 Memory、Skills、Web Search、Document、Voice、Vector Memory、SubAgent
参考 Aivy OS 架构
"""

from __future__ import annotations

import json
import time
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Mapping

from .config import Settings, default_data_dir
from .memory import MemoryStore, get_memory_store
from .skills import SkillManager, get_skill_manager
from .web_search import WebSearchService, get_search_service, SEARCH_TOOL_DEFINITION
from .document import DocumentProcessor, get_document_processor, DOCUMENT_TOOL_DEFINITIONS
from .voice_enhanced import EnhancedVoiceSystem, VoiceConfig, get_voice_system
from .memory_vector import VectorMemoryStore, EmbeddingService, get_vector_memory
from .subagent import SubAgentManager, TaskTypes, get_subagent_manager


class EnhancedContextBuilder:
    """
    增强上下文构建器 - v0.9.0
    整合所有子系统
    """

    def __init__(self, data_dir: Optional[Path] = None, embedding_provider: str = "local"):
        self._data_dir = data_dir or default_data_dir() / "jarvis_data"
        self._data_dir.mkdir(parents=True, exist_ok=True)

        # 初始化子系统
        self._memory_base = get_memory_store(self._data_dir / "memory")
        self._memory_vector = get_vector_memory(
            self._memory_base,
            embedding_provider=embedding_provider,
            data_dir=self._data_dir / "memory"
        )
        self._skills = get_skill_manager(self._data_dir / "skills")
        self._search = get_search_service()
        self._documents = get_document_processor()
        self._voice = get_voice_system()
        self._subagent = get_subagent_manager()

        # 自动加载默认技能
        if not self._skills.list_skills():
            self._load_default_skills()

    def _load_default_skills(self):
        """加载内置技能"""
        builtin_skills_dir = Path(__file__).parent / "skills"
        if builtin_skills_dir.exists():
            self._skills = get_skill_manager(builtin_skills_dir)

    @property
    def memory(self) -> VectorMemoryStore:
        return self._memory_vector

    @property
    def skills(self) -> SkillManager:
        return self._skills

    @property
    def search(self) -> WebSearchService:
        return self._search

    @property
    def documents(self) -> DocumentProcessor:
        return self._documents

    @property
    def voice(self) -> EnhancedVoiceSystem:
        return self._voice

    @property
    def subagent(self) -> SubAgentManager:
        return self._subagent

    def build_system_context(self, settings: Settings, include_skills: bool = True) -> str:
        """构建增强系统提示"""
        parts = []

        # 基础提示
        base_prompt = settings.system_prompt()
        parts.append(base_prompt)

        # 记忆上下文
        memory_context = self._memory_vector.build_context_prompt()
        if memory_context:
            parts.append(memory_context)

        # 技能上下文
        if include_skills:
            skills_context = self._skills.get_skill_context()
            if skills_context:
                parts.append(skills_context)

        # 能力描述
        capabilities = """
【增强能力】
你现在拥有以下增强能力：

1. **记忆系统** - 可以记住重要信息，回忆之前的对话
   - 使用 memory_store 存储信息
   - 使用 memory_recall 回忆信息
   - 支持语义搜索

2. **网络搜索** - 可以搜索互联网获取最新信息
   - 使用 web_search 工具

3. **文件操作** - 可以读取和写入各种格式的文件
   - 使用 read_file 读取文件
   - 使用 write_file 写入文件

4. **技能系统** - 可以使用专业技能完成复杂任务

5. **子代理** - 可以将复杂任务分解给子代理执行
   - 使用 submit_task 提交异步任务
   - 使用 wait_task 等待任务结果
"""
        parts.append(capabilities)

        return "\n\n".join(parts)

    def process_user_message(self, content: str, role: str = "user") -> None:
        """处理用户消息"""
        # 存储对话
        self._memory_vector.add_conversation(role, content)

        # 提取事实
        self._extract_and_store_facts(content)

    def _extract_and_store_facts(self, content: str):
        """从用户消息中提取事实"""
        import re

        patterns = [
            (r"我喜欢(.+)", "preference"),
            (r"我偏好(.+)", "preference"),
            (r"我习惯(.+)", "preference"),
            (r"我的(.+)是(.+)", "fact"),
            (r"记住(.+)", "fact"),
        ]

        for pattern, category in patterns:
            match = re.search(pattern, content)
            if match:
                fact = match.group(0)
                self._memory_vector.remember(fact, category=category, importance=0.7)

    def get_search_results(self, query: str, max_results: int = 5) -> str:
        """执行搜索"""
        try:
            response = self._search.search(query, max_results=max_results)
            return self._search.format_results_for_ai(response)
        except Exception as e:
            return f"搜索失败: {str(e)}"

    def get_tool_definitions(self) -> List[Dict[str, Any]]:
        """获取工具定义"""
        tools = []

        # 搜索工具
        tools.append(SEARCH_TOOL_DEFINITION)

        # 文档工具
        tools.extend(DOCUMENT_TOOL_DEFINITIONS)

        # 记忆工具
        memory_tools = {
            "type": "function",
            "function": {
                "name": "memory_store",
                "description": "存储重要信息到长期记忆。支持语义搜索。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "content": {"type": "string", "description": "要记住的内容"},
                        "category": {
                            "type": "string",
                            "description": "类别: fact, preference, task",
                            "default": "fact"
                        },
                        "importance": {
                            "type": "number",
                            "description": "重要程度 0.0-1.0",
                            "default": 0.6
                        }
                    },
                    "required": ["content"]
                }
            }
        }
        tools.append(memory_tools)

        memory_recall = {
            "type": "function",
            "function": {
                "name": "memory_recall",
                "description": "从长期记忆中搜索信息。支持语义搜索。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "搜索关键词"},
                        "limit": {"type": "integer", "description": "返回数量", "default": 5}
                    },
                    "required": ["query"]
                }
            }
        }
        tools.append(memory_recall)

        # 子代理工具
        submit_task = {
            "type": "function",
            "function": {
                "name": "submit_task",
                "description": "提交异步任务给子代理执行。适用于耗时操作。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "任务类型"},
                        "description": {"type": "string", "description": "任务描述"},
                        "args": {"type": "array", "description": "参数列表"},
                    },
                    "required": ["name", "description"]
                }
            }
        }
        tools.append(submit_task)

        return tools

    def execute_tool(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        """执行工具"""
        if tool_name == "web_search":
            query = arguments.get("query", "")
            max_results = arguments.get("max_results", 5)
            return self.get_search_results(query, max_results)

        elif tool_name == "memory_store":
            content = arguments.get("content", "")
            category = arguments.get("category", "fact")
            importance = arguments.get("importance", 0.6)
            entry_id = self._memory_vector.remember(content, category=category, importance=importance)
            return f"已记住: {content} (ID: {entry_id})"

        elif tool_name == "memory_recall":
            query = arguments.get("query", "")
            limit = arguments.get("limit", 5)
            results = self._memory_vector.recall(query, limit=limit, use_vector=True)
            if results:
                lines = ["回忆结果:"]
                for r in results:
                    lines.append(f"- [{r.category}] {r.content}")
                return "\n".join(lines)
            return "没有找到相关记忆。"

        elif tool_name == "read_file":
            file_path = arguments.get("file_path", "")
            result = self._documents.read_file(file_path)
            if result.success:
                return result.content
            return f"读取失败: {result.error}"

        elif tool_name == "write_file":
            file_path = arguments.get("file_path", "")
            content = arguments.get("content", "")
            overwrite = arguments.get("overwrite", False)
            result = self._documents.write_file(file_path, content, overwrite=overwrite)
            if result.success:
                return f"已写入: {file_path}"
            return f"写入失败: {result.error}"

        elif tool_name == "submit_task":
            task_name = arguments.get("name", "")
            task_desc = arguments.get("description", "")
            task_args = arguments.get("args", [])
            
            # 查找合适的处理函数
            handler = self._get_task_handler(task_name)
            if handler:
                task_id = self._subagent.submit_task(
                    name=task_name,
                    description=task_desc,
                    func=handler,
                    args=tuple(task_args),
                )
                return f"任务已提交 (ID: {task_id})"
            return f"未知任务类型: {task_name}"

        else:
            return f"未知工具: {tool_name}"

    def _get_task_handler(self, task_name: str) -> Optional[Any]:
        """获取任务处理函数"""
        handlers = {
            TaskTypes.WEB_SEARCH: lambda q: self.get_search_results(q),
        }
        return handlers.get(task_name)

    def get_stats(self) -> Dict[str, Any]:
        """获取系统统计"""
        return {
            "version": "1.1.0",
            "memory": self._memory_vector.get_stats(),
            "skills_count": len(self._skills.list_skills()),
            "search_engine": self._search.engine,
            "voice": self._voice.get_status(),
            "subagent": self._subagent.get_stats(),
        }


# 全局实例
_context_builder: Optional[EnhancedContextBuilder] = None
_context_lock = threading.Lock()


def get_context_builder(
    data_dir: Optional[Path] = None,
    embedding_provider: str = "local"
) -> EnhancedContextBuilder:
    """获取全局上下文构建器"""
    global _context_builder
    if _context_builder is None:
        with _context_lock:
            if _context_builder is None:
                _context_builder = EnhancedContextBuilder(data_dir, embedding_provider)
    return _context_builder
