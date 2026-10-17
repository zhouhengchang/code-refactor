#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DeepSeek API Key 安全轮换工具
==============================

背景：旧 Key 在对话/日志中出现过，必须轮换；但新 Key 是否真的可用
（是否充值、模型是否可调）不能靠猜。本工具先验证、后替换，
验证不通过则一个字节都不改，避免"换完 Key 服务直接 402"。

用法
----
    # 1) 先看结论，不改任何文件（推荐每次都先跑这个）
    python tools/rotate_key.py --check --key sk-xxxx

    # 2) 验证通过后再真正写入两个部署目录的 .env
    python tools/rotate_key.py --apply --key sk-xxxx

    # 3) 从环境变量读 Key（避免出现在命令行历史里）
    NEW_KEY=sk-xxxx python tools/rotate_key.py --check

验证三道关
----------
1. 鉴权：GET /models 必须 200（证明 Key 本身合法）
2. 余额：GET /user/balance 必须 is_available=true 且 total_balance>0
3. 真调用：POST /v1/chat/completions 必须 200 且 content 非空

设计约束
--------
- 源码中不出现任何密钥，Key 只从参数/环境变量传入
- 替换前自动备份为 .env.bak.<时间戳>，可一键回滚
- 只改 OPENAI_API_KEY 一行，其余配置原样保留
"""

import argparse
import json
import os
import shutil
import sys
import time
import urllib.error
import urllib.request

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# 需要同步替换 Key 的部署目录（每个目录一份 .env）
TARGET_DIRS = ["deploy", "deploy-service"]

API_ROOT = "https://api.deepseek.com"
TIMEOUT = 30


def _request(url: str, key: str, payload: dict | None = None) -> tuple[int, dict]:
    """发一个带鉴权的请求，返回 (HTTP 状态码, 解析后的 JSON)。

    :param url: 完整 URL
    :param key: API Key
    :param payload: 非空则用 POST 发 JSON
    :return: (状态码, 响应体)；网络异常时状态码为 0
    """
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, method="POST" if data else "GET")
    req.add_header("Authorization", "Bearer " + key)
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        try:
            return exc.code, json.loads(body)
        except json.JSONDecodeError:
            return exc.code, {"raw": body}
    except Exception as exc:  # 网络不可达 / 超时
        return 0, {"raw": repr(exc)}


def verify_key(key: str) -> tuple[bool, list[str]]:
    """对 Key 做三道校验，返回 (是否可用, 每道关的说明行)。

    :param key: 待验证的 API Key
    :return: (通过为 True, 人类可读的检查明细)
    """
    lines: list[str] = []
    ok = True

    # ---- 第 1 关：鉴权 ----
    status, body = _request(API_ROOT + "/v1/models", key)
    if status == 200:
        models = [m.get("id") for m in body.get("data", [])]
        lines.append(f"[1/3] 鉴权     : 200 OK，可用模型 {models}")
    else:
        lines.append(f"[1/3] 鉴权     : 失败（HTTP {status}）{json.dumps(body, ensure_ascii=False)[:200]}")
        return False, lines

    # ---- 第 2 关：余额 ----
    status, body = _request(API_ROOT + "/user/balance", key)
    if status != 200:
        lines.append(f"[2/3] 余额     : 查询失败（HTTP {status}）")
        return False, lines
    available = body.get("is_available")
    infos = body.get("balance_infos") or [{}]
    balance = infos[0].get("total_balance", "?")
    currency = infos[0].get("currency", "CNY")
    if available is True and balance not in ("0.00", "0", 0):
        lines.append(f"[2/3] 余额     : 可用，{balance} {currency}")
    else:
        ok = False
        lines.append(f"[2/3] 余额     : 不可用（is_available={available}, "
                     f"total_balance={balance} {currency}）→ 该账号未充值")

    # ---- 第 3 关：真实调用 ----
    model = os.environ.get("OPENAI_MODEL", "deepseek-chat")
    status, body = _request(
        API_ROOT + "/v1/chat/completions",
        key,
        {
            "model": model,
            "messages": [{"role": "user", "content": "只回答两个字：可用"}],
            "max_tokens": 64,
        },
    )
    if status == 200:
        choice = (body.get("choices") or [{}])[0]
        content = (choice.get("message") or {}).get("content") or ""
        usage = body.get("usage") or {}
        if content.strip():
            lines.append(f"[3/3] 真调用   : 200 OK，模型 {body.get('model')}，"
                         f"返回「{content.strip()[:20]}」，tokens={usage.get('total_tokens')}")
        else:
            ok = False
            lines.append(f"[3/3] 真调用   : 200 但正文为空"
                         f"（finish_reason={choice.get('finish_reason')}）")
    else:
        ok = False
        err = ((body.get("error") or {}).get("message") if isinstance(body, dict) else None) or body
        lines.append(f"[3/3] 真调用   : 失败（HTTP {status}）{str(err)[:160]}")

    return ok, lines


def replace_in_env(directory: str, new_key: str) -> str:
    """把某个部署目录 .env 里的 OPENAI_API_KEY 换成新值（其余内容不动）。

    :param directory: 相对 BASE_DIR 的子目录名
    :param new_key: 新 Key
    :return: 结果描述
    """
    env_path = os.path.join(BASE_DIR, directory, ".env")
    if not os.path.exists(env_path):
        return f"{directory}/.env 不存在，跳过"

    with open(env_path, "r", encoding="utf-8") as fh:
        original = fh.read()

    stamp = time.strftime("%Y%m%d-%H%M%S")
    backup = env_path + ".bak." + stamp
    shutil.copy2(env_path, backup)

    out_lines = []
    hit = False
    for line in original.splitlines():
        if line.strip().startswith("OPENAI_API_KEY="):
            out_lines.append("OPENAI_API_KEY=" + new_key)
            hit = True
        else:
            out_lines.append(line)
    if not hit:
        out_lines.append("OPENAI_API_KEY=" + new_key)

    # 先写临时文件再原子替换，避免写一半崩掉把配置弄坏
    tmp_path = env_path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(out_lines) + "\n")
    os.replace(tmp_path, env_path)

    return f"{directory}/.env 已更新（备份：{os.path.basename(backup)}）"


def mask(key: str) -> str:
    """脱敏显示 Key，只保留前 8 位与后 4 位。"""
    if len(key) <= 14:
        return key[:4] + "***"
    return f"{key[:8]}…{key[-4:]}（长度 {len(key)}）"


def main() -> int:
    parser = argparse.ArgumentParser(description="DeepSeek API Key 安全轮换")
    parser.add_argument("--key", help="新 Key；不传则读环境变量 NEW_KEY")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--check", action="store_true", help="只验证，不写入（默认行为）")
    group.add_argument("--apply", action="store_true", help="验证通过后写入 .env")
    args = parser.parse_args()

    key = (args.key or os.environ.get("NEW_KEY") or "").strip()
    if not key:
        print("错误：未提供 Key。用 --key sk-xxx 或设置环境变量 NEW_KEY。", file=sys.stderr)
        return 2

    print("待验证 Key：" + mask(key))
    ok, lines = verify_key(key)
    for line in lines:
        print("  " + line)

    if not ok:
        print("\n结论：该 Key 不可用，未修改任何文件。")
        print("常见原因：账号未充值 / Key 属于另一个账号 / Key 已删除。")
        return 1

    print("\n结论：该 Key 三关全过，可用于替换。")

    if not args.apply:
        print("当前为检查模式，未写入。确认无误后加 --apply 执行替换。")
        return 0

    print("\n开始写入：")
    for directory in TARGET_DIRS:
        print("  " + replace_in_env(directory, key))

    print("\n下一步：重新部署两个服务，使线上实例加载新 Key。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
