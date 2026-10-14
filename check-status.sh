#!/usr/bin/env bash
# 上线准备状态检查脚本
# ======================
# 用法：bash check-status.sh
# 作用：一键检查所有平台的准备进度，告诉你还差什么。

cd "$(dirname "$0")" || exit 1

PASS="✅"
FAIL="❌"
WARN="⚠️ "

echo "=========================================="
echo "  代码重构服务 —— 上线准备状态"
echo "=========================================="
echo

# ---------- 1. 环境 ----------
echo "【环境】"
export PATH="$PATH:$LOCALAPPDATA/Programs/Ollama"

if command -v python >/dev/null 2>&1; then
  echo "  $PASS Python: $(python --version 2>&1)"
else
  echo "  $FAIL Python 未找到"
fi

NODE="C:/Users/周恒昌/.workbuddy/binaries/node/versions/22.22.2-6/node.exe"
if [ -f "$NODE" ]; then
  echo "  $PASS Node: $("$NODE" --version 2>&1)"
else
  echo "  $FAIL Node 未找到"
fi

# Ollama 服务
if curl -s -m 3 http://localhost:11434/api/tags >/dev/null 2>&1; then
  echo "  $PASS Ollama 服务运行中"
  MODELS=$(curl -s -m 3 http://localhost:11434/api/tags | grep -o '"name":"[^"]*"' | cut -d'"' -f4 | tr '\n' ' ')
  echo "       已装模型: $MODELS"
else
  echo "  $WARN Ollama 服务未运行"
fi
echo

# ---------- 2. 推理后端 ----------
echo "【推理后端】"
BACKEND="${REFACTOR_BACKEND:-ollama}"
echo "  当前后端: $BACKEND"
if [ "$BACKEND" = "openai" ]; then
  if [ -n "${OPENAI_API_KEY:-}" ]; then
    echo "  $PASS OPENAI_API_KEY 已配置"
  else
    echo "  $FAIL OPENAI_API_KEY 未配置，云端后端无法工作"
  fi
else
  echo "  $WARN 使用本地 Ollama：实测单次 35-90 秒，超出 30 秒承诺"
  echo "       建议设置 REFACTOR_BACKEND=openai 并配置 OPENAI_API_KEY"
fi
echo

# ---------- 3. 交付物 ----------
echo "【交付物】"
for f in "README.md" "上线可行性报告.md" "上线操作手册.md" "凭据与操作清单.md"; do
  [ -f "$f" ] && echo "  $PASS $f" || echo "  $FAIL $f 缺失"
done
[ -f "dist/code-refactor-connector-1.0.0.zip" ] \
  && echo "  $PASS dist/code-refactor-connector-1.0.0.zip ($(du -h dist/code-refactor-connector-1.0.0.zip | cut -f1))" \
  || echo "  $FAIL 连接器 zip 未打包"
echo

# ---------- 4. GitHub ----------
echo "【GitHub】"
cd github-repo 2>/dev/null || { echo "  $FAIL 目录不存在"; exit 1; }
echo "  分支: $(git branch --show-current 2>&1)"
echo "  提交数: $(git rev-list --count HEAD 2>&1)"
echo "  文件数: $(git ls-files | wc -l | tr -d ' ')"
if git remote get-url origin >/dev/null 2>&1; then
  echo "  $PASS 远程仓库已配置: $(git remote get-url origin)"
else
  echo "  $WARN 远程仓库未配置 —— 需先创建 GitHub 仓库并执行 push-to-github.sh"
fi
# 密钥检查
if git grep -qEi "(api[_-]?key|secret|password)\s*[:=]\s*[\"'][A-Za-z0-9_\-]{16,}" HEAD 2>/dev/null; then
  echo "  $FAIL 检测到疑似硬编码密钥，请检查！"
else
  echo "  $PASS 无硬编码密钥"
fi
cd ..
echo

# ---------- 5. npm ----------
echo "【npm 包】"
NPM="C:/Users/周恒昌/.workbuddy/binaries/node/versions/22.22.2-6/npm.cmd"
if "$NPM" whoami >/dev/null 2>&1; then
  echo "  $PASS 已登录: $("$NPM" whoami 2>&1)"
  echo "       可执行: cd workbuddy-connector/server && npm publish --access public"
else
  echo "  $WARN 未登录 npm —— 需先执行 npm login"
fi
echo

# ---------- 6. 各平台材料 ----------
echo "【各平台提交材料】"
declare -A PLATFORM_FILES=(
  ["WorkBuddy"]="workbuddy-connector/connector-meta.json"
  ["XPack"]="xpack-server/openapi.json"
  ["扣子"]="coze-skill/skill.json"
  ["SkillHub"]="skillhub-skill/manifest.json"
  ["支付宝"]="alipay-ai/alipay-ai-config.json"
  ["讯飞星火"]="xinghuo-agent/agent-config.json"
)
for name in "WorkBuddy" "XPack" "扣子" "SkillHub" "支付宝" "讯飞星火"; do
  f="${PLATFORM_FILES[$name]}"
  [ -f "$f" ] && echo "  $PASS $name" || echo "  $FAIL $name ($f 缺失)"
done
echo

# ---------- 7. 占位符 ----------
echo "【待替换占位符】"
COUNT=$(grep -rn "your-org\|your-username\|your-domain" \
  --include="*.json" --include="*.md" --include="*.yml" . 2>/dev/null | grep -v "^./凭据" | wc -l | tr -d ' ')
if [ "$COUNT" -gt 0 ]; then
  echo "  $WARN 发现 $COUNT 处占位符待替换"
  echo "       执行以下命令查看："
  echo "       grep -rn 'your-org\\|your-username\\|your-domain' --include='*.json' --include='*.md' --include='*.yml' ."
else
  echo "  $PASS 无占位符"
fi
echo

echo "=========================================="
echo "  检查完成"
echo "=========================================="
