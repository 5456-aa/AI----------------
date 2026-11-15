# AI 应用场景的智能挖掘与机会评估系统（双赛道）

> **🎬 不想敲命令？双击这两个文件就行：**
> 1. 双击 **`设置KEY.bat`** —— 粘贴大模型 key（详细图文见 [`docs/如何配置API密钥.md`](docs/如何配置API密钥.md)）
> 2. 双击 **`跑全流程.bat`** —— 自动跑完，结果在 `data/out/`
> 3. 双击 **`启动界面.bat`** —— 浏览器打开可视化系统（也可在这里填自己的 key）
> 4. 双击 **`发起新需求.bat`** —— 输入任意需求方向，现场采集并生成新批次
> 5. 双击 **`启动系统.bat`** —— 首页（8500）：点模板或输入需求方向 → 一键采集分析；
>    跑完可跳转分析看板（8501）与问答（8505），批次参数自动带过去
> 6. 需要给评委公网地址时，双击 **`开启公网访问.bat`**（自动开隧道并打印 https 地址）
> 7. 双击 **`在线标注.bat`** —— 多人同时在线标（每人独立文件），或双击 **`标注工具.bat`** 单人标
> 8. 双击 **`问答咨询.bat`** —— 用自然语言查结果（数字全部来自 CSV，可溯源）
> 9. 双击 **`标注工具.bat`**
>
> 需要**固定公网地址**（不依赖本机开机）：见 `docs/部署到StreamlitCloud.md`，
> 推送前先跑 `python scripts/check_cloud_ready.py` 自检。 —— 人工标注 120 条，用于标定判别阈值（论文的"模型评价客观性"）
>    也可以直接用 Excel 标：`data/label/人工标注表.xlsx`（label 列有下拉框）
>
> 不配 key 也能跑，只是质量差一些。

> 2026 甘肃省第三届大学生数据挖掘挑战赛 · 本科组 · 赛题实现骨架
>
> 一条流水线从"原始采集记录"走到"四个提交 CSV + 立项策划案 + 仪表盘"，每条参数可配置、每步结果可溯源。
> **支持两个需求方向并行：电商客服与运营 / 教育学习与教学管理。**

---

## 0. 双赛道怎么跑

```bash
pip install -r requirements.txt

# 演示数据（两赛道各一套）
python scripts/make_demo.py

# 单跑一个赛道（各自独立的结果与图表）
python run_all.py --track ecommerce --batch DEMO20261111-01
python run_all.py --track education --batch DEMO20261111-02

# 两赛道合并成"提交版"（同一批次号，统一聚类/评分/排序）
python run_all.py --track all --batch B20261111-01

# 校验 + 出审计 + 出论文图
python validate.py --track all
python scripts/report_audit.py --track all
python scripts/make_figures.py --track all

# 仪表盘
streamlit run ui/app.py      # 左上角可切赛道
```

| 赛道 | 输出目录 | 记录编号前缀 |
|---|---|---|
| `ecommerce` | `data/out/ecommerce/` | `DS00001…` |
| `education` | `data/out/education/` | `JY00001…` |
| `all`（提交用） | `data/out/` | 两前缀并存，不撞号 |

四个提交文件（`all` 赛道）：

| 文件 | 内容 |
|---|---|
| `result1.csv` | 清洗去重后的全部记录 |
| `result2.csv` | 逐条机会判别（0/1 + 置信度）+ 功能类别 / 行业 |
| `result3.csv` | 主题簇 + 簇内记录数与来源覆盖（可溯源） |
| `result4.csv` | 簇机会价值分 + 优先级 |

> ⚠️ 演示批次号以 `DEMO` 开头，`validate.py` 会警告。**提交前必须换成真实采集数据。**

## 1. 用真实数据跑

```bash
# 采集（按赛道，用 track 里配好的检索词）
python run_collect.py --track ecommerce --limit 120
python run_collect.py --track education --limit 120

# 或者先探一个源
python run_collect.py --track education --source 掘金 --keyword "AI 批改" --limit 20
```

**当前实测可用的源（2026-11-11 验证，9 个正常出数）**

| 源 | 附件2 | 语言 | 方式 | 实测条数 |
|---|---|---|---|---|
| GitHub | ✅ | 英 | 官方 REST API（Issues 搜索，`created:>2024-01-01`） | 204 |
| 掘金 | ✅ | 中 | 站内搜索公开接口（POST，可按关键词检索） | 238 |
| SegmentFault | — | 中 | Atom feed（V2EX 的问答类替代） | 70 |
| 博客园 | — | 中 | Atom feed | 32 |
| InfoQ中国 | ✅ | 中 | RSS | 27 |
| 量子位 | ✅ | 中 | RSS | 10 |
| IT之家 | ✅ | 中 | RSS（要求两个词同时命中，压噪声） | 5 |
| 少数派 | ✅ | 中 | RSS | 4 |
| Stack Overflow | ✅ | 英 | Stack Exchange 官方 API（按投票排序） | 2 |
| ~~V2EX~~ | ✅ | 中 | 官方 API | ❌ DNS 正常但 80/443 全部 TCP 超时 |
| ~~36氪 / 机器之心~~ | ✅ | 中 | RSS / Web | ❌ SPA 渲染、feed 失效、RSSHub 公共实例不可达 |

