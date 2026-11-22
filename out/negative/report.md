# 健康分权重切换验证报告

- 模式：post（切换后验证）
- 权重版本：v3 → v4
- 数据日期：2026-11-22
- 生成时间：2026-11-22T13:11:49Z
- 一致率：98.33%（118/120）
- 阈值：99.00%
- 结论：FAIL

## 校验项

| 检查 | 结果 | 说明 |
|---|---|---|
| 一致率 | FAIL | 118/120 = 0.983333 |
| 续约/已流失冻结 | PASS | 0 个错误 |
| 续约/已流失计数 | PASS | 切换前 renewed=30, churned=30；切换后 renewed=30, churned=30 |
| 流失预警任务 | PASS | 0 个缺失 |
| 原因与版本号 | PASS | 0 个错误 |
| 状态流转合法性 | PASS | 0 个错误 |
| 集合漂移（set_drift） | FAIL | 2 行；actual_only=0，estimate_only=2 |
| 报告/日志同源 | PASS | 0 个字段不一致；以 run.log 末行为准 |

## 差集摘要

- 预估行：120；实际变化行：118；并集：120
- 实际缺失：2 个；预估缺失：0 个
- 集合漂移 set_drift：2 行（只在一侧出现的变化行，计入一致率并集分母）
- 分数漂移（匹配行中 >0.01）：0 个
- 不匹配行：0 个

## 明细

- actual.csv：切换后 CRM 快照的规范化输出（company_pid/state/score），不含企业名称。
- changed.csv：实际变化清单，每条带 reason=权重版本切换 与 weight_from/weight_to。
- compare.json：一致率、差集、set_drift、分数漂移、冻结/预警/原因校验的机器可读结果。
- pivot.csv：按会所、会员经理、四方向分组的计数。
- run.log：末行 checks 与 compare.json/report.md 同源，四组证据（一致率、冻结、reason/版本、扫描）同段。
- 报告与日志只含假名 id，不含企业名称。
