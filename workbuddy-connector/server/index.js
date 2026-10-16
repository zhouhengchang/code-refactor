#!/usr/bin/env node
/**
 * WorkBuddy 代码重构连接器 —— MCP Server 实现
 * ============================================
 *
 * 该服务基于 @modelcontextprotocol/sdk 实现 Model Context Protocol，
 * 通过 stdio 传输与 WorkBuddy 主程序通信，暴露两个工具：
 *
 *   1. refactor_code(code, task, language?) —— 执行代码重构
 *   2. check_status()                      —— 检查推理后端可用性
 *
 * 设计要点：
 * - 支持两种推理后端（环境变量 REFACTOR_BACKEND 切换）：
 *     ollama —— 调用本地 Ollama，代码不出本机（默认）
 *     openai —— 调用 OpenAI 兼容的云端接口（如需更高的重构质量）
 * - 地址、模型名与密钥一律从环境变量读取，绝不硬编码任何密钥。
 * - 所有工具调用都有超时保护（默认 180 秒，可用 REFACTOR_TIMEOUT_MS 覆盖），
 *   本地纯 CPU 推理较慢，故默认值取得较宽。
 * - 任何异常都被转换为用户可读的中文错误信息，而不是抛出堆栈。
 */

import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
} from "@modelcontextprotocol/sdk/types.js";

// ---------------------------------------------------------------------------
// 配置：全部来自环境变量，带安全默认值
// ---------------------------------------------------------------------------

/**
 * 推理后端类型：
 * - "ollama"（默认）调用本地 Ollama 服务，代码不出本机
 * - "openai" 调用 OpenAI 兼容的云端接口（DeepSeek / 硅基流动等）
 */
const BACKEND = (process.env.REFACTOR_BACKEND || "ollama").toLowerCase();

/** Ollama 服务地址，例如 http://127.0.0.1:11434 */
const OLLAMA_HOST = (process.env.OLLAMA_HOST || "http://127.0.0.1:11434").replace(/\/+$/, "");

/** 本地 Ollama 使用的模型 */
const OLLAMA_MODEL = process.env.OLLAMA_MODEL || "deepseek-coder";

/** 云端 OpenAI 兼容接口地址与模型（deepseek-chat 为实测可用的模型 ID） */
const OPENAI_BASE_URL = (process.env.OPENAI_BASE_URL || "https://api.deepseek.com/v1").replace(/\/+$/, "");
const OPENAI_MODEL = process.env.OPENAI_MODEL || "deepseek-flash";

/** 当前后端实际使用的模型名 */
const ACTIVE_MODEL = BACKEND === "openai" ? OPENAI_MODEL : OLLAMA_MODEL;

/**
 * 单次请求超时（毫秒）。
 * 本地低配机器（纯 CPU 推理）单次耗时可达 35-90 秒，故默认放宽到 180 秒；
 * 云端接口较快，可通过 REFACTOR_TIMEOUT_MS 覆盖。
 */
const REQUEST_TIMEOUT_MS = Number(process.env.REFACTOR_TIMEOUT_MS || 180000);

/** 服务名称与版本，会展示在 WorkBuddy 连接器详情中 */
const SERVER_NAME = "code-refactor";
const SERVER_VERSION = "1.0.0";

// ---------------------------------------------------------------------------
// 工具函数
// ---------------------------------------------------------------------------

/**
 * 构造发给代码模型的重构提示词。
 * 与 Python 侧 shared/refactor_core.py 中的提示词保持语义一致，
 * 确保各平台输出风格统一。
 *
 * @param {string} code 待重构的源代码
 * @param {string} task 重构任务描述
 * @param {string} [language] 可选的编程语言
 * @returns {string} 完整提示词
 */
function buildPrompt(code, task, language) {
  const langHint = language
    ? `这段代码使用的编程语言是 ${language}。`
    : "请先自行判断这段代码的编程语言。";
  return [
    "你是一名资深软件工程师，擅长把遗留代码重构为现代、可维护的规范代码。",
    langHint,
    "",
    "【重构任务】",
    task,
    "",
    "【待重构代码】",
    "```",
    code,
    "```",
    "",
    "【输出要求】",
    "1. 只输出重构后的完整代码，放在一个 Markdown 代码块中，不要输出任何额外解释。",
    "2. 必须保持原有的公共接口不变（函数名、类名、参数与返回值签名），除非任务明确要求修改。",
    "3. 保持原有业务逻辑等价，不要引入新的外部依赖。",
    "4. 补充必要的中文注释，说明关键改动点。",
  ].join("\n");
}

