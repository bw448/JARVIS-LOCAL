"""
Web search module for JARVIS LOCAL.
Provides web search capability using multiple search engines.
"""

from __future__ import annotations

import json
import re
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Mapping
from urllib import error, request
from urllib.parse import quote_plus, urlencode


@dataclass(slots=True)
class SearchResult:
    """A single search result."""
    title: str
    url: str
    snippet: str
    source: str = ""
    published_date: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "url": self.url,
            "snippet": self.snippet,
            "source": self.source,
            "published_date": self.published_date,
        }


@dataclass(slots=True)
class SearchResponse:
    """Search response with results and metadata."""
    query: str
    results: List[SearchResult]
    engine: str
    total_results: int = 0
    search_time_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "results": [r.to_dict() for r in self.results],
            "engine": self.engine,
            "total_results": self.total_results,
            "search_time_ms": self.search_time_ms,
        }


class WebSearchError(RuntimeError):
    """Web search error."""
    pass


class WebSearchService:
    """
    Web search service supporting multiple engines.
    
    Supported engines:
    - bing: Microsoft Bing (default, no API key needed for basic)
    - duckduckgo: DuckDuckGo (privacy-focused)
    - serper: Serper.dev (requires API key)
    """

    def __init__(self, engine: str = "bing", api_key: str = "", max_results: int = 10, timeout: int = 30):
        self._engine = engine
        self._api_key = api_key
        self._max_results = max_results
        self._timeout = timeout
        self._lock = threading.Lock()

    @property
    def engine(self) -> str:
        return self._engine

    def search(self, query: str, max_results: Optional[int] = None) -> SearchResponse:
        """
        Perform a web search.
        
        Args:
            query: Search query
            max_results: Maximum results to return (overrides default)
            
        Returns:
            SearchResponse with results
        """
        start_time = time.time()
        limit = max_results or self._max_results

        try:
            if self._engine == "bing":
                results = self._search_bing(query, limit)
            elif self._engine == "duckduckgo":
                results = self._search_duckduckgo(query, limit)
            elif self._engine == "serper":
                results = self._search_serper(query, limit)
            else:
                raise WebSearchError(f"不支持的搜索引擎: {self._engine}")

            elapsed_ms = (time.time() - start_time) * 1000

            return SearchResponse(
                query=query,
                results=results,
                engine=self._engine,
                total_results=len(results),
                search_time_ms=elapsed_ms,
            )
        except Exception as e:
            if isinstance(e, WebSearchError):
                raise
            raise WebSearchError(f"搜索失败: {str(e)}") from e

    def _search_bing(self, query: str, limit: int) -> List[SearchResult]:
        """Search using Bing (HTML scraping fallback)."""
        # Use DuckDuckGo lite as fallback (no API key needed)
        return self._search_duckduckgo(query, limit)

    def _search_duckduckgo(self, query: str, limit: int) -> List[SearchResult]:
        """Search using DuckDuckGo."""
        url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }

        req = request.Request(url, headers=headers, method="GET")
        try:
            with request.urlopen(req, timeout=self._timeout) as response:
                html = response.read().decode("utf-8", errors="replace")
        except (error.URLError, TimeoutError, OSError) as e:
            raise WebSearchError(f"无法连接到搜索引擎: {e}") from e

        # Parse results from HTML
        results = []

        # Extract result blocks
        result_pattern = re.compile(
            r'<a[^>]+class="result__a"[^>]+href="([^"]*)"[^>]*>(.*?)</a>.*?'
            r'<a[^>]+class="result__snippet"[^>]*>(.*?)</a>',
            re.DOTALL
        )

        for match in result_pattern.finditer(html):
            if len(results) >= limit:
                break

            url = match.group(1).strip()
            title = re.sub(r'<[^>]+>', '', match.group(2)).strip()
            snippet = re.sub(r'<[^>]+>', '', match.group(3)).strip()

            # Clean up URL (DuckDuckGo redirects)
            if "uddg=" in url:
                url_match = re.search(r'uddg=([^&]+)', url)
                if url_match:
                    from urllib.parse import unquote
                    url = unquote(url_match.group(1))

            if title and url:
                results.append(SearchResult(
                    title=title,
                    url=url,
                    snippet=snippet,
                    source="duckduckgo",
                ))

        # Fallback: simpler pattern
        if not results:
            link_pattern = re.compile(r'<a[^>]+href="(https?://[^"]+)"[^>]*>(.*?)</a>', re.DOTALL)
            for match in link_pattern.finditer(html):
                if len(results) >= limit:
                    break
                url = match.group(1)
                title = re.sub(r'<[^>]+>', '', match.group(2)).strip()
                if title and len(title) > 5 and "duckduckgo" not in url:
                    results.append(SearchResult(
                        title=title,
                        url=url,
                        snippet="",
                        source="duckduckgo",
                    ))

        return results

    def _search_serper(self, query: str, limit: int) -> List[SearchResult]:
        """Search using Serper.dev API."""
        if not self._api_key:
            raise WebSearchError("Serper API key not configured")

        url = "https://google.serper.dev/search"
        payload = json.dumps({
            "q": query,
            "num": limit,
            "gl": "cn",
            "hl": "zh-cn",
        }).encode("utf-8")

        headers = {
            "X-API-KEY": self._api_key,
            "Content-Type": "application/json",
        }

        req = request.Request(url, data=payload, headers=headers, method="POST")
        try:
            with request.urlopen(req, timeout=self._timeout) as response:
                data = json.loads(response.read().decode("utf-8"))
        except (error.URLError, TimeoutError, OSError) as e:
            raise WebSearchError(f"Serper API request failed: {e}") from e
        except json.JSONDecodeError as e:
            raise WebSearchError(f"Invalid response from Serper: {e}") from e

        results = []
        for item in data.get("organic", [])[:limit]:
            results.append(SearchResult(
                title=item.get("title", ""),
                url=item.get("link", ""),
                snippet=item.get("snippet", ""),
                source="serper",
                published_date=item.get("date", ""),
            ))

        return results

    def format_results_for_ai(self, response: SearchResponse) -> str:
        """Format search results for AI context."""
        if not response.results:
            return f"搜索 '{response.query}' 没有找到结果。"

        lines = [f"【搜索结果: {response.query}】"]
        lines.append(f"搜索引擎: {response.engine} | 结果数: {response.total_results} | 耗时: {response.search_time_ms:.0f}ms")
        lines.append("")

        for i, result in enumerate(response.results, 1):
            lines.append(f"{i}. {result.title}")
            lines.append(f"   链接: {result.url}")
            if result.snippet:
                lines.append(f"   摘要: {result.snippet}")
            if result.published_date:
                lines.append(f"   日期: {result.published_date}")
            lines.append("")

        return "\n".join(lines)


# Tool definition for AI
SEARCH_TOOL_DEFINITION = {
    "type": "function",
    "function": {
        "name": "web_search",
        "description": "搜索互联网获取信息。用于回答需要最新信息的问题、查找资料、验证事实。",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "搜索关键词"
                },
                "max_results": {
                    "type": "integer",
                    "description": "最大结果数",
                    "default": 5
                }
            },
            "required": ["query"]
        }
    }
}


# Global singleton
_search_service: Optional[WebSearchService] = None
_search_lock = threading.Lock()


def get_search_service(engine: str = "bing", api_key: str = "") -> WebSearchService:
    """Get the global search service instance."""
    global _search_service
    if _search_service is None:
        with _search_lock:
            if _search_service is None:
                _search_service = WebSearchService(engine=engine, api_key=api_key)
    return _search_service
