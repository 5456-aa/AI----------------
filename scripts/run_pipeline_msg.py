# -*- coding: utf-8 -*-
"""双击「跑全流程.bat」时调用：先自检 Key，再跑合并全流程，最后打印结果位置。"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore
except Exception:
    pass

LINE = "=" * 62
BATCH = "B20261113-01"


def main() -> int:
    py = sys.executable

    print()
    print(LINE)
    print("  一键跑全流程：清洗 → 去重 → 判别 → 聚类 → 评分 → 导出")
    print(LINE)
    print()

    # 熔断自检放在最前面：有泄漏就不跑
    guard = subprocess.run([py, str(ROOT / "scripts" / "guard_secrets.py")],
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace")
    if guard.returncode == 3:
        print(guard.stdout)
        print("  已熔断，本次不运行。修好泄漏后执行：")
        print(f'    "{py}" scripts/guard_secrets.py --clear')
        return 3
    print("  [自检] 密钥未泄漏。\n")

    # 先看 Key 在不在，不在就提醒（不阻断，纯规则也能跑完）
    probe = subprocess.run([py, str(ROOT / "scripts" / "check_llm.py")],
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace")
    if probe.returncode == 0:
        print("  [Key] 已配置，本次使用大模型判别 / 翻译 / 主题名。\n")
    else:
        print("  [Key] 未配置 —— 将以「纯规则模式」运行，四个 CSV 仍会正常产出，")
        print("        但机会判别与主题名质量会明显下降。")
        print("        想用大模型：先双击「设置KEY.bat」，再回来双击本文件。\n")
        print("-" * 62)

    cmd = [py, str(ROOT / "run_all.py"), "--track", "all",
           "--batch", BATCH, "--force"]
    rc = subprocess.run(cmd).returncode

    if rc != 0:
        print()
        print(f"  运行失败（返回码 {rc}），把上面最后 20 行报错发给我。")
        return rc

    # 顺手把论文要的东西也生成：数据审计 + 全套图表
    print()
    print("-" * 62)
    print("  生成数据审计与论文配图 …")
    for track in ("all", "ecommerce", "education"):
        for script in ("report_audit.py", "make_figures.py"):
            subprocess.run([py, str(ROOT / "scripts" / script), "--track", track],
                           capture_output=True)
    print("  完成。")

    print()
    print("-" * 62)
    print("  产出位置：")
    print(f"    四份结果 CSV   {ROOT / 'data' / 'out'}")
    print(f"    数据审计       {ROOT / 'reports' / 'data_audit.md'}")
    print(f"    论文配图       {ROOT / 'figs' / 'all'}")
    print(f"    立项策划案     {ROOT / 'reports'}")
    print()
    print("  交付前自查：")
    print(f'    "{py}" validate.py --track all')
    return 0


if __name__ == "__main__":
    sys.exit(main())
