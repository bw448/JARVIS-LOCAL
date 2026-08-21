"""
Document processing module for JARVIS LOCAL.
Provides basic document reading and generation capabilities.
Inspired by Aivy OS document processing skills.
"""

from __future__ import annotations

import json
import re
import subprocess
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class DocumentResult:
    """Result from document processing."""
    success: bool
    content: str = ""
    metadata: Dict[str, Any] = None
    error: str = ""

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class DocumentProcessor:
    """
    Document processor supporting multiple formats.
    
    Supported formats:
    - Text files (.txt, .md, .py, .js, etc.)
    - JSON files
    - CSV files (basic)
    - PDF (requires pdfminer)
    - DOCX (requires python-docx)
    """

    def __init__(self):
        self._supported_extensions = {
            '.txt', '.md', '.py', '.js', '.ts', '.html', '.css', '.json',
            '.csv', '.xml', '.yaml', '.yml', '.toml', '.ini', '.cfg',
            '.log', '.sh', '.bat', '.cmd', '.ps1',
        }

    def read_file(self, file_path: str, max_size: int = 1024 * 1024) -> DocumentResult:
        """
        Read a file and return its content.
        
        Args:
            file_path: Path to the file
            max_size: Maximum file size in bytes (default 1MB)
            
        Returns:
            DocumentResult with content
        """
        path = Path(file_path)
        
        if not path.exists():
            return DocumentResult(success=False, error=f"文件不存在: {file_path}")
        
        if not path.is_file():
            return DocumentResult(success=False, error=f"不是文件: {file_path}")
        
        # Check size
        size = path.stat().st_size
        if size > max_size:
            return DocumentResult(success=False, error=f"文件过大: {size} bytes (最大 {max_size})")
        
        # Check extension
        ext = path.suffix.lower()
        
        try:
            if ext in self._supported_extensions:
                # Text-based files
                content = path.read_text(encoding='utf-8', errors='replace')
                return DocumentResult(
                    success=True,
                    content=content,
                    metadata={
                        "type": "text",
                        "extension": ext,
                        "size": size,
                        "lines": content.count('\n') + 1,
                    }
                )
            elif ext == '.pdf':
                return self._read_pdf(path)
            elif ext == '.docx':
                return self._read_docx(path)
            elif ext == '.xlsx':
                return self._read_xlsx(path)
            else:
                # Try to read as text
                try:
                    content = path.read_text(encoding='utf-8', errors='replace')
                    return DocumentResult(
                        success=True,
                        content=content,
                        metadata={"type": "text", "extension": ext, "size": size}
                    )
                except:
                    return DocumentResult(success=False, error=f"不支持的文件格式: {ext}")
        except Exception as e:
            return DocumentResult(success=False, error=f"读取失败: {str(e)}")

    def _read_pdf(self, path: Path) -> DocumentResult:
        """Read PDF file."""
        try:
            from pdfminer.high_level import extract_text
            content = extract_text(str(path))
            return DocumentResult(
                success=True,
                content=content,
                metadata={"type": "pdf", "size": path.stat().st_size}
            )
        except ImportError:
            return DocumentResult(success=False, error="需要安装 pdfminer: pip install pdfminer.six")
        except Exception as e:
            return DocumentResult(success=False, error=f"PDF读取失败: {str(e)}")

    def _read_docx(self, path: Path) -> DocumentResult:
        """Read DOCX file."""
        try:
            from docx import Document
            doc = Document(str(path))
            content = '\n'.join([para.text for para in doc.paragraphs])
            return DocumentResult(
                success=True,
                content=content,
                metadata={"type": "docx", "size": path.stat().st_size}
            )
        except ImportError:
            return DocumentResult(success=False, error="需要安装 python-docx: pip install python-docx")
        except Exception as e:
            return DocumentResult(success=False, error=f"DOCX读取失败: {str(e)}")

    def _read_xlsx(self, path: Path) -> DocumentResult:
        """Read XLSX file."""
        try:
            import pandas as pd
            df = pd.read_excel(str(path))
            content = df.to_string()
            return DocumentResult(
                success=True,
                content=content,
                metadata={
                    "type": "xlsx",
                    "size": path.stat().st_size,
                    "rows": len(df),
                    "columns": len(df.columns),
                }
            )
        except ImportError:
            return DocumentResult(success=False, error="需要安装 pandas 和 openpyxl: pip install pandas openpyxl")
        except Exception as e:
            return DocumentResult(success=False, error=f"XLSX读取失败: {str(e)}")

    def write_file(self, file_path: str, content: str, overwrite: bool = False) -> DocumentResult:
        """
        Write content to a file.
        
        Args:
            file_path: Path to write to
            content: Content to write
            overwrite: Whether to overwrite existing file
            
        Returns:
            DocumentResult with success status
        """
        path = Path(file_path)
        
        if path.exists() and not overwrite:
            return DocumentResult(success=False, error=f"文件已存在: {file_path} (使用 overwrite=True 覆盖)")
        
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding='utf-8')
            return DocumentResult(
                success=True,
                metadata={"type": "write", "size": len(content.encode('utf-8'))}
            )
        except Exception as e:
            return DocumentResult(success=False, error=f"写入失败: {str(e)}")

    def list_directory(self, dir_path: str, pattern: str = "*") -> DocumentResult:
        """
        List files in a directory.
        
        Args:
            dir_path: Directory path
            pattern: Glob pattern (default: *)
            
        Returns:
            DocumentResult with file list
        """
        path = Path(dir_path)
        
        if not path.exists():
            return DocumentResult(success=False, error=f"目录不存在: {dir_path}")
        
        if not path.is_dir():
            return DocumentResult(success=False, error=f"不是目录: {dir_path}")
        
        try:
            files = []
            for item in sorted(path.glob(pattern)):
                files.append({
                    "name": item.name,
                    "path": str(item),
                    "is_dir": item.is_dir(),
                    "size": item.stat().st_size if item.is_file() else 0,
                })
            
            return DocumentResult(
                success=True,
                content=json.dumps(files, ensure_ascii=False, indent=2),
                metadata={"type": "directory", "count": len(files)}
            )
        except Exception as e:
            return DocumentResult(success=False, error=f"列出目录失败: {str(e)}")


# Tool definition for AI
DOCUMENT_TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "读取文件内容。支持文本文件、PDF、DOCX、XLSX等格式。",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "文件路径"
                    }
                },
                "required": ["file_path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "写入内容到文件。如果文件已存在，需要指定覆盖。",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "文件路径"
                    },
                    "content": {
                        "type": "string",
                        "description": "要写入的内容"
                    },
                    "overwrite": {
                        "type": "boolean",
                        "description": "是否覆盖已存在的文件",
                        "default": False
                    }
                },
                "required": ["file_path", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_directory",
            "description": "列出目录中的文件。",
            "parameters": {
                "type": "object",
                "properties": {
                    "dir_path": {
                        "type": "string",
                        "description": "目录路径"
                    },
                    "pattern": {
                        "type": "string",
                        "description": "文件匹配模式 (如 *.py)",
                        "default": "*"
                    }
                },
                "required": ["dir_path"]
            }
        }
    }
]


# Global singleton
_doc_processor: Optional[DocumentProcessor] = None
_doc_lock = threading.Lock()


def get_document_processor() -> DocumentProcessor:
    """Get the global document processor instance."""
    global _doc_processor
    if _doc_processor is None:
        with _doc_lock:
            if _doc_processor is None:
                _doc_processor = DocumentProcessor()
    return _doc_processor
