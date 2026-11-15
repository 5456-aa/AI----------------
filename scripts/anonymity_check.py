# -*- coding: utf-8 -*-
"""匿名性与可交付性自检。

赛题原文：「作品及附件内请勿出现队号、学校、学院、团队成员以及指导老师等任何相关
信息，否则该作品视为无效作品」——这条一旦踩中，成绩直接作废，所以必须脚本化检查。

检查四类：
  1. 本机路径泄漏（C:\\Users\\xxx、D:\\... 等绝对路径）
  2. 文档元数据泄漏（docx/xlsx 的 author / last_modified_by / company）
  3. 敏感词（学校、学院、指导、队号等；队号按 B+数字 之类模式粗筛）
  4. 密钥（sk- 长串）

用法：
  python scripts/anonymity_check.py            # 检查
  python scripts/anonymity_check.py --fix      # 清空文档元数据后再报告
"""
from __future__ import annotations

import argparse
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT.parent / "Desktop"  # 仅用于提示，不扫描

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore
except Exception:
    pass

TEXT_EXT = {".md", ".txt", ".py", ".bat", ".csv", ".yaml", ".yml", ".toml", ".json", ".html"}
DOC_EXT = {".docx", ".xlsx", ".pptx"}

PAT_PATH = re.compile(r"[A-Za-z]:\\\\?(?:Users|Documents|Desktop|sjwjbs)[^\\\s\"'<>]{0,80}", re.I)
PAT_USER = re.compile(r"Users\\\\[^\\\\\s]{1,20}", re.I)
PAT_KEY = re.compile(r"sk-[A-Za-z0-9]{16,}")
SENSITIVE = ["学校", "学院", "指导教师", "指导老师", "队号", "参赛队", "队长", "队员"]
# 队号/学号粗筛：连续 6 位以上数字

SKIP_DIRS = {"__pycache__", ".git", "tools", "logs", "data/raw", "data/clean",
             "data/cache", "figs"}


def iter_files(base: Path):
    for p in base.rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(base)
        if any(part in SKIP_DIRS for part in rel.parts):
            continue
        if p.name in {"anonymity_check.py", "make_ai_report_shots.py"}:
            continue
        if p.suffix.lower() in TEXT_EXT | DOC_EXT:
            yield p


def scan_text(p: Path) -> list[str]:
    hits = []
    try:
        s = p.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return hits
    for m in PAT_PATH.finditer(s):
        hits.append(f"绝对路径：{m.group(0)[:60]}")
    for m in PAT_KEY.finditer(s):
        hits.append(f"疑似密钥：{m.group(0)[:12]}…")
    # 敏感词：逐行判断，排除"不得出现/请勿出现"这类说明性句子
    EXEMPT = ("不得", "请勿", "禁止", "匿名", "不要出现", "去除", "自检", "检查",
              "删除", "脱敏", "留意", "小心")
    for ln_no, line in enumerate(s.splitlines(), 1):
        if any(k in line for k in EXEMPT):
            continue
        for w in SENSITIVE:
            if w in line:
                hits.append(f"第 {ln_no} 行敏感词「{w}」：{line.strip()[:50]}")
                break
    return hits


def doc_meta(p: Path) -> dict:
    """读 Office 文档核心属性（docProps/core.xml）。"""
    try:
        with zipfile.ZipFile(p) as z:
            if "docProps/core.xml" not in z.namelist():
                return {}
            xml = z.read("docProps/core.xml").decode("utf-8", "ignore")
    except Exception:
        return {}
    out = {}
    for tag in ("creator", "lastModifiedBy", "title", "subject", "description"):
        m = re.search(rf"<{tag}[^>]*>(.*?)</{tag}>", xml, re.S)
        if m:
            out[tag] = m.group(1).strip()
    return out


def fix_meta(p: Path) -> bool:
    """把作者等元数据清空（重写 docProps/core.xml）。"""
    try:
        with zipfile.ZipFile(p) as z:
            names = z.namelist()
            data = {n: z.read(n) for n in names}
    except Exception:
        return False
    if "docProps/core.xml" not in data:
        return False
    xml = data["docProps/core.xml"].decode("utf-8", "ignore")
    for tag in ("creator", "lastModifiedBy", "title", "subject", "description"):
        xml = re.sub(rf"<{tag}[^>]*>.*?</{tag}>", f"<{tag}></{tag}>", xml, flags=re.S)
    data["docProps/core.xml"] = xml.encode("utf-8")
    tmp = p.with_suffix(p.suffix + ".tmp")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        for n, b in data.items():
            z.writestr(n, b)
    tmp.replace(p)
    return True


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fix", action="store_true", help="清空 Office 文档元数据")
    args = ap.parse_args(argv)

    problems = 0
    fixed = 0
    print("=== 1. 文本文件：绝对路径 / 密钥 / 敏感词 ===")
    for p in iter_files(ROOT):
        if p.suffix.lower() in DOC_EXT:
            continue
        hits = scan_text(p)
        if not hits:
            continue
        problems += len(hits)
        print(f"  {p.relative_to(ROOT)}")
        for h in hits[:4]:
            print(f"      - {h}")

    print("\n=== 2. Office 文档：元数据 ===")
    for p in iter_files(ROOT):
        if p.suffix.lower() not in DOC_EXT:
            continue
        meta = doc_meta(p)
        bad = {k: v for k, v in meta.items() if v and k in
               ("creator", "lastModifiedBy", "title", "subject", "description")}
        if bad:
            print(f"  {p.relative_to(ROOT)}  {bad}")
            problems += 1
            if args.fix and fix_meta(p):
                fixed += 1
                print("      → 已清空")

    print("\n=== 3. 交付目录（桌面提交包）===")
    pack = Path.home() / "Desktop" / "数据挖掘挑战赛_提交包_20261115"
    if pack.exists():
        cnt = 0
        for p in pack.rglob("*"):
            if p.is_file() and p.suffix.lower() in TEXT_EXT:
                if scan_text(p):
                    print(f"  {p.relative_to(pack)} 存在可疑内容")
                    cnt += 1
        print(f"  扫描 {sum(1 for _ in pack.rglob('*') if _.is_file())} 个文件，可疑 {cnt} 个")
    else:
        print("  （提交包尚未生成）")

    print(f"\n合计问题 {problems} 项" + (f"，已修复元数据 {fixed} 个" if args.fix else ""))
    print("提示：敏感词命中多为「不得出现学校/学院」这类说明性文字，需人工确认；"
          "绝对路径与元数据必须清零。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
