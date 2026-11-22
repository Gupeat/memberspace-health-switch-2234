# 验证规则说明（verify-rules）

本文件把“健康分权重切换影响验证”的口径写死，避免报告与实现各说一套。

## 1. 生命周期状态与阈值

| 状态 | 判定 |
|---|---|
| active | score >= 75.0 |
| silent | 60.0 <= score < 75.0 |
| churn_warning | score < 60.0 |
| renewed | 冻结状态，不按分数重算 |
| churned | 冻结状态，不按分数重算 |

阈值来自 `fixtures/config-pre.json` / `config-post.json` 的 `bands`，默认值如上；配置文件不允许 `active_min <= silent_min`。

## 2. 分数

`score = activity*w_activity + transaction*w_transaction + engagement*w_engagement + tenure*w_tenure`，四舍五入到 2 位小数。两套权重文件必须四键齐全且和为 1.0。

示例：v3 = 0.40/0.30/0.20/0.10；v4 = 0.20/0.25/0.35/0.20。

## 3. 切换前（pre）守卫

pre 读取配置里的 `active_version`。只有它等于 `--from` 时才允许生成预估，否则退出码 3。这是为了证明预估值确实由“当前生效的 v3”算出，而不是用 v4 反推。

## 4. 四个变化方向

- active -> silent：`active_to_silent`
- silent -> active：`silent_to_active`
- 任意非预警 -> churn_warning：`enter_churn_warning`
- churn_warning -> 任意非预警：`exit_churn_warning`

冻结状态（renewed/churned）不参与以上方向。

## 5. 一致率

- 预估清单：pre 的 `estimate.csv`。
- 实际清单：post 从切换后**全量快照**派生，只保留非冻结、旧状态 != 新状态的行。
- 匹配键：`(company_pid, old_status, new_status, direction)`。
- 分母：预估与实际公司 pid 的并集行数。
- `set_drift`：只在一侧出现的变化行，记 `actual_only` / `estimate_only`；计入并集分母，old/new/direction 只在两侧交集上比较。
- 阈值：默认 0.99；`ratio = matched / total`（保留 6 位小数）。
- 边界样例：120/120=1.000000 通过；119/120=0.991667 通过；118/120=0.983333 不通过（退出码 2）。
- post 把读入的全量快照规范化为 `out/report/actual.csv`（company_pid/state/score），不含企业名称。

## 6. 冻结状态

- renewed/churned 在切换前后必须逐家保持原状态；缺失也算失败。
- renewed、churned 的总数必须与切换前一致。
- 冻结企业的基础分档如果会变，写入 `frozen_would_change.csv`，但不自动改状态；由业务人工确认。

## 7. 预警任务

实际变化中所有“进入 churn_warning”的企业，必须能在 `warn_tasks.json` 里按 company_pid 找到任务；缺失即失败。

## 8. 原因与版本号

每条实际变化记录必须带：

- `reason = 权重版本切换`
- `weight_from = --from`
- `weight_to = --to`

`--from == --to` 直接判失败。`changed.csv` 由 post 生成，所以正常运行时天然带齐；测试会构造坏行验证断言确实生效。

## 9. 隐私扫描

`scripts/scan_report.py` 扫描报告目录中的文本文件：

- 20 个虚构企业名（`fixtures/company_names.txt`）；
- 名称后缀 `有限公司|集团|工作室|中心`。

命中数必须为 0；扫描器自身的 `scan.log` 不参与扫描。报告只允许 company_pid、manager_id、club_id 等假名 id。

`scripts/run_acceptance.py` 会依次跑 pre/post/negative/scan/pytest，并在 `out/report/run.log` 末行追加 `mode=acceptance` 的 `checks`：一致率、冻结集合、reason/版本、扫描命中、negative 退出码、测试数。`check_log_consistency` 重新读该行并与 compare.json 的字段对账，不一致按失败处理。

## 10. 退出码汇总

| 退出码 | 含义 |
|---|---|
| 0 | 通过 |
| 1 | 输入/配置/扫描错误 |
| 2 | 一致率或冻结/预警/原因/版本/状态流转检查失败 |
| 3 | pre 守卫失败 |

## 11. 已知限制

- 桩数据是确定性的合成数据，不能外推生产真实效果。
- `actual.csv` 必须是全量快照；只给变化行会判缺失。
- 分数漂移 >0.01 会记录在 `compare.json`，但不单独改变退出码；如业务要求严格，可在集成层加断言。
- 本工具不调用生产 CRM、不发消息、不改状态。
