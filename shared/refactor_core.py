# -*- coding: utf-8 -*-
"""
代码重构核心逻辑（共享模块）
================================

本模块是整个「代码重构服务」的唯一真源（Single Source of Truth），
被 xpack-server（FastAPI 服务）以及其他 Python 侧适配层复用。

设计原则：
1. 只依赖标准库 + ollama-python（可选），不引入重量级框架，方便各平台裁剪复用。
2. 所有可配置项（服务地址、模型名、超时）一律通过参数或环境变量注入，
   严禁在代码中硬编码任何 API Key、密码或私有地址。
3. 所有对外函数在异常时返回结构化字典，而不是直接抛出，方便 MCP / HTTP 层
   统一包装成用户可读的中文错误信息。

支持两种推理后端，通过 REFACTOR_BACKEND 环境变量切换：

- ``ollama``（默认）：调用本地 Ollama 服务，代码不出本机，但速度取决于本机算力。
- ``openai``：调用任何 OpenAI 兼容的云端接口（DeepSeek 官方 API、硅基流动等），
  响应快、质量高，但代码会发送到该服务商。

环境变量说明：
- REFACTOR_BACKEND : 后端类型，ollama | openai，默认 ollama
- OLLAMA_HOST      : Ollama 服务地址，默认 http://127.0.0.1:11434
- OLLAMA_MODEL     : Ollama 使用的模型名，默认 deepseek-coder
- OPENAI_BASE_URL  : OpenAI 兼容接口地址，默认 https://api.deepseek.com/v1
- OPENAI_API_KEY   : API 密钥（仅从环境变量读取，严禁硬编码）
- OPENAI_MODEL     : 云端模型名，默认 deepseek-chat
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from typing import Any, Dict, Optional

# ---------------------------------------------------------------------------
# 默认配置（可被环境变量或显式参数覆盖）
# ---------------------------------------------------------------------------

# 推理后端：ollama（本地）或 openai（云端 OpenAI 兼容接口）
DEFAULT_BACKEND = os.environ.get("REFACTOR_BACKEND", "ollama").lower()

# Ollama 服务默认地址。注意：Ollama 官方 SDK 使用 OLLAMA_HOST，这里保持一致。
DEFAULT_OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")

# 默认模型。backend=ollama 时为本地模型，backend=openai 时为云端模型。
DEFAULT_MODEL = os.environ.get("OLLAMA_MODEL", "deepseek-coder")

# 云端 OpenAI 兼容接口配置（backend=openai 时生效）
DEFAULT_OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL", "https://api.deepseek.com/v1")
DEFAULT_OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "deepseek-chat")

# 单次推理超时时间（秒）。
# 注意：本地 Ollama 在低配机器上（如 4GB 内存的纯 CPU 环境）单次推理可能耗时 35-90 秒，
# 因此本地后端默认超时放宽到 180 秒，避免无谓失败；云端接口快，默认 30 秒。
DEFAULT_TIMEOUT = float(os.environ.get("REFACTOR_TIMEOUT", "180"))

# 支持的编程语言（用于提示词中做轻量约束，不做强制校验）
SUPPORTED_LANGUAGES = ("python", "javascript", "typescript", "java", "go", "rust", "c", "cpp")


# ---------------------------------------------------------------------------
# 内部工具函数
# ---------------------------------------------------------------------------

def _normalize_host(host: Optional[str]) -> str:
    """规范化 Ollama 服务地址。

    允许用户传入以下几种写法，统一转换为带协议的 http(s) 地址：
    - http://localhost:11434   -> 原样返回
    - localhost:11434          -> 补全为 http://localhost:11434
    - 127.0.0.1:11434/         -> 去掉尾部斜杠

    :param host: 用户传入的服务地址，可能为 None
    :return: 规范化后的地址字符串
    """
    value = (host or DEFAULT_OLLAMA_HOST).strip()
    if not value:
        value = DEFAULT_OLLAMA_HOST
    # 如果用户没有写协议头，默认补 http://
    if not value.startswith(("http://", "https://")):
        value = "http://" + value
    # 去掉尾部斜杠，避免拼接出 //api/generate 这种路径
    return value.rstrip("/")


def _http_json(
    url: str,
    payload: Optional[Dict[str, Any]] = None,
    timeout: float = DEFAULT_TIMEOUT,
    method: str = "POST",
) -> Dict[str, Any]:
    """向指定 URL 发送 JSON 请求并解析 JSON 响应。

    这里刻意使用标准库 urllib 而非 requests，目的是让 shared 模块
    可以被任意平台零依赖地复制使用（比如扣子的 Python 函数节点）。

    :param url: 完整请求地址
    :param payload: 请求体字典；为 None 时发送空对象
    :param timeout: 超时秒数
    :param method: HTTP 方法
    :return: 解析后的响应字典
    :raises RuntimeError: 网络异常、超时或响应非法时抛出，附带中文说明
    """
    data = json.dumps(payload or {}, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={"Content-Type": "application/json; charset=utf-8"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        # 服务端返回 4xx/5xx，读取响应体便于排查（例如模型不存在）
        detail = ""
        try:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
        except Exception:  # pragma: no cover - 极端情况下的兜底
            detail = ""
        raise RuntimeError(f"Ollama 服务返回错误（HTTP {exc.code}）：{detail or exc.reason}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(
            f"无法连接 Ollama 服务：{exc.reason}。请确认 Ollama 已启动，"
            f"且服务地址正确（可通过环境变量 OLLAMA_HOST 修改）。"
        ) from exc
    except TimeoutError as exc:
        raise RuntimeError(f"请求 Ollama 超时（超过 {timeout:g} 秒），请检查模型大小或调高超时时间。") from exc

    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Ollama 返回内容不是合法 JSON：{raw[:300]}") from exc


def _build_prompt(code: str, task: str, language: Optional[str] = None) -> str:
    """构造发送给代码模型的重构提示词。

    提示词直接影响输出质量，这里做了几条硬约束：
    - 只输出重构后的完整代码，不要解释文字（便于程序直接取用）
    - 保持原有公共接口不变（函数名、类名、参数签名），降低替换风险
    - 语言未知时让模型自行判断

    :param code: 待重构的源代码
    :param task: 重构任务描述，例如「提取重复逻辑为函数」
    :param language: 可选的编程语言提示
    :return: 拼装好的提示词字符串
    """
    lang_hint = f"这段代码使用的编程语言是 {language}。" if language else "请先自行判断这段代码的编程语言。"
    return (
        "你是一名资深软件工程师，擅长把遗留代码重构为现代、可维护的规范代码。\n"
        f"{lang_hint}\n\n"
        "【重构任务】\n"
        f"{task}\n\n"
        "【待重构代码】\n"
        "```\n"
        f"{code}\n"
        "```\n\n"
        "【输出要求】\n"
        "1. 只输出重构后的完整代码，放在一个 Markdown 代码块中，不要输出任何额外解释。\n"
        "2. 必须保持原有的公共接口不变（函数名、类名、参数与返回值签名），除非任务明确要求修改。\n"
        "3. 保持原有业务逻辑等价，不要引入新的外部依赖。\n"
        "4. 补充必要的中文注释，说明关键改动点。\n"
    )


def _extract_code_block(text: str) -> str:
    """从模型输出中提取 Markdown 代码块内容。

    模型有时会无视「只输出代码」的要求，附带解释文字；这里做一层容错：
    - 存在 ``` 围栏时，取第一个围栏内的内容（并去掉语言标识行）
    - 不存在围栏时，原样返回去空白后的文本

    :param text: 模型原始输出
    :return: 提取到的代码文本
    """
    if "```" not in text:
        return text.strip()
    # 以 ``` 切分：偶数段为围栏外，奇数段为围栏内
    parts = text.split("```")
    if len(parts) >= 3:
        block = parts[1]
        # 去掉第一行的语言标识（如 python / javascript）
        lines = block.splitlines()
        if lines and lines[0].strip().lower() in SUPPORTED_LANGUAGES + ("", "js", "ts", "sh", "bash", "text"):
            lines = lines[1:]
        return "\n".join(lines).strip()
    return text.strip()


