#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
线上实例验证脚本
=================

对一个或多个线上地址依次做检查：
1. GET  /healthz  存活探针
2. GET  /status   后端与模型
3. POST /refactor 真实重构（会消耗少量模型额度）

用法：
    python tools/verify_online.py https://code-refactor.app.workbuddy.host/ \
                                  https://code-refactor-api.app.workbuddy.host/
"""

import json
import sys
import time
import urllib.error
import urllib.request

SAMPLE = "def f(a,b):\n    r=[]\n    for i in range(len(a)):\n        if a[i]%2==0:\n            r.append(a[i]*b)\n    return r\n"
TASK = "改写成更清晰的 Python，加类型注解和文档字符串"


def call(base: str, path: str, payload: dict | None = None, timeout: int = 180):
    """调用线上接口，返回 (状态码, JSON 或错误文本, 耗时秒)。"""
    url = base.rstrip("/") + path
    data = json.dumps(payload).encode() if payload else None
    req = urllib.request.Request(url, data=data, method="POST" if data else "GET")
    if data:
        req.add_header("Content-Type", "application/json")
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", "replace")
            try:
                return resp.status, json.loads(body), time.time() - t0
            except json.JSONDecodeError:
                return resp.status, body[:200], time.time() - t0
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")[:300], time.time() - t0
    except Exception as exc:
        return 0, repr(exc), time.time() - t0


def main() -> int:
    urls = sys.argv[1:]
    if not urls:
        print("用法: python tools/verify_online.py <url> [url...]")
        return 2

    failed = 0
    for base in urls:
        print(f"########## {base} ##########")

        code, body, dt = call(base, "/healthz", timeout=30)
        print(f"  /healthz   → {code} ({dt:.1f}s)")

        code, body, dt = call(base, "/status", timeout=60)
        if code == 200 and isinstance(body, dict):
            print(f"  /status    → {code} backend={body.get('backend')} "
                  f"model={body.get('model')} available={body.get('available')}")
        else:
            failed += 1
            print(f"  /status    → {code} {str(body)[:200]}")

        code, body, dt = call(base, "/refactor", {"code": SAMPLE, "task": TASK, "language": "python"})
        if code == 200 and isinstance(body, dict) and body.get("code"):
            out = body["code"]
            print(f"  /refactor  → {code} ({dt:.1f}s) 输出 {len(out)} 字符，首行：{out.splitlines()[0][:60]}")
        else:
            failed += 1
            print(f"  /refactor  → {code} ({dt:.1f}s) {str(body)[:300]}")
        print()

    print("全部通过" if failed == 0 else f"有 {failed} 项失败")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
