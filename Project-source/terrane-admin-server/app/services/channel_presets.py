"""Model-channel provider presets (the variant-pattern dropdown items; one-click base_url fill + hint).

A provider is a type variant in the "New channel" dropdown. openai_compatible covers any
OpenAI-protocol-compatible service (OpenAI/DeepSeek/Zhipu/Moonshot/local vLLM, etc.); just fill in each Base URL.
"""

from __future__ import annotations

_PRESETS: list[dict] = [
    {"id": "openai_compatible", "label": "OpenAI Compatible", "kind": "chat",
     "base_url": "https://api.openai.com/v1", "needs_model": True,
     "key_hint": "Bearer API Key. For OpenAI-protocol-compatible services (OpenAI/DeepSeek/Zhipu/Moonshot/local vLLM, etc.), fill in each one's Base URL"},
    {"id": "anthropic", "label": "Anthropic Claude", "kind": "chat",
     "base_url": "https://api.anthropic.com", "needs_model": True,
     "key_hint": "x-api-key (from the Anthropic console)"},
    {"id": "tongyi", "label": "Tongyi Qianwen / Bailian (DashScope)", "kind": "chat",
     "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1", "needs_model": True,
     "key_hint": "DashScope API Key (Alibaba Cloud Bailian console)"},
    {"id": "web_search", "label": "Web Search", "kind": "web_search",
     "base_url": "", "needs_model": False,
     "key_hint": "Search-service API Key (e.g. Tavily / Bocha)"},
    {"id": "custom", "label": "Custom", "kind": "chat",
     "base_url": "", "needs_model": True,
     "key_hint": "Manually fill in Base URL / model / Key"},
]


def all_presets() -> list[dict]:
    return _PRESETS
