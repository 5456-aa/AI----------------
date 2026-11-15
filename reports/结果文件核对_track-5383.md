# 结果文件核对报告

> 生成于 2026-11-15 23:37　·　由 `scripts/check_result_spec.py` 按赛题标准逐条核对

| 检查项 | 结果 | 说明 |
|---|---|---|
| result1 表头与模板逐字一致 | ✅ |  |
| result1 含 UTF-8 BOM | ✅ |  |
| result2 表头与模板逐字一致 | ✅ |  |
| result2 含 UTF-8 BOM | ✅ |  |
| result3 表头与模板逐字一致 | ✅ |  |
| result3 含 UTF-8 BOM | ✅ |  |
| result4 表头与模板逐字一致 | ✅ |  |
| result4 含 UTF-8 BOM | ✅ |  |
| result1 采集批次号唯一 | ✅ | B20261115-01 |
| result1 记录编号唯一 | ✅ | 73 个 |
| result1 记录编号格式统一 | ✅ | 2~4 位前缀 + 5~8 位顺序号 |
| result1 来源名称合法 | ✅ | 3 个（附件2 内 3，清单外 0） |
| result1 发布时间格式 | ✅ | 异常 0 条 |
| result1 内容非空 | ✅ |  |
| result1 热度指标非空 | ✅ | 缺失填「无」 |
| result2 行数 = result1 | ✅ | 73 / 73 |
| result2 记录编号覆盖一致 | ✅ |  |
| result2 是否构成机会 取值 0/1 | ✅ |  |
| result2 置信度 0~1 | ✅ | 0.045 ~ 0.727 |
| result2 功能类别在附件1 | ✅ | 机会 4 条 |
| result2 所属行业在附件1 | ✅ | 机会 4 条 |
| result3 簇内记录数之和 = 机会数 | ✅ | 4 vs 4 |
| result3 簇内记录均可溯源 | ✅ | 4 个编号 |
| result3 簇内记录不重复归属 | ✅ |  |
| result3 来源覆盖名称合法 | ✅ |  |
| result3 标签在附件1 体系内 | ✅ |  |
| result4 簇号与 result3 一致 | ✅ |  |
| result4 优先级 1..N 连续 | ✅ | [1, 2] |
| result4 价值分 0~100 | ✅ | 41.7 ~ 58.3 |
| result4 按价值分降序 | ✅ |  |
| result4 标签在附件1 体系内 | ✅ |  |

**共 31 项，失败 0 项**
