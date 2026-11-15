# -*- coding: utf-8 -*-
"""OpenAI 兼容的 LLM 客户端：带磁盘缓存、重试与限流。

设计要点（论文里要写）：
1. **全部调用落缓存** data/cache/*.jsonl，key = sha1(model + prompt)。
   答辩/复现时即使模型下线，也能用缓存跑出同一份结果。
2. 只在环境变量里读 api_key，绝不写进仓库（提交前自查）。
3. 不可用时抛 LLMUnavailable，由上层自动降级到纯规则——保证管道永远能跑通。
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional

import requests

from io_utils import ROOT, append_jsonl, get_secret, read_jsonl


class LLMUnavailable(RuntimeError):
    pass


class LLMClient:
    def __init__(self, cfg: Dict[str, Any]):
        self.cfg = cfg["llm"]
        self.cache_path = Path(cfg["paths"]["cache"]) / "llm_calls.jsonl"
        self._cache: Dict[str, str] = {}
        self._lock = threading.Lock()
        self._load_cache()

        # 先看环境变量，再看项目根目录的 .env（两种都支持，谁先有值用谁）
        self.api_key, self.key_source = get_secret(
            self.cfg.get("api_key_env", ""), Path(cfg["_root"]) / ".env")

        # 无 key 时是否允许只靠缓存工作（命中即用，未命中才降级到规则）。
        # 这是「零配置演示」的关键：把缓存随程序发布，用户不填 key 也能复现结果。
        # 强制离线（--offline / LLM_OFFLINE=1）：只用缓存，绝不发起网络请求，
        # 保证评委重跑时结果与提交时完全一致。
        import os
        # 允许用环境变量临时覆盖（访客自带 Key 时由界面注入，不写入 .env）
        self.base_url = os.environ.get("LLM_BASE_URL") or self.cfg.get("base_url", "")
        self.model = os.environ.get("LLM_MODEL") or self.cfg.get("model", "")
        self.force_offline = bool(os.environ.get("LLM_OFFLINE")) or bool(self.cfg.get("force_offline"))
        self.cache_only = ((bool(self.cfg.get("cache_only_when_no_key", True)) and not self.api_key)
                           or self.force_offline)
        self.enabled = bool(self.cfg.get("use_llm", True)) and (
            bool(self.api_key) or (self.cache_only and bool(self._cache)))

    # ---------------- cache ----------------
    def _load_cache(self) -> None:
        for row in read_jsonl(self.cache_path):
            self._cache[row["key"]] = row["response"]

    def _key(self, prompt: str) -> str:
        raw = f"{self.model}||{self.cfg.get('temperature', 0)}||{prompt}"
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()

    def cache_size(self) -> int:
        return len(self._cache)

    # ---------------- call ----------------
    def chat(self, prompt: str, system: Optional[str] = None,
             json_mode: bool = True, retries: int = 3) -> str:
        if not self.enabled:
            raise LLMUnavailable("LLM 未启用（缺少 api_key 或 config.llm.use_llm=false）")

        key = self._key((system or "") + "\n" + prompt)
        with self._lock:
            if key in self._cache:
                return self._cache[key]

        # 没 key：命中缓存就返回过了，走到这里说明未命中 → 降级
        if not self.api_key:
            raise LLMUnavailable("未配置 API Key，且该请求不在预置缓存中")

        url = self.base_url.rstrip("/") + "/chat/completions"
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": self.cfg.get("temperature", 0.0),
            "max_tokens": self.cfg.get("max_tokens", 800),
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        last_err: Optional[Exception] = None
        for attempt in range(retries):
            try:
                resp = requests.post(
                    url,
                    headers={"Authorization": f"Bearer {self.api_key}",
                             "Content-Type": "application/json"},
                    json=payload,
                    timeout=90,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    content = data["choices"][0]["message"]["content"]
                    self._store(key, content)
                    return content
                if resp.status_code in (429, 500, 502, 503, 504):
                    raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:200]}")
                raise LLMUnavailable(f"HTTP {resp.status_code}: {resp.text[:300]}")
            except LLMUnavailable:
                raise
            except Exception as exc:  # 网络/限流：指数退避
                last_err = exc
                time.sleep(1.5 ** attempt)

        raise LLMUnavailable(f"LLM 调用失败（重试 {retries} 次）：{last_err}")

    def chat_json(self, prompt: str, system: Optional[str] = None) -> Dict[str, Any]:
        text = self.chat(prompt, system=system, json_mode=True)
        return parse_json_loose(text)

    def _store(self, key: str, response: str) -> None:
        with self._lock:
            self._cache[key] = response
        append_jsonl(self.cache_path, {"key": key, "response": response,
                                       "model": self.model,
                                       "ts": time.strftime("%Y-%m-%dT%H:%M:%S")})


def parse_json_loose(text: str) -> Dict[str, Any]:
    """兼容模型输出带 ```json 包裹或前后有废话的情况。"""
    text = (text or "").strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                pass
    return {}
