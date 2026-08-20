"""
即时通讯集成 - v1.1.0
支持微信、飞书、企业微信机器人
参考 Aivy OS 的微信集成
"""

from __future__ import annotations

import json
import hashlib
import hmac
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set
from urllib import error, request
from urllib.parse import urljoin


class MessageType(Enum):
    """消息类型"""
    TEXT = "text"
    IMAGE = "image"
    FILE = "file"
    LINK = "link"
    CARD = "card"


@dataclass(slots=True)
class Message:
    """消息"""
    msg_id: str
    platform: str  # wechat, feishu, wecom
    chat_id: str
    sender_id: str
    sender_name: str
    type: MessageType
    content: str
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "msg_id": self.msg_id,
            "platform": self.platform,
            "chat_id": self.chat_id,
            "sender_id": self.sender_id,
            "sender_name": self.sender_name,
            "type": self.type.value,
            "content": self.content,
            "timestamp": self.timestamp,
        }


@dataclass(slots=True)
class ChatInfo:
    """聊天信息"""
    chat_id: str
    platform: str
    name: str
    type: str = "private"  # private, group
    members: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


class MessageHandler(ABC):
    """消息处理器基类"""
    
    @abstractmethod
    def on_message(self, message: Message) -> Optional[str]:
        """处理消息，返回回复内容"""
        pass
    
    @abstractmethod
    def on_mention(self, message: Message) -> Optional[str]:
        """处理@消息"""
        pass


class DefaultMessageHandler(MessageHandler):
    """默认消息处理器"""
    
    def __init__(self, callback: Optional[Callable[[Message], Optional[str]]] = None):
        self._callback = callback
    
    def on_message(self, message: Message) -> Optional[str]:
        if self._callback:
            return self._callback(message)
        return None
    
    def on_mention(self, message: Message) -> Optional[str]:
        if self._callback:
            return self._callback(message)
        return f"收到消息: {message.content[:50]}"


class MessagingPlatform(ABC):
    """即时通讯平台基类"""
    
    @property
    @abstractmethod
    def platform_name(self) -> str:
        """平台名称"""
        pass
    
    @property
    @abstractmethod
    def is_connected(self) -> bool:
        """是否已连接"""
        pass
    
    @abstractmethod
    def connect(self) -> bool:
        """连接平台"""
        pass
    
    @abstractmethod
    def disconnect(self):
        """断开连接"""
        pass
    
    @abstractmethod
    def send_message(self, chat_id: str, content: str, type: MessageType = MessageType.TEXT) -> bool:
        """发送消息"""
        pass
    
    @abstractmethod
    def get_chats(self) -> List[ChatInfo]:
        """获取聊天列表"""
        pass


