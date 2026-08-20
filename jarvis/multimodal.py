"""
多模态输入模块 - v1.1.0
支持图片理解、OCR、视觉分析
参考 Aivy OS 的多模态能力
"""

from __future__ import annotations

import base64
import hashlib
import json
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from io import BytesIO


@dataclass(slots=True)
class ImageInfo:
    """图片信息"""
    path: Optional[str]
    data: bytes
    format: str = "png"  # png, jpg, gif, webp
    width: int = 0
    height: int = 0
    size_bytes: int = 0
    description: str = ""
    
    def to_base64(self) -> str:
        """转为 base64"""
        return base64.b64encode(self.data).decode("utf-8")
    
    def to_data_url(self) -> str:
        """转为 data URL"""
        mime = f"image/{self.format}"
        return f"data:{mime};base64,{self.to_base64()}"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "path": self.path,
            "format": self.format,
            "width": self.width,
            "height": self.height,
            "size_bytes": self.size_bytes,
            "description": self.description,
        }


@dataclass(slots=True)
class OCRResult:
    """OCR 识别结果"""
    text: str
    confidence: float
    language: str = "zh"
    regions: List[Dict[str, Any]] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "text": self.text,
            "confidence": self.confidence,
            "language": self.language,
            "regions": self.regions,
        }


@dataclass(slots=True)
class VisualAnalysis:
    """视觉分析结果"""
    description: str
    objects: List[str] = field(default_factory=list)
    scene: str = ""
    colors: List[str] = field(default_factory=list)
    text_content: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "description": self.description,
            "objects": self.objects,
            "scene": self.scene,
            "colors": self.colors,
            "text_content": self.text_content,
        }


class ImageProcessor:
    """
    图片处理器
    支持基本图片操作和信息提取
    """
    
    def __init__(self):
        self._supported_formats = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}
    
    def load_image(self, path: str) -> Optional[ImageInfo]:
        """
        加载图片文件
        
        Args:
            path: 图片路径
            
        Returns:
            ImageInfo 或 None
        """
        file_path = Path(path)
        
        if not file_path.exists():
            return None
        
        if file_path.suffix.lower() not in self._supported_formats:
            return None
        
        try:
            data = file_path.read_bytes()
            format_ext = file_path.suffix.lower().lstrip(".")
            if format_ext == "jpg":
                format_ext = "jpeg"
            
            return ImageInfo(
                path=str(file_path),
                data=data,
                format=format_ext,
                size_bytes=len(data),
            )
        except Exception as e:
            print(f"[ImageProcessor] Failed to load {path}: {e}")
            return None
    
    def load_from_bytes(self, data: bytes, format: str = "png") -> ImageInfo:
        """从字节加载图片"""
        return ImageInfo(
            path=None,
            data=data,
            format=format,
            size_bytes=len(data),
        )
    
    def get_image_size(self, image: ImageInfo) -> tuple[int, int]:
        """获取图片尺寸"""
        try:
            # 尝试使用 PIL
            from PIL import Image
            img = Image.open(BytesIO(image.data))
            return img.size
        except ImportError:
            pass
        
        # 简单解析 PNG 头
        if image.format == "png" and len(image.data) > 24:
            width = int.from_bytes(image.data[16:20], "big")
            height = int.from_bytes(image.data[20:24], "big")
            return (width, height)
        
        # 简单解析 JPEG 头
        if image.format in ("jpeg", "jpg"):
            # JPEG 解析较复杂，返回默认值
            return (0, 0)
        
        return (0, 0)
    
    def resize_image(self, image: ImageInfo, max_size: int = 1024) -> ImageInfo:
        """调整图片大小"""
        try:
            from PIL import Image
            img = Image.open(BytesIO(image.data))
            
            # 保持宽高比
            ratio = min(max_size / img.width, max_size / img.height)
            if ratio < 1:
                new_size = (int(img.width * ratio), int(img.height * ratio))
                img = img.resize(new_size, Image.Resampling.LANCZOS)
            
            # 转为字节
            buffer = BytesIO()
            img.save(buffer, format=image.format.upper())
            
            return ImageInfo(
                path=image.path,
                data=buffer.getvalue(),
                format=image.format,
                width=img.width,
                height=img.height,
                size_bytes=buffer.tell(),
            )
        except ImportError:
            # 没有 PIL，返回原图
            return image
    
    def image_to_base64(self, image: ImageInfo) -> str:
        """图片转 base64"""
        return image.to_base64()


