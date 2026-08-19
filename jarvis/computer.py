from __future__ import annotations

import os
import platform
import secrets
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


class ComputerToolError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    name: str
    title: str
    description: str
    risk: str
    requires_confirmation: bool
    parameters: dict[str, Any]

    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


@dataclass(slots=True)
class PendingAction:
    proposal_id: str
    tool_name: str
    arguments: dict[str, Any]
    title: str
    preview: str
    risk: str
    expires_at: float


APPLICATIONS = {
    "notepad": ("记事本", ("System32", "notepad.exe")),
    "calculator": ("计算器", ("System32", "calc.exe")),
    "file_explorer": ("文件资源管理器", ("explorer.exe",)),
    "task_manager": ("任务管理器", ("System32", "taskmgr.exe")),
}

FOLDER_LABELS = {
    "desktop": "桌面",
    "documents": "文档",
    "downloads": "下载",
    "home": "用户主目录",
}


class ComputerToolService:
    """Small Windows-only action surface with no arbitrary command execution."""

    PROPOSAL_TTL_SECONDS = 120

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._pending: dict[str, PendingAction] = {}
        self._definitions = {
            definition.name: definition
            for definition in (
                ToolDefinition(
                    name="get_system_status",
                    title="读取系统概况",
                    description="读取操作系统、CPU 核心数和磁盘剩余空间，不修改电脑。",
                    risk="read_only",
                    requires_confirmation=False,
                    parameters={"type": "object", "properties": {}, "additionalProperties": False},
                ),
                ToolDefinition(
                    name="open_application",
                    title="打开应用",
                    description="打开白名单中的 Windows 系统应用。",
                    risk="low",
                    requires_confirmation=True,
                    parameters={
                        "type": "object",
                        "properties": {
                            "application": {
                                "type": "string",
                                "enum": sorted(APPLICATIONS),
                                "description": "要打开的白名单应用",
                            }
                        },
                        "required": ["application"],
                        "additionalProperties": False,
                    },
                ),
                ToolDefinition(
                    name="open_folder",
                    title="打开文件夹",
                    description="打开当前用户的桌面、文档、下载或主目录。不能接受任意路径。",
                    risk="low",
                    requires_confirmation=True,
                    parameters={
                        "type": "object",
                        "properties": {
                            "folder": {
                                "type": "string",
                                "enum": sorted(FOLDER_LABELS),
                                "description": "要打开的固定文件夹别名",
                            }
                        },
                        "required": ["folder"],
                        "additionalProperties": False,
                    },
                ),
                ToolDefinition(
                    name="lock_workstation",
                    title="锁定电脑",
                    description="锁定当前 Windows 会话。不会关机或删除数据。",
                    risk="high",
                    requires_confirmation=True,
                    parameters={"type": "object", "properties": {}, "additionalProperties": False},
                ),
            )
        }

    @property
    def available(self) -> bool:
        return sys.platform == "win32"

    def schemas(self) -> list[dict[str, Any]]:
        return [definition.schema() for definition in self._definitions.values()]

    def propose(self, name: str, raw_arguments: Any) -> dict[str, Any]:
        definition = self._definitions.get(str(name))
        if definition is None:
            raise ComputerToolError("模型请求了不在白名单中的电脑操作")
        arguments = self._validate_arguments(definition, raw_arguments)
        preview = self._preview(definition.name, arguments)
        if not definition.requires_confirmation:
            return {
                "kind": "result",
                "tool": definition.name,
                "message": self._execute(definition.name, arguments),
            }

        proposal_id = secrets.token_urlsafe(24)
        action = PendingAction(
            proposal_id=proposal_id,
            tool_name=definition.name,
            arguments=arguments,
            title=definition.title,
            preview=preview,
            risk=definition.risk,
            expires_at=time.monotonic() + self.PROPOSAL_TTL_SECONDS,
        )
        with self._lock:
            self._purge_expired_locked()
            self._pending[proposal_id] = action
        return {
            "kind": "proposal",
            "proposal_id": proposal_id,
            "tool": definition.name,
            "title": definition.title,
            "preview": preview,
            "risk": definition.risk,
            "expires_in_seconds": self.PROPOSAL_TTL_SECONDS,
        }

    def resolve(self, proposal_id: str, approved: bool) -> dict[str, Any]:
        cleaned = str(proposal_id or "").strip()
        if not cleaned:
            raise ComputerToolError("操作提案编号无效")
        with self._lock:
            self._purge_expired_locked()
            action = self._pending.pop(cleaned, None)
        if action is None:
            raise ComputerToolError("操作提案不存在、已经使用或已经过期")
        if not approved:
            return {"executed": False, "message": f"已取消：{action.preview}"}
        return {
            "executed": True,
            "message": self._execute(action.tool_name, action.arguments),
        }

    def _purge_expired_locked(self) -> None:
        now = time.monotonic()
        expired = [key for key, action in self._pending.items() if action.expires_at <= now]
        for key in expired:
            self._pending.pop(key, None)

    @staticmethod
    def _validate_arguments(
        definition: ToolDefinition,
        raw_arguments: Any,
    ) -> dict[str, Any]:
        if raw_arguments is None or raw_arguments == "":
            arguments: dict[str, Any] = {}
        elif isinstance(raw_arguments, Mapping):
            arguments = dict(raw_arguments)
        else:
            raise ComputerToolError("电脑操作参数必须是 JSON 对象")
        properties = definition.parameters.get("properties", {})
        required = set(definition.parameters.get("required", []))
        if set(arguments) - set(properties):
            raise ComputerToolError("电脑操作包含未允许的参数")
        if required - set(arguments):
            raise ComputerToolError("电脑操作缺少必要参数")
        for key, value in arguments.items():
            allowed = properties[key].get("enum")
            if allowed is not None and value not in allowed:
                raise ComputerToolError("电脑操作参数不在白名单中")
            if properties[key].get("type") == "string" and not isinstance(value, str):
                raise ComputerToolError("电脑操作参数类型无效")
        return arguments

    @staticmethod
    def _preview(name: str, arguments: Mapping[str, Any]) -> str:
        if name == "open_application":
            return f"打开 Windows {APPLICATIONS[arguments['application']][0]}"
        if name == "open_folder":
            return f"打开当前用户的{FOLDER_LABELS[arguments['folder']]}"
        if name == "lock_workstation":
            return "立即锁定当前 Windows 会话"
        return "读取本机系统概况"

    def _execute(self, name: str, arguments: Mapping[str, Any]) -> str:
        if name == "get_system_status":
            root = Path.home().anchor or os.sep
            disk = shutil.disk_usage(root)
            free_gib = disk.free / (1024**3)
            return (
                f"系统：{platform.system()} {platform.release()}；"
                f"CPU 逻辑核心：{os.cpu_count() or '未知'}；"
                f"系统盘可用空间：{free_gib:.1f} GiB。"
            )
        if not self.available:
            raise ComputerToolError("电脑控制目前只支持 Windows 桌面版")
        if name == "open_application":
            key = str(arguments["application"])
            label, _ = APPLICATIONS[key]
            executable = self._application_path(key)
            subprocess.Popen(
                [str(executable)],
                close_fds=True,
                creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
            )
            return f"已打开{label}。"
        if name == "open_folder":
            folder = self._folder_path(str(arguments["folder"]))
            os.startfile(str(folder))
            return f"已打开{FOLDER_LABELS[str(arguments['folder'])]}。"
        if name == "lock_workstation":
            import ctypes

            if not ctypes.windll.user32.LockWorkStation():
                raise ComputerToolError("Windows 拒绝了锁屏请求")
            return "电脑已锁定。"
        raise ComputerToolError("电脑操作不在白名单中")

    @staticmethod
    def _folder_path(alias: str) -> Path:
        home = Path.home()
        candidates = {
            "home": home,
            "desktop": home / "Desktop",
            "documents": home / "Documents",
            "downloads": home / "Downloads",
        }
        path = candidates[alias]
        if not path.is_dir():
            raise ComputerToolError(f"找不到{FOLDER_LABELS[alias]}文件夹")
        return path

    @staticmethod
    def _application_path(key: str) -> Path:
        import ctypes

        buffer = ctypes.create_unicode_buffer(32_768)
        length = ctypes.windll.kernel32.GetWindowsDirectoryW(buffer, len(buffer))
        if length <= 0 or length >= len(buffer):
            raise ComputerToolError("无法确定可信的 Windows 系统目录")
        windows_root = Path(buffer.value)
        _, relative_parts = APPLICATIONS[key]
        executable = windows_root.joinpath(*relative_parts)
        if not executable.is_file():
            raise ComputerToolError(f"找不到 Windows {APPLICATIONS[key][0]}")
        return executable
