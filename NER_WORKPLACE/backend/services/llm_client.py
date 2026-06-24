from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any

import httpx


@dataclass
class LLMResult:
    ok: bool
    content: str = ""
    latency_ms: int = 0
    error_type: str | None = None
    error_message: str | None = None
    raw: dict[str, Any] | None = None


class RateLimiter:
    def __init__(self, rps: float):
        self.interval = 1.0 / max(rps, 0.01)
        self._lock = asyncio.Lock()
        self._last = 0.0

    async def wait(self) -> None:
        async with self._lock:
            now = time.monotonic()
            sleep_for = self.interval - (now - self._last)
            if sleep_for > 0:
                await asyncio.sleep(sleep_for)
            self._last = time.monotonic()


class LLMClient:
    def __init__(self, settings: dict[str, Any]):
        self.base_url = str(settings.get("base_url") or "").rstrip("/")
        self.api_key = str(settings.get("api_key") or "")
        self.model_name = str(settings.get("model_name") or "")
        self.temperature = float(settings.get("temperature") or 0)
        self.max_tokens = int(settings.get("max_tokens") or 800)
        self.timeout_seconds = int(settings.get("timeout_seconds") or 60)
        self.semaphore = asyncio.Semaphore(int(settings.get("concurrency") or 1))
        self.rate_limiter = RateLimiter(float(settings.get("rps") or 1))

    async def chat(self, messages: list[dict[str, str]], max_tokens: int | None = None) -> LLMResult:
        if not self.base_url or not self.model_name:
            return LLMResult(ok=False, error_type="config", error_message="缺少 base_url 或 model_name")
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        payload = {
            "model": self.model_name,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": max_tokens or self.max_tokens,
        }
        async with self.semaphore:
            await self.rate_limiter.wait()
            start = time.perf_counter()
            for attempt in range(4):
                try:
                    async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                        resp = await client.post(f"{self.base_url}/chat/completions", json=payload, headers=headers)
                    latency_ms = int((time.perf_counter() - start) * 1000)
                    if resp.status_code in {429, 500, 502, 503, 504} and attempt < 3:
                        await asyncio.sleep(2**attempt)
                        continue
                    if resp.status_code == 401:
                        return LLMResult(False, latency_ms=latency_ms, error_type="auth", error_message="鉴权失败")
                    if resp.status_code >= 400:
                        return LLMResult(False, latency_ms=latency_ms, error_type="http", error_message=resp.text[:500])
                    data = resp.json()
                    content = data["choices"][0]["message"]["content"]
                    return LLMResult(True, content=content, latency_ms=latency_ms, raw=data)
                except httpx.TimeoutException:
                    if attempt < 3:
                        await asyncio.sleep(2**attempt)
                        continue
                    return LLMResult(False, error_type="timeout", error_message="请求超时")
                except Exception as exc:
                    return LLMResult(False, error_type="error", error_message=str(exc))
        return LLMResult(False, error_type="unknown", error_message="未知错误")

    async def test(self) -> LLMResult:
        return await self.chat(
            [
                {"role": "system", "content": "只返回 pong。"},
                {"role": "user", "content": "ping"},
            ],
            max_tokens=16,
        )

