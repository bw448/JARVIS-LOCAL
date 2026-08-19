"""
集成测试脚本
验证所有优化功能正常工作
"""

from __future__ import annotations

import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from urllib import request

from jarvis.app_enhanced import EnhancedJarvisApplication, create_enhanced_server
from jarvis.config import Settings, SettingsStore
from jarvis.computer_use import ComputerUseService, ComputerUseError
from jarvis.speech_optimizer import get_tts_cache, get_metrics


class MemorySecretStore:
    def __init__(self) -> None:
        self.value = ""

    def get_brain_api_key(self) -> str:
        return self.value

    def has_brain_api_key(self) -> bool:
        return bool(self.value)

    def set_brain_api_key(self, value: str | None) -> None:
        self.value = (value or "").strip()


class TestTTSCache(unittest.TestCase):
    """测试TTS缓存功能"""
    
    def test_cache_put_and_get(self):
        """测试缓存存储和获取"""
        cache = get_tts_cache()
        cache.clear()
        
        # 存储
        cache.put("你好", "zf_xiaoxiao", 1.0, b"fake-audio", "audio/wav")
        
        # 获取
        result = cache.get("你好", "zf_xiaoxiao", 1.0)
        self.assertIsNotNone(result)
        self.assertEqual(result[0], b"fake-audio")
        self.assertEqual(result[1], "audio/wav")
    
    def test_cache_miss(self):
        """测试缓存未命中"""
        cache = get_tts_cache()
        cache.clear()
        
        result = cache.get("不存在的文本", "zf_xiaoxiao", 1.0)
        self.assertIsNone(result)
    
    def test_cache_stats(self):
        """测试缓存统计"""
        cache = get_tts_cache()
        cache.clear()
        
        # 添加一些缓存
        cache.put("测试1", "voice1", 1.0, b"audio1", "audio/wav")
        cache.put("测试2", "voice2", 1.0, b"audio2", "audio/wav")
        
        stats = cache.stats()
        self.assertEqual(stats["entries"], 2)
        self.assertGreater(stats["size_mb"], 0)
    
    def test_cache_clear(self):
        """测试清空缓存"""
        cache = get_tts_cache()
        cache.put("测试", "voice", 1.0, b"audio", "audio/wav")
        
        cache.clear()
        stats = cache.stats()
        self.assertEqual(stats["entries"], 0)


class TestComputerUse(unittest.TestCase):
    """测试Computer Use功能"""
    
    def test_schemas_count(self):
        """测试工具数量"""
        service = ComputerUseService()
        schemas = service.schemas()
        
        # 应该有8个工具
        self.assertEqual(len(schemas), 8)
    
    def test_unknown_tool_rejected(self):
        """测试未知工具被拒绝"""
        service = ComputerUseService()
        
        with self.assertRaises(ComputerUseError):
            service.propose("unknown_tool", {})
    
    def test_system_status(self):
        """测试系统状态读取"""
        service = ComputerUseService()
        result = service.propose("get_system_status", {})
        
        self.assertEqual(result["kind"], "result")
        self.assertIn("CPU", result["message"])
        self.assertIn("内存", result["message"])
    
    def test_open_application_proposal(self):
        """测试打开应用提案"""
        service = ComputerUseService()
        
        # 这需要确认
        result = service.propose("open_application", {"application": "notepad"})
        self.assertEqual(result["kind"], "proposal")
        self.assertIn("记事本", result["preview"])
    
    def test_open_url_proposal(self):
        """测试打开网页提案"""
        service = ComputerUseService()
        
        result = service.propose("open_url", {"url": "https://example.com"})
        self.assertEqual(result["kind"], "proposal")
        self.assertIn("example.com", result["preview"])
    
    def test_invalid_url_rejected(self):
        """测试无效URL被拒绝"""
        service = ComputerUseService()
        
        with self.assertRaises(ComputerUseError):
            service.propose("open_url", {"url": "invalid-url"})
    
    def test_proposal_resolve(self):
        """测试提案解决"""
        service = ComputerUseService()
        
        # 创建提案
        proposal = service.propose("get_clipboard", {})
        self.assertEqual(proposal["kind"], "result")  # 只读操作不需要确认
        
        # 创建需要确认的提案
        proposal = service.propose("set_clipboard", {"text": "test"})
        self.assertEqual(proposal["kind"], "proposal")
        
        # 解决提案（模拟用户拒绝）
        result = service.resolve(proposal["proposal_id"], False)
        self.assertFalse(result["executed"])


