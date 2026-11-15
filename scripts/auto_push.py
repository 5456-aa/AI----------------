# -*- coding: utf-8 -*-
"""推送守护：等 github.com 可连通后自动 git push。

背景：本机到 github.com:443 时通时不通（取决于代理是否开启）。
本脚本每 30 秒探测一次，一旦连通就立刻推送；推送成功后自动退出。

用法：python scripts/auto_push.py [--interval 30] [--timeout 7200]
"""
from __future__ import annotations

import argparse
import socket
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOG = ROOT / "reports" / "_push_watch.log"
OK_FLAG = ROOT / "reports" / "_push_ok.txt"


def log(msg: str) -> None:
    line = f"[{datetime.now():%H:%M:%S}] {msg}"
    print(line, flush=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def reachable(host: str = "github.com", port: int = 443, timeout: int = 6) -> bool:
    try:
        socket.create_connection((host, port), timeout=timeout).close()
        return True
    except Exception:
        return False


def push() -> tuple[bool, str]:
    cmd = [ "git", "-c", "http.version=HTTP/1.1",
            "-c", "http.postBuffer=524288000", "push", "-u", "origin", "main" ]
    env = {"GIT_TERMINAL_PROMPT": "0"}
    import os
    e = dict(os.environ); e.update(env)
    r = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=600, env=e)
    out = (r.stdout + r.stderr).strip().splitlines()
    tail = out[-1] if out else ""
    return r.returncode == 0, tail


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--interval", type=int, default=30)
    ap.add_argument("--timeout", type=int, default=7200, help="最长守候秒数")
    args = ap.parse_args(argv)

    log("开始守候：等 github.com:443 可连通后自动推送")
    deadline = time.time() + args.timeout
    tries = 0

    while time.time() < deadline:
        tries += 1
        if reachable():
            log(f"第 {tries} 次探测：网络已连通，开始推送 …")
            try:
                ok, tail = push()
            except subprocess.TimeoutExpired:
                log("推送超时（10 分钟），30 秒后重试")
                time.sleep(args.interval)
                continue
            if ok:
                log("✅ 推送成功：" + tail)
                OK_FLAG.write_text(f"{datetime.now():%Y-%m-%d %H:%M:%S}\n{tail}\n",
                                   encoding="utf-8")
                return 0
            log(f"推送失败：{tail}")
        else:
            if tries % 10 == 1:
                log(f"第 {tries} 次探测：github.com 仍不可达（请确认代理已开启）")
        time.sleep(args.interval)

    log("守候超时，已退出。可稍后手动重跑本脚本。")
    return 1


if __name__ == "__main__":
    sys.exit(main())
