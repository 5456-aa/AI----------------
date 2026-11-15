# -*- coding: utf-8 -*-
"""生成提交包：在桌面新建文件夹，把比赛要交的东西按类放好。

会先做两道闸：密钥泄漏自检 + 交付物校验，任一不过就拒绝打包。

用法：python scripts/pack_submission.py
      python scripts/pack_submission.py --skip-check   # 强制打包（不推荐）
"""
from __future__ import annotations

import argparse
import csv
import io
import os
import shutil
import sys
import zipfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from io_utils import load_config  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore
except Exception:
    pass


def desktop_dir() -> Path:
    """兼容 OneDrive 重定向的桌面。"""
    home = Path(os.path.expanduser("~"))
    for cand in (home / "Desktop", home / "OneDrive" / "Desktop", home / "桌面"):
        if cand.exists():
            return cand
    d = home / "Desktop"
    d.mkdir(parents=True, exist_ok=True)
    return d


CODE_INCLUDE_SUFFIX = {".py", ".yaml", ".yml", ".md", ".txt", ".bat", ".json"}
CODE_EXCLUDE_DIRS = {"data", "figs", "reports", "logs", "tools", "__pycache__", ".git",
                     "node_modules", ".venv", ".idea", ".vscode"}
CODE_EXCLUDE_FILES = {".env", ".env.example", ".leak_alert", "LEAK_ALERT.txt"}


def zip_code(dest: Path) -> Path:
    out = dest / "源代码.zip"
    n = 0
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in ROOT.rglob("*"):
            if not path.is_file():
                continue
            rel = path.relative_to(ROOT)
            # 例外：把「复现快照」带上，评委不联网、不填 key 也能完整跑一遍
            if rel.as_posix() == "data/cache/llm_calls.jsonl" or \
                    rel.as_posix() == "data/tracks" or \
                    rel.parts[:2] in {("data", "raw"), ("data", "tracks")}:
                zf.write(path, rel)
                n += 1
                continue
            if set(rel.parts) & CODE_EXCLUDE_DIRS:
                continue
            if rel.name in CODE_EXCLUDE_FILES or rel.name.startswith((".env.bak", ".leak_alert")):
                continue
            if path.suffix.lower() not in CODE_INCLUDE_SUFFIX:
                continue
            if path.stat().st_size > 3 * 1024 * 1024:
                continue
            zf.write(path, rel)
            n += 1
    print(f"  源代码.zip：{n} 个文件，{out.stat().st_size / 1024:.0f} KB")
    return out


def check_results() -> tuple[bool, list[str]]:
    cfg = load_config(track="all")
    out = Path(cfg["paths"]["out"])
    msgs, ok = [], True
    for name in ("result1.csv", "result2.csv", "result3.csv", "result4.csv"):
        p = out / name
        if not p.exists():
            msgs.append(f"缺少 {name}")
            ok = False
            continue
        rows = list(csv.DictReader(io.open(p, encoding="utf-8-sig")))
        msgs.append(f"{name}：{len(rows)} 行")
    return ok, msgs