# ---------------------------------------------------------------------------
# 对外能力 1：检查 Ollama 服务可用性
# ---------------------------------------------------------------------------

def check_ollama_status(
    host: Optional[str] = None,
    model: Optional[str] = None,
    timeout: float = 5.0,
) -> Dict[str, Any]:
    """检查 Ollama 服务是否可用，以及目标模型是否已拉取。

    该函数永不抛异常，始终返回结构化字典，方便 MCP 工具直接透传给用户。

    :param host: Ollama 服务地址，默认读取 OLLAMA_HOST
    :param model: 需要检查的模型名，默认读取 OLLAMA_MODEL
    :param timeout: 健康检查超时秒数，默认 5 秒
    :return: 形如 {"ok": True, "available": True, ...} 的字典
    """
    base = _normalize_host(host)
    target_model = model or DEFAULT_MODEL
    try:
        # /api/tags 会列出本机已拉取的全部模型，用于判断服务与模型状态
        resp = _http_json(f"{base}/api/tags", payload={}, timeout=timeout, method="GET")
        models = [m.get("name", "") for m in resp.get("models", [])]
        # 允许 deepseek-coder 与 deepseek-coder:latest 互相匹配
        available = any(
            name == target_model or name.split(":")[0] == target_model.split(":")[0]
            for name in models
        )
        return {
            "ok": True,
            "available": available,
            "host": base,
            "model": target_model,
            "installed_models": models,
            "message": (
                f"Ollama 服务正常，模型 {target_model} 已就绪。"
                if available
                else f"Ollama 服务正常，但未找到模型 {target_model}，请先执行 `ollama pull {target_model}`。"
            ),
        }
    except RuntimeError as exc:
        return {
            "ok": False,
            "available": False,
            "host": base,
            "model": target_model,
            "installed_models": [],
            "message": str(exc),
        }


