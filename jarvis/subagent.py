"""
子代理系统 - v0.9.0
异步任务执行、任务队列、结果聚合
参考 Aivy OS 的 subagent 架构
"""

from __future__ import annotations

import asyncio
import json
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, Future
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Awaitable
from queue import Queue, Empty


class TaskStatus(Enum):
    """任务状态"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(slots=True)
class TaskResult:
    """任务结果"""
    task_id: str
    status: TaskStatus
    result: Any = None
    error: Optional[str] = None
    started_at: float = 0.0
    completed_at: float = 0.0
    execution_time_ms: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "status": self.status.value,
            "result": self.result,
            "error": self.error,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "execution_time_ms": self.execution_time_ms,
            "metadata": self.metadata,
        }


@dataclass(slots=True)
class Task:
    """任务定义"""
    task_id: str
    name: str
    description: str
    func: Callable[..., Any]
    args: tuple = ()
    kwargs: Dict[str, Any] = field(default_factory=dict)
    priority: int = 0
    timeout: float = 300.0
    created_at: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)


class TaskQueue:
    """任务队列"""
    
    def __init__(self, max_size: int = 100):
        self._queue: Queue = Queue(maxsize=max_size)
        self._lock = threading.Lock()
    
    def put(self, task: Task):
        self._queue.put(task)
    
    def get(self, timeout: float = 1.0) -> Optional[Task]:
        try:
            return self._queue.get(timeout=timeout)
        except Empty:
            return None
    
    def size(self) -> int:
        return self._queue.qsize()
    
    def empty(self) -> bool:
        return self._queue.empty()


class SubAgent:
    """子代理"""
    
    def __init__(
        self,
        agent_id: str,
        name: str,
        description: str,
        capabilities: List[str],
        handler: Callable[..., Any],
    ):
        self.agent_id = agent_id
        self.name = name
        self.description = description
        self.capabilities = capabilities
        self._handler = handler
        self._is_busy = False
        self._current_task: Optional[Task] = None
        self._completed_tasks = 0
        self._lock = threading.Lock()
    
    @property
    def is_busy(self) -> bool:
        return self._is_busy
    
    def can_handle(self, task_name: str) -> bool:
        return task_name in self.capabilities or "*" in self.capabilities
    
    def execute(self, task: Task) -> TaskResult:
        with self._lock:
            if self._is_busy:
                return TaskResult(
                    task_id=task.task_id,
                    status=TaskStatus.FAILED,
                    error="Agent is busy"
                )
            self._is_busy = True
            self._current_task = task
        
        result = TaskResult(task_id=task.task_id, status=TaskStatus.RUNNING)
        result.started_at = time.time()
        
        try:
            # 执行任务函数
            task_result = self._handler(task.func, *task.args, **task.kwargs)
            result.status = TaskStatus.COMPLETED
            result.result = task_result
            self._completed_tasks += 1
        except Exception as e:
            result.status = TaskStatus.FAILED
            result.error = str(e)
        finally:
            result.completed_at = time.time()
            result.execution_time_ms = (result.completed_at - result.started_at) * 1000
            with self._lock:
                self._is_busy = False
                self._current_task = None
        
        return result


class SubAgentManager:
    """子代理管理器"""
    
    def __init__(self, max_workers: int = 4):
        self._agents: Dict[str, SubAgent] = {}
        self._task_queue = TaskQueue()
        self._results: Dict[str, TaskResult] = {}
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._futures: Dict[str, Future] = {}
        self._lock = threading.RLock()
        self._is_running = False
        self._worker_thread: Optional[threading.Thread] = None
    
    def register_agent(self, agent: SubAgent):
        with self._lock:
            self._agents[agent.agent_id] = agent
    
    def unregister_agent(self, agent_id: str):
        with self._lock:
            self._agents.pop(agent_id, None)
    
    def get_agent(self, agent_id: str) -> Optional[SubAgent]:
        return self._agents.get(agent_id)
    
    def find_agent_for_task(self, task_name: str) -> Optional[SubAgent]:
        with self._lock:
            for agent in self._agents.values():
                if not agent.is_busy and agent.can_handle(task_name):
                    return agent
        return None
    
    def submit_task(
        self,
        name: str,
        description: str,
        func: Callable[..., Any],
        args: tuple = (),
        kwargs: Dict[str, Any] = None,
        priority: int = 0,
        timeout: float = 300.0,
        metadata: Dict[str, Any] = None,
    ) -> str:
        task_id = str(uuid.uuid4())[:8]
        
        task = Task(
            task_id=task_id,
            name=name,
            description=description,
            func=func,
            args=args,
            kwargs=kwargs or {},
            priority=priority,
            timeout=timeout,
            metadata=metadata or {},
        )
        
        agent = self.find_agent_for_task(name)
        if agent:
            self._execute_async(agent, task)
        else:
            self._task_queue.put(task)
        
        return task_id
    
    def _execute_async(self, agent: SubAgent, task: Task):
        def run():
            result = agent.execute(task)
            with self._lock:
                self._results[task.task_id] = result
                self._futures.pop(task.task_id, None)
            if task.metadata.get("callback"):
                try:
                    task.metadata["callback"](result)
                except Exception:
                    pass
        
        future = self._executor.submit(run)
        with self._lock:
            self._futures[task.task_id] = future
    
    def get_result(self, task_id: str) -> Optional[TaskResult]:
        return self._results.get(task_id)
    
    def wait_for_task(self, task_id: str, timeout: float = 300.0) -> Optional[TaskResult]:
        start = time.time()
        while time.time() - start < timeout:
            result = self._results.get(task_id)
            if result and result.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED):
                return result
            time.sleep(0.1)
        return None
    
    def cancel_task(self, task_id: str) -> bool:
        with self._lock:
            future = self._futures.get(task_id)
            if future:
                cancelled = future.cancel()
                if cancelled:
                    self._results[task_id] = TaskResult(
                        task_id=task_id,
                        status=TaskStatus.CANCELLED
                    )
                return cancelled
        return False
    
    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "agents": {
                    agent_id: {
                        "name": agent.name,
                        "is_busy": agent.is_busy,
                        "completed_tasks": agent._completed_tasks,
                    }
                    for agent_id, agent in self._agents.items()
                },
                "queue_size": self._task_queue.size(),
                "pending_results": len(self._results),
                "active_tasks": len(self._futures),
            }
    
    def start(self):
        if self._is_running:
            return
        self._is_running = True
        self._worker_thread = threading.Thread(target=self._scheduler_loop, daemon=True)
        self._worker_thread.start()
    
    def stop(self):
        self._is_running = False
        if self._worker_thread:
            self._worker_thread.join(timeout=5)
        self._executor.shutdown(wait=False)
    
    def _scheduler_loop(self):
        while self._is_running:
            try:
                task = self._task_queue.get(timeout=1.0)
                if not task:
                    continue
                agent = self.find_agent_for_task(task.name)
                if agent:
                    self._execute_async(agent, task)
                else:
                    self._task_queue.put(task)
                    time.sleep(0.5)
            except Exception as e:
                print(f"[SubAgent] Scheduler error: {e}")


class TaskTypes:
    WEB_SEARCH = "web_search"
    FILE_READ = "file_read"
    FILE_WRITE = "file_write"
    CODE_EXECUTE = "code_execute"
    DATA_ANALYSIS = "data_analysis"
    DOCUMENT_PROCESS = "document_process"
    CUSTOM = "custom"


_manager: Optional[SubAgentManager] = None
_manager_lock = threading.Lock()


def get_subagent_manager(max_workers: int = 4) -> SubAgentManager:
    global _manager
    if _manager is None:
        with _manager_lock:
            if _manager is None:
                _manager = SubAgentManager(max_workers=max_workers)
                _manager.start()
                _register_default_agents(_manager)
    return _manager


def _register_default_agents(manager: SubAgentManager):
    # 搜索代理
    search_agent = SubAgent(
        agent_id="search_agent",
        name="搜索代理",
        description="执行网络搜索任务",
        capabilities=[TaskTypes.WEB_SEARCH],
        handler=lambda func, *args, **kwargs: func(*args, **kwargs),
    )
    manager.register_agent(search_agent)
    
    # 文件代理
    file_agent = SubAgent(
        agent_id="file_agent",
        name="文件代理",
        description="处理文件读写任务",
        capabilities=[TaskTypes.FILE_READ, TaskTypes.FILE_WRITE],
        handler=lambda func, *args, **kwargs: func(*args, **kwargs),
    )
    manager.register_agent(file_agent)
    
    # 通用代理
    general_agent = SubAgent(
        agent_id="general_agent",
        name="通用代理",
        description="处理通用任务",
        capabilities=["*"],
        handler=lambda func, *args, **kwargs: func(*args, **kwargs),
    )
    manager.register_agent(general_agent)
