"""大模型统一封装：OpenAI 兼容接口、超时、重试、JSON 解析。

chat_json 失败时返回 None，由调用方走降级路径；不抛异常。
测试用 set_backend 注入假模型，不访问网络。
"""
from __future__ import annotations

import json
import re
import time
from functools import lru_cache
from string import Template
from typing import Callable

import yaml

from app.config import settings

_backend: Callable[[str, dict], dict | None] | None = None
last_error: str = ""


def set_backend(fn: Callable[[str, dict], dict | None] | None) -> None:
    """注入假模型：fn(prompt_name, variables) -> dict 或 None。传 None 恢复真实调用。"""
    global _backend
    _backend = fn


def available() -> bool:
    return _backend is not None or bool(settings.llm_api_key and settings.llm_model)


@lru_cache(maxsize=8)
def load_prompt(name: str) -> dict:
    with open(settings.prompts_dir / f"{name}.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _parse_json(text: str) -> dict | None:
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", (text or "").strip())
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.S)
        if not m:
            return None
        try:
            data = json.loads(m.group(0))
        except json.JSONDecodeError:
            return None
    return data if isinstance(data, dict) else None


@lru_cache(maxsize=4)
def _client(base_url: str, api_key: str, timeout: float):
    """共用一个客户端（连接池），并发调用时不必每次重新建立连接。"""
    from openai import OpenAI

    return OpenAI(base_url=base_url, api_key=api_key, timeout=timeout, max_retries=0)


def chat_json(prompt_name: str, variables: dict, refresh: bool = False,
              cache_ignore: tuple[str, ...] = ()) -> dict | None:
    """调用一次 Prompt，返回解析后的 JSON 对象；超时、报错或解析失败（重试后仍失败）返回 None。

    同样的提示词和变量直接复用上次成功的结果（app/cache.py 第二层）。refresh=True 时不读缓存、用新结果覆盖；
    cache_ignore 列出与结论无关、不参与缓存键的变量（如判定时的评估日期：在先状态已作为事实给出）。
    """
    global last_error
    if _backend is not None:
        try:
            return _backend(prompt_name, variables)
        except Exception as e:  # 假模型抛错等同于调用失败
            last_error = f"{type(e).__name__}: {e}"
            return None
    if not available():
        last_error = "未配置 LLM_API_KEY 或 LLM_MODEL"
        return None
    prompt = load_prompt(prompt_name)
    str_vars = {k: v if isinstance(v, str) else json.dumps(v, ensure_ascii=False, default=str)
                for k, v in variables.items()}
    from app import cache
    ck = cache.key(settings.llm_model, prompt_name, prompt["system"], prompt["user"],
                   {k: v for k, v in str_vars.items() if k not in cache_ignore})
    if not refresh:
        hit = cache.llm_get(ck)
        if hit is not None:
            return hit
    messages = [{"role": "system", "content": prompt["system"]},
                {"role": "user", "content": Template(prompt["user"]).safe_substitute(str_vars)}]
    client = _client(settings.llm_base_url, settings.llm_api_key, settings.llm_timeout)
    attempts, conn_extra = settings.llm_retries + 1, 2     # 连接失败（非超时）很快返回，额外多试 2 次
    while attempts > 0:
        attempts -= 1
        try:
            resp = client.chat.completions.create(
                model=settings.llm_model, messages=messages, temperature=0,
                response_format={"type": "json_object"})
            data = _parse_json(resp.choices[0].message.content)
            if data is not None:
                cache.llm_put(ck, prompt_name, data)
                return data
            last_error = "模型输出不是合法 JSON"
        except Exception as e:
            last_error = f"{type(e).__name__}: {e}"
            if type(e).__name__ == "APIConnectionError" and conn_extra > 0:
                conn_extra -= 1
                attempts += 1
        time.sleep(0.5)
    return None