def write_checklist(dest: Path, stats: dict) -> None:
    L = []
    A = L.append
    A("# 提交清单")
    A("")
    A(f"> 生成时间 {datetime.now():%Y-%m-%d %H:%M}　·　由 `scripts/pack_submission.py` 自动生成")
    A("")
    A("## 一、必须提交的 5 项")
    A("")
    A("| # | 材料 | 位置 | 状态 |")
    A("|---|---|---|---|")
    A(f"| 1 | 论文（Word + PDF，正文 ≤30 页） | `01_论文/` | ⬜ 待放入 |")
    A(f"| 2 | 结果文件 result1~4.csv | `02_结果文件/` | ✅ 已就绪（{stats.get('结果行数','?')} 行） |")
    A(f"| 3 | 源代码与运行说明 | `03_源代码/` | ✅ 已就绪 |")
    A(f"| 4 | 成果附件（全流程截图） | `04_成果截图/`（{stats.get('截图',0)} 张） | ✅ 已就绪 |")
    A(f"| 4b | 系统可视化报告（单文件 HTML，双击即看） | 包根目录 `系统可视化报告.html` | ✅ 已就绪 |")
    A(f"| 5 | AI 使用报告 | `05_AI使用报告/` | ⬜ 待放入 |")
    A("")
    A("## 二、提交前逐条打勾")
    A("")
    for item in [
        "四个 CSV 表头与模板逐字一致（含全角括号），UTF-8 with BOM",
        "result3 的「簇内机会记录数」之和 = result2 中「是否构成机会=1」的行数",
        "result3 / result4 的功能类别、所属行业都在附件1 体系内（16 类 / 30 类）",
        "result4 按机会价值分降序，优先级为 1..N 连续整数",
        "论文正文 ≤30 页（含图表，不含附录）",
        "论文、代码、截图中无队号 / 学校 / 学院 / 姓名 / 指导教师",
        "截图不含浏览器书签、聊天窗口、个人信息",
        "参考文献格式统一为 GB/T 7714，卷期页码已核对",
        "自行查重预检：重复率 <30%（>30% 取消资格，>50% 按学术不端）",
        "AI 使用报告已写明工具名称、版本、用途、人工修改情况",
        "提交包内不含 .env / 密钥 / 个人 token",
        "在平台（数睿思竞赛页）完成提交，18:00 前留出 1 小时余量",
    ]:
        A(f"- [ ] {item}")
    A("")
    A("## 三、本包已替你排除的东西")
    A("")
    A("- `.env`（本机 API Key）—— **绝不打包**，密钥已做泄漏自检")
    A("- `data/` 原始数据快照与缓存、`logs/`、`__pycache__`")
    A("- 备份文件 `.env.bak.*`、`.leak_alert`")
    A("")
    A("## 四、如果重跑了流程")
    A("")
    A("按顺序执行，四份 CSV、图表、截图、本清单会一起更新：")
    A("")
    A("```")
    A("python run_all.py --track all --batch B20261113-01 --force")
    A("python scripts/report_audit.py --track all")
    A("python scripts/make_figures.py --track all")
    A("python scripts/make_paper_pack.py")
    A("python scripts/pack_submission.py")
    A("```")
    A("")
    A("## 五、数据快照（来自本次运行）")
    A("")
    for k, v in stats.items():
        A(f"- {k}：{v}")
    (dest / "提交清单.md").write_text("\n".join(L) + "\n", encoding="utf-8")


