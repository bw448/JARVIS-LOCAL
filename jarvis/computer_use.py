"""
通用电脑控制模块
提供类似Computer Use的通用桌面操作能力
"""

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


class ComputerUseError(RuntimeError):
    """电脑操作错误"""
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


# 扩展的应用程序白名单
APPLICATIONS = {
    # 系统应用
    "notepad": ("记事本", ("System32", "notepad.exe")),
    "calculator": ("计算器", ("System32", "calc.exe")),
    "file_explorer": ("文件资源管理器", ("explorer.exe",)),
    "task_manager": ("任务管理器", ("System32", "taskmgr.exe")),
    "paint": ("画图", ("System32", "mspaint.exe")),
    "wordpad": ("写字板", ("System32", "write.exe")),
    "cmd": ("命令提示符", ("System32", "cmd.exe")),
    "powershell": ("PowerShell", ("System32", "WindowsPowerShell", "v1.0", "powershell.exe")),
    
    # 浏览器
    "edge": ("Microsoft Edge", ("Microsoft", "Edge", "Application", "msedge.exe")),
    "chrome": ("Google Chrome", ("Google", "Chrome", "Application", "chrome.exe")),
    "firefox": ("Firefox", ("Mozilla Firefox", "firefox.exe")),
    
    # 办公软件
    "word": ("Word", ("Microsoft Office", "root", "Office16", "WINWORD.EXE")),
    "excel": ("Excel", ("Microsoft Office", "root", "Office16", "EXCEL.EXE")),
    "powerpoint": ("PowerPoint", ("Microsoft Office", "root", "Office16", "POWERPNT.EXE")),
    "outlook": ("Outlook", ("Microsoft Office", "root", "Office16", "OUTLOOK.EXE")),
    
    # 开发工具
    "vscode": ("VS Code", ("Microsoft VS Code", "Code.exe")),
    "notepad++": ("Notepad++", ("Notepad++", "notepad++.exe")),
    
    # 媒体应用
    "vlc": ("VLC播放器", ("VideoLAN", "VLC", "vlc.exe")),
    "spotify": ("Spotify", ("Spotify", "Spotify.exe")),
    
    # 通讯应用
    "teams": ("Microsoft Teams", ("Microsoft", "Teams", "current", "Teams.exe")),
    "slack": ("Slack", ("Slack", "slack.exe")),
    "discord": ("Discord", ("Discord", "Discord.exe")),
    "telegram": ("Telegram", ("Telegram Desktop", "Telegram.exe")),
    "whatsapp": ("WhatsApp", ("WhatsApp", "WhatsApp.exe")),
}

# 文件夹别名
FOLDER_LABELS = {
    "desktop": "桌面",
    "documents": "文档",
    "downloads": "下载",
    "pictures": "图片",
    "music": "音乐",
    "videos": "视频",
    "home": "用户主目录",
}

# 浏览器URL协议
BROWSER_PROTOCOLS = {
    "edge": "microsoft-edge:",
    "chrome": "googlechrome:",
    "firefox": "firefox:",
}


