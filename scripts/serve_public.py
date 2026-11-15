# -*- coding: utf-8 -*-
"""公网演示：把本机 8500 映射成临时 https 地址，并自动重连。

特性：
  * 隧道断开 / 健康检查连续失败 → 自动重建，并打印新地址
  * 地址实时写入 data/runtime/public_urls.json，界面自动引用
  * Ctrl+C 退出时清理子进程

安全：只暴露 8500（单应用多页）；公网请求由 ui/auth.py 按 Host 自动降权。
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CF = ROOT / "tools" / "cloudflared.exe"
PORT = 8500
URL_FILE = ROOT / "data" / "runtime" / "public_urls.json"

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore
except Exception:
    pass

URL_RE = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")
HEALTH_TIMEOUT = 20
IDLE_CHECK = 20
MAX_FAILS = 3


def save_url(url: str) -> None:
    URL_FILE.parent.mkdir(parents=True, exist_ok=True)
    URL_FILE.write_text(json.dumps({"home": url, "dashboard": url},
                                   ensure_ascii=False, indent=2), encoding="utf-8")


def start_tunnel():
    proc = subprocess.Popen(
        [str(CF), "tunnel", "--no-autoupdate", "--url", f"http://localhost:{PORT}"],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        encoding="utf-8", errors="replace", bufsize=1)
    deadline = time.time() + 60
    url = None
    while time.time() < deadline:
        line = proc.stdout.readline() if proc.stdout else ""
        if not line:
            if proc.poll() is not None:
                break
            time.sleep(0.2)
            continue
        m = URL_RE.search(line)
        if m:
            url = m.group(0)
            break
    return proc, url


def healthy(url):
    if not url:
        return False
    try:
        import requests
        return requests.get(f"{url}/_stcore/health", timeout=HEALTH_TIMEOUT).status_code == 200
    except Exception:
        return False


def banner(url: str) -> None:
    print("\n" + "=" * 68)
    print("  公网演示已就绪 —— 把这个地址发给评委 / 队友")
    print(f"    {url}")
    print("  进入后左侧切换：首页 / 分析看板 / 问答咨询")
    print("=" * 68)
    print("  · 地址每次重连都会变，变了会在这里打印新地址；")
    print("  · 本窗口关闭 = 公网访问立即失效；")
    print("  · 公网只读：可浏览 + 离线采集，不能改配置。\n")


def main() -> int:
    if not CF.exists():
        print(f"[错误] 找不到 {CF}")
        return 1
    if not healthy(f"http://127.0.0.1:{PORT}"):
        print(f"[警告] 本机 {PORT} 没有响应，先运行 启动系统.bat")

    round_no = 0
    while True:
        round_no += 1
        print(f"[第 {round_no} 次] 建立隧道 …", flush=True)
        proc, url = start_tunnel()
        if not url:
            print("  建立失败，10 秒后重试", flush=True)
            try:
                proc.kill()
            except Exception:
                pass
            time.sleep(10)
            continue

        save_url(url)
        banner(url)

        fails = 0
        try:
            while True:
                time.sleep(IDLE_CHECK)
                if proc.poll() is not None:
                    print("  ⚠ 隧道进程退出，准备重连", flush=True)
                    break
                if healthy(url):
                    fails = 0
                else:
                    fails += 1
                    print(f"  ⚠ 健康检查失败 {fails}/{MAX_FAILS}", flush=True)
                    if fails >= MAX_FAILS:
                        print("  → 连续失败，重建隧道", flush=True)
                        break
        except KeyboardInterrupt:
            print("\n已手动停止。")
            return 0
        finally:
            try:
                proc.kill()
            except Exception:
                pass
        time.sleep(3)


if __name__ == "__main__":
    sys.exit(main())
