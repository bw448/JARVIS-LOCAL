"""
向量嵌入记忆系统 - v0.9.0
使用本地嵌入模型实现语义搜索
参考 Aivy OS 的 nomic-embed-text 集成
"""

from __future__ import annotations

import hashlib
import json
import math
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .memory import MemoryEntry, MemoryStore


@dataclass
class VectorEntry:
    """带向量的记忆条目"""
    memory: MemoryEntry
    embedding: List[float] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "memory": self.memory.to_dict(),
            "embedding": self.embedding[:50] if self.embedding else [],  # 只保存前50维用于调试
        }


class EmbeddingService:
    """
    嵌入服务
    支持本地模型和云端API
    """
    
    def __init__(self, provider: str = "local", model: str = "", api_key: str = "", base_url: str = ""):
        self._provider = provider
        self._model = model
        self._api_key = api_key
        self._base_url = base_url
        self._local_model = None
        self._dimension = 384  # 默认维度
    
    @property
    def dimension(self) -> int:
        return self._dimension
    
    def _load_local_model(self):
        """加载本地嵌入模型"""
        if self._local_model is not None:
            return
        
        try:
            from sentence_transformers import SentenceTransformer
            model_name = self._model or "paraphrase-multilingual-MiniLM-L12-v2"
            self._local_model = SentenceTransformer(model_name)
            self._dimension = self._local_model.get_sentence_embedding_dimension()
            print(f"[Embedding] Loaded local model: {model_name} (dim={self._dimension})")
        except ImportError:
            print("[Embedding] sentence-transformers not installed. Using simple fallback.")
            self._local_model = "fallback"
    
    def embed(self, text: str) -> List[float]:
        """
        生成文本嵌入向量
        
        Args:
            text: 输入文本
            
        Returns:
            嵌入向量
        """
        if self._provider == "local":
            return self._embed_local(text)
        elif self._provider == "openai":
            return self._embed_openai(text)
        else:
            return self._embed_simple(text)
    
    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """批量生成嵌入向量"""
        if self._provider == "local" and self._local_model and self._local_model != "fallback":
            try:
                return self._local_model.encode(texts).tolist()
            except Exception:
                pass
        
        return [self.embed(text) for text in texts]
    
    def _embed_local(self, text: str) -> List[float]:
        """使用本地模型生成嵌入"""
        self._load_local_model()
        
        if self._local_model == "fallback":
            return self._embed_simple(text)
        
        try:
            return self._local_model.encode(text).tolist()
        except Exception as e:
            print(f"[Embedding] Local embedding failed: {e}")
            return self._embed_simple(text)
    
    def _embed_openai(self, text: str) -> List[float]:
        """使用 OpenAI API 生成嵌入"""
        import urllib.request
        
        url = (self._base_url or "https://api.openai.com/v1") + "/embeddings"
        
        payload = {
            "model": self._model or "text-embedding-ada-002",
            "input": text
        }
        
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST"
        )
        
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                embedding = result["data"][0]["embedding"]
                self._dimension = len(embedding)
                return embedding
        except Exception as e:
            print(f"[Embedding] OpenAI embedding failed: {e}")
            return self._embed_simple(text)
    
    def _embed_simple(self, text: str) -> List[float]:
        """
        简单的本地嵌入 (基于字符哈希)
        用于在没有模型时提供基本功能
        """
        # 使用多个哈希函数生成伪嵌入
        dim = 128
        embedding = [0.0] * dim
        
        # 字符级特征
        for i, char in enumerate(text[:1000]):
            idx = ord(char) % dim
            embedding[idx] += 1.0
        
        # 词级特征
        words = text.split()
        for i, word in enumerate(words[:100]):
            hash_val = int(hashlib.md5(word.encode()).hexdigest(), 16)
            idx = hash_val % dim
            embedding[idx] += 0.5
        
        # 归一化
        norm = math.sqrt(sum(x * x for x in embedding))
        if norm > 0:
            embedding = [x / norm for x in embedding]
        
        self._dimension = dim
        return embedding


def cosine_similarity(a: List[float], b: List[float]) -> float:
    """计算余弦相似度"""
    if len(a) != len(b):
        min_len = min(len(a), len(b))
        a = a[:min_len]
        b = b[:min_len]
    
    dot_product = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    
    if norm_a == 0 or norm_b == 0:
        return 0.0
    
    return dot_product / (norm_a * norm_b)


