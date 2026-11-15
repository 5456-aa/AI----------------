# -*- coding: utf-8 -*-
"""交互式配置 Key：双击「设置KEY.bat」时调用它。

把中文提示全部放在 Python 里（UTF-8），bat 只负责启动——
这样不会出现 bat 用 GBK 解析中文注释导致的一堆报错。
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

from io_utils import load_config  # noqa: E402

LINE = "=" * 62


def main() -> int:
    cfg = load_config(track="all")
    env_name = cfg["llm"].get("api_key_env", "DEEPSEEK_API_KEY")
    dotenv = Path(cfg["_root"]) / ".env"

    print()
    print(LINE)
    print("  第一步：配置大模型 API Key（只做这一次）")
    print(LINE)
    print()
    print("  key 从哪来？")
    print("    1. 浏览器打开  https://platform.deepseek.com")
    print("    2. 手机号注册 / 登录")
    print("    3. 左侧菜单点「API keys」→「创建 API key」")
    print("       （英文界面：API keys → Create new API key）")
    print("    4. 复制以 sk- 开头的那一串（只显示一次，马上存好）")
    print()
    print("  充值：deepseek-chat 很便宜，充 10 元足够这次比赛用。")
    print()
    print("-" * 62)

    try:
        raw = input("  把 key 粘贴到这里，按回车： ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\n  已取消。")
        return 1

    raw = raw.strip().strip('"').strip("'").replace(" ", "")
    if not raw:
        print("\n  [错误] 没读到内容。重新双击「设置KEY.bat」再试。")
        return 1
    if not raw.startswith("sk-"):
        print(f"\n  [提醒] 这个 key 不是以 sk- 开头（当前开头：{raw[:6]}…），"
              f"确认没粘错？仍然写入，稍后检查会告诉你行不行。")

    dotenv.write_text(f"{env_name}={raw}\n", encoding="utf-8")
    print(f"\n  [已保存] {dotenv}")

    # 立刻反扫：确认这把 key 没有以明文出现在其他文件里
    try:
        import security
        leaks = security.scan()
        if leaks:
            security.trip(leaks, "设置 Key 后的即时自检")
            print("  [熔断] 这把 key 还出现在上面的文件里，请先删掉再跑流程。")
            return 3
    except Exception:
        pass
    print(f"  [提示] 中途想换 key，再双击一次本文件即可覆盖。\n")
    print("-" * 62)
    print("  正在用这个 key 发一个测试请求，请稍等 3~10 秒...\n")

    from scripts.check_llm import main as check_main  # noqa: E402
    return check_main()


if __name__ == "__main__":
    sys.exit(main())
