# 代码重构服务 —— XPack MCP Server 镜像
# ========================================
# 基于 python:3.11-slim 构建，对外暴露 8000 端口。
# 启动后 XPack 平台可直接通过 OpenAPI 描述（openapi.json）调用本服务。
#
# 构建：docker build -t code-refactor-xpack:1.0.0 .
# 运行：docker run -p 8000:8000 \
#         -e OLLAMA_HOST=http://host.docker.internal:11434 \
#         -e OLLAMA_MODEL=deepseek-coder \
#         code-refactor-xpack:1.0.0
#
# 注意：Ollama 服务地址通过环境变量注入，镜像内不包含任何密钥。

FROM python:3.11-slim

# 基础环境设置：不写 pyc、日志直接输出、关闭缓冲
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    OLLAMA_HOST=http://host.docker.internal:11434 \
    OLLAMA_MODEL=deepseek-coder

WORKDIR /app

# 先装依赖，利用 Docker 层缓存加速后续构建
# ollama 为官方 Python SDK；fastapi + uvicorn 提供 HTTP 服务
RUN pip install --no-cache-dir \
        "fastapi>=0.110" \
        "uvicorn[standard]>=0.27" \
        "ollama>=0.2.0" \
        "pydantic>=2.0"

# 复制共享核心逻辑与适配层
COPY shared/ /app/shared/
COPY xpack-server/app.py /app/app.py

# 非 root 用户运行，降低容器逃逸风险
RUN useradd --create-home --shell /bin/bash appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# 健康检查：调用 /status 端点确认服务存活
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/status',timeout=5)" || exit 1

# 以 uvicorn 启动 FastAPI 应用
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
