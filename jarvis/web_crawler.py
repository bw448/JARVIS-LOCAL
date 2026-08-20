"""
网页爬取模块 - v1.0.0
支持网页内容提取、结构化解析、知识库构建
参考 Aivy OS 的 crawl4ai 集成
"""

from __future__ import annotations

import re
import json
import hashlib
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from urllib import error, request
from urllib.parse import urljoin, urlparse
from html.parser import HTMLParser


@dataclass(slots=True)
class WebPage:
    """网页数据"""
    url: str
    title: str
    content: str
    html: str
    links: List[str] = field(default_factory=list)
    images: List[str] = field(default_factory=list)
    metadata: Dict[str, str] = field(default_factory=dict)
    crawled_at: float = field(default_factory=time.time)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "url": self.url,
            "title": self.title,
            "content": self.content[:5000],  # 限制长度
            "links": self.links[:50],
            "images": self.images[:20],
            "metadata": self.metadata,
            "crawled_at": self.crawled_at,
        }


class HTMLTextExtractor(HTMLParser):
    """HTML 文本提取器"""
    
    def __init__(self):
        super().__init__()
        self._text_parts: List[str] = []
        self._skip_tags: Set[str] = {"script", "style", "noscript", "iframe"}
        self._current_skip = False
        self._title = ""
        self._in_title = False
        self._links: List[str] = []
        self._images: List[str] = []
        self._metadata: Dict[str, str] = {}
    
    def handle_starttag(self, tag: str, attrs: list):
        if tag in self._skip_tags:
            self._current_skip = True
        
        if tag == "title":
            self._in_title = True
        
        if tag == "a":
            for name, value in attrs:
                if name == "href" and value:
                    self._links.append(value)
        
        if tag == "img":
            for name, value in attrs:
                if name == "src" and value:
                    self._images.append(value)
        
        if tag == "meta":
            name = None
            content = None
            for attr_name, attr_value in attrs:
                if attr_name == "name":
                    name = attr_value
                elif attr_name == "content":
                    content = attr_value
            if name and content:
                self._metadata[name] = content
    
    def handle_endtag(self, tag: str):
        if tag in self._skip_tags:
            self._current_skip = False
        if tag == "title":
            self._in_title = False
    
    def handle_data(self, data: str):
        if self._in_title:
            self._title = data.strip()
        
        if not self._current_skip:
            text = data.strip()
            if text:
                self._text_parts.append(text)
    
    def get_text(self) -> str:
        return " ".join(self._text_parts)
    
    def get_title(self) -> str:
        return self._title
    
    def get_links(self) -> List[str]:
        return self._links
    
    def get_images(self) -> List[str]:
        return self._images
    
    def get_metadata(self) -> Dict[str, str]:
        return self._metadata


class WebCrawler:
    """
    网页爬取器
    支持单页爬取和批量爬取
    """
    
    def __init__(
        self,
        max_pages: int = 100,
        timeout: int = 30,
        user_agent: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        respect_robots: bool = True,
    ):
        self._max_pages = max_pages
        self._timeout = timeout
        self._user_agent = user_agent
        self._respect_robots = respect_robots
        self._visited: Set[str] = set()
        self._lock = threading.Lock()
    
    def crawl_page(self, url: str) -> Optional[WebPage]:
        """
        爬取单个页面
        
        Args:
            url: 页面 URL
            
        Returns:
            WebPage 或 None
        """
        try:
            headers = {
                "User-Agent": self._user_agent,
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            }
            
            req = request.Request(url, headers=headers, method="GET")
            
            with request.urlopen(req, timeout=self._timeout) as response:
                html = response.read().decode("utf-8", errors="replace")
            
            # 解析 HTML
            extractor = HTMLTextExtractor()
            extractor.feed(html)
            
            # 处理相对链接
            links = []
            for link in extractor.get_links():
                absolute = urljoin(url, link)
                if absolute.startswith("http"):
                    links.append(absolute)
            
            images = []
            for img in extractor.get_images():
                absolute = urljoin(url, img)
                if absolute.startswith("http"):
                    images.append(absolute)
            
            page = WebPage(
                url=url,
                title=extractor.get_title(),
                content=extractor.get_text(),
                html=html,
                links=links,
                images=images,
                metadata=extractor.get_metadata(),
            )
            
            with self._lock:
                self._visited.add(url)
            
            return page
        
        except Exception as e:
            print(f"[Crawler] Failed to crawl {url}: {e}")
            return None
    
    def crawl_site(
        self,
        start_url: str,
        max_depth: int = 2,
        same_domain: bool = True,
        callback: Optional[Callable[[WebPage], None]] = None,
    ) -> List[WebPage]:
        """
        爬取网站
        
        Args:
            start_url: 起始 URL
            max_depth: 最大深度
            same_domain: 是否只爬取同域名
            callback: 每页回调
            
        Returns:
            页面列表
        """
        pages: List[WebPage] = []
        queue: List[tuple[str, int]] = [(start_url, 0)]
        visited: Set[str] = set()
        
        start_domain = urlparse(start_url).netloc
        
        while queue and len(pages) < self._max_pages:
            url, depth = queue.pop(0)
            
            if url in visited:
                continue
            
            if depth > max_depth:
                continue
            
            # 同域名检查
            if same_domain:
                page_domain = urlparse(url).netloc
                if page_domain != start_domain:
                    continue
            
            visited.add(url)
            
            page = self.crawl_page(url)
            if page:
                pages.append(page)
                
                if callback:
                    callback(page)
                
                # 添加子链接
                if depth < max_depth:
                    for link in page.links:
                        if link not in visited:
                            queue.append((link, depth + 1))
        
        return pages
    
    def extract_text(self, html: str) -> str:
        """从 HTML 提取纯文本"""
        extractor = HTMLTextExtractor()
        extractor.feed(html)
        return extractor.get_text()
    
    def extract_links(self, html: str, base_url: str = "") -> List[str]:
        """从 HTML 提取链接"""
        extractor = HTMLTextExtractor()
        extractor.feed(html)
        
        links = []
        for link in extractor.get_links():
            if base_url:
                link = urljoin(base_url, link)
            if link.startswith("http"):
                links.append(link)
        
        return links