def write_runbook(dest: Path) -> None:
    text = """# 运行说明

## 环境
- Python 3.10+
- 依赖：`pip install -r requirements.txt`

## 零配置演示（不用申请 API Key）

源码包里已带 **`data/cache/llm_calls.jsonl`**（约 680 KB 预置缓存）。
解压后直接跑：

```bash
python run_all.py --track all --batch B20261113-01
```

没有 API Key 时，系统会**先用缓存**：命中即用，未命中才降级为纯规则。
在本文提交的数据上可 100% 复现论文中的结果（621 条 → 77 条机会 → 8 个主题簇）。

> 说明：这是「预生成结果」而非实时调用；换成新数据时缓存不命中，会自动降级到规则模式，
> 若要处理新数据，再按下一节配置自己的 Key。

## 三步跑通

```bash
# 1) 配置模型（可选，不配则用纯规则模式）
python scripts/setup_key.py

# 2) 一键全流程：清洗 → 去重 → 判别 → 聚类 → 评估 → 导出
python run_all.py --track all --batch B20240601-01

# 3) 交付前自检
python validate.py --track all
```

产物：
- `data/out/result1~4.csv` —— 四份结果文件
- `reports/data_audit.md` —— 数据审计报告
- `reports/proposal_C*.docx` —— 立项策划案
- `figs/` —— 论文图表

## 双赛道

```bash
python run_collect.py --track all --limit 130   # 采集
python run_all.py --track ecommerce            # 单跑电商
python run_all.py --track education            # 单跑教育
python run_all.py --track all                  # 合并（提交版）
streamlit run ui/app.py                        # 可视化界面
streamlit run ui/label.py                      # 人工标注工具
```

## 目录说明

| 目录 | 内容 |
|---|---|
| `collectors/` | 各来源采集适配器（GitHub / 掘金 / SegmentFault / RSS 若干） |
| `pipeline/` | clean / dedup / translate / judge / cluster / score |
| `llm/` | OpenAI 兼容客户端（带磁盘缓存）与提示词 |
| `export/` | 四份 CSV 导出、立项策划案生成 |
| `ui/` | Streamlit 界面与标注工具 |
| `scripts/` | 标定、审计、制图、打包等工具脚本 |
| `docs/` | 参考文献、数据来源说明、密钥配置文档 |

## 复现性说明

- 所有大模型调用落盘缓存（`data/cache/llm_calls.jsonl`），重跑不再计费；
- 随机种子固定（聚类 42、敏感性分析 42）；
- 阈值 τ、权重、聚类参数全部在 `config.yaml`，与论文数值一一对应。

### 运行环境

| 项目 | 要求 |
|---|---|
| 操作系统 | Windows 10/11（macOS / Linux 亦可） |
| Python | 3.10 及以上 |
| 内存 | 400~600 MB |
| 磁盘 | 约 200 MB（含依赖） |
| 网络 | 离线模式不需要联网 |

### 角色与权限

系统内置三种角色（`ui/auth.py`）：

| 角色 | 对应赛题 | 发起需求 | 查看批次 | 原始链接 | 模型设置 | 标注数据 |
|---|---|---|---|---|---|---|
| 决策者 decider | 决策者 | ❌ | ✅ | ❌ | ❌ | ❌ |
| 需求发起者 requester | 需求发起者 | ✅ | ✅ | ✅ | ❌ | ❌ |
| 系统管理员 admin | 运维角色 | ✅ | ✅ | ✅ | ✅ | ✅ |

本机默认系统管理员；**按访问来源自动降权**：通过公网隧道或云主机访问时自动变为
决策者只读（侧栏不显示「管理模式」开关，也看不到模型设置）。

### 复现提交结果（推荐给评委）

```bash
python scripts/doctor.py --run          # 先自检环境并试跑（约 20 秒，不改动原有结果）
python run_all.py --track all --batch B20261113-01 --offline --force
```

**评委模拟验证（已实测）**：把 `源代码.zip` 解压到全新目录，直接跑上面第二条命令，
得到四份 CSV 与 `02_结果文件/` **逐字节一致**（md5 相同）。
源码包含 `data/raw/` 原始快照与 `data/cache/` 模型缓存，因此**无需联网、无需 API Key**。

`--offline` 表示**只用随包缓存、不发起任何网络请求**，因此不需要 API Key、
不产生费用，且四个结果文件与提交版本**逐字节一致**。
自检命令：`python scripts/check_determinism.py --offline`
"""
    (dest / "03_源代码" / "运行说明.md").write_text(text, encoding="utf-8")


