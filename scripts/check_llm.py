# -*- coding: utf-8 -*-
"""检查 LLM Key 是否配好：python scripts/check_llm.py

做三件事：
  1. 看环境变量里有没有 key（不打印 key 本身，只看前后 4 位）；
  2. 有 key 就发一个最小请求，验证 base_url / model / JSON 模式是否都通；
  3. 没配就打印 Windows 下的三种配置方式（当前窗口 / 永久 / 临时脚本）。
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from io_utils import get_secret, load_config  # noqa: E402
from llm.client import LLMClient, LLMUnavailable  # noqa: E402


def mask(key: str) -> str:
    if not key:
        return "(空)"
    if len(key) <= 8:
        return key[:2] + "***"
    return f"{key[:4]}…{key[-4:]}（长度 {len(key)}）"


def show_howto(env_name: str, base_url: str, model: str, dotenv: Path) -> None:
    print("\n" + "=" * 68)
    print("还没有配 Key。最省事的办法：")
    print("=" * 68)
    print("\n  【推荐】双击项目根目录的「设置KEY.bat」，粘贴 key，回车，完事。\n")
    print("  它做的事就是：把 key 写进下面这个文件")
    print(f"      {dotenv}")
    print("\n  你也可以自己用记事本打开这个文件，写成一行：")
    print(f"      {env_name}=sk-你的key")
    print("\n  保存后重跑：python scripts/check_llm.py")
    print("-" * 68)
    print("  另一种办法（临时，只对当前窗口有效）：")
    print(f'      $env:{env_name}="sk-你的key"')
    print("-" * 68)
    print(f"当前配置：base_url = {base_url}")
    print(f"          model    = {model}")
    print(f"          变量名    = {env_name}")
    print("\n换成别家（通义/Moonshot/本地 vLLM）只改 config.yaml → llm 三行，不用动代码：")
    print('  base_url: "https://dashscope.aliyuncs.com/compatible-mode/v1"')
    print('  model: "qwen-plus"')
    print('  api_key_env: "DASHSCOPE_API_KEY"')
    print("-" * 68)
    print("注意：不要把 key 写进代码、论文或截图里——提交时评委会看到源码。")


def main() -> int:
    cfg = load_config(track="all")
    lcfg = cfg["llm"]
    env_name = lcfg.get("api_key_env", "DEEPSEEK_API_KEY")
    dotenv = Path(cfg["_root"]) / ".env"
    key, source = get_secret(env_name, dotenv)

    print(f"配置：base_url = {lcfg.get('base_url')}")
    print(f"      model    = {lcfg.get('model')}")
    src_cn = {"env": "系统环境变量", "dotenv": ".env 文件"}.get(source, "未找到")
    print(f"      key      = {mask(key)}  （来源：{src_cn}）")

    if not key:
        show_howto(env_name, lcfg.get("base_url", ""), lcfg.get("model", ""), dotenv)
        return 1

    client = LLMClient(cfg)
    print(f"客户端状态：enabled={client.enabled}，缓存 {client.cache_size()} 条")

    t0 = time.time()
    try:
        out = client.chat_json(
            '只输出 JSON：{"ok": true, "msg": "pong"}',
            system="你是一个连通性测试端点，只回 JSON。")
    except LLMUnavailable as exc:
        print(f"\n[失败] 调用不通：{exc}")
        print("\n排查顺序：")
        print("  1) key 是否抄错（注意首尾空格、sk- 前缀）")
        print("  2) base_url 是否带 /v1 后缀（DeepSeek 需要：https://api.deepseek.com/v1）")
        print("  3) 账号是否欠费 / 模型名是否拼错")
        return 2

    dt = time.time() - t0
    print(f"\n[成功] 往返 {dt:.2f}s，返回：{out}")
    if not out:
        print("[警告] 返回不是合法 JSON —— 该模型可能不支持 response_format，"
              "把 config.yaml 的 llm 里改用默认文本模式，或换 deepseek-chat")
    else:
        print("\nLLM 可用，可以跑判别/翻译/主题名了：")
        print("  python run_all.py --track all --batch B20261111-01 --force")
    return 0


if __name__ == "__main__":
    sys.exit(main())
