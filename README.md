<div align="center">

# 代码重构助手

**把遗留代码重构为现代规范代码，保持原有接口与行为不变**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB.svg?logo=python&logoColor=white)](https://www.python.org/)
[![Node.js](https://img.shields.io/badge/Node.js-18%2B-339933.svg?logo=node.js&logoColor=white)](https://nodejs.org/)
[![MCP](https://img.shields.io/badge/MCP-Compatible-6E56CF.svg)](https://modelcontextprotocol.io/)
[![npm](https://img.shields.io/npm/v/workbuddy-code-refactor-connector.svg?logo=npm&color=CB3837)](https://www.npmjs.com/package/workbuddy-code-refactor-connector)

一个基于本地大模型的代码重构服务。输入一段源代码和一句重构要求，输出重构后的完整代码。

**代码不离开你的机器** —— 核心版通过本地 Ollama 推理，无任何数据上传。

[快速开始](#-快速开始) · [功能](#-功能) · [使用方式](#-使用方式) · [定价](#-开源版与托管版) · [贡献](#-贡献)

</div>

---

## 这是什么

历史项目里总有些代码：能跑，但没人愿意碰。变量叫 `a`、`tmp1`、`data2`，三层嵌套的 `if` 里塞着业务逻辑，同一个校验规则在五个地方各写了一遍。

这个项目做的就是把这些代码改造好。它**不修复 bug、不添加功能**，只改结构——让代码好读、好改，同时保证外部行为完全不变。

核心能力由本地 [Ollama](https://ollama.com/) 上的代码模型（默认 `deepseek-coder`）驱动，可以以 **MCP Server**、**HTTP API**、**技能包** 等多种形态接入你现有的工作流。

## 功能

| 能力 | 说明 |
|---|---|
| **命名规范化** | 把 `f`、`a`、`tmp1` 改为能表达意图的命名 |
| **重复逻辑提取** | 识别重复代码片段，提取为独立函数或方法 |
| **控制流简化** | 嵌套条件改为提前返回（卫语句），合并冗余分支 |
| **类型标注补充** | 为 Python、TypeScript 补充类型标注 |
| **文档注释生成** | 按语言惯例补充 docstring / JSDoc / Javadoc |
| **语法现代化** | 回调改 `async/await`、`var` 改 `let/const`、循环改推导式 |

**支持语言**：Python · JavaScript · TypeScript · Java · Go · Rust · C · C++

### 设计原则

重构这件事，改坏比不改更糟。所以本项目有两条硬约束：

1. **不改公共接口** —— 函数名、类名、参数签名、返回值结构保持原样（除非你明确要求改）
2. **保持行为等价** —— 重构后逻辑与原代码一致，不顺手修 bug

## 快速开始

### 前置条件

- Python 3.11+ 或 Node.js 18+
- [Ollama](https://ollama.com/download) 已安装并运行
- 已拉取代码模型：`ollama pull deepseek-coder`

### 方式一：本地 Python 直接调用

```bash
git clone https://github.com/zhouhengchang/code-refactor.git
cd code-refactor
python shared/refactor_core.py   # 内置自测，会先检查服务再跑一个示例
```

也可以在自己的代码里调用：

```python
# -*- coding: utf-8 -*-
"""最小调用示例。"""

from shared.refactor_core import refactor_code, check_ollama_status

# 先确认环境就绪
print(check_ollama_status())

# 执行重构
result = refactor_code(
    code="def f(a):\n    r = []\n    for i in a:\n        if i % 2 == 0:\n            r.append(i * i)\n    return r\n",
    task="重命名为有意义的函数名与变量名，补充类型标注与中文注释",
    language="python",
)

if result["ok"]:
    print(result["code"])
else:
    print("失败：", result["error"])
```

### 方式二：作为 MCP Server 接入（Claude Desktop / WorkBuddy / 任意 MCP 客户端）

已发布到 npm，**不用克隆仓库**，直接在 MCP 客户端配置里引用：

```json
{
  "mcpServers": {
    "code-refactor": {
      "command": "npx",
      "args": ["-y", "workbuddy-code-refactor-connector"],
      "env": {
        "REFACTOR_BACKEND": "ollama",
        "OLLAMA_HOST": "http://localhost:11434",
        "OLLAMA_MODEL": "deepseek-coder"
      }
    }
  }
}
```

> npm 包：[workbuddy-code-refactor-connector](https://www.npmjs.com/package/workbuddy-code-refactor-connector)

也可以从源码运行，便于自己改代码：

```bash
cd workbuddy-connector/server
npm install
```

然后把上面的 `command` 改成 `node`，`args` 改成 `["/绝对路径/to/workbuddy-connector/server/index.js"]` 即可。

重启客户端后即可使用 `refactor_code` 和 `check_status` 两个工具。

### 方式三：Docker 部署 HTTP 服务

```bash
docker build -t code-refactor-xpack:1.0.0 -f xpack-server/Dockerfile .
docker run -p 8000:8000 \
  -e OLLAMA_HOST=http://host.docker.internal:11434 \
  -e OLLAMA_MODEL=deepseek-coder \
  code-refactor-xpack:1.0.0
```

调用：

```bash
curl -X POST http://localhost:8000/refactor \
  -H "Content-Type: application/json" \
  -d '{
    "code": "def f(a):\n    return [i*i for i in a if i % 2 == 0]\n",
    "task": "函数名与变量名改为有意义的命名，补充类型标注",
    "language": "python"
  }'
```

## 使用方式

### 输入

| 参数 | 必填 | 说明 |
|---|---|---|
| `code` | 是 | 待重构代码，≤ 20000 字符 |
| `task` | 是 | 重构要求，越具体效果越好 |
| `language` | 否 | 语言标识，不填自动判断 |

### 输出

```json
{
  "ok": true,
  "code": "重构后的完整代码",
  "model": "deepseek-coder",
  "language": "python",
  "elapsed_ms": 3820
}
```

失败时返回 `{"ok": false, "error": "可读中文错误信息", "error_type": "..."}`，**不抛异常、不暴露堆栈**。

### `task` 怎么写

这是影响结果质量最大的一个变量。

| 别这样写 | 换成这样 |
|---|---|
| 「优化一下」 | 「把五层嵌套 if 改为提前返回，提取重复的参数校验为独立函数」 |
| 「太乱了」 | 「统一命名规范，拆分超过 50 行的函数，补充中文注释」 |
| 「改写好点」 | 「把回调写法改为 async/await，保留原有的错误处理分支」 |

### 使用建议

- **一次一个目标。** 「重构 + 加功能」拆成两步做。
- **长代码分批。** 单次 ≤ 300 行为宜，按函数粒度提交。
- **结果先验证再应用。** 跑一遍现有测试再替换生产代码。

## 配置

全部通过环境变量注入，**代码中不含任何密钥**。

| 环境变量 | 默认值 | 说明 |
|---|---|---|
| `REFACTOR_BACKEND` | `ollama` | 推理后端：`ollama`（本地）或 `openai`（任意 OpenAI 兼容接口） |
| `OLLAMA_HOST` | `http://127.0.0.1:11434` | Ollama 服务地址 |
| `OLLAMA_MODEL` | `deepseek-coder` | 本地模型 |
| `OPENAI_BASE_URL` | `https://api.deepseek.com/v1` | 云端接口地址（`REFACTOR_BACKEND=openai` 时生效） |
| `OPENAI_API_KEY` | — | 云端密钥，**仅从环境变量读取，永不写进代码** |
| `OPENAI_MODEL` | `deepseek-flash` | 云端模型（DeepSeek 官方在列：`deepseek-flash` / `deepseek-v4-pro`） |
| `REFACTOR_TIMEOUT` | `180` | 超时秒数（Python） |
| `REFACTOR_TIMEOUT_MS` | `180000` | 超时毫秒数（Node.js） |

本地和云端两套后端**同一份代码**，切换只改环境变量：

```bash
# 改用云端 OpenAI 兼容接口
export REFACTOR_BACKEND=openai
export OPENAI_API_KEY=sk-xxxx
```

> 超时默认给到 180 秒，是因为在纯 CPU 的低配机器上本地推理可能需要 1 分钟以上。如果你的机器有 GPU，可以调小。

想用更小更快的本地模型：`OLLAMA_MODEL=qwen2.5-coder:1.5b`。

## 运维工具

`tools/` 下有两个自检脚本，改完配置或轮换密钥后建议跑一遍，避免"改完才发现用不了"：

| 脚本 | 作用 |
|---|---|
| `tools/rotate_key.py` | 密钥轮换：先校验**鉴权 / 余额 / 真实调用**三关，全过才允许写入；替换前自动备份，可一键回滚 |
| `tools/verify_online.py` | 线上体检：依次请求 `/healthz`、`/status`、`/refactor`，确认新配置在生产环境真正生效 |

```bash
# 只验证，不改任何文件
python tools/rotate_key.py --check --key sk-xxxx

# 验证通过后写入 .env
python tools/rotate_key.py --apply --key sk-xxxx

# 线上实例体检
python tools/verify_online.py https://your-host/
```

> `rotate_key.py` 只改 `.env` 里 `OPENAI_API_KEY` 一行，其余配置原样保留。

## 项目结构

```
code-refactor/
├── shared/refactor_core.py      # 核心逻辑（唯一真源）
├── workbuddy-connector/         # WorkBuddy / MCP 连接器
├── xpack-server/                # OpenAPI + FastAPI + Dockerfile
├── coze-skill/                  # 扣子技能包
├── skillhub-skill/              # SkillHub Pay Skill
├── alipay-ai/                   # 支付宝 AI收 接入配置
├── xinghuo-agent/               # 讯飞星火智能体配置
├── tools/                       # 密钥轮换与线上体检脚本
└── github-repo/                 # 本文档所在的开源仓库
```

## 开源版与托管版

本项目采用 **Freemium** 模式：核心能力完全开源免费，托管服务面向不想自己部署的用户。

| | **开源版（MIT）** | **托管版 Pro** |
|---|---|---|
| 价格 | 免费 | ¥29/月（含 200 次调用）<br>或 ¥1/次按需付费 |
| 部署 | 自己部署 Ollama | 无需部署，开箱即用 |
| 模型 | 你自己选的模型 | 更大的代码模型，效果更好 |
| 速度 | 取决于你的硬件 | GPU 加速，平均 3-5 秒响应 |
| 语言支持 | 8 种 | 8 种 + 优先级支持 |
| 批量重构 | 需自行封装 | 支持仓库级批量重构 |
| 私有部署 | — | 支持 |
| 支持 | 社区 Issue | 优先工单响应 |

**该选哪个？**

- 代码不能出内网 / 想完全掌控 → **开源版**，直接克隆部署
- 本机没有 GPU、不想折腾环境、需要更好的重构质量 → **托管版**

👉 **托管版入口：** <https://code-refactor.app.workbuddy.host>

> 托管版同样承诺：**代码仅用于本次推理，不留存、不用于模型训练。**

## 在各大平台使用

本服务已适配以下平台，可按需取用对应目录下的配置文件：

| 平台 | 形态 | 配置 / 入口 |
|---|---|---|
| **npm** | 可执行 MCP Server（已上线） | `npx -y workbuddy-code-refactor-connector` |
| WorkBuddy 开放平台 | Connector / MCP Server | `workbuddy-connector/` |
| XPack MCP 交易平台 | OpenAPI → MCP 服务 | `xpack-server/openapi.json` |
| 扣子（Coze） | 技能商店 Skill | `coze-skill/skill.json` |
| SkillHub | Pay Skill | `skillhub-skill/manifest.json` |
| 支付宝 AI收 | 按调用即时收款 | `alipay-ai/alipay-ai-config.json` |
| 讯飞星火 | 智能体 / 独立 API | `xinghuo-agent/agent-config.json` |

## 常见问题

**Q：为什么非要本地跑？云端 API 不是更方便？**
代码是核心资产。本地推理意味着你的代码一个字节都不会离开你的机器——这对企业代码库往往是硬性要求。想省事就用托管版。

**Q：重构会不会改坏我的代码？**
设计上不会改变外部行为，但这不构成保证。**上生产前请务必跑测试。** 项目的第一原则就是"不改接口、不改行为"，但模型输出总有不确定性，代码审查不可省。

**Q：支持多大的代码？**
单次 20000 字符以内，建议 300 行以内。更大的文件按函数拆分。

**Q：能只重构一个函数吗？**
可以，只把那个函数贴进来就行。

**Q：为什么用 `deepseek-coder`？**
在代码任务上表现稳定，是本地小体量模型里性价比较好的选择。你可以通过 `OLLAMA_MODEL` 换成任何 Ollama 模型。

> 注意：Ollama 上的 `deepseek-coder` 标签实际是 **约 776MB 的小体量版本**，并不是原版的 6.7B。算力允许的话，换成 `qwen2.5-coder:7b` 效果会明显更好。

**Q：响应慢怎么办？**
换更小的模型（`qwen2.5-coder:1.5b`）、缩小单次重构范围、或确认本机没有其他任务在抢 GPU。用托管版也能绕开本地算力限制。

## 贡献

欢迎 Issue 和 PR。特别需要这些方向的帮助：

- **新的重构模式** —— 你反复手动做的事，可能就是下一个内置能力
- **语言适配** —— 目前对 Kotlin、Swift、PHP 的支持还比较弱
- **测试用例** —— 尤其是"重构后行为保持一致"的验证用例

提 PR 前请确认：代码有中文注释、不含硬编码密钥、通过现有测试。

## 许可证

[MIT](LICENSE) —— 可自由商用、修改、分发。

---

<div align="center">

**如果这个项目帮你省下了清理遗留代码的时间，给个 ⭐ 是最好的鼓励。**

[赞助这个项目](https://github.com/sponsors/zhouhengchang) · [提交 Issue](https://github.com/zhouhengchang/code-refactor/issues)

</div>