> 论文「数据来源」一节要交代**为什么没用某些源**（见 `collectors/registry.py → SOURCE_STATUS`）。

# 跑链路
python run_all.py --track ecommerce
python run_all.py --track education
python run_all.py --track all            # 自动复用各赛道的清洗判别结果
```

`data/raw/<track>/*.jsonl` 每条记录字段：

```json
{"source": "V2EX", "url": "https://...", "title": "...", "content": "...",
 "published_at": "2026-10-28", "heat": {"回复": 42}, "record_id": "DS00001",
 "batch": "B20261111-01", "source_category": "问答与需求社区"}
```

> `source` 必须写**附件2 的规范名**（`哔哩哔哩` 而不是 `B站`）。

## 2. 目录结构

```
ai-opp-system/
├─ config.yaml           # 赛道定义 + 全部参数（阈值/权重/聚类/LLM）
├─ schema.py             # 四个 CSV 表头 + 附件1 标签体系 + 附件2 来源清单
├─ io_utils.py           # 配置（多赛道）/JSONL/带 BOM 的 CSV/批次号/日志
├─ run_all.py            # 一键流水线（--track / --stage）
├─ run_collect.py        # 采集入口（--track）
├─ validate.py           # 交付自检（表头/编码/行数/主键/交叉一致性）
├─ collectors/           # 采集适配器（GitHub / V2EX 参考实现）
├─ pipeline/
│   ├─ clean.py          # 清洗规则链 + 有效性判定 + 分来源审计
│   ├─ dedup.py          # L1 URL / L2 SimHash / L3 TF-IDF 余弦 三层去重
│   ├─ judge.py          # 规则特征 + LLM 打分 + sigmoid 校准 + 双标签
│   ├─ cluster.py        # 向量化 + k 扫描 + 小簇合并 + 主题名
│   └─ score.py          # 四维指标 + 熵权/AHP + 敏感性分析
├─ llm/                  # OpenAI 兼容客户端（带缓存）+ 提示词
├─ export/               # 四个 CSV 导出 / 立项策划案（md + docx）
├─ ui/app.py             # Streamlit 仪表盘（可按赛道切换）
├─ docs/
│   ├─ references.md     # 参考文献（GB/T 7714）+ 待核对字段一览 + 正文引用位置对照表
│   ├─ data_sources.md   # 数据来源/检索式/合规声明/AI 使用报告 素材
│   └─ 论文引用核对与改写清单.docx   # 标红版：红字=必须你们核对/重写
├─ scripts/
│   ├─ make_demo.py      # 两赛道演示数据
│   ├─ report_audit.py   # 数据审计报告（评分标准第一条）
│   ├─ tune_threshold.py # 标注 → P-R 曲线 → 标定 τ
│   └─ make_figures.py   # 论文图表一键生成
├─ data/{raw,clean,out}/<track>/
├─ reports/<track>/       # 策划案 + data_audit.md
└─ figs/<track>/          # 论文图
```

## 2.1 当前数据状态（2026-11-11 实跑）

```
原始采集 448 条（GitHub 268 / 掘金 172 / Stack Overflow 7 / 少数派 1）
   ↓ 清洗（剔除 3 条过短）
445 条 → 三层去重剔除 106 条
415 条 → 判别：机会 47 条（11.3%）
   ↓ 分赛道聚类
电商 3 簇 + 教育 2 簇 = 5 个主题簇 → 价值分排序
```

`validate.py` 当前 **0 错误 0 警告**。

## 2.2 零配置演示（不用申请 Key）

没有 API Key 也能跑出与论文一致的结果——程序会先用**预置缓存**（`data/cache/llm_calls.jsonl`）：

1. 命中缓存 → 直接用（等于复用已生成的大模型判断）
2. 未命中 → 降级为纯规则（仍能出四件套，只是质量低一档）

所以：**同一份数据 100% 可复现；换新数据才需要自己的 Key。**

```bash
python run_all.py --track all --batch B20261113-01   # 无 key 也能跑
```

> 为什么不接「手机端 DeepSeek 免费版 / 账号登录」：DeepSeek 没有对第三方开放
> OAuth 登录或免费版 API，抓取 App 接口违反服务条款。零配置要靠缓存或本地模型，
> 不能靠「借用户的 App 账号」。

## 3. 关键设计（写论文时直接对照）

| 环节 | 做法 | 论文里的卖点 |
|---|---|---|
| 去重 | L1 URL → L2 SimHash(汉明≤3) → L3 TF-IDF 余弦≥0.95 | 三层漏斗 + **分来源剔除明细** |
| 翻译 | 中文占比<30% 的记录经 LLM 译为中文，原文存 `orig_*` | 英文源可用，来源多样性翻倍且可溯源 |
| 审计 | `audit_clean/audit_dedup` 每源统计缺失、过短、非中文、广告、去重 | 直接命中"数据预处理完整性" |
| 判别 | 4 条规则 → 3 个连续分 + 1 个排除类别；`sigmoid(slope·加权和+bias)` | 规则可解释 + LLM 覆盖语义 |
| 阈值 | 150+ 条人工标注，扫 τ 取 F1 最大点 | `tune_threshold.py` 出 P-R 曲线与混淆矩阵 |
| 聚类 | TF-IDF+SVD 或 BGE；k 扫描 + 均衡约束 + **简约原则** | 三种约束的取舍本身就是方法贡献 |
| 评估 | Silhouette / DB / CH + 簇内-簇间相似度差 | 无监督场景下的完整评估方案 |
| 权重 | 熵权 + AHP 组合，α 可调 | 组合赋权 + ±10% 扰动敏感性 |
| LLM | OpenAI 兼容，**全部调用落缓存** | 可复现；不可用自动降级规则 → 天然 baseline |

## 3.5 密钥熔断（防 key 混进提交包）

| 项 | 说明 |
|---|---|
| 扫描什么 | 项目目录内所有文本文件（.py/.md/.json/.csv/.bat/日志…），匹配 `sk-` 长串与硬编码 `api_key=…` |
| 发现之后 | 写 `.leak_alert` + `LEAK_ALERT.txt`，**流程立即中止**（退出码 3），不出包 |
| 生效位置 | `run_all.py` 启动时、`validate.py` 交付自检、`设置KEY.bat` 写完 key 后、`跑全流程.bat` 最前面 |
| 解除方式 | 修掉泄漏后 `python scripts/guard_secrets.py --clear` |
| 边界（重要） | **只读扫描 `ai-opp-system` 目录**；不读 `~/.dsh/.credentials.yaml`、不改进程环境变量，**不影响当前对话所用的 API** |

手动检查：`python scripts/guard_secrets.py`（干净=0，泄漏=3）。扫描一次约 0.6 秒。

## 4. LLM 配置

```bash
set DEEPSEEK_API_KEY=sk-xxx        # PowerShell: $env:DEEPSEEK_API_KEY="sk-xxx"
```

`config.yaml` 里 `judge.use_llm: false` 可切到纯规则基线（离线也能跑）。两赛道**共用缓存**，同一 prompt 不会重复计费。

## 5. 交付前

```bash
python validate.py --track all      # 必须 ✅
python scripts/report_audit.py --track all
python scripts/make_figures.py --track all
```

再按 `../赛题解读与实施方案.md` 第 9 节清单逐条打勾。

## 6. 已实现 / 待补

- [x] 双赛道配置、独立输出、合并提交
- [x] 清洗 + 三层去重 + **分来源数据审计**
- [x] 规则 + LLM 判别、双标签、阈值标定脚本
- [x] 聚类（k 扫描 + 均衡 + 简约约束）+ 评估 + 主题名
- [x] 熵权/AHP + 敏感性
- [x] 四 CSV 导出 + 自检
- [x] 策划案 md/docx、仪表盘（切赛道）、论文图
- [x] 翻译层（英文 → 中文，原文留档，可关闭）
- [ ] 更多采集适配器（Stack Overflow / RSS 类）
- [ ] 人工标注小工具（当前 CSV 手填）
- [ ] BGE 句向量切换（`cluster.embedding: sentence_transformers`，需装 torch）

## 7. 已知限制（论文「模型局限」一节要写）

1. **TF-IDF 基线会低估簇数**：演示数据上电商赛道只分出 2 个簇，因为短文本的 TF-IDF 向量近乎正交。
   换成 BGE 句向量（`cluster.embedding: sentence_transformers`）后语义相似度更真实；
   正式数据（每赛道 150+ 条）结构也会明显好于演示数据。
2. **未配置 API Key 时**：英文记录保留原文不翻译（`translated=false`），规则层的英文句式已覆盖，
   但效果弱于翻译后；论文需如实说明。
3. **单条簇**：`min_cluster_size=2` 会把相似度达标的单点并入最近簇，达不到则保留为独立方向，
   `validate.py` 会给出警告——论文里要交代处理规则。
