"""
Canvas 可视化工作台 - v1.1.0
支持代码预览、图表渲染、交互式输出
参考 Aivy OS 的 Canvas 系统
"""

from __future__ import annotations

import json
import threading
import time
import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Callable
from enum import Enum


class CanvasType(Enum):
    """画布类型"""
    CODE = "code"
    HTML = "html"
    MARKDOWN = "markdown"
    CHART = "chart"
    IMAGE = "image"
    TABLE = "table"
    TERMINAL = "terminal"


@dataclass
class CanvasItem:
    """画布项目"""
    item_id: str
    type: CanvasType
    content: str
    title: str = ""
    language: str = ""  # 代码语言
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "item_id": self.item_id,
            "type": self.type.value,
            "content": self.content,
            "title": self.title,
            "language": self.language,
            "metadata": self.metadata,
            "created_at": self.created_at,
        }


@dataclass
class CanvasState:
    """画布状态"""
    items: List[CanvasItem] = field(default_factory=list)
    active_item: Optional[str] = None
    layout: str = "tabs"  # tabs, split, grid
    theme: str = "dark"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "items": [item.to_dict() for item in self.items],
            "active_item": self.active_item,
            "layout": self.layout,
            "theme": self.theme,
        }


class CanvasRenderer:
    """
    画布渲染器
    将不同类型的内容渲染为 HTML
    """
    
    @staticmethod
    def render_code(code: str, language: str = "") -> str:
        """渲染代码"""
        lang_class = f"language-{language}" if language else ""
        return f'''<pre class="canvas-code"><code class="{lang_class}">{_escape_html(code)}</code></pre>'''
    
    @staticmethod
    def render_html(html: str) -> str:
        """渲染 HTML"""
        return f'<div class="canvas-html">{html}</div>'
    
    @staticmethod
    def render_markdown(md: str) -> str:
        """渲染 Markdown"""
        # 简单的 Markdown 转 HTML
        html = md
        html = html.replace("**", "<strong>", 1).replace("**", "</strong>", 1)
        html = html.replace("*", "<em>", 1).replace("*", "</em>", 1)
        
        # 代码块
        if "```" in html:
            parts = html.split("```")
            for i in range(1, len(parts), 2):
                parts[i] = f'<pre><code>{_escape_html(parts[i])}</code></pre>'
            html = "".join(parts)
        
        # 标题
        for i in range(6, 0, -1):
            prefix = "#" * i
            html = html.replace(f"\n{prefix} ", f"\n<h{i}>")
        
        # 列表
        html = html.replace("\n- ", "\n<li>")
        html = html.replace("\n* ", "\n<li>")
        
        return f'<div class="canvas-markdown">{html}</div>'
    
    @staticmethod
    def render_chart(data: Dict[str, Any], chart_type: str = "bar") -> str:
        """渲染图表"""
        chart_id = hashlib.md5(json.dumps(data).encode()).hexdigest()[:8]
        
        return f'''
<div class="canvas-chart">
    <canvas id="chart-{chart_id}"></canvas>
    <script>
        new Chart(document.getElementById('chart-{chart_id}'), {{
            type: '{chart_type}',
            data: {json.dumps(data)},
            options: {{ responsive: true }}
        }});
    </script>
</div>'''
    
    @staticmethod
    def render_table(headers: List[str], rows: List[List[str]]) -> str:
        """渲染表格"""
        header_html = "".join(f"<th>{_escape_html(h)}</th>" for h in headers)
        rows_html = ""
        for row in rows:
            cells = "".join(f"<td>{_escape_html(str(c))}</td>" for c in row)
            rows_html += f"<tr>{cells}</tr>"
        
        return f'''
<div class="canvas-table-wrapper">
    <table class="canvas-table">
        <thead><tr>{header_html}</tr></thead>
        <tbody>{rows_html}</tbody>
    </table>
</div>'''
    
    @staticmethod
    def render_image(src: str, alt: str = "") -> str:
        """渲染图片"""
        if src.startswith("data:"):
            return f'<img class="canvas-image" src="{src}" alt="{alt}">'
        else:
            return f'<img class="canvas-image" src="/api/files/{src}" alt="{alt}">'
    
    @staticmethod
    def render_terminal(output: str) -> str:
        """渲染终端输出"""
        return f'<div class="canvas-terminal"><pre>{_escape_html(output)}</pre></div>'


