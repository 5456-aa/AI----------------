# -*- coding: utf-8 -*-
"""公网演示：把首页(8500) 与 分析看板(8501) 同时映射成临时 https 地址。

原理：调用 Cloudflare Quick Tunnel（无需账号），为每个端口开一条隧道，
从输出里解析出 trycloudflare.com 地址并打印。

安全约束：
  * 只暴露 8500 / 8501 两个只读页面，**不暴露标注工具（8502/8504）**
  * 服务须以 PUBLIC_DEMO=1 启动，此时分析看板会隐藏「模型设置」面板，
    防止陌生访客改写本机 .env
  * 隧道随窗口关闭而失效，地址每次重启都会变

用法（一般由 开启公网访问.bat 调用）：
  python scripts/serve_public.py
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CF = ROOT / "tools" / "cloudflared.exe"
PORTS = [8500]   # 单应用多页：只需一个端口

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore
except Exception:
    pass

URL_RE = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")


def watch(port: int, found: dict) -> None:
    proc = subprocess.Popen(
        [str(CF), "tunnel", "--no-autoupdate", "--url", f"http://localhost:{port}"],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        encoding="utf-8", errors="replace", bufsize=1)
    while True:
        line = proc.stdout.readline() if proc.stdout else ""
        if not line:
            if proc.poll() is not None:
                break
            time.sleep(0.2)
            continue
        m = URL_RE.search(line)
        if m and port not in found:
            found[port] = m.group(0)
            print(f"  ✅ {port}  →  {m.group(0)}", flush=True)


def main() -> int:
    if not CF.exists():
        print(f"[错误] 找不到 {CF}\n请到 Cloudflare 官网下载 cloudflared.exe 放到 tools/ 下")
        return 1
    if not os.environ.get("PUBLIC_DEMO"):
        print("[提示] 未设置 PUBLIC_DEMO=1，分析看板会显示模型设置面板（有被改写 .env 的风险）")

    found: dict[int, str] = {}
    for p in PORTS:
        threading.Thread(target=watch, args=(p, found), daemon=True).start()

    print("正在建立隧道，通常 10~20 秒 …\n", flush=True)
    deadline = time.time() + 60
    while time.time() < deadline and len(found) < len(PORTS):
        time.sleep(1)

    if not found:
        print("❌ 隧道建立失败：检查网络，或改用其它方案（见 docs/公网演示方案.md）")
        return 1

    # 把地址写给界面用：公网访客点「看板」时要用对应的公网地址
    try:
        import json as _json
        rt = ROOT / "data" / "runtime"
        rt.mkdir(parents=True, exist_ok=True)
        (rt / "public_urls.json").write_text(
            _json.dumps({"home": found.get(8500, ""),
                         "dashboard": found.get(8500, "")},
                        ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  地址已写入 {rt / 'public_urls.json'}（界面会自动引用）")
    except Exception as exc:
        print(f"  写入地址文件失败：{exc}")

    print("\n" + "=" * 64)
    print("  把这个地址发给评委（在浏览器或手机 4G 下都能打开）：")
    print(f"    首页（发起需求 / 批次总览）：{found.get(8500, '（未建立）')}")
    print("    进入后左侧可切换：首页 / 分析看板 / 问答咨询")
    print("=" * 64)
    print("\n注意：")
    print("  1. 地址每次重启都会变，重启后要重新发；")
    print("  2. 本窗口关闭 = 公网访问立即失效；")
    print("  3. 公网只暴露只读页面，采集与密钥设置仅在本机可用。")
    print("\n按 Ctrl+C 停止。\n")

    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        print("\n已停止。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
