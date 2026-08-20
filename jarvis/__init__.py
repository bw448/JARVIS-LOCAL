"""
JARVIS LOCAL - 私人语音助手
版本 1.1.0 - P2 完成
"""

__version__ = "1.1.0"
__app_name__ = "JARVIS LOCAL"

# 基础模块
from .memory import MemoryStore, get_memory_store
from .skills import SkillManager, get_skill_manager
from .web_search import WebSearchService, get_search_service
from .document import DocumentProcessor, get_document_processor
from .app_integration import EnhancedContextBuilder, get_context_builder

# P0 模块
from .voice_enhanced import EnhancedVoiceSystem, VoiceConfig, get_voice_system
from .memory_vector import VectorMemoryStore, EmbeddingService, get_vector_memory
from .subagent import SubAgentManager, SubAgent, get_subagent_manager

# P1 模块
from .voice_stream import RealtimeVoiceStream, WebSocketVoiceHandler, get_voice_stream
from .web_crawler import WebCrawler, KnowledgeBase, get_crawler, get_knowledge_base

# P2 模块
from .multimodal import MultimodalService, ImageProcessor, OCRService, get_multimodal_service
from .canvas import CanvasWorkbench, CanvasType, get_canvas_workbench
from .messaging import MessagingManager, get_messaging_manager
from .llm_local import LocalLLMService, LLMConfig, get_llm_service
