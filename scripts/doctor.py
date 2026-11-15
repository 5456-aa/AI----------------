# -*- coding: utf-8 -*-
"""运行环境自检（给评委/换机器用）。

一条命令回答三个问题：
  1. 这台机器能不能跑？（Python 版本、依赖、内存）
  2. 数据齐不齐？（结果文件、原始快照、缓存）
  3. 不联网能不能出结果？（离线跑一遍最小链路）

用法：
  python scripts/doctor.py            # 只检查，不改动
  python scripts/doctor.py --run      # 检查并实际离线跑一遍（约 20 秒）
"""
from __future__ import annotations

import argparse
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore
except Exception:
    pass

DEPS = [("yaml", "pyyaml"), ("requests", "requests"), ("numpy", "numpy"),
        ("pandas", "pandas"), ("sklearn", "scikit-learn"), ("jieba", "jieba"),
        ("matplotlib", "matplotlib"), ("streamlit", "streamlit")]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", action="store_true", help="实际离线跑一遍最小链路")
    args = ap.parse_args(argv)

    ok = True
    print("=" * 60)
    print("  AI 机会评估系统 · 运行环境自检")
    print("=" * 60)

    print(f"\n[1] 系统：{platform.system()} {platform.release()}　"
          f"Python {sys.version.split()[0]}")
    if sys.version_info < (3, 10):
        print("    ❌ 需要 Python 3.10 及以上")
        ok = False
    else:
        print("    ✅ Python 版本满足要求（≥3.10）")

    print("\n[2] 依赖：")
    missing = []
    for mod, pkg in DEPS:
        try:
            __import__(mod)
            print(f"    ✅ {pkg}")
        except Exception:
            print(f"    ❌ {pkg}（pip install {pkg}）")
            missing.append(pkg)
    if missing:
        ok = False

    print("\n[3] 数据：")
    need = ["config.yaml", "data/out/result1.csv", "data/out/result2.csv",
            "data/out/result3.csv", "data/out/result4.csv"]
    for f in need:
        p = ROOT / f
        if p.exists():
            print(f"    ✅ {f}（{p.stat().st_size/1024:.0f} KB）")
        else:
            print(f"    ❌ 缺少 {f}")
            ok = False
    cache = ROOT / "data" / "cache" / "llm_calls.jsonl"
    if cache.exists():
        n = sum(1 for _ in cache.open(encoding="utf-8", errors="ignore"))
        print(f"    ✅ 模型缓存 {n} 条（离线模式靠它，无需 API Key）")
    else:
        print("    ⚠ 没有模型缓存：离线模式无法命中，只能走纯规则")
    has_env = (ROOT / ".env").exists()
    print(f"    {'· 已配置 .env' if has_env else '· 无 .env（正常，离线可跑）'}")

    disk = shutil.disk_usage(str(ROOT))
    print(f"\n[4] 磁盘：可用 {disk.free/1024**3:.1f} GB（本项目约需 0.2 GB）")

    if args.run:
        print("\n[5] 离线跑一遍（清理→判别→导出，约 20 秒）…")
        # 先备份官方结果：自检用临时批次，跑完必须还原，避免污染提交结果
        import shutil as _sh
        import tempfile as _tf
        out_dir = ROOT / "data" / "out"
        backup = Path(_tf.mkdtemp(prefix="doctor_bak_"))
        for f in out_dir.glob("result*.csv"):
            _sh.copy2(f, backup / f.name)
        r = subprocess.run([sys.executable, "run_all.py", "--track", "all",
                            "--batch", "DOCTOR", "--offline", "--force",
                            "--no-proposal"], cwd=str(ROOT),
                           capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        tail = [ln for ln in r.stdout.splitlines() if "result" in ln or "判别完成" in ln]
        for ln in tail[-6:]:
            print("    " + ln.split("| ")[-1])
        if r.returncode == 0 and any("result1.csv" in ln for ln in tail):
            print("    ✅ 离线全流程正常")
        else:
            print("    ❌ 离线运行失败，日志：")
            print(r.stdout[-800:] or r.stderr[-800:])
            ok = False

        # 还原官方结果（无论成功失败）
        for f in backup.glob("result*.csv"):
            _sh.copy2(f, out_dir / f.name)
        _sh.rmtree(backup, ignore_errors=True)
        print("    （已还原原有结果文件，自检不影响提交内容）")

    print("\n" + "=" * 60)
    print("  结论：" + ("✅ 环境正常，可以运行" if ok else "❌ 存在问题，见上"))
    print("  下一步：双击 启动系统.bat（界面）或 跑全流程.bat（命令行）")
    print("=" * 60)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