class ComputerUseService:
    """通用电脑控制服务"""
    
    PROPOSAL_TTL_SECONDS = 120

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._pending: dict[str, PendingAction] = {}
        self._definitions = self._create_definitions()
    
    def _create_definitions(self) -> dict[str, ToolDefinition]:
        """创建工具定义"""
        definitions = {}
        
        # 1. 系统状态（只读）
        definitions["get_system_status"] = ToolDefinition(
            name="get_system_status",
            title="读取系统概况",
            description="读取操作系统、CPU核心数、内存使用和磁盘剩余空间，不修改电脑。",
            risk="read_only",
            requires_confirmation=False,
            parameters={"type": "object", "properties": {}, "additionalProperties": False},
        )
        
        # 2. 打开应用
        definitions["open_application"] = ToolDefinition(
            name="open_application",
            title="打开应用",
            description="打开白名单中的Windows应用程序。",
            risk="low",
            requires_confirmation=True,
            parameters={
                "type": "object",
                "properties": {
                    "application": {
                        "type": "string",
                        "enum": sorted(APPLICATIONS.keys()),
                        "description": "要打开的白名单应用",
                    }
                },
                "required": ["application"],
                "additionalProperties": False,
            },
        )
        
        # 3. 打开文件夹
        definitions["open_folder"] = ToolDefinition(
            name="open_folder",
            title="打开文件夹",
            description="打开当前用户的常用文件夹。",
            risk="low",
            requires_confirmation=True,
            parameters={
                "type": "object",
                "properties": {
                    "folder": {
                        "type": "string",
                        "enum": sorted(FOLDER_LABELS.keys()),
                        "description": "要打开的固定文件夹别名",
                    }
                },
                "required": ["folder"],
                "additionalProperties": False,
            },
        )
        
        # 4. 打开URL
        definitions["open_url"] = ToolDefinition(
            name="open_url",
            title="打开网页",
            description="在默认浏览器中打开指定的网页地址。",
            risk="low",
            requires_confirmation=True,
            parameters={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "要打开的网页地址（必须以http://或https://开头）",
                    }
                },
                "required": ["url"],
                "additionalProperties": False,
            },
        )
        
        # 5. 锁定电脑
        definitions["lock_workstation"] = ToolDefinition(
            name="lock_workstation",
            title="锁定电脑",
            description="锁定当前Windows会话。不会关机或删除数据。",
            risk="high",
            requires_confirmation=True,
            parameters={"type": "object", "properties": {}, "additionalProperties": False},
        )
        
        # 6. 获取剪贴板内容
        definitions["get_clipboard"] = ToolDefinition(
            name="get_clipboard",
            title="读取剪贴板",
            description="读取当前剪贴板中的文本内容。",
            risk="read_only",
            requires_confirmation=False,
            parameters={"type": "object", "properties": {}, "additionalProperties": False},
        )
        
        # 7. 设置剪贴板内容
        definitions["set_clipboard"] = ToolDefinition(
            name="set_clipboard",
            title="设置剪贴板",
            description="将指定文本复制到剪贴板。",
            risk="low",
            requires_confirmation=True,
            parameters={
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "要复制到剪贴板的文本内容",
                    }
                },
                "required": ["text"],
                "additionalProperties": False,
            },
        )
        
        # 8. 截图
        definitions["take_screenshot"] = ToolDefinition(
            name="take_screenshot",
            title="截图",
            description="截取当前屏幕的截图并保存到临时目录。",
            risk="low",
            requires_confirmation=True,
            parameters={"type": "object", "properties": {}, "additionalProperties": False},
        )
        
        return definitions
    
    @property
    def available(self) -> bool:
        return sys.platform == "win32"
    
    def schemas(self) -> list[dict[str, Any]]:
        return [definition.schema() for definition in self._definitions.values()]
    
    def propose(self, name: str, raw_arguments: Any) -> dict[str, Any]:
        """提出一个操作提案"""
        definition = self._definitions.get(str(name))
        if definition is None:
            raise ComputerUseError("模型请求了不在白名单中的电脑操作")
        
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
        """解决一个操作提案"""
        cleaned = str(proposal_id or "").strip()
        if not cleaned:
            raise ComputerUseError("操作提案编号无效")
        
        with self._lock:
            self._purge_expired_locked()
            action = self._pending.pop(cleaned, None)
        
        if action is None:
            raise ComputerUseError("操作提案不存在、已经使用或已经过期")
        
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
    def _validate_arguments(definition: ToolDefinition, raw_arguments: Any) -> dict[str, Any]:
        if raw_arguments is None or raw_arguments == "":
            arguments: dict[str, Any] = {}
        elif isinstance(raw_arguments, Mapping):
            arguments = dict(raw_arguments)
        else:
            raise ComputerUseError("电脑操作参数必须是JSON对象")
        
        properties = definition.parameters.get("properties", {})
        required = set(definition.parameters.get("required", []))
        
        if set(arguments) - set(properties):
            raise ComputerUseError("电脑操作包含未允许的参数")
        if required - set(arguments):
            raise ComputerUseError("电脑操作缺少必要参数")
        
        for key, value in arguments.items():
            allowed = properties[key].get("enum")
            if allowed is not None and value not in allowed:
                raise ComputerUseError("电脑操作参数不在白名单中")
            if properties[key].get("type") == "string" and not isinstance(value, str):
                raise ComputerUseError("电脑操作参数类型无效")
        
        return arguments
    
    @staticmethod
    def _preview(name: str, arguments: Mapping[str, Any]) -> str:
        if name == "open_application":
            app_name = APPLICATIONS.get(arguments['application'], ("未知",))[0]
            return f"打开 Windows {app_name}"
        if name == "open_folder":
            folder_name = FOLDER_LABELS.get(arguments['folder'], "未知")
            return f"打开当前用户的{folder_name}"
        if name == "open_url":
            url = arguments.get('url', '')
            return f"打开网页：{url}"
        if name == "lock_workstation":
            return "立即锁定当前Windows会话"
        if name == "get_clipboard":
            return "读取剪贴板内容"
        if name == "set_clipboard":
            text = arguments.get('text', '')
            preview = text[:50] + "..." if len(text) > 50 else text
            return f"设置剪贴板为：{preview}"
        if name == "take_screenshot":
            return "截取屏幕截图"
        return "读取本机系统概况"
    
    def _execute(self, name: str, arguments: Mapping[str, Any]) -> str:
        """执行操作"""
        if name == "get_system_status":
            return self._get_system_status()
        
        if not self.available:
            raise ComputerUseError("电脑控制目前只支持Windows桌面版")
        
        if name == "open_application":
            return self._open_application(arguments)
        if name == "open_folder":
            return self._open_folder(arguments)
        if name == "open_url":
            return self._open_url(arguments)
        if name == "lock_workstation":
            return self._lock_workstation()
        if name == "get_clipboard":
            return self._get_clipboard()
        if name == "set_clipboard":
            return self._set_clipboard(arguments)
        if name == "take_screenshot":
            return self._take_screenshot()
        
        raise ComputerUseError("电脑操作不在白名单中")
    
    def _get_system_status(self) -> str:
        root = Path.home().anchor or os.sep
        disk = shutil.disk_usage(root)
        free_gib = disk.free / (1024**3)
        total_gib = disk.total / (1024**3)
        
        import psutil
        memory = psutil.virtual_memory()
        
        return (
            f"系统：{platform.system()} {platform.release()}\n"
            f"CPU：{os.cpu_count() or '未知'} 逻辑核心\n"
            f"内存：{memory.used / (1024**3):.1f} / {memory.total / (1024**3):.1f} GB ({memory.percent}%)\n"
            f"系统盘：{free_gib:.1f} / {total_gib:.1f} GB 可用"
        )
    
    def _open_application(self, arguments: Mapping[str, Any]) -> str:
        key = str(arguments["application"])
        label, _ = APPLICATIONS[key]
        executable = self._application_path(key)
        
        subprocess.Popen(
            [str(executable)],
            close_fds=True,
            creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
        )
        return f"已打开{label}。"
    
    def _open_folder(self, arguments: Mapping[str, Any]) -> str:
        folder = self._folder_path(str(arguments["folder"]))
        os.startfile(str(folder))
        return f"已打开{FOLDER_LABELS[str(arguments['folder'])]}。"
    
    def _open_url(self, arguments: Mapping[str, Any]) -> str:
        url = str(arguments["url"])
        if not url.startswith(("http://", "https://")):
            raise ComputerUseError("URL必须以http://或https://开头")
        
        import webbrowser
        webbrowser.open(url)
        return f"已打开网页：{url}"
    
    def _lock_workstation(self) -> str:
        import ctypes
        if not ctypes.windll.user32.LockWorkStation():
            raise ComputerUseError("Windows拒绝了锁屏请求")
        return "电脑已锁定。"
    
    def _get_clipboard(self) -> str:
        import win32clipboard
        win32clipboard.OpenClipboard()
        try:
            text = win32clipboard.GetClipboardData(win32clipboard.CF_UNICODETEXT)
            return f"剪贴板内容：{text[:500]}" if text else "剪贴板为空"
        finally:
            win32clipboard.CloseClipboard()
    
    def _set_clipboard(self, arguments: Mapping[str, Any]) -> str:
        text = str(arguments["text"])
        import win32clipboard
        win32clipboard.OpenClipboard()
        try:
            win32clipboard.EmptyClipboard()
            win32clipboard.SetClipboardText(text, win32clipboard.CF_UNICODETEXT)
        finally:
            win32clipboard.CloseClipboard()
        return f"已将文本复制到剪贴板。"
    
    def _take_screenshot(self) -> str:
        from PIL import ImageGrab
        import tempfile
        
        screenshot = ImageGrab.grab()
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        filename = f"screenshot_{timestamp}.png"
        filepath = Path(tempfile.gettempdir()) / filename
        
        screenshot.save(str(filepath))
        return f"截图已保存到：{filepath}"
    
    @staticmethod
    def _folder_path(alias: str) -> Path:
        home = Path.home()
        candidates = {
            "home": home,
            "desktop": home / "Desktop",
            "documents": home / "Documents",
            "downloads": home / "Downloads",
            "pictures": home / "Pictures",
            "music": home / "Music",
            "videos": home / "Videos",
        }
        path = candidates[alias]
        if not path.is_dir():
            raise ComputerUseError(f"找不到{FOLDER_LABELS[alias]}文件夹")
        return path
    
    @staticmethod
    def _application_path(key: str) -> Path:
        import ctypes
        
        buffer = ctypes.create_unicode_buffer(32_768)
        length = ctypes.windll.kernel32.GetWindowsDirectoryW(buffer, len(buffer))
        if length <= 0 or length >= len(buffer):
            raise ComputerUseError("无法确定可信的Windows系统目录")
        
        windows_root = Path(buffer.value)
        _, relative_parts = APPLICATIONS[key]
        executable = windows_root.joinpath(*relative_parts)
        
        if not executable.is_file():
            # 尝试从Program Files查找
            program_files = Path(os.environ.get("ProgramFiles", "C:\\Program Files"))
            alt_executable = program_files.joinpath(*relative_parts)
            if alt_executable.is_file():
                return alt_executable
            raise ComputerUseError(f"找不到Windows {APPLICATIONS[key][0]}")
        
        return executable