def _escape_html(text: str) -> str:
    """转义 HTML"""
    return (text
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;"))


class CanvasWorkbench:
    """
    Canvas 工作台
    管理多个画布项目
    """
    
    def __init__(self, data_dir: Optional[Path] = None):
        self._data_dir = data_dir or Path.home() / ".jarvis" / "canvas"
        self._data_dir.mkdir(parents=True, exist_ok=True)
        
        self._state = CanvasState()
        self._renderer = CanvasRenderer()
        self._lock = threading.RLock()
        self._listeners: List[Callable[[Dict[str, Any]], None]] = []
        
        # 加载状态
        self._load_state()
    
    def _load_state(self):
        """加载状态"""
        state_file = self._data_dir / "state.json"
        if state_file.exists():
            try:
                data = json.loads(state_file.read_text(encoding="utf-8"))
                # TODO: 反序列化状态
            except Exception:
                pass
    
    def _save_state(self):
        """保存状态"""
        state_file = self._data_dir / "state.json"
        try:
            state_file.write_text(
                json.dumps(self._state.to_dict(), ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
        except Exception as e:
            print(f"[Canvas] Failed to save state: {e}")
    
    def _emit(self, event_type: str, data: Any):
        """发送事件"""
        event = {"type": event_type, "data": data, "timestamp": time.time()}
        for listener in self._listeners:
            try:
                listener(event)
            except Exception:
                pass
    
    def add_listener(self, callback: Callable[[Dict[str, Any]], None]):
        """添加监听器"""
        self._listeners.append(callback)
    
    def add_item(
        self,
        type: CanvasType,
        content: str,
        title: str = "",
        language: str = "",
        metadata: Dict[str, Any] = None,
    ) -> str:
        """
        添加画布项目
        
        Returns:
            项目 ID
        """
        item_id = hashlib.md5(f"{time.time()}{content[:100]}".encode()).hexdigest()[:8]
        
        item = CanvasItem(
            item_id=item_id,
            type=type,
            content=content,
            title=title or f"{type.value}-{item_id}",
            language=language,
            metadata=metadata or {},
        )
        
        with self._lock:
            self._state.items.append(item)
            self._state.active_item = item_id
            self._save_state()
        
        self._emit("item_added", item.to_dict())
        return item_id
    
    def add_code(self, code: str, language: str = "", title: str = "") -> str:
        """添加代码项目"""
        return self.add_item(CanvasType.CODE, code, title, language)
    
    def add_html(self, html: str, title: str = "") -> str:
        """添加 HTML 项目"""
        return self.add_item(CanvasType.HTML, html, title)
    
    def add_markdown(self, md: str, title: str = "") -> str:
        """添加 Markdown 项目"""
        return self.add_item(CanvasType.MARKDOWN, md, title)
    
    def add_chart(self, data: Dict[str, Any], chart_type: str = "bar", title: str = "") -> str:
        """添加图表项目"""
        return self.add_item(CanvasType.CHART, json.dumps(data), title, metadata={"chart_type": chart_type})
    
    def add_table(self, headers: List[str], rows: List[List[str]], title: str = "") -> str:
        """添加表格项目"""
        content = json.dumps({"headers": headers, "rows": rows})
        return self.add_item(CanvasType.TABLE, content, title)
    
    def add_image(self, src: str, alt: str = "", title: str = "") -> str:
        """添加图片项目"""
        return self.add_item(CanvasType.IMAGE, src, title, metadata={"alt": alt})
    
    def add_terminal(self, output: str, title: str = "") -> str:
        """添加终端输出"""
        return self.add_item(CanvasType.TERMINAL, output, title)
    
    def get_item(self, item_id: str) -> Optional[CanvasItem]:
        """获取项目"""
        with self._lock:
            for item in self._state.items:
                if item.item_id == item_id:
                    return item
        return None
    
    def remove_item(self, item_id: str) -> bool:
        """删除项目"""
        with self._lock:
            for i, item in enumerate(self._state.items):
                if item.item_id == item_id:
                    self._state.items.pop(i)
                    if self._state.active_item == item_id:
                        self._state.active_item = self._state.items[-1].item_id if self._state.items else None
                    self._save_state()
                    self._emit("item_removed", {"item_id": item_id})
                    return True
        return False
    
    def set_active(self, item_id: str):
        """设置活动项目"""
        with self._lock:
            self._state.active_item = item_id
            self._emit("active_changed", {"item_id": item_id})
    
    def clear(self):
        """清空画布"""
        with self._lock:
            self._state.items.clear()
            self._state.active_item = None
            self._save_state()
            self._emit("cleared", {})
    
    def render(self) -> str:
        """渲染整个画布为 HTML"""
        with self._lock:
            if not self._state.items:
                return '<div class="canvas-empty">画布为空</div>'
            
            # 渲染活动项目
            active = None
            for item in self._state.items:
                if item.item_id == self._state.active_item:
                    active = item
                    break
            
            if not active:
                active = self._state.items[-1]
            
            return self.render_item(active)
    
    def render_item(self, item: CanvasItem) -> str:
        """渲染单个项目"""
        if item.type == CanvasType.CODE:
            return self._renderer.render_code(item.content, item.language)
        elif item.type == CanvasType.HTML:
            return self._renderer.render_html(item.content)
        elif item.type == CanvasType.MARKDOWN:
            return self._renderer.render_markdown(item.content)
        elif item.type == CanvasType.CHART:
            data = json.loads(item.content)
            chart_type = item.metadata.get("chart_type", "bar")
            return self._renderer.render_chart(data, chart_type)
        elif item.type == CanvasType.TABLE:
            data = json.loads(item.content)
            return self._renderer.render_table(data["headers"], data["rows"])
        elif item.type == CanvasType.IMAGE:
            return self._renderer.render_image(item.content, item.metadata.get("alt", ""))
        elif item.type == CanvasType.TERMINAL:
            return self._renderer.render_terminal(item.content)
        else:
            return f'<div class="canvas-unknown">未知类型: {item.type}</div>'
    
    def render_tabs(self) -> str:
        """渲染标签页"""
        with self._lock:
            if not self._state.items:
                return ""
            
            tabs = []
            for item in self._state.items:
                active_class = "active" if item.item_id == self._state.active_item else ""
                icon = self._get_type_icon(item.type)
                tabs.append(f'<div class="canvas-tab {active_class}" data-id="{item.item_id}" onclick="setActiveTab(\'{item.item_id}\')">{icon} {item.title}</div>')
            
            return f'<div class="canvas-tabs">{"".join(tabs)}</div>'
    
    def _get_type_icon(self, type: CanvasType) -> str:
        """获取类型图标"""
        icons = {
            CanvasType.CODE: "📝",
            CanvasType.HTML: "🌐",
            CanvasType.MARKDOWN: "📄",
            CanvasType.CHART: "📊",
            CanvasType.IMAGE: "🖼️",
            CanvasType.TABLE: "📋",
            CanvasType.TERMINAL: "💻",
        }
        return icons.get(type, "📁")
    
    def get_state(self) -> Dict[str, Any]:
        """获取状态"""
        return self._state.to_dict()
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计"""
        with self._lock:
            type_counts = {}
            for item in self._state.items:
                type_name = item.type.value
                type_counts[type_name] = type_counts.get(type_name, 0) + 1
            
            return {
                "total_items": len(self._state.items),
                "active_item": self._state.active_item,
                "type_counts": type_counts,
                "layout": self._state.layout,
            }


# Canvas HTML 模板
CANVAS_HTML_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>JARVIS Canvas</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        :root {
            --bg: #1a1a2e;
            --surface: #16213e;
            --text: #eee;
            --accent: #0f3460;
            --highlight: #e94560;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: 'Segoe UI', sans-serif; background: var(--bg); color: var(--text); }
        .canvas-container { padding: 20px; }
        .canvas-tabs { display: flex; gap: 4px; margin-bottom: 16px; overflow-x: auto; }
        .canvas-tab {
            padding: 8px 16px;
            background: var(--surface);
            border: 1px solid transparent;
            border-radius: 8px 8px 0 0;
            cursor: pointer;
            white-space: nowrap;
            font-size: 14px;
        }
        .canvas-tab.active { background: var(--accent); border-color: var(--highlight); }
        .canvas-content { background: var(--surface); border-radius: 0 8px 8px 8px; padding: 20px; min-height: 400px; }
        .canvas-code { background: #0d1117; padding: 16px; border-radius: 8px; overflow-x: auto; }
        .canvas-code code { font-family: 'JetBrains Mono', monospace; font-size: 14px; }
        .canvas-table { width: 100%; border-collapse: collapse; }
        .canvas-table th, .canvas-table td { padding: 8px 12px; border: 1px solid #333; text-align: left; }
        .canvas-table th { background: var(--accent); }
        .canvas-chart { max-width: 600px; margin: 0 auto; }
        .canvas-image { max-width: 100%; border-radius: 8px; }
        .canvas-terminal { background: #000; padding: 16px; border-radius: 8px; font-family: monospace; }
        .canvas-markdown { line-height: 1.6; }
        .canvas-markdown h1, .canvas-markdown h2, .canvas-markdown h3 { margin: 16px 0 8px; }
        .canvas-markdown pre { background: #0d1117; padding: 12px; border-radius: 6px; }
        .canvas-empty { text-align: center; color: #666; padding: 40px; }
    </style>
</head>
<body>
    <div class="canvas-container">
        {tabs}
        <div class="canvas-content">
            {content}
        </div>
    </div>
    <script>
        function setActiveTab(id) {{
            // 发送到服务器
            fetch('/api/canvas/active', {{
                method: 'POST',
                headers: {{'Content-Type': 'application/json'}},
                body: JSON.stringify({{item_id: id}})
            }}).then(() => location.reload());
        }}
    </script>
</body>
</html>
'''


# 全局实例
_workbench: Optional[CanvasWorkbench] = None
_workbench_lock = threading.Lock()


def get_canvas_workbench(data_dir: Optional[Path] = None) -> CanvasWorkbench:
    """获取全局 Canvas 工作台"""
    global _workbench
    if _workbench is None:
        with _workbench_lock:
            if _workbench is None:
                _workbench = CanvasWorkbench(data_dir)
    return _workbench


# 工具定义
CANVAS_TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "canvas_add_code",
            "description": "在画布上显示代码。支持语法高亮。",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "代码内容"},
                    "language": {"type": "string", "description": "编程语言", "default": ""},
                    "title": {"type": "string", "description": "标签标题", "default": ""}
                },
                "required": ["code"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "canvas_add_table",
            "description": "在画布上显示表格。",
            "parameters": {
                "type": "object",
                "properties": {
                    "headers": {"type": "array", "items": {"type": "string"}, "description": "表头"},
                    "rows": {"type": "array", "items": {"type": "array"}, "description": "数据行"},
                    "title": {"type": "string", "description": "标签标题", "default": ""}
                },
                "required": ["headers", "rows"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "canvas_add_chart",
            "description": "在画布上显示图表。",
            "parameters": {
                "type": "object",
                "properties": {
                    "data": {"type": "object", "description": "图表数据"},
                    "chart_type": {"type": "string", "description": "图表类型: bar, line, pie, doughnut", "default": "bar"},
                    "title": {"type": "string", "description": "标签标题", "default": ""}
                },
                "required": ["data"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "canvas_add_markdown",
            "description": "在画布上显示 Markdown 内容。",
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {"type": "string", "description": "Markdown 内容"},
                    "title": {"type": "string", "description": "标签标题", "default": ""}
                },
                "required": ["content"]
            }
        }
    }
]
