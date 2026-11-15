# -*- coding: utf-8 -*-
"""密钥泄漏自检 CLI。

    python scripts/guard_secrets.py            # 扫描，干净则退出码 0，发现泄漏则 3 并熔断
    python scripts/guard_secrets.py --clear    # 修好之后解除熔断
    python scripts/guard_secrets.py --show     # 只显示当前熔断状态

只扫本项目目录，不碰 DSH 的凭据与环境变量。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore
except Exception:
    pass

import security  # noqa: E402


def main(argv=None) -> int:
    args = sys.argv[1:] if argv is None else argv

    if "--clear" in args:
        security.clear()
        print("已解除熔断标记（.leak_alert）。请确认泄漏已修好再跑流程。")
        return 0

    if "--show" in args:
        if security.is_tripped():
            print("状态：熔断中（.leak_alert 存在）")
            print(security.ALERT_FILE.read_text(encoding="utf-8"))
            return 3
        print("状态：正常（未熔断）")
        return 0

    findings = security.scan()
    if not findings:
        print("密钥自检：通过。项目目录内未发现明文密钥。")
        if security.is_tripped():
            print("提示：仍存在旧的熔断标记，修好后请执行 --clear")
        return 0

    security.trip(findings, "guard_secrets.py 手动扫描")
    return 3


if __name__ == "__main__":
    sys.exit(main())