# ---------------------------------------------------------------------------
# 对外能力 2：代码重构
# ---------------------------------------------------------------------------

def _call_ollama(prompt: str, target_model: str, base: str, timeout: float) -> Dict[str, Any]:
    """调用本地 Ollama 的 /api/generate 接口。

    :param prompt: 完整提示词
    :param target_model: 模型名
    :param base: 规范化后的服务地址
    :param timeout: 超时秒数
    :return: 模型原始输出文本
    :raises RuntimeError: 调用失败时抛出，附带中文说明
    """
    payload = {
        "model": target_model,
        "prompt": prompt,
        "stream": False,          # 非流式，便于一次性返回结构化结果
        "options": {
            # temperature 调低，保证重构结果稳定、少发挥
            "temperature": 0.2,
            # 限制最大生成长度
            "num_predict": 2048,
        },
    }
    resp = _http_json(f"{base}/api/generate", payload=payload, timeout=timeout)
    return resp


def _call_openai_compatible(
    prompt: str, target_model: str, base_url: str, timeout: float
) -> Dict[str, Any]:
    """调用 OpenAI 兼容的云端接口（DeepSeek / 硅基流动 / 阿里百炼等）。

    密钥从环境变量 OPENAI_API_KEY 读取，**不通过参数传入、不写入日志**。

    :param prompt: 完整提示词
    :param target_model: 云端模型名
    :param base_url: 接口基地址，例如 https://api.deepseek.com/v1
    :param timeout: 超时秒数
    :return: 兼容 Ollama 返回结构的字典（含 response 字段）
    :raises RuntimeError: 密钥缺失或调用失败时抛出
    """
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError(
            "使用云端后端时必须在环境变量 OPENAI_API_KEY 中配置 API 密钥。"
            "请设置后重试（密钥不会被写入代码或日志）。"
        )

    payload = {
        "model": target_model,
        "messages": [
            {
                "role": "system",
                "content": "你是一名资深软件工程师，擅长把遗留代码重构为现代、可维护的规范代码。",
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
        "max_tokens": 4096,
        "stream": False,
    }

    url = base_url.rstrip("/") + "/chat/completions"
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={
            "Content-Type": "application/json; charset=utf-8",
            "Authorization": f"Bearer {api_key}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
        except Exception:  # pragma: no cover
            detail = ""
        # 常见错误给出更有指向性的中文提示
        hint = ""
        if exc.code == 401:
            hint = "（密钥无效或已过期，请检查 OPENAI_API_KEY）"
        elif exc.code == 402:
            hint = "（账户余额不足，请充值）"
        elif exc.code == 429:
            hint = "（请求过于频繁或超出配额，请稍后重试）"
        raise RuntimeError(f"云端接口返回错误（HTTP {exc.code}）{hint}：{detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(
            f"无法连接云端接口（{base_url}）：{exc.reason}。请检查网络与 OPENAI_BASE_URL 配置。"
        ) from exc
    except TimeoutError as exc:
        raise RuntimeError(f"云端接口请求超时（超过 {timeout:g} 秒）。") from exc

    try:
        obj = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"云端接口返回内容不是合法 JSON：{raw[:300]}") from exc

    # 提取回复内容，兼容 OpenAI 标准结构
    try:
        content = obj["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError(f"云端接口返回结构异常：{raw[:300]}") from exc

    # 统一成 Ollama 的返回结构，方便上层复用解析逻辑
    return {"response": content}

def refactor_code(
    code: str,
    task: str,
    model: Optional[str] = None,
    host: Optional[str] = None,
    language: Optional[str] = None,
    timeout: Optional[float] = None,
) -> Dict[str, Any]:
    """调用 Ollama 对给定代码执行重构。

    该函数永不抛异常，始终返回结构化字典：

    成功时::

        {
          "ok": True,
          "code": "<重构后的代码>",
          "raw": "<模型原始输出>",
          "model": "deepseek-coder",
          "language": "python",
          "elapsed_ms": 1234
        }

    失败时::

        {"ok": False, "error": "<可读中文错误信息>", "error_type": "..."}

    :param code: 待重构的源代码片段
    :param task: 重构任务描述（自然语言）
    :param model: 模型名，默认读取 OLLAMA_MODEL 或 deepseek-coder
    :param host: Ollama 地址，默认读取 OLLAMA_HOST
    :param language: 可选的编程语言提示
    :param timeout: 超时秒数，默认 25 秒
    :return: 结构化结果字典
    """
    # --- 入参校验：提前拦截空输入，避免无意义地占用模型 ---
    if not code or not code.strip():
        return {"ok": False, "error": "参数 code 不能为空，请提供需要重构的代码片段。", "error_type": "invalid_argument"}
    if not task or not task.strip():
        return {"ok": False, "error": "参数 task 不能为空，请说明希望如何重构，例如「提取重复逻辑为函数」。", "error_type": "invalid_argument"}

    # 超长代码保护：Ollama 上下文有限，超过约 2 万字符时提示用户拆分
    if len(code) > 20000:
        return {
            "ok": False,
            "error": f"代码片段过长（{len(code)} 字符），建议拆分到 20000 字符以内再提交。",
            "error_type": "payload_too_large",
        }

    base = _normalize_host(host)
    target_model = model or DEFAULT_MODEL
    effective_timeout = timeout or DEFAULT_TIMEOUT

    payload = {
        "model": target_model,
        "prompt": _build_prompt(code, task, language),
        "stream": False,          # 非流式，便于一次性返回结构化结果
        "options": {
            # temperature 调低，保证重构结果稳定、少发挥
            "temperature": 0.2,
            # 限制最大生成长度，配合 30 秒响应承诺
            "num_predict": 2048,
        },
    }

    started = time.time()
    try:
        resp = _http_json(f"{base}/api/generate", payload=payload, timeout=effective_timeout)
    except RuntimeError as exc:
        # 区分「模型不存在」与「服务不可达」，给出更有指向性的中文提示
        message = str(exc)
        error_type = "ollama_unreachable"
        if "not found" in message.lower() or "no such model" in message.lower():
            error_type = "model_not_found"
            message = f"未找到模型 {target_model}，请先执行 `ollama pull {target_model}`。原始信息：{message}"
        return {"ok": False, "error": message, "error_type": error_type}

    raw = (resp.get("response") or "").strip()
    if not raw:
        return {"ok": False, "error": "模型返回了空内容，请重试或换用更大的模型。", "error_type": "empty_response"}

    elapsed_ms = int((time.time() - started) * 1000)
    return {
        "ok": True,
        "code": _extract_code_block(raw),
        "raw": raw,
        "model": target_model,
        "language": language or "auto",
        "elapsed_ms": elapsed_ms,
    }


# ---------------------------------------------------------------------------
# 命令行自测入口：python refactor_core.py
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # 简单自测：先打印服务状态，再对一段示例代码做重构
    status = check_ollama_status()
    print("【服务状态】", json.dumps(status, ensure_ascii=False, indent=2))

    if status.get("available"):
        demo_code = (
            "def f(a):\n"
            "    r = []\n"
            "    for i in a:\n"
            "        if i % 2 == 0:\n"
            "            r.append(i * i)\n"
            "    return r\n"
        )
        result = refactor_code(demo_code, "重命名为有意义的函数名与变量名，补充类型标注与中文注释", language="python")
        print("【重构结果】", json.dumps(result, ensure_ascii=False, indent=2))
