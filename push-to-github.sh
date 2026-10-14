#!/usr/bin/env bash
# GitHub 一键推送脚本
# =====================
# 用法：先替换下方三个变量，然后执行 bash push-to-github.sh
#
# 前置条件（只需做一次）：
#   1. 在 GitHub 上创建一个空仓库（不要勾选 README/LICENSE，避免冲突）
#   2. 准备好 GitHub 用户名与 Personal Access Token
#      Token 生成地址：https://github.com/settings/tokens
#      勾选权限：repo（完整仓库访问）
#
# ⚠️ 安全提示：Token 等同于密码，不要把本脚本连同真实 Token 提交到任何仓库。
#    推荐改用下方「方式二」的环境变量写法。

set -euo pipefail

# ============ 需要你修改的配置 ============
GITHUB_USER="your-username"                 # 你的 GitHub 用户名
REPO_NAME="code-refactor"                   # 仓库名
GITHUB_TOKEN="${GITHUB_TOKEN:-}"            # 建议用环境变量传入，不要写死在这里
# =========================================

cd "$(dirname "$0")"

if [ "$GITHUB_USER" = "your-username" ]; then
  echo "❌ 请先在脚本中把 GITHUB_USER 改为你的 GitHub 用户名"
  exit 1
fi

if [ -z "$GITHUB_TOKEN" ]; then
  echo "❌ 未检测到 GITHUB_TOKEN"
  echo "   请这样运行："
  echo "   export GITHUB_TOKEN='你的token'"
  echo "   bash push-to-github.sh"
  echo
  echo "   Token 生成地址：https://github.com/settings/tokens（勾选 repo 权限）"
  exit 1
fi

echo "=== 1. 检查当前状态 ==="
git status --short
echo "分支：$(git branch --show-current)"
echo

echo "=== 2. 配置远程仓库 ==="
REMOTE_URL="https://${GITHUB_USER}:${GITHUB_TOKEN}@github.com/${GITHUB_USER}/${REPO_NAME}.git"
if git remote get-url origin >/dev/null 2>&1; then
  git remote set-url origin "$REMOTE_URL"
  echo "  已更新 origin"
else
  git remote add origin "$REMOTE_URL"
  echo "  已添加 origin"
fi
# 避免 Token 落盘到 .git/config 明文（推送完可选择移除远程）
echo

echo "=== 3. 推送到 GitHub ==="
git push -u origin main
echo

echo "=== 4. 清理凭据 ==="
# 把带 Token 的 URL 换回不带 Token 的形式，防止明文长期留存
git remote set-url origin "https://github.com/${GITHUB_USER}/${REPO_NAME}.git"
echo "  已移除远程 URL 中的 Token"
echo

echo "✅ 推送完成"
echo "   仓库地址：https://github.com/${GITHUB_USER}/${REPO_NAME}"
