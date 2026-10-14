/**
 * MCP Server 本地测试脚本
 * =======================
 *
 * 通过 stdio 启动 server/index.js，发送标准 MCP 协议消息，
 * 验证 initialize / tools/list / tools/call 三个环节是否正常。
 *
 * 运行：node test-mcp.mjs
 */

import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const __dirname = dirname(fileURLToPath(import.meta.url));
const SERVER = join(__dirname, "index.js");

// 可用的测试模型：优先用环境变量，默认 deepseek-coder
const TEST_MODEL = process.env.TEST_MODEL || "deepseek-coder";

const child = spawn(process.execPath, [SERVER], {
  stdio: ["pipe", "pipe", "pipe"],
  env: { ...process.env, OLLAMA_MODEL: TEST_MODEL },
});

let buffer = "";
const pending = new Map();

// 按行解析 MCP 的 JSON-RPC 响应
child.stdout.on("data", (chunk) => {
  buffer += chunk.toString();
  let idx;
  while ((idx = buffer.indexOf("\n")) >= 0) {
    const line = buffer.slice(0, idx).trim();
    buffer = buffer.slice(idx + 1);
    if (!line) continue;
    try {
      const msg = JSON.parse(line);
      if (msg.id !== undefined && pending.has(msg.id)) {
        pending.get(msg.id)(msg);
        pending.delete(msg.id);
      }
    } catch {
      // 非 JSON 行忽略
    }
  }
});

child.stderr.on("data", (chunk) => {
  process.stderr.write(`[server] ${chunk}`);
});

/** 发送一个 JSON-RPC 请求并等待响应 */
function request(id, method, params = {}) {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error(`请求 ${method} 超时`)), 120000);
    pending.set(id, (msg) => {
      clearTimeout(timer);
      resolve(msg);
    });
    child.stdin.write(JSON.stringify({ jsonrpc: "2.0", id, method, params }) + "\n");
  });
}

function log(title, obj) {
  console.log(`\n=== ${title} ===`);
  console.log(typeof obj === "string" ? obj : JSON.stringify(obj, null, 2));
}

async function main() {
  // --- 1. initialize 握手 ---
  const init = await request(1, "initialize", {
    protocolVersion: "2024-11-05",
    capabilities: {},
    clientInfo: { name: "local-test", version: "1.0.0" },
  });
  log("1. initialize", {
    serverInfo: init.result?.serverInfo,
    protocolVersion: init.result?.protocolVersion,
  });

  // 通知服务器初始化完成（MCP 协议要求）
  child.stdin.write(JSON.stringify({ jsonrpc: "2.0", method: "notifications/initialized" }) + "\n");

  // --- 2. tools/list ---
  const tools = await request(2, "tools/list");
  const names = (tools.result?.tools || []).map((t) => t.name);
  log("2. tools/list", { tools: names });

  // --- 3. tools/call: check_status ---
  const status = await request(3, "tools/call", { name: "check_status", arguments: {} });
  const statusText = status.result?.content?.[0]?.text || "";
  let statusObj = {};
  try {
    statusObj = JSON.parse(statusText);
  } catch {
    statusObj = { raw: statusText };
  }
  log("3. check_status", {
    available: statusObj.available,
    model: statusObj.model,
    installed_models: statusObj.installed_models,
    message: statusObj.message,
  });

  if (!statusObj.available) {
    console.log(`\n⚠️  模型 ${TEST_MODEL} 不可用，跳过 refactor_code 实测。`);
    console.log(`   可执行 ollama pull ${TEST_MODEL} 后重试，或用 TEST_MODEL=已装模型 运行本脚本。`);
    child.kill();
    process.exit(0);
  }

  // --- 4. tools/call: refactor_code（计时验证 30 秒承诺）---
  const started = Date.now();
  const call = await request(4, "tools/call", {
    name: "refactor_code",
    arguments: {
      code: "def f(a):\n    r = []\n    for i in a:\n        if i % 2 == 0:\n            r.append(i * i)\n    return r\n",
      task: "变量名改为有意义的命名，补充类型标注与中文注释",
      language: "python",
    },
  });
  const wallMs = Date.now() - started;

  const text = call.result?.content?.[0]?.text || "";
  let result = {};
  try {
    result = JSON.parse(text);
  } catch {
    result = { raw: text };
  }

  log("4. refactor_code", {
    ok: result.ok,
    model: result.model,
    elapsed_ms: result.elapsed_ms,
    wall_clock_ms: wallMs,
    within_30s: wallMs <= 30000,
    error: result.error,
  });

  if (result.ok) {
    console.log("\n--- 重构后的代码 ---");
    console.log(result.code);
  }

  console.log(`\n【结论】端到端耗时 ${wallMs} ms，${wallMs <= 30000 ? "✅ 满足" : "❌ 超出"} 30 秒响应承诺。`);
  child.kill();
  process.exit(0);
}

main().catch((err) => {
  console.error("测试失败：", err.message);
  child.kill();
  process.exit(1);
});
