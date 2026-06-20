"""模型渠道服务商预设(变体范式的下拉项;一键填充 base_url + 提示)。

provider 即「新建渠道」下拉的类型变体。openai_compatible 覆盖一切 OpenAI 协议兼容服务
(OpenAI/DeepSeek/智谱/Moonshot/本地 vLLM…),各自填 Base URL 即可。
"""

from __future__ import annotations

_PRESETS: list[dict] = [
    {"id": "openai_compatible", "label": "OpenAI 兼容", "kind": "chat",
     "base_url": "https://api.openai.com/v1", "needs_model": True,
     "key_hint": "Bearer API Key。兼容 OpenAI 协议的服务(OpenAI/DeepSeek/智谱/Moonshot/本地 vLLM 等)填各自 Base URL"},
    {"id": "anthropic", "label": "Anthropic Claude", "kind": "chat",
     "base_url": "https://api.anthropic.com", "needs_model": True,
     "key_hint": "x-api-key(Anthropic 控制台获取)"},
    {"id": "tongyi", "label": "通义千问 / 百炼(DashScope)", "kind": "chat",
     "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1", "needs_model": True,
     "key_hint": "DashScope API Key(阿里云百炼控制台)"},
    {"id": "web_search", "label": "Web 搜索", "kind": "web_search",
     "base_url": "", "needs_model": False,
     "key_hint": "搜索服务 API Key(如 Tavily / 博查 Bocha)"},
    {"id": "custom", "label": "自定义", "kind": "chat",
     "base_url": "", "needs_model": True,
     "key_hint": "手动填写 Base URL / 模型 / Key"},
]


def all_presets() -> list[dict]:
    return _PRESETS