class WeChatBot(MessagingPlatform):
    """
    微信机器人
    通过 WebSocket 或 HTTP 接口连接
    """
    
    def __init__(self, config: Dict[str, Any]):
        self._config = config
        self._mode = config.get("mode", "websocket")  # websocket, http
        self._corp_id = config.get("corp_id", "")
        self._bot_id = config.get("bot_id", "")
        self._bot_secret = config.get("bot_secret", "")
        self._master_userid = config.get("master_userid", "")
        
        self._is_connected = False
        self._handler: Optional[MessageHandler] = None
        self._ws = None
        self._lock = threading.Lock()
    
    @property
    def platform_name(self) -> str:
        return "wechat"
    
    @property
    def is_connected(self) -> bool:
        return self._is_connected
    
    def set_handler(self, handler: MessageHandler):
        """设置消息处理器"""
        self._handler = handler
    
    def connect(self) -> bool:
        """连接微信"""
        if self._mode == "websocket":
            return self._connect_websocket()
        else:
            return self._connect_http()
    
    def _connect_websocket(self) -> bool:
        """WebSocket 连接"""
        try:
            import websocket
            
            ws_url = self._config.get("ws_url", "ws://localhost:8080/ws")
            
            def on_message(ws, message):
                self._handle_raw_message(message)
            
            def on_error(ws, error):
                print(f"[WeChat] WebSocket error: {error}")
            
            def on_close(ws, close_status_code, close_msg):
                print("[WeChat] WebSocket closed")
                self._is_connected = False
            
            def on_open(ws):
                print("[WeChat] WebSocket connected")
                self._is_connected = True
            
            self._ws = websocket.WebSocketApp(
                ws_url,
                on_message=on_message,
                on_error=on_error,
                on_close=on_close,
                on_open=on_open,
            )
            
            # 在后台线程运行
            thread = threading.Thread(target=self._ws.run_forever, daemon=True)
            thread.start()
            
            return True
        except ImportError:
            print("[WeChat] websocket-client not installed")
            return False
        except Exception as e:
            print(f"[WeChat] Connection failed: {e}")
            return False
    
    def _connect_http(self) -> bool:
        """HTTP 轮询连接"""
        # TODO: 实现 HTTP 轮询
        print("[WeChat] HTTP mode not implemented")
        return False
    
    def disconnect(self):
        """断开连接"""
        if self._ws:
            self._ws.close()
        self._is_connected = False
    
    def _handle_raw_message(self, raw: str):
        """处理原始消息"""
        try:
            data = json.loads(raw)
            
            message = Message(
                msg_id=data.get("msg_id", ""),
                platform="wechat",
                chat_id=data.get("chat_id", ""),
                sender_id=data.get("sender_id", ""),
                sender_name=data.get("sender_name", ""),
                type=MessageType(data.get("type", "text")),
                content=data.get("content", ""),
                timestamp=data.get("timestamp", time.time()),
            )
            
            if self._handler:
                # 检查是否@机器人
                is_mention = f"@{self._bot_id}" in message.content
                
                if is_mention:
                    reply = self._handler.on_mention(message)
                else:
                    reply = self._handler.on_message(message)
                
                if reply:
                    self.send_message(message.chat_id, reply)
        except Exception as e:
            print(f"[WeChat] Failed to handle message: {e}")
    
    def send_message(self, chat_id: str, content: str, type: MessageType = MessageType.TEXT) -> bool:
        """发送消息"""
        if not self._is_connected:
            return False
        
        try:
            data = {
                "action": "send",
                "chat_id": chat_id,
                "content": content,
                "type": type.value,
            }
            
            if self._ws:
                self._ws.send(json.dumps(data))
                return True
            return False
        except Exception as e:
            print(f"[WeChat] Send failed: {e}")
            return False
    
    def get_chats(self) -> List[ChatInfo]:
        """获取聊天列表"""
        # TODO: 实现获取聊天列表
        return []


