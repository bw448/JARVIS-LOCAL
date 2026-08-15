from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Iterable, Mapping
from urllib import error, request

from .config import Settings


class BrainError(RuntimeError):
    pass


@dataclass(slots=True)
class ChatMessage:
    role: str
    content: str


def normalize_messages(raw: Any) -> list[ChatMessage]:
    if not isinstance(raw, list):
        raise BrainError("消息列表格式无效")
    normalized: list[ChatMessage] = []
    for item in raw[-24:]:
        if not isinstance(item, Mapping):
            continue
        role = str(item.get("role", ""))
        content = str(item.get("content", "")).strip()
        if role not in {"user", "assistant"} or not content:
            continue
        normalized.append(ChatMessage(role=role, content=content[:20_000]))
    if not normalized or normalized[-1].role != "user":
        raise BrainError("请先输入一条消息")
    return normalized


class OpenAICompatibleBrain:
    def complete(
        self,
        settings: Settings,
        messages: Iterable[ChatMessage],
        api_key: str = "",
    ) -> str:
        if settings.brain.provider == "disabled":
            raise BrainError("大脑服务已关闭，请先在设置中配置模型接口")

        endpoint = settings.brain.base_url.rstrip("/") + "/chat/completions"
        payload = {
            "model": settings.brain.model,
            "temperature": settings.brain.temperature,
            "stream": False,
            "messages": [
                {"role": "system", "content": settings.system_prompt()},
                *[
                    {"role": message.role, "content": message.content}
                    for message in messages
                ],
            ],
        }
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        outgoing = request.Request(
            endpoint,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with request.urlopen(outgoing, timeout=settings.brain.timeout_seconds) as response:
                body = response.read(4 * 1024 * 1024)
        except error.HTTPError as exc:
            detail = exc.read(2048).decode("utf-8", errors="replace")
            raise BrainError(f"模型接口返回 HTTP {exc.code}：{detail[:300]}") from exc
        except (error.URLError, TimeoutError, OSError) as exc:
            raise BrainError(
                f"无法连接模型接口 {settings.brain.base_url}。请确认本地 llama-server 或在线接口已启动。"
            ) from exc

        try:
            decoded = json.loads(body)
            content = decoded["choices"][0]["message"]["content"]
        except (json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
            raise BrainError("模型接口返回了无法识别的数据") from exc

        if isinstance(content, list):
            content = "".join(
                str(part.get("text", "")) if isinstance(part, Mapping) else str(part)
                for part in content
            )
        answer = str(content).strip()
        if not answer:
            raise BrainError("模型没有返回文字内容")
        return answer

