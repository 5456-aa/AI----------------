# -*- coding: utf-8 -*-
"""模型服务商设置：让"用的人填自己的 key"，而不是共用一把。

设计原则（对应"密钥要单独抽出来"）：
  * 密钥只存在**本机**的 `.env` 里，一行一个，不写进任何代码/文档/配置模板；
  * `.env` 已在 `.gitignore` 与打包排除列表里，任何人拿到项目都要自己填；
  * 切换服务商 = 改 `.env` 里的 4 个变量，不需要动 config.yaml 或代码。

`.env` 里与模型相关的变量（全部可选，缺省用 config.yaml）：
    LLM_PROVIDER=deepseek
    LLM_BASE_URL=https://api.deepseek.com/v1
    LLM_MODEL=deepseek-chat
    LLM_API_KEY=sk-xxxx
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from io_utils import get_secret, load_dotenv

# 常见 OpenAI 兼容服务商。新增一家只需在这里加一条。
PROVIDERS: Dict[str, Dict[str, str]] = {
    "deepseek": {
        "label": "DeepSeek（便宜，推荐）",
        "base_url": "https://api.deepseek.com/v1",
        "model": "deepseek-chat",
        "env": "DEEPSEEK_API_KEY",
        "signup": "https://platform.deepseek.com/api_keys",
    },
    "qwen": {
        "label": "通义千问（阿里云百炼）",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model": "qwen-plus",
        "env": "DASHSCOPE_API_KEY",
        "signup": "https://bailian.console.aliyun.com/",
    },
    "moonshot": {
        "label": "Moonshot（Kimi）",
        "base_url": "https://api.moonshot.cn/v1",
        "model": "moonshot-v1-8k",
        "env": "MOONSHOT_API_KEY",
        "signup": "https://platform.moonshot.cn/console/api-keys",
    },
    "openai": {
        "label": "OpenAI",
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4o-mini",
        "env": "OPENAI_API_KEY",
        "signup": "https://platform.openai.com/api-keys",
    },
    "custom": {
        "label": "自定义（任何 OpenAI 兼容接口，含本地 vLLM/Ollama）",
        "base_url": "http://127.0.0.1:8000/v1",
        "model": "local-model",
        "env": "LLM_API_KEY",
        "signup": "",
    },
}


def dotenv_path() -> Path:
    from io_utils import ROOT
    return ROOT / ".env"


def read_settings() -> Dict[str, str]:
    """读本机 .env 里的模型设置（不含任何回退）。"""
    d = load_dotenv(dotenv_path())
    return {
        "provider": d.get("LLM_PROVIDER", ""),
        "base_url": d.get("LLM_BASE_URL", ""),
        "model": d.get("LLM_MODEL", ""),
        "api_key": d.get("LLM_API_KEY", "")
        or next((v for k, v in d.items() if k.endswith("_API_KEY")), ""),
    }


def _backup_env(p: Path) -> Path | None:
    """覆盖前先备份，避免误操作把 key 弄丢（吃过一次亏）。"""
    if not p.exists():
        return None
    import time
    bak = p.with_name(f".env.bak.{time.strftime('%Y%m%d_%H%M%S')}")
    bak.write_text(p.read_text(encoding="utf-8"), encoding="utf-8")
    return bak


def save_settings(provider: str, base_url: str, model: str,
                  api_key: str, keep_other: bool = True) -> Path:
    """把设置写进本机 .env。

    * 覆盖前自动备份为 .env.bak.<时间戳>（最多保留 5 份）；
    * keep_other=True 时保留 .env 里其他变量，只改模型相关的几行；
    * 不写任何注释性密钥，便于 guard_secrets 扫描。
    """
    p = dotenv_path()
    bak = _backup_env(p)

    lines: list[str] = []
    if keep_other and p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            key = line.split("=", 1)[0].strip()
            if key.startswith("LLM_") or not key:
                continue          # 这几个由下面重写
            if not api_key and key.endswith("_API_KEY"):
                continue          # 清除时必须把服务商的 *_API_KEY 一并删掉
            lines.append(line)

    if api_key:
        lines += [
            f"LLM_PROVIDER={provider}",
            f"LLM_BASE_URL={base_url}",
            f"LLM_MODEL={model}",
            f"LLM_API_KEY={api_key}",
        ]
        env_name = PROVIDERS.get(provider, {}).get("env")
        if env_name and env_name != "LLM_API_KEY":
            lines.append(f"{env_name}={api_key}")

    p.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    try:
        p.chmod(0o600)
    except Exception:
        pass

    # 清理过旧的备份，只留最近 5 份
    if bak is not None:
        baks = sorted(p.parent.glob(".env.bak.*"), key=lambda x: x.stat().st_mtime)
        for old in baks[:-5]:
            try:
                old.unlink()
            except OSError:
                pass
    return p


def migrate_legacy() -> bool:
    """把老的 DEEPSEEK_API_KEY=... 迁移成 LLM_* 四项，统一成一个入口。

    只在本机 .env 内搬运，不打印 key。返回是否做了迁移。
    """
    p = dotenv_path()
    if not p.exists():
        return False
    d = load_dotenv(p)
    if d.get("LLM_API_KEY"):
        return False

    legacy_key = next((v for k, v in d.items() if k.endswith("_API_KEY") and v), "")
    if not legacy_key:
        return False

    legacy_name = next(k for k, v in d.items() if v == legacy_key)
    provider = next((k for k, v in PROVIDERS.items() if v["env"] == legacy_name), "custom")
    preset = PROVIDERS.get(provider, PROVIDERS["custom"])

    save_settings(
        provider=provider,
        base_url=d.get("LLM_BASE_URL") or preset["base_url"],
        model=d.get("LLM_MODEL") or preset["model"],
        api_key=legacy_key,
    )
    return True


def status(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """当前生效的模型配置（供界面显示）。"""
    s = read_settings()
    provider = s["provider"] or "config.yaml"
    key, src = get_secret(cfg["llm"].get("api_key_env", "LLM_API_KEY"), dotenv_path())
    if not key:
        key, src = get_secret("LLM_API_KEY", dotenv_path())
    return {
        "provider": provider,
        "label": PROVIDERS.get(provider, {}).get("label", "配置文件默认"),
        "base_url": cfg["llm"].get("base_url", ""),
        "model": cfg["llm"].get("model", ""),
        "key_masked": (key[:4] + "…" + key[-4:]) if len(key) > 8 else ("(未配置)" if not key else "***"),
        "key_source": {"env": "系统环境变量", "dotenv": ".env 文件"}.get(src, "未找到"),
        "enabled": bool(key),
    }


def mask(key: str) -> str:
    if not key:
        return "(未配置)"
    return key[:4] + "…" + key[-4:] if len(key) > 8 else "***"
