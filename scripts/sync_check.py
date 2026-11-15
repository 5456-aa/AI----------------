# -*- coding: utf-8 -*-
"""一键同步检查：本地改了什么 / 能不能跑 / 要不要推。

场景：项目可能被多个会话或队友同时改动，容易「本地能跑、云端崩」。
本脚本按顺序做四件事：

  1. 列出未提交与未推送的改动
  2. 对三个界面做冒烟测试（Streamlit AppTest），有异常就停
  3. 扫描敏感文件（.env 等）与明文密钥
  4. 可选：提交并推送到 GitHub

用法：
  python scripts/sync_check.py                 # 只检查
  python scripts/sync_check.py --commit "说明"  # 检查通过后提交
  python scripts/sync_check.py --push          # 提交后推送
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "ui"))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore
except Exception:
    pass

PAGES = ["ui/home.py", "ui/app.py", "ui/qa.py"]


def sh(args: list[str]) -> str:
    r = subprocess.run(args, cwd=str(ROOT), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return (r.stdout + r.stderr).strip()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--commit", default=None, help="提交说明；给了才会提交")
    ap.add_argument("--push", action="store_true", help="提交后推送到 origin")
    args = ap.parse_args(argv)

    ok = True

    # 1 改动概览
    print("=" * 60)
    print("1) 本地改动")
    status = sh(["git", "status", "--short"])
    if not status:
        print("   工作区干净")
    else:
        lines = status.splitlines()
        print(f"   共 {len(lines)} 项：")
        for ln in lines[:20]:
            print("   " + ln)
        if len(lines) > 20:
            print(f"   … 还有 {len(lines)-20} 项")

    ahead = sh(["git", "rev-list", "--count", "origin/main..HEAD"])
    if ahead.isdigit() and int(ahead) > 0:
        print(f"   ⚠ 有 {ahead} 个提交尚未推送")

    # 2 冒烟测试
    print("\n2) 界面冒烟测试")
    try:
        from streamlit.testing.v1 import AppTest
        for f in PAGES:
            try:
                at = AppTest.from_file(str(ROOT / f), default_timeout=120)
                at.run()
                n = len(list(at.exception))
                if n:
                    ok = False
                    print(f"   ❌ {f}  异常 {n}：{str(at.exception[0].value)[:100]}")
                else:
                    print(f"   ✅ {f}")
            except Exception as exc:
                ok = False
                print(f"   ❌ {f} 启动失败：{type(exc).__name__}: {str(exc)[:100]}")
    except Exception as exc:
        print(f"   ⚠ 跳过（streamlit 未安装？{type(exc).__name__}）")

    # 3 敏感检查
    print("\n3) 敏感文件")
    tracked = sh(["git", "ls-files"]).splitlines()
    bad = [f for f in tracked if f.endswith(".env") or "cloudflared" in f]
    if bad:
        ok = False
        print("   ❌ 仓库里有关键文件：" + ", ".join(bad[:5]))
    else:
        print("   ✅ 无 .env / 工具二进制入仓")
    try:
        from security import scan  # type: ignore
        hits = scan(ROOT)
        if hits:
            ok = False
            print(f"   ❌ 发现 {len(hits)} 处疑似明文密钥")
        else:
            print("   ✅ 无明文密钥")
    except Exception:
        print("   （密钥扫描跳过）")

    # 4 提交 / 推送
    if args.commit:
        if not ok:
            print("\n❌ 检查未通过，已终止提交。先修问题再跑。")
            return 1
        print(f"\n4) 提交：{args.commit}")
        sh(["git", "add", "-A"])
        env = dict(os.environ, GIT_TERMINAL_PROMPT="0")
        r = subprocess.run(["git", "-c", "user.name=AI-Opp Team",
                            "-c", "user.email=ai-opp@example.com",
                            "commit", "-q", "-m", args.commit],
                           cwd=str(ROOT), capture_output=True, text=True, env=env)
        if r.returncode != 0:
            print("   提交失败：" + (r.stdout + r.stderr).strip()[:200])
            return 1
        print("   ✅ 已提交：" + sh(["git", "log", "--oneline", "-1"]))

        if args.push:
            print("\n5) 推送")
            r = subprocess.run(["git", "-c", "http.version=HTTP/1.1",
                                "-c", "http.postBuffer=524288000",
                                "push", "origin", "main"],
                               cwd=str(ROOT), capture_output=True, text=True, env=env)
            out = (r.stdout + r.stderr).strip().splitlines()
            print("   " + (out[-1] if out else ""))
            if r.returncode != 0:
                print("   ❌ 推送失败（多为网络/代理问题），重跑本脚本即可")
                return 1
            print("   ✅ 已推送，Streamlit Cloud 会在 1~2 分钟内自动重建")

    print("\n" + "=" * 60)
    print("结论：" + ("✅ 可以提交" if ok else "❌ 有问题，先修"))
    if not args.commit and ok:
        print('提交命令：python scripts/sync_check.py --commit "说明" --push')
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