/**
 * 从模型输出中提取 Markdown 代码块。
 * 模型偶尔会附带解释文字，这里做一层容错处理。
 *
 * @param {string} text 模型原始输出
 * @returns {string} 提取后的代码
 */
function extractCodeBlock(text) {
  const raw = (text || "").trim();
  if (!raw.includes("```")) return raw;
  const parts = raw.split("```");
  if (parts.length >= 3) {
    const lines = parts[1].split("\n");
    // 去掉首行的语言标识（python / javascript 等）
    if (lines.length && /^[a-zA-Z+#]*\s*$/.test(lines[0])) {
      lines.shift();
    }
    return lines.join("\n").trim();
  }
  return raw;
}

/**
 * 带超时的 fetch 封装。
 * 使用 AbortController 实现，超时后抛出可读中文错误。
 *
 * @param {string} url 请求地址
 * @param {object} options fetch 选项
 * @param {number} timeoutMs 超时毫秒数
 * @returns {Promise<Response>}
 */
async function fetchWithTimeout(url, options, timeoutMs) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(url, { ...options, signal: controller.signal });
  } catch (err) {
    if (err && err.name === "AbortError") {
      throw new Error(`请求 Ollama 超时（超过 ${timeoutMs / 1000} 秒）。请检查模型规模，或改用更小的模型。`);
    }
    throw new Error(`无法连接 Ollama 服务（${OLLAMA_HOST}）。请确认 Ollama 已启动，并检查 OLLAMA_HOST 配置。`);
  } finally {
    clearTimeout(timer);
  }
}

/**
 * 检查推理后端是否可用。
 * 永不抛出异常，始终返回结构化对象。
 *
 * - ollama：请求 /api/tags 检查服务与模型列表
 * - openai：仅检查密钥是否配置，不发起请求（避免产生费用）
 *
 * @returns {Promise<object>} 状态对象
 */
async function checkBackendStatus() {
  // --- 云端后端：只检查密钥配置 ---
  if (BACKEND === "openai") {
    const hasKey = Boolean((process.env.OPENAI_API_KEY || "").trim());
    return {
      ok: true,
      available: hasKey,
      backend: "openai",
      base_url: OPENAI_BASE_URL,
      model: OPENAI_MODEL,
      message: hasKey
        ? `云端后端已配置，模型 ${OPENAI_MODEL} 可用。`
        : "云端后端未配置，请设置环境变量 OPENAI_API_KEY（密钥仅存于环境变量，不会写入代码）。",
    };
  }

  // --- 本地后端：请求 Ollama /api/tags ---
  try {
    const res = await fetchWithTimeout(`${OLLAMA_HOST}/api/tags`, { method: "GET" }, 5000);
    if (!res.ok) {
      return {
        ok: false,
        available: false,
        backend: "ollama",
        host: OLLAMA_HOST,
        model: OLLAMA_MODEL,
        message: `Ollama 服务返回异常状态码 HTTP ${res.status}。`,
      };
    }
    const data = await res.json();
    const models = (data.models || []).map((m) => m.name);
    // deepseek-coder 与 deepseek-coder:latest 视为同一模型
    const base = OLLAMA_MODEL.split(":")[0];
    const available = models.some((name) => name === OLLAMA_MODEL || name.split(":")[0] === base);
    return {
      ok: true,
      available,
      backend: "ollama",
      host: OLLAMA_HOST,
      model: OLLAMA_MODEL,
      installed_models: models,
      message: available
        ? `Ollama 服务正常，模型 ${OLLAMA_MODEL} 已就绪。`
        : `Ollama 服务正常，但未找到模型 ${OLLAMA_MODEL}，请先执行 ollama pull ${OLLAMA_MODEL}。`,
    };
  } catch (err) {
    return {
      ok: false,
      available: false,
      backend: "ollama",
      host: OLLAMA_HOST,
      model: OLLAMA_MODEL,
      message: err instanceof Error ? err.message : String(err),
    };
  }
}