class FeishuBot(MessagingPlatform):
    """
    飞书机器人
    通过 Webhook 或 API 连接
    """
    
    def __init__(self, config: Dict[str, Any]):
        self._config = config
        self._app_id = config.get("app_id", "")
        self._app_secret = config.get("app_secret", "")
        self._webhook_url = config.get("webhook_url", "")
        self._verification_token = config.get("verification_token", "")
        
        self._is_connected = False
        self._handler: Optional[MessageHandler] = None
        self._access_token = ""
        self._token_expires = 0.0
        self._lock = threading.Lock()
    
    @property
    def platform_name(self) -> str:
        return "feishu"
    
    @property
    def is_connected(self) -> bool:
        return self._is_connected
    
    def set_handler(self, handler: MessageHandler):
        """设置消息处理器"""
        self._handler = handler
    
    def connect(self) -> bool:
        """连接飞书"""
        if self._webhook_url:
            # Webhook 模式
            self._is_connected = True
            return True
        
        if self._app_id and self._app_secret:
            # API 模式
            return self._get_access_token()
        
        return False
    
    def _get_access_token(self) -> bool:
        """获取访问令牌"""
        try:
            url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
            
            payload = {
                "app_id": self._app_id,
                "app_secret": self._app_secret,
            }
            
            req = request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            
            with request.urlopen(req, timeout=10) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                
                if result.get("code") == 0:
                    self._access_token = result.get("tenant_access_token", "")
                    self._token_expires = time.time() + result.get("expire", 7200)
                    self._is_connected = True
                    return True
                else:
                    print(f"[Feishu] Token error: {result.get('msg')}")
                    return False
        except Exception as e:
            print(f"[Feishu] Connection failed: {e}")
            return False
    
    def disconnect(self):
        """断开连接"""
        self._is_connected = False
        self._access_token = ""
    
    def send_message(self, chat_id: str, content: str, type: MessageType = MessageType.TEXT) -> bool:
        """发送消息"""
        if self._webhook_url:
            return self._send_webhook(content)
        
        if not self._is_connected or not self._access_token:
            return False
        
        try:
            url = f"https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=chat_id"
            
            # 构建消息体
            if type == MessageType.TEXT:
                msg_content = json.dumps({"text": content})
            else:
                msg_content = json.dumps({"text": content})
            
            payload = {
                "receive_id": chat_id,
                "msg_type": type.value if type == MessageType.TEXT else "text",
                "content": msg_content,
            }
            
            headers = {
                "Authorization": f"Bearer {self._access_token}",
                "Content-Type": "application/json",
            }
            
            req = request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers=headers,
                method="POST"
            )
            
            with request.urlopen(req, timeout=10) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                return result.get("code") == 0
        except Exception as e:
            print(f"[Feishu] Send failed: {e}")
            return False
    
    def _send_webhook(self, content: str) -> bool:
        """通过 Webhook 发送"""
        try:
            payload = {
                "msg_type": "text",
                "content": {"text": content}
            }
            
            req = request.Request(
                self._webhook_url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            
            with request.urlopen(req, timeout=10) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                return result.get("code") == 0 or result.get("StatusCode") == 0
        except Exception as e:
            print(f"[Feishu] Webhook failed: {e}")
            return False
    
    def get_chats(self) -> List[ChatInfo]:
        """获取聊天列表"""
        # TODO: 实现获取聊天列表
        return []


class MessagingManager:
    """
    即时通讯管理器
    管理多个平台的连接
    """
    
    def __init__(self):
        self._platforms: Dict[str, MessagingPlatform] = {}
        self._handler: Optional[MessageHandler] = None
        self._lock = threading.RLock()
    
    def set_handler(self, handler: MessageHandler):
        """设置全局消息处理器"""
        self._handler = handler
        
        for platform in self._platforms.values():
            if isinstance(platform, WeChatBot):
                platform.set_handler(handler)
            elif isinstance(platform, FeishuBot):
                platform.set_handler(handler)
    
    def add_wechat(self, config: Dict[str, Any]) -> bool:
        """添加微信平台"""
        bot = WeChatBot(config)
        bot.set_handler(self._handler or DefaultMessageHandler())
        
        with self._lock:
            self._platforms["wechat"] = bot
        
        return bot.connect()
    
    def add_feishu(self, config: Dict[str, Any]) -> bool:
        """添加飞书平台"""
        bot = FeishuBot(config)
        bot.set_handler(self._handler or DefaultMessageHandler())
        
        with self._lock:
            self._platforms["feishu"] = bot
        
        return bot.connect()
    
    def get_platform(self, name: str) -> Optional[MessagingPlatform]:
        """获取平台"""
        return self._platforms.get(name)
    
    def send_message(self, platform: str, chat_id: str, content: str) -> bool:
        """发送消息"""
        with self._lock:
            p = self._platforms.get(platform)
            if p:
                return p.send_message(chat_id, content)
        return False
    
    def broadcast(self, content: str):
        """广播消息"""
        with self._lock:
            for platform in self._platforms.values():
                if platform.is_connected:
                    # 发送到所有聊天
                    for chat in platform.get_chats():
                        platform.send_message(chat.chat_id, content)
    
    def get_status(self) -> Dict[str, Any]:
        """获取状态"""
        with self._lock:
            return {
                name: {
                    "connected": p.is_connected,
                    "platform": p.platform_name,
                }
                for name, p in self._platforms.items()
            }


# 全局实例
_manager: Optional[MessagingManager] = None
_manager_lock = threading.Lock()


def get_messaging_manager() -> MessagingManager:
    """获取全局即时通讯管理器"""
    global _manager
    if _manager is None:
        with _manager_lock:
            if _manager is None:
                _manager = MessagingManager()
    return _manager


# 工具定义
MESSAGING_TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "send_message",
            "description": "通过即时通讯发送消息。支持微信、飞书。",
            "parameters": {
                "type": "object",
                "properties": {
                    "platform": {
                        "type": "string",
                        "description": "平台: wechat, feishu"
                    },
                    "chat_id": {
                        "type": "string",
                        "description": "聊天 ID"
                    },
                    "content": {
                        "type": "string",
                        "description": "消息内容"
                    }
                },
                "required": ["platform", "chat_id", "content"]
            }
        }
    }
]
