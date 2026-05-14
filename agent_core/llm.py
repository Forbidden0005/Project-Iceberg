"""
Pluggable LLM providers with auto-detection.

Each provider implements:
    chat(messages, **kwargs) -> str      # messages = [{"role":..., "content":...}]
    complete(prompt, **kwargs) -> str    # convenience for single-turn

Auto-detect order: LM Studio -> Ollama -> Anthropic.
First one that answers its health endpoint within a short timeout wins.

Override via config.json or env vars:
  AI_ASSISTANT_PROVIDER=lmstudio|ollama|anthropic
"""

import json
import os
from abc import ABC, abstractmethod
from typing import Optional

from agent_core.constants import (LLM_CLOUD_REQUEST_TIMEOUT_SECONDS,
                                  LLM_LOCAL_REQUEST_TIMEOUT_SECONDS,
                                  LLM_PROBE_TIMEOUT_SECONDS)

try:
    import requests
except ImportError:
    requests = None


# ------------------------------------------------------------------
# Base
# ------------------------------------------------------------------


class LLMProvider(ABC):
    name: str = "base"

    @abstractmethod
    def chat(self, messages: list[dict[str, str]], **kwargs) -> str: ...

    def chat_stream(self, messages: list[dict[str, str]], **kwargs):
        """Yield text chunks as they arrive.  Default: yield the full response as one chunk.

        Providers that support native streaming override this to yield individual
        tokens so the web UI can render them incrementally.
        """
        yield self.chat(messages, **kwargs)

    def complete(self, prompt: str, system: Optional[str] = None, **kwargs) -> str:
        msgs: list[dict[str, str]] = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.append({"role": "user", "content": prompt})
        return self.chat(msgs, **kwargs)

    @staticmethod
    @abstractmethod
    def is_reachable(**kwargs) -> bool: ...


# ------------------------------------------------------------------
# LM Studio (OpenAI-compatible)
# ------------------------------------------------------------------


class LMStudioProvider(LLMProvider):
    name = "lmstudio"

    def __init__(self, host: str = "http://localhost:1234", model: str = "local-model"):
        if requests is None:
            raise RuntimeError("requests not installed")
        self.host = host.rstrip("/")
        self.model = model

    def chat(self, messages, max_tokens: int = 1024, temperature: float = 0.2, **_) -> str:
        res = requests.post(
            f"{self.host}/v1/chat/completions",
            json={
                "model": self.model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
            timeout=LLM_LOCAL_REQUEST_TIMEOUT_SECONDS,
        )
        res.raise_for_status()
        return res.json()["choices"][0]["message"]["content"]

    def chat_stream(self, messages, max_tokens: int = 1024, temperature: float = 0.2, **_):
        """Yield text chunks via the OpenAI-compatible SSE streaming endpoint."""
        with requests.post(
            f"{self.host}/v1/chat/completions",
            json={
                "model": self.model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "stream": True,
            },
            timeout=LLM_LOCAL_REQUEST_TIMEOUT_SECONDS,
            stream=True,
        ) as res:
            res.raise_for_status()
            for raw_line in res.iter_lines():
                if not raw_line:
                    continue
                line = raw_line.decode("utf-8") if isinstance(raw_line, bytes) else raw_line
                if not line.startswith("data: "):
                    continue
                payload = line[6:]  # strip "data: "
                if payload.strip() == "[DONE]":
                    break
                try:
                    chunk = json.loads(payload)
                except Exception:
                    continue
                token = chunk.get("choices", [{}])[0].get("delta", {}).get("content", "")
                if token:
                    yield token

    @staticmethod
    def is_reachable(
        host: str = "http://localhost:1234", timeout: float = LLM_PROBE_TIMEOUT_SECONDS
    ) -> bool:
        if requests is None:
            return False
        try:
            r = requests.get(f"{host.rstrip('/')}/v1/models", timeout=timeout)
            return r.status_code == 200
        except Exception:
            return False


# ------------------------------------------------------------------
# Ollama
# ------------------------------------------------------------------


class OllamaProvider(LLMProvider):
    name = "ollama"

    def __init__(self, host: str = "http://localhost:11434", model: str = "llama3"):
        if requests is None:
            raise RuntimeError("requests not installed")
        self.host = host.rstrip("/")
        self.model = model

    def chat(self, messages, max_tokens: int = 1024, temperature: float = 0.2, **_) -> str:
        # Ollama has a native /api/chat that accepts the messages format directly
        res = requests.post(
            f"{self.host}/api/chat",
            json={
                "model": self.model,
                "messages": messages,
                "stream": False,
                "options": {
                    "temperature": temperature,
                    "num_predict": max_tokens,
                },
            },
            timeout=LLM_LOCAL_REQUEST_TIMEOUT_SECONDS,
        )
        res.raise_for_status()
        data = res.json()
        return data.get("message", {}).get("content", "")

    def chat_stream(self, messages, max_tokens: int = 1024, temperature: float = 0.2, **_):
        """Yield text chunks as Ollama streams them (NDJSON, one JSON object per line)."""
        with requests.post(
            f"{self.host}/api/chat",
            json={
                "model": self.model,
                "messages": messages,
                "stream": True,
                "options": {
                    "temperature": temperature,
                    "num_predict": max_tokens,
                },
            },
            timeout=LLM_LOCAL_REQUEST_TIMEOUT_SECONDS,
            stream=True,
        ) as res:
            res.raise_for_status()
            for raw_line in res.iter_lines():
                if not raw_line:
                    continue
                try:
                    chunk = json.loads(raw_line)
                except Exception:
                    continue
                token = chunk.get("message", {}).get("content", "")
                if token:
                    yield token
                if chunk.get("done"):
                    break

    @staticmethod
    def is_reachable(
        host: str = "http://localhost:11434", timeout: float = LLM_PROBE_TIMEOUT_SECONDS
    ) -> bool:
        if requests is None:
            return False
        try:
            r = requests.get(f"{host.rstrip('/')}/api/tags", timeout=timeout)
            return r.status_code == 200
        except Exception:
            return False


# ------------------------------------------------------------------
# Anthropic
# ------------------------------------------------------------------


class AnthropicProvider(LLMProvider):
    name = "anthropic"

    def __init__(self, api_key: str, model: str = "claude-opus-4-7"):
        if requests is None:
            raise RuntimeError("requests not installed")
        if not api_key:
            raise RuntimeError("Anthropic API key missing")
        self.api_key = api_key
        self.model = model

    def _build_body(self, messages, max_tokens: int, temperature: float) -> tuple[dict, dict]:
        """Separate system prompt from conversation; return (body, headers)."""
        system = None
        convo = []
        for m in messages:
            if m["role"] == "system":
                system = (system + "\n\n" if system else "") + m["content"]
            else:
                convo.append({"role": m["role"], "content": m["content"]})
        body: dict = {
            "model": self.model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": convo,
        }
        if system:
            body["system"] = system
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        return body, headers

    def chat(self, messages, max_tokens: int = 1024, temperature: float = 0.2, **_) -> str:
        body, headers = self._build_body(messages, max_tokens, temperature)
        res = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers=headers,
            json=body,
            timeout=LLM_CLOUD_REQUEST_TIMEOUT_SECONDS,
        )
        res.raise_for_status()
        data = res.json()
        return "".join(
            block.get("text", "")
            for block in data.get("content", [])
            if block.get("type") == "text"
        )

    def chat_stream(self, messages, max_tokens: int = 1024, temperature: float = 0.2, **_):
        """Yield text chunks via Anthropic streaming (SSE with content_block_delta events)."""
        body, headers = self._build_body(messages, max_tokens, temperature)
        body["stream"] = True
        with requests.post(
            "https://api.anthropic.com/v1/messages",
            headers=headers,
            json=body,
            timeout=LLM_CLOUD_REQUEST_TIMEOUT_SECONDS,
            stream=True,
        ) as res:
            res.raise_for_status()
            for raw_line in res.iter_lines():
                if not raw_line:
                    continue
                line = raw_line.decode("utf-8") if isinstance(raw_line, bytes) else raw_line
                if not line.startswith("data: "):
                    continue
                payload = line[6:]
                if payload.strip() in ("[DONE]", ""):
                    continue
                try:
                    event = json.loads(payload)
                except Exception:
                    continue
                # content_block_delta carries the actual text tokens
                if event.get("type") == "content_block_delta":
                    token = event.get("delta", {}).get("text", "")
                    if token:
                        yield token

    @staticmethod
    def is_reachable(api_key: Optional[str] = None, **_) -> bool:
        # We don't ping Anthropic (costs a round trip + real credentials).
        # Just check that a key is present.
        return bool(api_key)