@dataclass(slots=True)
class CrawlResult:
    """爬取结果"""
    pages: List[WebPage]
    total_pages: int
    total_chars: int
    crawl_time: float
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_pages": self.total_pages,
            "total_chars": self.total_chars,
            "crawl_time": self.crawl_time,
            "pages": [p.to_dict() for p in self.pages[:10]],  # 只返回前10页
        }
    
    def get_summary(self) -> str:
        """获取摘要"""
        lines = [
            f"爬取完成: {self.total_pages} 页, {self.total_chars} 字符",
            f"耗时: {self.crawl_time:.1f} 秒",
            "",
            "页面列表:"
        ]
        
        for i, page in enumerate(self.pages[:10], 1):
            lines.append(f"{i}. {page.title or '无标题'}")
            lines.append(f"   URL: {page.url}")
            lines.append(f"   内容: {page.content[:100]}...")
        
        if len(self.pages) > 10:
            lines.append(f"... 还有 {len(self.pages) - 10} 页")
        
        return "\n".join(lines)


class KnowledgeBase:
    """
    知识库
    存储和检索爬取的内容
    """
    
    def __init__(self, data_dir: Optional[Path] = None):
        self._data_dir = data_dir or Path.home() / ".jarvis" / "knowledge"
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._index: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()
        
        # 加载索引
        self._load_index()
    
    def _load_index(self):
        """加载索引"""
        index_file = self._data_dir / "index.json"
        if index_file.exists():
            try:
                self._index = json.loads(index_file.read_text(encoding="utf-8"))
            except Exception:
                self._index = {}
    
    def _save_index(self):
        """保存索引"""
        index_file = self._data_dir / "index.json"
        try:
            index_file.write_text(
                json.dumps(self._index, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
        except Exception as e:
            print(f"[Knowledge] Failed to save index: {e}")
    
    def add_page(self, page: WebPage):
        """添加页面到知识库"""
        with self._lock:
            url_hash = hashlib.md5(page.url.encode()).hexdigest()[:12]
            
            # 保存内容
            content_file = self._data_dir / f"{url_hash}.txt"
            content_file.write_text(page.content, encoding="utf-8")
            
            # 更新索引
            self._index[url_hash] = {
                "url": page.url,
                "title": page.title,
                "content_preview": page.content[:200],
                "added_at": time.time(),
            }
            
            self._save_index()
    
    def search(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """搜索知识库"""
        with self._lock:
            results = []
            query_lower = query.lower()
            
            for url_hash, info in self._index.items():
                title = info.get("title", "").lower()
                preview = info.get("content_preview", "").lower()
                
                if query_lower in title or query_lower in preview:
                    results.append({
                        "url": info["url"],
                        "title": info["title"],
                        "preview": info["content_preview"],
                    })
            
            return results[:limit]
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计"""
        return {
            "total_pages": len(self._index),
            "data_dir": str(self._data_dir),
        }


# 全局实例
_crawler: Optional[WebCrawler] = None
_knowledge: Optional[KnowledgeBase] = None
_crawler_lock = threading.Lock()


def get_crawler() -> WebCrawler:
    """获取全局爬虫实例"""
    global _crawler
    if _crawler is None:
        with _crawler_lock:
            if _crawler is None:
                _crawler = WebCrawler()
    return _crawler


def get_knowledge_base(data_dir: Optional[Path] = None) -> KnowledgeBase:
    """获取全局知识库实例"""
    global _knowledge
    if _knowledge is None:
        with _crawler_lock:
            if _knowledge is None:
                _knowledge = KnowledgeBase(data_dir)
    return _knowledge


# 工具定义
CRAWLER_TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "crawl_page",
            "description": "爬取网页内容。提取文本、链接、图片等信息。",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "要爬取的网页 URL"
                    }
                },
                "required": ["url"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "crawl_site",
            "description": "爬取整个网站。从起始 URL 开始，递归爬取链接。",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "起始 URL"
                    },
                    "max_depth": {
                        "type": "integer",
                        "description": "最大爬取深度",
                        "default": 2
                    },
                    "max_pages": {
                        "type": "integer",
                        "description": "最大页面数",
                        "default": 10
                    }
                },
                "required": ["url"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_knowledge",
            "description": "搜索知识库中的内容。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "搜索关键词"
                    }
                },
                "required": ["query"]
            }
        }
    }
]