class TestSpeechMetrics(unittest.TestCase):
    """测试语音性能指标"""
    
    def test_record_metrics(self):
        """测试记录性能指标"""
        metrics = get_metrics()
        
        # 记录一些指标
        metrics.record_tts_time(100.0)
        metrics.record_tts_time(150.0)
        metrics.record_stt_time(200.0)
        
        stats = metrics.get_stats()
        self.assertGreater(stats["tts"]["samples"], 0)
        self.assertGreater(stats["stt"]["samples"], 0)
    
    def test_metrics_stats(self):
        """测试指标统计"""
        metrics = get_metrics()
        
        # 记录一些指标
        for i in range(10):
            metrics.record_tts_time(100.0 + i)
        
        stats = metrics.get_stats()
        self.assertEqual(stats["tts"]["samples"], 10)
        self.assertGreater(stats["tts"]["avg_ms"], 0)


class TestEnhancedApplication(unittest.TestCase):
    """测试增强版应用"""
    
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.application = EnhancedJarvisApplication(
            SettingsStore(Path(self.temporary.name)), MemorySecretStore()
        )
    
    def test_public_state_has_performance(self):
        """测试公开状态包含性能信息"""
        state = self.application.public_state()
        
        self.assertIn("performance", state)
        self.assertIn("tts_cache", state["performance"])
        self.assertIn("metrics", state["performance"])
    
    def test_public_state_has_tools(self):
        """测试公开状态包含工具列表"""
        state = self.application.public_state()
        
        self.assertIn("computer_control", state)
        self.assertIn("tools", state["computer_control"])
        self.assertGreater(len(state["computer_control"]["tools"]), 0)
    
    def test_performance_stats(self):
        """测试性能统计"""
        stats = self.application.get_performance_stats()
        
        self.assertIn("tts_cache", stats)
        self.assertIn("metrics", stats)
    
    def test_clear_cache(self):
        """测试清空缓存"""
        # 添加一些缓存
        get_tts_cache().put("test", "voice", 1.0, b"audio", "audio/wav")
        
        # 清空缓存
        self.application.clear_cache()
        
        stats = get_tts_cache().stats()
        self.assertEqual(stats["entries"], 0)


class TestPerformanceAPI(unittest.TestCase):
    """测试性能监控API"""
    
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.application = EnhancedJarvisApplication(
            SettingsStore(Path(self.temporary.name)), MemorySecretStore()
        )
        self.server = create_enhanced_server("127.0.0.1", 0, self.application)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_address[1]}"
    
    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.temporary.cleanup()
    
    def test_performance_endpoint(self):
        """测试性能监控端点"""
        with request.urlopen(f"{self.base_url}/api/performance", timeout=2) as response:
            payload = json.load(response)
        
        self.assertIn("tts_cache", payload)
        self.assertIn("metrics", payload)
    
    def test_clear_cache_endpoint(self):
        """测试清空缓存端点"""
        # 添加一些缓存
        get_tts_cache().put("test", "voice", 1.0, b"audio", "audio/wav")
        
        with request.urlopen(f"{self.base_url}/api/performance/clear-cache", timeout=2) as response:
            payload = json.load(response)
        
        self.assertIn("message", payload)
        
        # 验证缓存已清空
        stats = get_tts_cache().stats()
        self.assertEqual(stats["entries"], 0)
    
    def test_bootstrap_has_performance(self):
        """测试启动状态包含性能信息"""
        with request.urlopen(f"{self.base_url}/api/bootstrap", timeout=2) as response:
            payload = json.load(response)
        
        self.assertIn("performance", payload)
        self.assertIn("computer_control", payload)
        self.assertIn("tools", payload["computer_control"])


if __name__ == "__main__":
    unittest.main()
