# -*- coding: utf-8 -*-
"""生成《AI 使用情况说明》的附录截图（脱敏版）。

三张图：
  A1 调用缓存结构（证明「每次调用可回放」，且 key 只是哈希）
  A2 连通性自检输出（证明真实调用成功）
  A3 判别提示词与返回字段（证明模型怎么被约束）

脱敏规则（全部自动处理）：
  * 绝对路径 → <项目根> / <本机>（去掉用户名）
  * sk- 开头的长串 → sk-****（本不该出现，兜底）
  * 长哈希截断显示

用法：python scripts/make_ai_report_shots.py
产出：reports/AI报告附录.html + figs/screens/20~22_*.png
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from io_utils import load_config, read_jsonl  # noqa: E402

HTML = ROOT / "reports" / "AI报告附录.html"

PAT_PATH = re.compile(r"[A-Za-z]:\\[^\s\"'<>]+")
PAT_KEY = re.compile(r"sk-[A-Za-z0-9_\-]{12,}")


def sanitize(text: str) -> str:
    """去掉本机路径与任何疑似密钥。"""
    def _path(m: re.Match) -> str:
        p = m.group(0)
        if "ai-opp-system" in p:
            return "<项目根>"
        return "<本机路径>"

    text = PAT_PATH.sub(_path, text)
    text = PAT_KEY.sub("sk-****（已脱敏）", text)
    text = re.sub(r"C:\\\\Users\\\\[^\\\\\s]+", "<本机>", text)
    return text


def cache_sample(n: int = 5) -> str:
    """挑三种典型调用各取几条：判别（has_need）、翻译（title_zh）、连通性测试。"""
    p = ROOT / "data" / "cache" / "llm_calls.jsonl"
    if not p.exists():
        return "（缓存文件不存在）"
    picked, kinds = [], {"judge": 0, "translate": 0, "ping": 0}
    for line in p.read_text(encoding="utf-8").splitlines():
        try:
            r = json.loads(line)
        except Exception:
            continue
        resp = r.get("response") or ""
        if "has_need" in resp and kinds["judge"] < 2:
            kinds["judge"] += 1
        elif "title_zh" in resp and kinds["translate"] < 2:
            kinds["translate"] += 1
        elif "pong" in resp and kinds["ping"] < 1:
            kinds["ping"] += 1
        else:
            continue
        picked.append(r)
        if len(picked) >= n:
            break
    lines = []
    for r in picked:
        resp = (r.get("response") or "")[:150].replace("\n", " ")
        lines.append(
            f'{{"key": "{r.get("key","")[:16]}…（sha1，不可逆）", '
            f'"model": "{r.get("model")}", "ts": "{r.get("ts")}",\n'
            f' "response": "{resp}…"}}'
        )
    return "\n".join(lines)


def prompt_case() -> tuple[str, str]:
    """挑一条真实记录，重建它的判别提示词与返回字段。"""
    cfg = load_config(track="all")
    judged = read_jsonl(Path(cfg["paths"]["clean"]) / "judged.jsonl")
    rec = next((r for r in judged
                if r.get("source") == "GitHub" and r.get("is_opportunity") == 1
                and len(r.get("clean_text", "")) > 120), None)
    if not rec:
        return "（无可用样例）", "（无可用样例）"

    from llm import prompts
    prompt = prompts.judge_prompt(rec)
    fields = {
        "has_need": rec.get("has_need"),
        "ai_core": rec.get("ai_core"),
        "feasible": rec.get("feasible"),
        "exclude": rec.get("exclude"),
        "func_category": rec.get("func_category"),
        "industry": rec.get("industry"),
        "reason": rec.get("reason"),
    }
    return prompt, json.dumps(fields, ensure_ascii=False, indent=2)


CSS = """
body{margin:0;background:#f8fafc;color:#111827;
font:14px/1.7 -apple-system,"Segoe UI","Microsoft YaHei",sans-serif}
.wrap{max-width:1000px;margin:0 auto;padding:26px}
h1{font-size:20px;margin:0 0 6px}
.sub{color:#6b7280;font-size:12.5px;margin-bottom:18px}
.sec{background:#fff;border:1px solid #e5e7eb;border-radius:10px;padding:16px 18px;margin-bottom:16px}
.sec h2{font-size:15px;margin:0 0 8px;color:#2563eb}
pre{background:#0f172a;color:#e2e8f0;padding:14px 16px;border-radius:8px;
font:12px/1.65 ui-monospace,Consolas,monospace;overflow-x:auto;white-space:pre-wrap}
.note{font-size:12px;color:#6b7280;margin-top:8px}
.tag{display:inline-block;background:#ecfdf5;color:#047857;border-radius:4px;
padding:1px 8px;font-size:11.5px;margin-left:6px}
"""


def main() -> int:
    cfg = load_config(track="all")
    cache_file = ROOT / "data" / "cache" / "llm_calls.jsonl"
    n_calls = sum(1 for _ in cache_file.open(encoding="utf-8")) if cache_file.exists() else 0
    check_out = (ROOT / "reports" / "_check_llm.txt")
    check_txt = check_out.read_text(encoding="utf-8", errors="replace") if check_out.exists() else "（未运行自检）"
    prompt, resp = prompt_case()

    L = []
    A = L.append
    A("<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'>")
    A("<title>AI 使用情况说明 · 附录</title>")
    A(f"<style>{CSS}</style></head><body><div class='wrap'>")
    A("<h1>AI 使用情况说明 · 附录证据</h1>")
    A(f"<div class='sub'>以下截图均已在生成时自动脱敏：路径替换为 &lt;项目根&gt;，"
      f"任何疑似密钥替换为 sk-****。</div>")

    A("<div class='sec' id='s1'><h2>附录 A1　调用缓存：每次调用可回放<span class='tag'>共 "
      f"{n_calls} 条</span></h2>")
    A("<pre>" + sanitize(cache_sample(5)) + "</pre>")
    A("<p class='note'>缓存以「模型名 + 温度 + 提示词」的 SHA1 作为键；"
      "同一请求重复执行不再计费，也保证答辩时结果可复现。"
      "缓存中<b>不含任何密钥</b>，密钥只存在于本机 .env，不进入仓库与提交包。</p></div>")

    A("<div class='sec' id='s2'><h2>附录 A2　连通性自检输出</h2>")
    A("<pre>" + sanitize(check_txt.strip()[:900]) + "</pre>")
    A("<p class='note'>输出中的 Key 仅显示前 4 位与后 4 位（脱敏显示），完整值不落日志。</p></div>")

    A("<div class='sec' id='s3'><h2>附录 A3　判别提示词与返回字段（真实样例）</h2>")
    A("<p class='note'>提示词把赛题的四条判定标准写成结构化约束，要求只输出 JSON：</p>")
    A("<pre>" + sanitize(prompt[:1200]) + "…</pre>")
    A("<p class='note'>对应记录最终落库的判别字段：</p>")
    A("<pre>" + sanitize(resp) + "</pre></div>")

    A("</div></body></html>")
    HTML.parent.mkdir(parents=True, exist_ok=True)
    HTML.write_text("\n".join(L), encoding="utf-8")
    print(f"已生成：{HTML}")
    print(f"  调用缓存 {n_calls} 条；已脱敏路径与密钥")
    return 0


if __name__ == "__main__":
    sys.exit(main())