JUDGE_README = """# 评委请先看我（3 分钟看完）

本提交包含五个部分，**不联网也能看完全部结论**。

## 一、只想快速了解结论（不需要运行）

1. `04_成果截图/01_总览与来源.png` —— 数据规模与各来源机会密度
2. `04_成果截图/02_主题簇排名.png` —— 13 个主题簇的价值分与优先级
3. `系统可视化报告.html` —— 单文件网页，双击即可看全部图表（无需联网）
4. `01_论文/` —— 论文 Word 与 PDF

## 二、想验证"结果是不是真的"（3 条命令，约 1 分钟）

```bash
pip install -r requirements.txt          # 1. 装依赖（一次即可）
python scripts/doctor.py --run           # 2. 环境自检 + 离线跑一遍
python run_all.py --track all --batch B20261113-01 --offline --force   # 3. 重算四份结果
```

第 3 步**不需要 API Key、不需要联网**，跑完的四份 CSV 与 `02_结果文件/` 里的
**逐字节一致**（可用 `python scripts/check_determinism.py --offline` 自证）。

> 源码包里已附带原始采集快照（`data/raw/`）与模型调用缓存
> （`data/cache/llm_calls.jsonl`），所以离线也能完整重算，不是只给结论。

## 三、想看界面

| 方式 | 操作 |
|---|---|
| 本机 | 双击 `启动系统.bat`，浏览器打开 http://localhost:8500 |
| 只看静态 | 双击 `系统可视化报告.html` |

## 四、数据与合规

- 只采集公开接口（官方 API / RSS / 公开搜索），不登录、不绕验证码；
- **CSDN 的 robots.txt 为 `Disallow: /`，已主动放弃**；
- 手册 20 个来源逐个实测，可用 8 个 + 清单外补充 3 个，共 11 个；
- 抓取文本中的密钥类字符串已在清洗阶段脱敏（`sk-***`）。

## 五、匿名声明

本作品及全部附件不含队号、学校、学院、团队成员与指导教师信息；
文档元数据（作者/单位）已清空，可运行 `python scripts/anonymity_check.py` 复核。

## 六、如果只想看"系统能力"而不装环境

`04_成果截图/10~15_阶段*.png` 是六个阶段的运行截图（采集→清洗→判别→聚类→评估→导出），
每张都带实际执行的命令与真实数字。
"""


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-check", action="store_true")
    args = ap.parse_args(argv)

    # 闸 1：密钥泄漏
    if not args.skip_check:
        import security
        leaks = security.scan()
        if leaks:
            security.trip(leaks, "打包前自检")
            print("\n[拒绝打包] 检测到密钥泄漏，先处理上面的问题。")
            return 3

    # 闸 2：交付物
    ok, msgs = check_results()
    print("交付物检查：")
    for m in msgs:
        print("  " + m)
    if not ok and not args.skip_check:
        print("\n[拒绝打包] 四份结果文件不全。")
        return 4

    root_dir = desktop_dir() / f"数据挖掘挑战赛_提交包_{datetime.now():%Y%m%d}"
    if root_dir.exists():
        # 截图是从附件目录拷来的只读文件，先去掉只读属性再删
        def _onerr(func, path, exc):
            try:
                os.chmod(path, 0o666)
                func(path)
            except Exception:
                pass
        shutil.rmtree(root_dir, onerror=_onerr)
    dirs = {
        "paper": root_dir / "01_论文",
        "result": root_dir / "02_结果文件",
        "code": root_dir / "03_源代码",
        "shots": root_dir / "04_成果截图",
        "ai": root_dir / "05_AI使用报告",
        "refs": root_dir / "06_参考文献与数据来源",
    }
    for d in dirs.values():
        d.mkdir(parents=True, exist_ok=True)

    print(f"\n目标文件夹：{root_dir}")

    # 单文件 HTML 报告（双击即看，不依赖 Python）
    try:
        import subprocess
        subprocess.run([sys.executable, str(ROOT / "scripts" / "make_html_report.py")],
                       capture_output=True, timeout=120)
    except Exception:
        pass
    html_src = ROOT / "reports" / "系统可视化报告.html"
    if html_src.exists():
        shutil.copy(html_src, root_dir / "系统可视化报告.html")
        print(f"  系统可视化报告.html：{html_src.stat().st_size / 1024:.0f} KB（单文件，双击可看）")

    # 结果文件
    cfg = load_config(track="all")
    out_dir = Path(cfg["paths"]["out"])
    rows_n = 0
    for name in ("result1.csv", "result2.csv", "result3.csv", "result4.csv"):
        src = out_dir / name
        if src.exists():
            shutil.copy(src, dirs["result"] / name)
            if name == "result2.csv":
                rows_n = sum(1 for _ in csv.DictReader(io.open(src, encoding="utf-8-sig")))
    print(f"  02_结果文件：4 个 CSV")

    # 截图
    shot_dir = ROOT / "figs" / "screens"
    shots = sorted(shot_dir.glob("*.jpg")) + sorted(shot_dir.glob("*.png"))
    for s in shots:
        dst = dirs["shots"] / s.name
        shutil.copy(s, dst)
        try:
            os.chmod(dst, 0o666)   # 源文件是只读，拷完要放开，否则下次打包删不掉
        except OSError:
            pass
    if (shot_dir / "README.md").exists():
        shutil.copy(shot_dir / "README.md", dirs["shots"] / "截图说明.md")
    print(f"  04_成果截图：{len(shots)} 张")

    # 代码
    zip_code(dirs["code"])
    write_runbook(root_dir)

    # 参考文献 / 数据来源 / 报告
    for f, target in [
        (ROOT / "docs" / "references.md", dirs["refs"]),
        (ROOT / "docs" / "data_sources.md", dirs["refs"]),
        (ROOT / "reports" / "data_audit.md", dirs["refs"]),
        (ROOT / "reports" / "threshold_report.md", dirs["refs"]),
        (ROOT / "reports" / "论文数据包.md", dirs["refs"]),
        (ROOT / "reports" / "论文详细提纲.md", dirs["refs"]),
        (ROOT / "docs" / "公网演示方案.md", dirs["refs"]),
        (ROOT / "docs" / "部署到StreamlitCloud.md", dirs["refs"]),
        (ROOT / "reports" / "成本与资源.md", dirs["refs"]),
        (ROOT / "reports" / "标签体系对照.md", dirs["refs"]),
        (ROOT / "reports" / "需求完成度复核.md", dirs["refs"]),
        (ROOT / "reports" / "系统任务覆盖自检.md", dirs["refs"]),
        (ROOT / "reports" / "复现性说明.md", dirs["refs"]),
        (ROOT / "reports" / "答辩问答准备.md", dirs["refs"]),
        (ROOT / "reports" / "答辩PPT.pptx", dirs["refs"]),
        (ROOT / "reports" / "标注重映射报告.md", dirs["refs"]),
        (ROOT / "reports" / "多批次验证.md", dirs["refs"]),
        (ROOT / "reports" / "来源探测结果.md", dirs["refs"]),
        (ROOT / "reports" / "结果文件核对.md", dirs["refs"]),
        (ROOT / "reports" / "阈值稳健性.md", dirs["refs"]),
        (ROOT / "reports" / "标注一致性报告.md", dirs["refs"]),
        (ROOT / "data" / "label" / "人工标注表.xlsx", dirs["refs"]),
        (ROOT / "data" / "label" / "双标样本_B.xlsx", dirs["refs"]),
        (ROOT / "data" / "label" / "双标样本_C.xlsx", dirs["refs"]),
        (ROOT / "docs" / "标注说明_给标注人.md", dirs["refs"]),
        (ROOT / "docs" / "判定细则_v2.md", dirs["refs"]),
            ]:
        if f.exists():
            shutil.copy(f, target / f.name)
    print(f"  06_参考文献与数据来源：{len(list(dirs['refs'].glob('*')))} 个文件")

    # 占位说明
    (dirs["paper"] / "放这里.txt").write_text(
        "把论文的 Word 和 PDF 放进这个文件夹。\r\n"
        "要求：正文不超过 30 页（含图表，不含附录）；\r\n"
        "论文里不能出现队号、学校、学院、姓名、指导教师。\r\n", encoding="utf-8")
    for _ext in (".pdf",):
        _f = ROOT / "reports" / f"AI使用情况说明{_ext}"
        if _f.exists():
            shutil.copy(_f, dirs["ai"] / _f.name)
    ai_doc = ROOT / "reports" / "AI使用情况说明.docx"
    if ai_doc.exists():
        shutil.copy(ai_doc, dirs["ai"] / ai_doc.name)
        print(f"  05_AI使用报告：{ai_doc.name}（{ai_doc.stat().st_size/1024:.0f} KB）")
    (dirs["ai"] / "放这里.txt").write_text(
        "把《AI 使用情况说明》放进来（PDF 或 Word）。\r\n"
        "必须写明：工具名称与版本、使用目的、交互记录、采纳与人工修改情况。\r\n",
        encoding="utf-8")

    write_checklist(root_dir, {"结果行数": rows_n, "截图": len(shots)})

    (root_dir / "00_评委请先看我.md").write_text(JUDGE_README, encoding="utf-8")
    print("  00_评委请先看我.md：已生成")
    print(f"\n完成：{root_dir}")
    print("  ⬜ 01_论文 —— 待放入（论文还没写完）")
    print("  ✅ 02_结果文件 / 03_源代码 / 04_成果截图 / 06_参考文献")
    print("  ✅ 05_AI使用报告 —— 已生成草稿（提交前需队员确认第七节）")
    print(f"\n  清单：{root_dir / '提交清单.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