# ------------------------------------------------------------------
# Config + auto-detect
# ------------------------------------------------------------------


def _load_config(path: str = "config.json") -> dict:
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _resolve(cfg: dict, key: str, env: str, default=None):
    return cfg.get(key) or os.getenv(env) or default


def get_provider(config_path: str = "config.json", logger=None) -> Optional[LLMProvider]:
    """
    Return the first reachable provider, or None.

    Order:
      1. Explicit override (config.llm_provider or AI_ASSISTANT_PROVIDER) - used if reachable
      2. Auto-detect: LM Studio -> Ollama -> Anthropic
    """
    cfg = _load_config(config_path)
    forced = cfg.get("llm_provider") or os.getenv("AI_ASSISTANT_PROVIDER")

    def _log(msg):
        if logger:
            logger.info(msg)

    # Resolve connection details once
    lm_host = _resolve(cfg, "lmstudio_host", "LMSTUDIO_HOST", "http://localhost:1234")
    lm_model = _resolve(cfg, "lmstudio_model", "LMSTUDIO_MODEL", "local-model")

    ol_host = _resolve(cfg, "ollama_host", "OLLAMA_HOST", "http://localhost:11434")
    ol_model = _resolve(cfg, "ollama_model", "OLLAMA_MODEL", "llama3")

    an_key = _resolve(cfg, "anthropic_api_key", "ANTHROPIC_API_KEY")
    an_model = _resolve(cfg, "anthropic_model", "ANTHROPIC_MODEL", "claude-opus-4-7")

    candidates = {
        "lmstudio": lambda: LMStudioProvider.is_reachable(lm_host)
        and LMStudioProvider(lm_host, lm_model),
        "ollama": lambda: OllamaProvider.is_reachable(ol_host)
        and OllamaProvider(ol_host, ol_model),
        "anthropic": lambda: AnthropicProvider.is_reachable(api_key=an_key)
        and AnthropicProvider(an_key, an_model),
    }

    # Forced provider - try it, but only if reachable
    if forced in candidates:
        try:
            p = candidates[forced]()
            if p:
                _log(f"[llm] using {forced} (forced)")
                return p
            _log(f"[llm] forced provider '{forced}' not reachable; falling through")
        except Exception as e:
            _log(f"[llm] forced provider '{forced}' error: {e}")

    # Auto-detect in preference order
    for name in ("lmstudio", "ollama", "anthropic"):
        try:
            p = candidates[name]()
            if p:
                _log(f"[llm] auto-selected {name}")
                return p
        except Exception as e:
            _log(f"[llm] {name} init error: {e}")

    _log("[llm] no provider reachable")
    return None
