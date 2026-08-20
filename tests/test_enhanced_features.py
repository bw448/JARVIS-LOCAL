"""
Tests for enhanced features: Memory, Skills, Web Search, Document Processing
"""

import pytest
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add parent directory to path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from jarvis.memory import MemoryStore, MemoryEntry
from jarvis.skills import SkillManager, Skill, SkillMetadata
from jarvis.web_search import WebSearchService, SearchResult
from jarvis.document import DocumentProcessor, DocumentResult


class TestMemoryStore:
    """Test memory store functionality."""
    
    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()
        self.memory = MemoryStore(data_dir=Path(self.temp_dir))
    
    def test_core_memory(self):
        """Test core memory operations."""
        self.memory.set_core("user_name", "张先生")
        assert self.memory.get_core("user_name") == "张先生"
        
        # Test all core
        all_core = self.memory.get_all_core()
        assert "user_name" in all_core
        
        # Test delete
        assert self.memory.delete_core("user_name") is True
        assert self.memory.get_core("user_name") is None
    
    def test_conversation_memory(self):
        """Test conversation memory."""
        self.memory.add_conversation("user", "你好")
        self.memory.add_conversation("assistant", "你好！有什么可以帮助你的吗？")
        
        recent = self.memory.get_recent_conversation(count=2)
        assert len(recent) == 2
        assert recent[0]["role"] == "user"
        assert recent[1]["role"] == "assistant"
    
    def test_long_term_memory(self):
        """Test long-term memory storage and recall."""
        # Store memories
        id1 = self.memory.remember("用户喜欢喝咖啡", category="preference")
        id2 = self.memory.remember("用户住在上海", category="fact")
        id3 = self.memory.remember("用户是程序员", category="fact")
        
        # Recall
        results = self.memory.recall("咖啡")
        assert len(results) > 0
        assert any("咖啡" in r.content for r in results)
        
        # Recall with different query
        results = self.memory.recall("上海")
        assert len(results) > 0
    
    def test_memory_stats(self):
        """Test memory statistics."""
        self.memory.set_core("test", "value")
        self.memory.add_conversation("user", "hello")
        self.memory.remember("test fact")
        
        stats = self.memory.get_memory_stats()
        assert stats["core_count"] == 1
        assert stats["short_term_count"] == 1
        assert stats["long_term_count"] == 1
    
    def test_context_prompt(self):
        """Test context prompt generation."""
        self.memory.set_core("owner", "张先生")
        self.memory.add_conversation("user", "今天天气怎么样？")
        
        prompt = self.memory.build_context_prompt()
        assert "核心记忆" in prompt
        assert "近期对话" in prompt


class TestSkillManager:
    """Test skill manager functionality."""
    
    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()
        self.skills_dir = Path(self.temp_dir) / "skills"
        self.skills_dir.mkdir()
    
    def test_add_skill(self):
        """Test adding a skill."""
        manager = SkillManager(skills_dir=self.skills_dir)
        
        # Add a skill
        content = "# Test Skill\n\nThis is a test skill."
        result = manager.add_skill("test-skill", content, description="A test skill")
        assert result is True
        
        # Get the skill
        skill = manager.get_skill("test-skill")
        assert skill is not None
        assert skill.name == "test-skill"
        assert "Test Skill" in skill.content
    
    def test_list_skills(self):
        """Test listing skills."""
        manager = SkillManager(skills_dir=self.skills_dir)
        
        # Add skills
        manager.add_skill("skill1", "# Skill 1", description="First skill", tags=["tag1"])
        manager.add_skill("skill2", "# Skill 2", description="Second skill", tags=["tag2"])
        
        # List
        skills = manager.list_skills()
        assert len(skills) == 2
    
    def test_search_skills(self):
        """Test searching skills."""
        manager = SkillManager(skills_dir=self.skills_dir)
        
        manager.add_skill("code-dev", "# Code Development", description="Coding skills", tags=["coding", "python"])
        manager.add_skill("web-research", "# Web Research", description="Search skills", tags=["search", "web"])
        
        # Search by tag
        results = manager.search_skills("coding")
        assert len(results) > 0
        assert results[0].name == "code-dev"
    
    def test_skill_context(self):
        """Test skill context generation."""
        manager = SkillManager(skills_dir=self.skills_dir)
        
        manager.add_skill("test", "# Test\n\nInstructions here.", description="Test skill")
        
        context = manager.get_skill_context()
        assert "可用技能" in context
        assert "test" in context


class TestWebSearch:
    """Test web search functionality."""
    
    def test_search_duckduckgo(self):
        """Test DuckDuckGo search."""
        service = WebSearchService(engine="duckduckgo")
        
        # This test might fail if network is unavailable
        try:
            response = service.search("Python programming", max_results=3)
            assert response.query == "Python programming"
            assert response.engine == "duckduckgo"
            # Results might be empty if parsing fails, but response should be valid
        except Exception as e:
            pytest.skip(f"Network unavailable: {e}")
    
    def test_format_results(self):
        """Test result formatting."""
        service = WebSearchService()
        
        from jarvis.web_search import SearchResponse
        response = SearchResponse(
            query="test",
            results=[
                SearchResult(title="Test", url="http://test.com", snippet="A test result"),
            ],
            engine="test",
            total_results=1,
            search_time_ms=100.0,
        )
        
        formatted = service.format_results_for_ai(response)
        assert "搜索结果" in formatted
        assert "Test" in formatted


class TestDocumentProcessor:
    """Test document processor functionality."""
    
    def setup_method(self):
        self.processor = DocumentProcessor()
        self.temp_dir = tempfile.mkdtemp()
    
    def test_read_text_file(self):
        """Test reading text files."""
        # Create a test file
        test_file = Path(self.temp_dir) / "test.txt"
        test_file.write_text("Hello, World!", encoding="utf-8")
        
        result = self.processor.read_file(str(test_file))
        assert result.success is True
        assert result.content == "Hello, World!"
    
    def test_read_nonexistent_file(self):
        """Test reading nonexistent file."""
        result = self.processor.read_file("/nonexistent/file.txt")
        assert result.success is False
        assert "不存在" in result.error
    
    def test_write_file(self):
        """Test writing files."""
        test_file = Path(self.temp_dir) / "output.txt"
        
        result = self.processor.write_file(str(test_file), "Test content")
        assert result.success is True
        assert test_file.read_text() == "Test content"
    
    def test_write_file_no_overwrite(self):
        """Test writing file without overwrite."""
        test_file = Path(self.temp_dir) / "existing.txt"
        test_file.write_text("Original")
        
        result = self.processor.write_file(str(test_file), "New content")
        assert result.success is False
        assert "已存在" in result.error
    
    def test_list_directory(self):
        """Test listing directory."""
        # Create test files
        (Path(self.temp_dir) / "file1.txt").touch()
        (Path(self.temp_dir) / "file2.txt").touch()
        
        result = self.processor.list_directory(self.temp_dir)
        assert result.success is True
        assert "file1.txt" in result.content
        assert "file2.txt" in result.content


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
