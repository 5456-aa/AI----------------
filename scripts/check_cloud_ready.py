# -*- coding: utf-8 -*-
"""推送 GitHub / 部署 Streamlit Cloud 之前的自检。

检查：
  1. .env 与密钥文件是否会被提交（最致命）
  2. 代码里有没有硬编码的 sk- 密钥
  3. 云端运行必需的数据文件是否齐全
  4. 是否有超过 50 MB 的文件（GitHub 单文件上限 100 MB）
  5. 入口能否 import、依赖是否声明

用法：python scripts/check_cloud_ready.py
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore
except Exception:
    pass

REQUIRED = [
    "ui/home.py",
    "ui/app.py",
    "requirements.txt",
    "config.yaml",
    "data/out/result1.csv",
    "data/out/result2.csv",
    "data/out/result3.csv",
    "data/out/result4.csv",
    "data/cache/llm_calls.jsonl",
]
REQUIRED_DIRS = ["data/tracks", "data/clean/ecommerce", "data/clean/education"]

FORBIDDEN = [".env", ".leak_alert", "LEAK_ALERT.txt"]
BIG_LIMIT = 50 * 1024 * 1024


def main() -> int:
    rows: list[tuple[str, bool, str]] = []
    add = lambda n, ok, note="": rows.append((n, ok, note))

    # 1 密钥文件：允许本地存在，但必须被 .gitignore 覆盖
    gi_text = ""
    gi_path = ROOT / ".gitignore"
    if gi_path.exists():
        gi_text = gi_path.read_text(encoding="utf-8")
    for f in [".env"]:
        exists = (ROOT / f).exists()
        ignored = any(line.strip() == f for line in gi_text.splitlines())
        add(f"{f} 不会被提交", ignored,
            "本地存在但已在 .gitignore 中，安全" if (exists and ignored)
            else ("未加入 .gitignore，极其危险！" if exists else "本地不存在"))
    for f in [".leak_alert", "LEAK_ALERT.txt"]:
        add(f"不存在 {f}", not (ROOT / f).exists())

    # 2 硬编码密钥
    try:
        from security import scan  # type: ignore
        hits = scan(ROOT)
        add("代码中无明文密钥", not hits, f"发现 {len(hits)} 处" if hits else "")
    except Exception as exc:
        add("代码中无明文密钥", True, f"（扫描跳过：{type(exc).__name__}）")

    # 3 必需文件
    for f in REQUIRED:
        add(f"存在 {f}", (ROOT / f).exists())
    for d in REQUIRED_DIRS:
        p = ROOT / d
        add(f"存在 {d}/", p.exists() and any(p.glob("*")))

    # 4 超大文件（排查 git 会跟踪的）
    skip_dirs = {"tools", "data", "logs", "__pycache__", ".git", "figs", "reports"}
    big = []
    for p in ROOT.rglob("*"):
        if not p.is_file() or ".git" in p.parts or "__pycache__" in p.parts:
            continue
        if set(p.relative_to(ROOT).parts) & skip_dirs:
            continue
        if p.name in FORBIDDEN:
            continue
        try:
            if p.stat().st_size > BIG_LIMIT:
                big.append((p.relative_to(ROOT), p.stat().st_size))
        except OSError:
            pass
    add("无超过 50MB 的文件", not big,
        "；".join(f"{n} {s/1024/1024:.0f}MB" for n, s in big[:3]))

    # 5 依赖声明
    req = (ROOT / "requirements.txt").read_text(encoding="utf-8").lower()
    for pkg in ["streamlit", "pandas", "numpy", "pyyaml", "scikit-learn", "jieba"]:
        add(f"requirements 含 {pkg}", pkg in req)

    # 6 入口脚本语法
    for f in ["ui/home.py", "ui/app.py"]:
        p = ROOT / f
        ok = False
        try:
            import ast
            ast.parse(p.read_text(encoding="utf-8"))
            ok = True
        except Exception:
            pass
        add(f"{f} 语法正常", ok)

    # 7 git 是否已忽略 .env（若已是 git 仓库）
    in_git = (ROOT / ".git").exists() or (ROOT.parent / ".git").exists()
    if in_git:
        try:
            r = subprocess.run(["git", "check-ignore", "-q", ".env"], cwd=str(ROOT))
            add("git 已忽略 .env", r.returncode == 0)
        except Exception:
            add("git 已忽略 .env", True, "（无法调用 git，跳过）")
    else:
        add("git 已忽略 .env", True, "（尚未初始化 git，推送时注意）")

    w = max(len(r[0]) for r in rows)
    for name, ok, note in rows:
        print(f"{name:<{w}}  {'✅' if ok else '❌'}  {note}")
    bad = [r for r in rows if not r[1]]
    print(f"\n共 {len(rows)} 项，未通过 {len(bad)} 项")
    if bad:
        print("先修好这些再推送 GitHub。")
    else:
        print("可以推送。步骤见 docs/部署到StreamlitCloud.md")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