class OCRService:
    """
    OCR 服务
    支持本地和云端 OCR
    """
    
    def __init__(self, provider: str = "local", api_key: str = ""):
        self._provider = provider
        self._api_key = api_key
        self._local_engine = None
    
    def _init_local_engine(self):
        """初始化本地 OCR 引擎"""
        if self._local_engine is not None:
            return
        
        try:
            import easyocr
            self._local_engine = easyocr.Reader(["ch_sim", "en"], gpu=False)
            print("[OCR] Loaded EasyOCR engine")
        except ImportError:
            print("[OCR] EasyOCR not installed. Using fallback.")
            self._local_engine = "fallback"
    
    def recognize(self, image: ImageInfo, language: str = "zh") -> OCRResult:
        """
        OCR 识别
        
        Args:
            image: 图片信息
            language: 语言
            
        Returns:
            OCRResult
        """
        if self._provider == "local":
            return self._recognize_local(image, language)
        elif self._provider == "baidu":
            return self._recognize_baidu(image, language)
        else:
            return self._recognize_fallback(image, language)
    
    def _recognize_local(self, image: ImageInfo, language: str) -> OCRResult:
        """本地 OCR"""
        self._init_local_engine()
        
        if self._local_engine == "fallback":
            return self._recognize_fallback(image, language)
        
        try:
            import numpy as np
            from PIL import Image
            from io import BytesIO
            
            img = Image.open(BytesIO(image.data))
            img_array = np.array(img)
            
            results = self._local_engine.readtext(img_array)
            
            texts = []
            regions = []
            total_conf = 0
            
            for (bbox, text, conf) in results:
                texts.append(text)
                total_conf += conf
                regions.append({
                    "text": text,
                    "confidence": conf,
                    "bbox": bbox,
                })
            
            avg_conf = total_conf / len(results) if results else 0
            
            return OCRResult(
                text=" ".join(texts),
                confidence=avg_conf,
                language=language,
                regions=regions,
            )
        except Exception as e:
            print(f"[OCR] Local OCR failed: {e}")
            return self._recognize_fallback(image, language)
    
    def _recognize_baidu(self, image: ImageInfo, language: str) -> OCRResult:
        """百度 OCR"""
        if not self._api_key:
            return OCRResult(text="", confidence=0, error="No API key")
        
        # TODO: 实现百度 OCR API
        return self._recognize_fallback(image, language)
    
    def _recognize_fallback(self, image: ImageInfo, language: str) -> OCRResult:
        """回退方案"""
        return OCRResult(
            text="[OCR 功能需要安装 easyocr: pip install easyocr]",
            confidence=0,
            language=language,
        )