class VectorMemoryStore:
    """
    向量记忆存储
    结合关键词和语义搜索
    """
    
    def __init__(
        self,
        base_memory: MemoryStore,
        embedding_service: Optional[EmbeddingService] = None,
        data_dir: Optional[Path] = None,
    ):
        self._base = base_memory
        self._embedding = embedding_service or EmbeddingService()
        self._data_dir = data_dir or base_memory._data_dir
        self._lock = threading.Lock()
        
        # 向量索引
        self._vectors: Dict[str, VectorEntry] = {}
        
        # 加载已有向量
        self._load_vectors()
    
    def _load_vectors(self):
        """加载向量索引"""
        vector_file = self._data_dir / "vector_index.json"
        if not vector_file.exists():
            return
        
        try:
            data = json.loads(vector_file.read_text(encoding="utf-8"))
            for entry_id, entry_data in data.items():
                memory = MemoryEntry.from_dict(entry_data.get("memory", {}))
                embedding = entry_data.get("embedding", [])
                self._vectors[entry_id] = VectorEntry(memory=memory, embedding=embedding)
            print(f"[VectorMemory] Loaded {len(self._vectors)} vectors")
        except Exception as e:
            print(f"[VectorMemory] Failed to load vectors: {e}")
    
    def _save_vectors(self):
        """保存向量索引"""
        vector_file = self._data_dir / "vector_index.json"
        
        # 只保存长期记忆的向量
        data = {}
        for entry_id, entry in self._vectors.items():
            if entry.memory.category != "conversation":
                data[entry_id] = entry.to_dict()
        
        try:
            vector_file.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
        except Exception as e:
            print(f"[VectorMemory] Failed to save vectors: {e}")
    
    def remember(self, content: str, category: str = "fact", importance: float = 0.6, metadata: Optional[Dict] = None) -> str:
        """
        存储记忆并生成向量
        """
        # 存储到基础记忆
        entry_id = self._base.remember(content, category=category, importance=importance, metadata=metadata)
        
        # 生成向量
        embedding = self._embedding.embed(content)
        
        # 获取记忆条目
        memory_entry = self._base._long_term.get(entry_id)
        if memory_entry:
            with self._lock:
                self._vectors[entry_id] = VectorEntry(
                    memory=memory_entry,
                    embedding=embedding
                )
                self._save_vectors()
        
        return entry_id
    
    def recall(self, query: str, limit: int = 5, use_vector: bool = True) -> List[MemoryEntry]:
        """
        智能召回 (结合关键词和语义搜索)
        """
        results = []
        
        # 1. 关键词搜索
        keyword_results = self._base.recall(query, limit=limit * 2)
        results.extend(keyword_results)
        
        # 2. 向量搜索
        if use_vector and self._vectors:
            query_embedding = self._embedding.embed(query)
            
            # 计算相似度
            scored: List[Tuple[float, MemoryEntry]] = []
            for entry_id, vector_entry in self._vectors.items():
                if vector_entry.embedding:
                    similarity = cosine_similarity(query_embedding, vector_entry.embedding)
                    if similarity > 0.3:  # 阈值
                        scored.append((similarity, vector_entry.memory))
            
            # 按相似度排序
            scored.sort(key=lambda x: x[0], reverse=True)
            
            # 添加到结果 (去重)
            existing_ids = {r.id for r in results}
            for sim, memory in scored[:limit]:
                if memory.id not in existing_ids:
                    results.append(memory)
                    existing_ids.add(memory.id)
        
        # 按重要性和时间排序
        results.sort(key=lambda x: (x.importance, x.timestamp), reverse=True)
        
        return results[:limit]
    
    def semantic_search(self, query: str, limit: int = 10, min_similarity: float = 0.5) -> List[Tuple[float, MemoryEntry]]:
        """
        纯语义搜索
        返回 (相似度, 记忆条目) 的列表
        """
        if not self._vectors:
            return []
        
        query_embedding = self._embedding.embed(query)
        
        scored: List[Tuple[float, MemoryEntry]] = []
        for entry_id, vector_entry in self._vectors.items():
            if vector_entry.embedding:
                similarity = cosine_similarity(query_embedding, vector_entry.embedding)
                if similarity >= min_similarity:
                    scored.append((similarity, vector_entry.memory))
        
        scored.sort(key=lambda x: x[0], reverse=True)
        return scored[:limit]
    
    def rebuild_index(self):
        """重建向量索引"""
        with self._lock:
            self._vectors.clear()
            
            # 为所有长期记忆生成向量
            for entry_id, memory in self._base._long_term.items():
                embedding = self._embedding.embed(memory.content)
                self._vectors[entry_id] = VectorEntry(
                    memory=memory,
                    embedding=embedding
                )
            
            self._save_vectors()
            print(f"[VectorMemory] Rebuilt index with {len(self._vectors)} entries")
    
    def get_stats(self) -> Dict[str, Any]:
        """获取向量统计"""
        base_stats = self._base.get_memory_stats()
        base_stats["vector_count"] = len(self._vectors)
        base_stats["embedding_dimension"] = self._embedding.dimension
        return base_stats
    
    # 代理方法 (delegate to base memory)
    def set_core(self, key: str, content: str, importance: float = 0.8):
        return self._base.set_core(key, content, importance)
    
    def get_core(self, key: str) -> Optional[str]:
        return self._base.get_core(key)
    
    def get_all_core(self) -> Dict[str, str]:
        return self._base.get_all_core()
    
    def add_conversation(self, role: str, content: str, metadata: Optional[Dict] = None):
        return self._base.add_conversation(role, content, metadata)
    
    def get_recent_conversation(self, count: int = 10) -> List[Dict[str, str]]:
        return self._base.get_recent_conversation(count)
    
    def clear_conversation(self):
        return self._base.clear_conversation()
    
    def build_context_prompt(self) -> str:
        return self._base.build_context_prompt()


# 全局实例
_vector_store: Optional[VectorMemoryStore] = None
_vector_lock = threading.Lock()


def get_vector_memory(
    base_memory: Optional[MemoryStore] = None,
    embedding_provider: str = "local",
    data_dir: Optional[Path] = None,
) -> VectorMemoryStore:
    """获取全局向量记忆实例"""
    global _vector_store
    if _vector_store is None:
        with _vector_lock:
            if _vector_store is None:
                from .memory import get_memory_store
                base = base_memory or get_memory_store(data_dir)
                embedding = EmbeddingService(provider=embedding_provider)
                _vector_store = VectorMemoryStore(base, embedding, data_dir)
    return _vector_store
