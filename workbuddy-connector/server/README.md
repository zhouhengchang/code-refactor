# workbuddy-code-refactor-connector

WorkBuddy 代码重构连接器 —— 一个基于 [Model Context Protocol](https://modelcontextprotocol.io/) 的 MCP Server，把「代码重构」能力封装成 AI 可直接调用的工具。

支持**本地 Ollama** 与**任意 OpenAI 兼容的云端接口**两种推理后端，通过环境变量切换。

## 功能

暴露两个 MCP 工具：

| 工具 | 参数 | 说明 |
| --- | --- | --- |
| `refactor_code` | `code`（源代码）、`task`（重构任务描述）、`language`（可选，语言提示） | 执行代码重构，返回重构后的代码与说明 |
| `check_status` | 无 | 检查当前推理后端是否可用，并返回后端/模型信息 |

## 安装

```bash
npm install -g workbuddy-code-refactor-connector
```

或直接以 `npx` 运行（无需全局安装）：

```bash
npx workbuddy-code-refactor-connector
```

## 配置

所有配置均通过**环境变量**读取，包内不硬编码任何密钥。

### 方式一：本地 Ollama（默认，代码不出本机）

```bash
REFACTOR_BACKEND=ollama          # 默认值，可省略
OLLAMA_HOST=http://127.0.0.1:11434
OLLAMA_MODEL=deepseek-coder
```

### 方式二：云端 OpenAI 兼容接口

```bash
REFACTOR_BACKEND=openai
OPENAI_BASE_URL=https://api.deepseek.com/v1
OPENAI_MODEL=deepseek-flash
OPENAI_API_KEY=sk-xxxxxxxxxxxx
```

### 全部环境变量

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `REFACTOR_BACKEND` | `ollama` | 推理后端：`ollama` \| `openai` |
| `OLLAMA_HOST` | `http://127.0.0.1:11434` | Ollama 服务地址 |
| `OLLAMA_MODEL` | `deepseek-coder` | 本地模型名 |
| `OPENAI_BASE_URL` | `https://api.deepseek.com/v1` | OpenAI 兼容接口地址 |
| `OPENAI_MODEL` | `deepseek-flash` | 云端模型名 |
| `OPENAI_API_KEY` | 无 | 云端接口密钥（`openai` 后端必填） |
| `REFACTOR_TIMEOUT_MS` | `180000` | 单次推理超时毫秒数（纯 CPU 本地推理较慢，默认放宽到 3 分钟） |

## 接入 WorkBuddy

在 WorkBuddy 的连接器配置（`mcp.json`）中登记本服务：

```json
{
  "mcpServers": {
    "code-refactor": {
      "command": "npx",
      "args": ["-y", "workbuddy-code-refactor-connector"],
      "env": {
        "REFACTOR_BACKEND": "ollama",
        "OLLAMA_MODEL": "deepseek-coder"
      }
    }
  }
}
```

若使用云端后端，在 `env` 中补充 `REFACTOR_BACKEND`、`OPENAI_BASE_URL`、`OPENAI_MODEL`、`OPENAI_API_KEY`。

## 设计要点

- **密钥零硬编码**：地址、模型名、密钥全部来自环境变量。
- **超时保护**：所有工具调用都有超时上限，默认 180 秒。
- **错误可读**：任何异常都转换为可读的中文提示，不向调用方抛出原始堆栈。
- **双后端**：本地推理保障代码不出本机；云端接口用于追求更高重构质量。

## 许可

[MIT](./LICENSE)