/**
 * 调用 OpenAI 兼容的云端接口执行重构。
 *
 * @param {string} prompt 完整提示词
 * @returns {Promise<object>} 结构化结果
 */
async function callOpenAICompatible(prompt) {
  const apiKey = (process.env.OPENAI_API_KEY || "").trim();
  if (!apiKey) {
    return {
      ok: false,
      error: "使用云端后端时必须在环境变量 OPENAI_API_KEY 中配置 API 密钥。请设置后重试（密钥不会被写入代码或日志）。",
      error_type: "missing_api_key",
    };
  }

  const body = {
    model: OPENAI_MODEL,
    messages: [
      { role: "system", content: "你是一名资深软件工程师，擅长把遗留代码重构为现代、可维护的规范代码。" },
      { role: "user", content: prompt },
    ],
    temperature: 0.2,
    max_tokens: 4096,
    stream: false,
  };

  let res;
  try {
    res = await fetchWithTimeout(
      `${OPENAI_BASE_URL}/chat/completions`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${apiKey}` },
        body: JSON.stringify(body),
      },
      REQUEST_TIMEOUT_MS,
    );
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    return { ok: false, error: message, error_type: "backend_unreachable" };
  }

  if (!res.ok) {
    let detail = "";
    try {
      detail = (await res.text()).slice(0, 500);
    } catch {
      detail = "";
    }
    // 常见错误给出更有指向性的中文提示
    const hints = {
      401: "（密钥无效或已过期，请检查 OPENAI_API_KEY）",
      402: "（账户余额不足，请充值）",
      429: "（请求过于频繁或超出配额，请稍后重试）",
    };
    return {
      ok: false,
      error: `云端接口返回错误（HTTP ${res.status}）${hints[res.status] || ""}：${detail}`,
      error_type: "backend_error",
    };
  }

  const data = await res.json();
  const content = data?.choices?.[0]?.message?.content;
  if (!content) {
    return { ok: false, error: `云端接口返回结构异常：${JSON.stringify(data).slice(0, 300)}`, error_type: "bad_response" };
  }
  return { ok: true, raw: content };
}

/**
 * 调用 Ollama /api/generate 执行代码重构。
 *
 * @param {string} code 待重构代码
 * @param {string} task 重构任务
 * @param {string} [language] 编程语言
 * @returns {Promise<object>} 结构化结果
 */
async function refactorCode(code, task, language) {
  // 入参校验
  if (!code || !String(code).trim()) {
    return { ok: false, error: "参数 code 不能为空，请提供需要重构的代码片段。", error_type: "invalid_argument" };
  }
  if (!task || !String(task).trim()) {
    return { ok: false, error: "参数 task 不能为空，请说明希望如何重构。", error_type: "invalid_argument" };
  }
  if (String(code).length > 20000) {
    return {
      ok: false,
      error: `代码片段过长（${String(code).length} 字符），建议拆分到 20000 字符以内再提交。`,
      error_type: "payload_too_large",
    };
  }

  const prompt = buildPrompt(code, task, language);
  const started = Date.now();

  // --- 云端后端 ---
  if (BACKEND === "openai") {
    const r = await callOpenAICompatible(prompt);
    if (!r.ok) return r;
    const raw = (r.raw || "").trim();
    if (!raw) {
      return { ok: false, error: "模型返回了空内容，请重试。", error_type: "empty_response" };
    }
    return {
      ok: true,
      code: extractCodeBlock(raw),
      raw,
      model: OPENAI_MODEL,
      backend: "openai",
      language: language || "auto",
      elapsed_ms: Date.now() - started,
    };
  }

  // --- 本地 Ollama 后端 ---
  const body = {
    model: OLLAMA_MODEL,
    prompt,
    stream: false,
    options: { temperature: 0.2, num_predict: 2048 },
  };

  let res;
  try {
    res = await fetchWithTimeout(
      `${OLLAMA_HOST}/api/generate`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      },
      REQUEST_TIMEOUT_MS,
    );
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    return { ok: false, error: message, error_type: "ollama_unreachable" };
  }

  if (!res.ok) {
    let detail = "";
    try {
      detail = (await res.text()).slice(0, 500);
    } catch {
      detail = "";
    }
    const isNotFound = /not found|no such model/i.test(detail);
    return {
      ok: false,
      error: isNotFound
        ? `未找到模型 ${OLLAMA_MODEL}，请先执行 ollama pull ${OLLAMA_MODEL}。原始信息：${detail}`
        : `Ollama 服务返回错误（HTTP ${res.status}）：${detail}`,
      error_type: isNotFound ? "model_not_found" : "ollama_error",
    };
  }

  const data = await res.json();
  const raw = (data.response || "").trim();
  if (!raw) {
    return { ok: false, error: "模型返回了空内容，请重试或换用更大的模型。", error_type: "empty_response" };
  }

  return {
    ok: true,
    code: extractCodeBlock(raw),
    raw,
    model: OLLAMA_MODEL,
    backend: "ollama",
    language: language || "auto",
    elapsed_ms: Date.now() - started,
  };
}

// ---------------------------------------------------------------------------
// MCP Server 定义
// ---------------------------------------------------------------------------

const server = new Server(
  { name: SERVER_NAME, version: SERVER_VERSION },
  { capabilities: { tools: {} } },
);

// 声明可用工具列表（供 WorkBuddy 展示给模型）
server.setRequestHandler(ListToolsRequestSchema, async () => ({
  tools: [
    {
      name: "refactor_code",
      description:
        "将遗留代码自动重构为现代规范代码，支持 Python、JavaScript、Java 等语言。" +
        "输入待重构代码与重构任务描述，返回重构后的完整代码。适用于提炼函数、统一命名、" +
        "消除重复逻辑、补充类型标注与注释等场景。",
      inputSchema: {
        type: "object",
        properties: {
          code: { type: "string", description: "待重构的源代码片段" },
          task: { type: "string", description: "重构任务描述，例如：提取重复逻辑为独立函数并补充类型标注" },
          language: {
            type: "string",
            description: "可选的编程语言提示，例如 python、javascript、java；不填则由模型自动判断",
          },
        },
        required: ["code", "task"],
      },
    },
    {
      name: "check_status",
      description:
        "检查代码重构服务的推理后端是否可用（本地 Ollama 或云端 API），以及所需模型是否就绪。" +
        "在调用重构前建议先执行本工具确认环境。",
      inputSchema: { type: "object", properties: {} },
    },
  ],
}));

// 处理工具调用
server.setRequestHandler(CallToolRequestSchema, async (request) => {
  const { name, arguments: args = {} } = request.params;

  try {
    if (name === "refactor_code") {
      const result = await refactorCode(args.code, args.task, args.language);
      return {
        content: [{ type: "text", text: JSON.stringify(result, null, 2) }],
        isError: !result.ok,
      };
    }

    if (name === "check_status") {
      const result = await checkBackendStatus();
      return {
        content: [{ type: "text", text: JSON.stringify(result, null, 2) }],
        isError: !result.ok,
      };
    }

    return {
      content: [{ type: "text", text: `未知工具：${name}。本连接器仅提供 refactor_code 与 check_status 两个工具。` }],
      isError: true,
    };
  } catch (err) {
    // 兜底：任何未预期异常都转成可读中文信息，避免直接抛栈给用户
    const message = err instanceof Error ? err.message : String(err);
    return {
      content: [{ type: "text", text: `工具 ${name} 执行失败：${message}` }],
      isError: true,
    };
  }
});

// ---------------------------------------------------------------------------
// 启动：使用 stdio 传输
// ---------------------------------------------------------------------------

async function main() {
  const transport = new StdioServerTransport();
  await server.connect(transport);
  // 注意：stdio 模式下 stdout 被协议占用，日志必须写 stderr
  console.error(`[code-refactor] MCP Server 已启动 | 后端: ${BACKEND} | 模型: ${ACTIVE_MODEL}`);
}

main().catch((err) => {
  console.error("[code-refactor] MCP Server 启动失败：", err);
  process.exit(1);
});
