# -*- coding: utf-8 -*-
"""
XPack MCP Server —— FastAPI 适配层
===================================

把 shared/refactor_core.py 的核心能力包装成符合 xpack-server/openapi.json
描述的 HTTP 接口，供 XPack 平台按 OpenAPI 规范自动生成可调用的 MCP 服务。

提供的端点：
- POST /refactor  执行代码重构（计费端点）
- GET  /status    服务健康检查（不计费）
- GET  /healthz   容器存活探针

所有配置通过环境变量注入，代码中不包含任何密钥。
"""

from __future__ import annotations

import os
import sys
from typing import Optional

# 把 shared 目录加入模块搜索路径，保证容器内也能正确导入核心逻辑
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "shared"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "shared"))

from fastapi import FastAPI, HTTPException  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

from refactor_core import check_ollama_status, refactor_code  # noqa: E402

app = FastAPI(
    title="代码重构服务",
    description="将遗留代码自动重构为现代规范代码，支持 Python / JavaScript / Java 等语言。",
    version="1.0.0",
)

# 允许跨域调用，方便平台侧与调试工具直接访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class RefactorRequest(BaseModel):
    """重构请求体。字段定义与 openapi.json 保持一致。"""

    code: str = Field(..., description="待重构的源代码片段，不超过 20000 字符")
    task: str = Field(..., description="重构任务描述")
    language: Optional[str] = Field("auto", description="编程语言提示，auto 表示自动判断")


@app.get("/healthz", tags=["系统"])
def healthz():
    """容器存活探针，供 Docker HEALTHCHECK 使用。"""
    return {"ok": True}


@app.get("/status", tags=["系统"])
def status(host: Optional[str] = None, model: Optional[str] = None):
    """检查 Ollama 服务与模型状态。

    :param host: 可选，覆盖环境变量中的 Ollama 地址
    :param model: 可选，覆盖环境变量中的模型名
    """
    return check_ollama_status(host=host, model=model)


@app.post("/refactor", tags=["代码重构"])
def refactor(req: RefactorRequest):
    """执行代码重构。

    返回结构与 openapi.json 中定义的 200 响应一致；参数错误返回 400，
    代码过长返回 413，模型超时返回 504。
    """
    language = None if req.language in (None, "", "auto") else req.language
    result = refactor_code(code=req.code, task=req.task, language=language)

    if result.get("ok"):
        return result

    # 依据错误类型映射到合适的 HTTP 状态码，便于平台侧统一处理
    error_type = result.get("error_type", "")
    status_map = {
        "invalid_argument": 400,
        "payload_too_large": 413,
        "model_not_found": 503,
        "ollama_unreachable": 503,
        "empty_response": 502,
        "timeout": 504,
    }
    raise HTTPException(status_code=status_map.get(error_type, 500), detail=result)


if __name__ == "__main__":
    # 本地直接运行：python app.py
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))
