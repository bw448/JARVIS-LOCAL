from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Iterable, Iterator, Mapping
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
    @staticmethod
    def _payload(
        settings: Settings,
        messages: Iterable[ChatMessage],
        *,
        stream: bool,
        voice_context: str = "",
        tools: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        system_prompt = settings.system_prompt()
        if voice_context:
            system_prompt += f"\n{voice_context}"
        payload: dict[str, Any] = {
            "model": settings.brain.model,
            "temperature": settings.brain.temperature,
            "stream": stream,
            "messages": [
                {"role": "system", "content": system_prompt},
                *[
                    {"role": message.role, "content": message.content}
                    for message in messages
                ],
            ],
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        return payload

    @staticmethod
    def _request(
        settings: Settings,
        payload: Mapping[str, Any],
        api_key: str,
    ) -> request.Request:
        endpoint = settings.brain.base_url.rstrip("/") + "/chat/completions"
        accept = "text/event-stream" if payload.get("stream") else "application/json"
        headers = {"Content-Type": "application/json", "Accept": accept}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        return request.Request(
            endpoint,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers=headers,
            method="POST",
        )

    @staticmethod
    def _content(decoded: Mapping[str, Any]) -> str:
        try:
            content = decoded["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise BrainError("模型接口返回了无法识别的数据") from exc
        if isinstance(content, list):
            content = "".join(
                str(part.get("text", "")) if isinstance(part, Mapping) else str(part)
                for part in content
            )
        return str(content).strip()

    def complete(
        self,
        settings: Settings,
        messages: Iterable[ChatMessage],
        api_key: str = "",
        voice_context: str = "",
    ) -> str:
        if settings.brain.provider == "disabled":
            raise BrainError("大脑服务已关闭，请先在设置中配置模型接口")

        payload = self._payload(
            settings, messages, stream=False, voice_context=voice_context
        )
        outgoing = self._request(settings, payload, api_key)
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
        except json.JSONDecodeError as exc:
            raise BrainError("模型接口返回了无法识别的数据") from exc
        answer = self._content(decoded)
        if not answer:
            raise BrainError("模型没有返回文字内容")
        return answer

    def stream(
        self,
        settings: Settings,
        messages: Iterable[ChatMessage],
        api_key: str = "",
        voice_context: str = "",
    ) -> Iterator[str]:
        """Yield OpenAI-compatible text deltas without buffering the whole answer."""

        for event in self.stream_events(
            settings,
            messages,
            api_key=api_key,
            voice_context=voice_context,
        ):
            if event["type"] == "text":
                yield str(event["text"])

    def stream_events(
        self,
        settings: Settings,
        messages: Iterable[ChatMessage],
        api_key: str = "",
        voice_context: str = "",
        tools: list[dict[str, Any]] | None = None,
    ) -> Iterator[dict[str, Any]]:
        """Yield text and fully assembled OpenAI-compatible tool calls."""

        if settings.brain.provider == "disabled":
            raise BrainError("大脑服务已关闭，请先在设置中配置模型接口")

        payload = self._payload(
            settings,
            messages,
            stream=True,
            voice_context=voice_context,
            tools=tools,
        )
        outgoing = self._request(settings, payload, api_key)
        emitted = False
        tool_calls: dict[int, dict[str, str]] = {}
        try:
            with request.urlopen(
                outgoing, timeout=settings.brain.timeout_seconds
            ) as response:
                for raw_line in response:
                    if len(raw_line) > 1024 * 1024:
                        raise BrainError("模型流返回的单条数据过大")
                    line = raw_line.decode("utf-8", errors="replace").strip()
                    if not line or line.startswith(":"):
                        continue
                    if line.startswith("data:"):
                        line = line[5:].strip()
                    if line == "[DONE]":
                        break
                    try:
                        decoded = json.loads(line)
                    except json.JSONDecodeError as exc:
                        raise BrainError("模型流返回了无法识别的数据") from exc

                    choices = decoded.get("choices") if isinstance(decoded, Mapping) else None
                    if not isinstance(choices, list) or not choices:
                        continue
                    choice = choices[0]
                    if not isinstance(choice, Mapping):
                        continue
                    delta = choice.get("delta")
                    content: Any = ""
                    event_source: Mapping[str, Any] | None = None
                    if isinstance(delta, Mapping):
                        event_source = delta
                        content = delta.get("content", "")
                    elif isinstance(choice.get("message"), Mapping):
                        # Some compatible servers ignore stream=true and return one JSON object.
                        event_source = choice["message"]
                        content = event_source.get("content", "")
                    if isinstance(content, list):
                        content = "".join(
                            str(part.get("text", ""))
                            if isinstance(part, Mapping)
                            else str(part)
                            for part in content
                        )
                    text = str(content or "")
                    if text:
                        emitted = True
                        yield {"type": "text", "text": text}

                    raw_tool_calls = (
                        event_source.get("tool_calls") if event_source is not None else None
                    )
                    if isinstance(raw_tool_calls, list):
                        for fallback_index, raw_call in enumerate(raw_tool_calls):
                            if not isinstance(raw_call, Mapping):
                                continue
                            try:
                                index = int(raw_call.get("index", fallback_index))
                            except (TypeError, ValueError):
                                index = fallback_index
                            if index < 0 or index >= 3:
                                raise BrainError("模型一次请求了过多电脑操作")
                            call = tool_calls.setdefault(
                                index, {"id": "", "name": "", "arguments": ""}
                            )
                            if raw_call.get("id"):
                                call["id"] += str(raw_call["id"])
                            function = raw_call.get("function")
                            if isinstance(function, Mapping):
                                if function.get("name"):
                                    call["name"] += str(function["name"])
                                if function.get("arguments"):
                                    call["arguments"] += str(function["arguments"])
                                    if len(call["arguments"]) > 16_384:
                                        raise BrainError("模型返回的电脑操作参数过大")
        except error.HTTPError as exc:
            detail = exc.read(2048).decode("utf-8", errors="replace")
            raise BrainError(f"模型接口返回 HTTP {exc.code}：{detail[:300]}") from exc
        except (error.URLError, TimeoutError, OSError) as exc:
            raise BrainError(
                f"无法连接模型接口 {settings.brain.base_url}。请确认本地 llama-server 或在线接口已启动。"
            ) from exc

        for index in sorted(tool_calls):
            call = tool_calls[index]
            try:
                arguments = json.loads(call["arguments"] or "{}")
            except json.JSONDecodeError as exc:
                raise BrainError("模型返回的电脑操作参数不是有效 JSON") from exc
            if not isinstance(arguments, Mapping) or not call["name"]:
                raise BrainError("模型返回了无效的电脑操作")
            emitted = True
            yield {
                "type": "tool_call",
                "id": call["id"],
                "name": call["name"],
                "arguments": dict(arguments),
            }

        if not emitted:
            raise BrainError("模型流没有返回文字内容")
