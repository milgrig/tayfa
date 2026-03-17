"""
Ollama provider — sends prompts to locally running Ollama via OpenAI-compatible API.

Ollama serves on http://localhost:11434 by default and exposes /v1/chat/completions
which is fully OpenAI-compatible.  This module provides both blocking and streaming
calls, converting responses to the event format Tayfa frontend expects.
"""

import json
import logging
from typing import AsyncIterator

import httpx

logger = logging.getLogger("tayfa")

OLLAMA_BASE_URL = "http://localhost:11434"

_KNOWN_OLLAMA_PREFIXES = (
    "qwen", "llama", "mistral", "gemma", "phi", "deepseek",
    "codellama", "starcoder", "codegemma", "nomic", "yi",
    "vicuna", "orca", "falcon", "solar", "dolphin", "nous",
    "tinyllama", "granite",
)


def is_ollama_model(model: str) -> bool:
    """True if the model name looks like an Ollama local model."""
    if not model:
        return False
    m = model.lower().strip()
    if m.startswith("ollama:"):
        return True
    for prefix in _KNOWN_OLLAMA_PREFIXES:
        if m.startswith(prefix):
            return True
    return False


def normalize_model_name(model: str) -> str:
    """Strip 'ollama:' prefix if present."""
    if model.lower().startswith("ollama:"):
        return model[7:]
    return model


async def check_available() -> bool:
    """Check if Ollama is running and responding."""
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(f"{OLLAMA_BASE_URL}/api/tags")
            return resp.status_code == 200
    except Exception:
        return False


async def list_models() -> list[dict]:
    """List locally available Ollama models."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{OLLAMA_BASE_URL}/api/tags")
            if resp.status_code != 200:
                return []
            data = resp.json()
            return data.get("models", [])
    except Exception:
        return []


async def call_ollama(
    model: str,
    prompt: str,
    system_prompt: str = "",
    timeout: float = 300.0,
) -> dict:
    """Non-streaming call to Ollama. Returns dict compatible with Tayfa's result format."""
    model = normalize_model_name(model)
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                f"{OLLAMA_BASE_URL}/v1/chat/completions",
                json={"model": model, "messages": messages, "stream": False},
            )
            if resp.status_code != 200:
                return {
                    "result": "",
                    "is_error": True,
                    "error": f"Ollama returned {resp.status_code}: {resp.text[:500]}",
                    "cost_usd": 0,
                    "num_turns": 1,
                }
            data = resp.json()
            result_text = ""
            choices = data.get("choices", [])
            if choices:
                result_text = choices[0].get("message", {}).get("content", "")

            usage = data.get("usage", {})
            return {
                "result": result_text,
                "is_error": False,
                "cost_usd": 0,
                "num_turns": 1,
                "ollama_usage": {
                    "prompt_tokens": usage.get("prompt_tokens", 0),
                    "completion_tokens": usage.get("completion_tokens", 0),
                    "total_tokens": usage.get("total_tokens", 0),
                },
            }
    except httpx.ConnectError:
        return {
            "result": "",
            "is_error": True,
            "error": "Ollama is not running. Start it with: ollama serve",
            "cost_usd": 0,
            "num_turns": 0,
        }
    except httpx.ReadTimeout:
        return {
            "result": "",
            "is_error": True,
            "error": f"Ollama timeout ({timeout}s). Model may be loading into VRAM.",
            "cost_usd": 0,
            "num_turns": 0,
        }
    except Exception as e:
        return {
            "result": "",
            "is_error": True,
            "error": f"Ollama error: {e}",
            "cost_usd": 0,
            "num_turns": 0,
        }


async def stream_ollama(
    model: str,
    prompt: str,
    system_prompt: str = "",
) -> AsyncIterator[str]:
    """
    Streaming call to Ollama.  Yields SSE-compatible JSON strings in the format
    the Tayfa frontend already understands (content_block_delta / result events).
    """
    model = normalize_model_name(model)
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    full_result = ""

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(None, connect=10.0)) as client:
            async with client.stream(
                "POST",
                f"{OLLAMA_BASE_URL}/v1/chat/completions",
                json={"model": model, "messages": messages, "stream": True},
            ) as resp:
                if resp.status_code != 200:
                    body = await resp.aread()
                    yield json.dumps({"type": "error", "error": f"Ollama {resp.status_code}: {body.decode()[:500]}"})
                    return

                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    payload = line[6:].strip()
                    if payload == "[DONE]":
                        break

                    try:
                        chunk = json.loads(payload)
                    except json.JSONDecodeError:
                        continue

                    choices = chunk.get("choices", [])
                    if not choices:
                        continue

                    delta = choices[0].get("delta", {})
                    text = delta.get("content", "")
                    if text:
                        full_result += text
                        yield json.dumps({
                            "type": "content_block_delta",
                            "delta": {"type": "text_delta", "text": text},
                        })

    except httpx.ConnectError:
        yield json.dumps({"type": "error", "error": "Ollama is not running. Start it with: ollama serve"})
        return
    except Exception as e:
        yield json.dumps({"type": "error", "error": f"Ollama stream error: {e}"})
        return

    yield json.dumps({
        "type": "result",
        "result": full_result,
        "cost_usd": 0,
        "num_turns": 1,
    })
