# -*- coding: utf-8 -*-
"""一键备份：把项目打成 zip，放在 ../backup/ 下。

包含：代码、配置、文档、原始数据、清洗结果、四个 CSV、报告、图表
排除：__pycache__、缓存、node_modules、.git、日志（可选保留）

用法：
    python scripts/backup.py               # 完整备份
    python scripts/backup.py --no-log      # 不包含 logs
"""
from __future__ import annotations

import argparse
import sys
import zipfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

EXCLUDE_DIRS = {
    "tools",          # cloudflared.exe（52MB，隧道实验用，与参赛无关）
    "__pycache__", ".git", "node_modules", ".venv", "venv", ".idea", ".vscode",
    ".pytest_cache", "dsh-browser",
}
EXCLUDE_FILES = {
    ".env.bak",          # 旧密钥备份（可能含历史 key，不打包）
}
EXCLUDE_PREFIX = (".env.bak.",)


def should_skip(rel: Path, include_log: bool) -> bool:
    parts = set(rel.parts)
    if parts & EXCLUDE_DIRS:
        return True
    if rel.name in EXCLUDE_FILES or rel.name.startswith(EXCLUDE_PREFIX):
        return True
    if not include_log and rel.parts and rel.parts[0] == "logs":
        return True
    if rel.suffix == ".pyc":
        return True
    return False


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-log", action="store_true", help="不打包 logs")
    ap.add_argument("--out", default=None, help="输出目录（默认 ../backup）")
    args = ap.parse_args(argv)

    out_dir = Path(args.out) if args.out else ROOT.parent / "backup"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    zip_path = out_dir / f"ai-opp-system_{stamp}.zip"

    n_files = 0
    n_bytes = 0
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in ROOT.rglob("*"):
            if not path.is_file():
                continue
            rel = path.relative_to(ROOT)
            if should_skip(rel, include_log=not args.no_log):
                continue
            zf.write(path, Path("ai-opp-system") / rel)
            n_files += 1
            n_bytes += path.stat().st_size

    print(f"备份完成：{zip_path}")
    print(f"  文件数 {n_files}，原始大小 {n_bytes / 1024 / 1024:.1f} MB，"
          f"压缩后 {zip_path.stat().st_size / 1024 / 1024:.1f} MB")

    has_env = (ROOT / ".env").exists()
    print(f"\n  含 .env：{'是（里面有本机 key，备份别外传）' if has_env else '否（未配置 key）'}")
    print("  说明：.env 里的 key 仅本机有效，恢复给别人用时对方要填自己的。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