class VisionAnalyzer:
    """
    视觉分析器
    使用多模态 AI 模型分析图片
    """
    
    def __init__(self, api_key: str = "", base_url: str = ""):
        self._api_key = api_key
        self._base_url = base_url or "https://api.openai.com/v1"
    
    def analyze(self, image: ImageInfo, prompt: str = "") -> VisualAnalysis:
        """
        分析图片
        
        Args:
            image: 图片信息
            prompt: 分析提示
            
        Returns:
            VisualAnalysis
        """
        if not self._api_key:
            return VisualAnalysis(
                description="[视觉分析需要配置 API Key]",
                metadata={"error": "no_api_key"}
            )
        
        try:
            return self._analyze_openai(image, prompt)
        except Exception as e:
            return VisualAnalysis(
                description=f"[分析失败: {str(e)}]",
                metadata={"error": str(e)}
            )
    
    def _analyze_openai(self, image: ImageInfo, prompt: str) -> VisualAnalysis:
        """使用 OpenAI Vision API"""
        import urllib.request
        
        url = f"{self._base_url}/chat/completions"
        
        # 构建消息
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt or "请描述这张图片的内容，包括主要对象、场景、颜色等。"},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": image.to_data_url()
                        }
                    }
                ]
            }
        ]
        
        payload = {
            "model": "gpt-4o",
            "messages": messages,
            "max_tokens": 500
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
        
        with urllib.request.urlopen(req, timeout=60) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            content = result["choices"][0]["message"]["content"]
            
            return VisualAnalysis(
                description=content,
                metadata={"model": "gpt-4o"}
            )


class MultimodalService:
    """
    多模态服务
    整合图片处理、OCR、视觉分析
    """
    
    def __init__(
        self,
        ocr_provider: str = "local",
        vision_api_key: str = "",
        vision_base_url: str = "",
    ):
        self._image_processor = ImageProcessor()
        self._ocr_service = OCRService(provider=ocr_provider)
        self._vision_analyzer = VisionAnalyzer(api_key=vision_api_key, base_url=vision_base_url)
    
    @property
    def image_processor(self) -> ImageProcessor:
        return self._image_processor
    
    @property
    def ocr(self) -> OCRService:
        return self._ocr_service
    
    @property
    def vision(self) -> VisionAnalyzer:
        return self._vision_analyzer
    
    def process_image(
        self,
        image_path: str,
        do_ocr: bool = True,
        do_analyze: bool = True,
        prompt: str = "",
    ) -> Dict[str, Any]:
        """
        处理图片
        
        Args:
            image_path: 图片路径
            do_ocr: 是否进行 OCR
            do_analyze: 是否进行视觉分析
            prompt: 分析提示
            
        Returns:
            处理结果
        """
        result = {"success": False}
        
        # 加载图片
        image = self._image_processor.load_image(image_path)
        if not image:
            result["error"] = f"无法加载图片: {image_path}"
            return result
        
        # 获取尺寸
        width, height = self._image_processor.get_image_size(image)
        image.width = width
        image.height = height
        
        result["image"] = image.to_dict()
        result["success"] = True
        
        # OCR
        if do_ocr:
            ocr_result = self._ocr_service.recognize(image)
            result["ocr"] = ocr_result.to_dict()
        
        # 视觉分析
        if do_analyze:
            analysis = self._vision_analyzer.analyze(image, prompt)
            result["analysis"] = analysis.to_dict()
        
        return result
    
    def describe_image(self, image_path: str) -> str:
        """获取图片描述"""
        result = self.process_image(image_path, do_ocr=True, do_analyze=True)
        
        if not result.get("success"):
            return result.get("error", "处理失败")
        
        parts = []
        
        # 图片信息
        img_info = result.get("image", {})
        parts.append(f"图片格式: {img_info.get('format', 'unknown')}")
        if img_info.get("width") and img_info.get("height"):
            parts.append(f"尺寸: {img_info['width']}x{img_info['height']}")
        
        # OCR 结果
        ocr = result.get("ocr", {})
        if ocr.get("text"):
            parts.append(f"识别文字: {ocr['text'][:200]}")
        
        # 视觉分析
        analysis = result.get("analysis", {})
        if analysis.get("description"):
            parts.append(f"内容描述: {analysis['description'][:300]}")
        
        return "\n".join(parts)


# 工具定义
MULTIMODAL_TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "analyze_image",
            "description": "分析图片内容。可以识别文字(OCR)、描述图片内容、分析场景。",
            "parameters": {
                "type": "object",
                "properties": {
                    "image_path": {
                        "type": "string",
                        "description": "图片文件路径"
                    },
                    "prompt": {
                        "type": "string",
                        "description": "分析提示 (可选)",
                        "default": ""
                    },
                    "do_ocr": {
                        "type": "boolean",
                        "description": "是否进行文字识别",
                        "default": True
                    }
                },
                "required": ["image_path"]
            }
        }
    }
]


# 全局实例
_multimodal: Optional[MultimodalService] = None
_multimodal_lock = threading.Lock()


def get_multimodal_service(
    ocr_provider: str = "local",
    vision_api_key: str = "",
    vision_base_url: str = "",
) -> MultimodalService:
    """获取全局多模态服务"""
    global _multimodal
    if _multimodal is None:
        with _multimodal_lock:
            if _multimodal is None:
                _multimodal = MultimodalService(ocr_provider, vision_api_key, vision_base_url)
    return _multimodal
