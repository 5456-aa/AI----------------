# -*- coding: utf-8 -*-
"""密钥泄漏自检与熔断（只在本项目目录内活动）。

边界（很重要，写在这里防止以后误改）：
  * **只读**扫描 `D:\\sjwjbs\\ai-opp-system` 及其子目录；
  * **绝不**读取/修改 `~/.dsh/.credentials.yaml`、环境变量、DSH 配置，
    因此不会影响当前对话所用的 API 通道；
  * 唯一写入的是本项目根目录下的 `.leak_alert`（熔断标记）和 `LEAK_ALERT.txt`（给人看的说明）。

熔断语义：
  * 扫描到疑似密钥 → 写标记文件 → 流程（run_all / 跑全流程）直接拒绝运行；
  * 修掉之后 `python scripts/guard_secrets.py --clear` 才能恢复。
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional

ROOT = Path(__file__).resolve().parent
ALERT_FILE = ROOT / ".leak_alert"
ALERT_TXT = ROOT / "LEAK_ALERT.txt"

# 只扫这些类型；二进制、图片、数据快照不扫（也没有密钥）
SCAN_SUFFIXES = {
    ".py", ".md", ".txt", ".yml", ".yaml", ".json", ".jsonl", ".csv",
    ".bat", ".ps1", ".cmd", ".html", ".ipynb", ".cfg", ".ini", ".toml", ".log",
}
SKIP_DIRS = {
    ".git", "__pycache__", "node_modules", ".venv", "venv", ".idea", ".vscode",
    "dsh-browser", "figs", "attachments",
}
# 第三方抓取内容（可能天然含 "sk-xxx" 之类字符串）不做模式匹配，
# 但仍会参与「真实 key 精确定位」——那才是真正的泄漏信号。
DATA_DIRS = {"data", "logs"}
SKIP_FILES = {".env", ".env.example"}      # .env 是密钥的合法存放处
MAX_BYTES = 2 * 1024 * 1024

# sk- 开头 + 至少 20 位（占位符如 sk-你的key / sk-xxx 不会被误伤）
PAT_KEY = re.compile(r"\bsk-[A-Za-z0-9]{20,}")
# api_key = "..." / token: "..." 这类硬编码
PAT_ASSIGN = re.compile(
    r"(?i)\b(api[_-]?key|apikey|secret[_-]?key|access[_-]?token)\b\s*[:=]\s*"
    r"[\"']?([A-Za-z0-9_\-]{20,})")


@dataclass
class Finding:
    path: str
    line: int
    kind: str
    snippet: str        # 已脱敏

    def format(self) -> str:
        return f"{self.path}:{self.line}  [{self.kind}]  {self.snippet}"


def _mask(text: str) -> str:
    """把疑似密钥打码，避免自检报告本身又变成泄漏源。"""
    def _m(m: re.Match) -> str:
        s = m.group(0)
        return s[:6] + "…" + s[-4:] + f"(len={len(s)})"
    return PAT_KEY.sub(_m, text)


def _iter_files(root: Path, include_data: bool = True) -> Iterable[Path]:
    for dirpath, dirnames, filenames in os.walk(root):
        skip = set(SKIP_DIRS) if include_data else (set(SKIP_DIRS) | DATA_DIRS)
        dirnames[:] = [d for d in dirnames if d not in skip]
        for name in filenames:
            if name in SKIP_FILES:
                continue
            p = Path(dirpath) / name
            if p.suffix.lower() not in SCAN_SUFFIXES:
                continue
            try:
                if p.stat().st_size > MAX_BYTES:
                    continue
            except OSError:
                continue
            yield p


def _real_key() -> str:
    """.env 里的真实 key，用于精确比对（只读，不打印）。"""
    env = ROOT / ".env"
    if not env.exists():
        return ""
    for line in env.read_text(encoding="utf-8", errors="replace").splitlines():
        if "=" in line and line.split("=", 1)[0].strip().endswith("API_KEY"):
            return line.split("=", 1)[1].strip()
    return ""


def scan(root: Optional[Path] = None) -> List[Finding]:
    root = root or ROOT
    real = _real_key()
    findings: List[Finding] = []

    # 第一遍：真实 key 是否出现在 .env 之外的任何文件（含抓取数据）
    if real and len(real) >= 16:
        for path in _iter_files(root, include_data=True):
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            rel = str(path.relative_to(root))
            for i, line in enumerate(text.splitlines(), 1):
                if real in line:
                    findings.append(Finding(rel, i, "真实密钥外泄",
                                            _mask(line.strip())[:120]))

    # 第二遍：只看我们自己的代码/文档/配置，找「长得像密钥」的串
    for path in _iter_files(root, include_data=False):
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        rel = str(path.relative_to(root))
        for i, line in enumerate(text.splitlines(), 1):
            if PAT_KEY.search(line):
                findings.append(Finding(rel, i, "疑似 API Key", _mask(line.strip())[:120]))
                continue
            m = PAT_ASSIGN.search(line)
            if m and not any(w in line for w in ("你的", "example", "placeholder", "<", "***")):
                findings.append(Finding(rel, i, "疑似硬编码密钥",
                                        _mask(line.strip())[:120]))
    return findings


def is_tripped() -> bool:
    return ALERT_FILE.exists()


def trip(findings: List[Finding], reason: str = "") -> None:
    """熔断：写标记 + 写人话说明。"""
    lines = [
        "=" * 70,
        "  ⚠ 熔断：检测到疑似密钥泄漏",
        "=" * 70,
        "",
    ]
    if reason:
        lines += [f"原因：{reason}", ""]
    lines += [f"  共 {len(findings)} 处：" , ""]
    lines += [f"  - {f.format()}" for f in findings[:50]]
    if len(findings) > 50:
        lines.append(f"  …… 还有 {len(findings) - 50} 处")
    lines += [
        "",
        "  现在该做什么：",
        "    1. 打开上面的文件，把 key 删掉（或换成 <从环境变量读取> 的写法）",
        "    2. 立刻去 https://platform.deepseek.com/api_keys 把该 key 删除并重建",
        "       —— 因为它已经出现在文件里了，等于已泄露",
        "    3. 修完后运行：python scripts/guard_secrets.py --clear",
        "",
        "  说明：本次熔断只作用于本项目目录，不影响当前对话所用的 API。",
        "=" * 70,
    ]
    text = "\n".join(lines)
    ALERT_FILE.write_text(text, encoding="utf-8")
    ALERT_TXT.write_text(text, encoding="utf-8")
    print(text)


def clear() -> None:
    for p in (ALERT_FILE, ALERT_TXT):
        if p.exists():
            p.unlink()


def assert_clean(where: str = "流程", abort: bool = True) -> bool:
    """供 run_all / validate 调用。发现泄漏就熔断并中止。"""
    findings = scan()
    if findings:
        trip(findings, f"{where}启动前的自检")
        if abort:
            raise SystemExit(3)
        return False
    return True
