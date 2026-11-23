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

阈值来自 `fixtures/config-pre.json` 的 `bands`，默认值如上；配置文件不允许 `active_min <= silent_min`。`fixtures/config-post.json` 只作为 pre 守卫测试的反例配置，post 不接受 `--config`。

## 2. 分数

`score = activity*w_activity + transaction*w_transaction + engagement*w_engagement + tenure*w_tenure`，四舍五入到 2 位小数。两套权重文件必须四键齐全且和为 1.0。

示例：v3 = 0.40/0.30/0.20/0.10；v4 = 0.20/0.25/0.35/0.20。

## 3. 切换前（pre）守卫

pre 读取配置里的 `active_version`。只有它等于 `--from` 时才允许生成预估，否则先删除同一输出目录里的旧 pre/post 产物（包括 estimate.csv、pre-report.md、report.md、compare.json、changed.csv、actual.csv、run.log、scan.log），写一条 `mode="pre-guard-failed"` 的 run.log，再退出码 3。任何 pre 输入错误（非法 asof、NaN 权重、空快照、权重版本不符）也先清理旧产物并写 `mode="pre-failed"`，避免把上一代 PASS 当成当前结果。这是为了证明预估值确实由“当前生效的 v3”算出，而不是用 v4 反推。

pre 的报告写入 `out/report/pre-report.md`，post 写 `out/report/report.md`，两者互不覆盖；交付同时包含预估样例与核对样例。`--from == --to` 在进入子命令前直接按输入错误拒绝（退出码 1）。

## 4. 四个变化方向

- active -> silent：`active_to_silent`
- silent -> active：`silent_to_active`
- 任意非预警 -> churn_warning：`enter_churn_warning`
- churn_warning -> 任意非预警：`exit_churn_warning`

冻结状态（renewed/churned）不参与以上方向。

## 5. 一致率

- 预估清单：pre 的 `estimate.csv`。
- 实际清单：post 从切换后**全量快照**派生，只保留非冻结、旧状态 != 新状态的行。
- 匹配键：`(company_pid, old_status, new_status, direction)`，并要求 |old_score 差| <= 0.01 且 |new_score 差| <= 0.01。post 还会校验 estimate 的 `weight_from`/`weight_to` 与 `--from`/`--to` 一致，不一致按输入错误退出 1。
- 分母：预估变化行与实际变化行的并集行数（不是 500 家，也不是单侧 120 行）。
- `set_drift`：只在一侧出现的变化行，记 `actual_only` / `estimate_only`；计入并集分母，old/new/direction 只在两侧交集上比较。该行只标 WARN，不单独改变退出码。
- 一致率口径：状态/方向匹配且 old/new 分数差都在 0.01 以内才算 matched；状态匹配但分数超差的记 `score_drift` 并计为不匹配。
- 阈值：默认 0.99，只允许 0.99–1.0；`ratio = matched / total`（保留 6 位小数）。低于 0.99 的 `--threshold` 按输入错误拒绝。
- 边界样例：120/120=1.000000 通过；119/120=0.991667 通过；118/120=0.983333 不通过（退出码 2）。只改分数也可能触发不通过。
- post 把读入的全量快照规范化为 `out/report/actual.csv`（company_pid/state/score），不含企业名称；`compare.json` 记录 estimate 路径与 SHA-256。
- 数据日期 `--asof` 默认为配置里的 `asof`（pre）或当天（post）；pre 会校验配置中的 asof，非法 `YYYY-MM-DD` 直接拒绝并清理旧产物。

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

`--from == --to` 在 dispatch 前直接判输入错误（退出码 1）。`changed.csv` 由 post 生成，所以正常运行时天然带齐；测试会构造坏行验证断言确实生效。

## 9. 隐私扫描

`scripts/scan_report.py` 扫描多个目录中的文本文件（`--dir` 可重复）：

- `out/report`（pre/post 产物、报告、日志）；
- `out/negative`（负例产物）；
- `artifacts`（验收记录）；
- 20 个虚构企业名（`fixtures/company_names.txt`）；
- 名称后缀 `有限公司|集团|工作室|中心`。

命中数必须为 0；扫描器自身的 `scan.log` 不参与扫描。报告只允许 company_pid、manager_id、club_id 等假名 id。每个 `--dir` 都必须含文本文件，否则失败；`--min-files` 可要求扫描文件数下限，acceptance 使用 12，避免 AC4 空转。

`scripts/run_acceptance.py` 会依次跑 pre/post/negative/scan/pytest，并在 `out/report/run.log` 末行追加 `mode=acceptance` 的 `checks`：一致率、冻结集合、reason/版本、扫描命中、negative 退出码、测试数。`check_log_consistency` 只回读该行与内存 checks 对比（不解析 compare.json/report.md）；不一致按失败处理。写出 ACCEPTANCE.md/acceptance.json 后还会对三个目录做一次最终复扫，结果写入 `artifacts/FINAL-SCAN.md` 和 `final-scan.log`；这两个文件在复扫之后生成，不声称被本次扫描覆盖。

## 10. 退出码汇总

| 退出码 | 含义 |
|---|---|
| 0 | 通过 |
| 1 | 输入/配置/扫描错误（文件缺失、权重非法、阈值越界、from=to、扫描 0 文件等） |
| 2 | 一致率、快照完整性或冻结/预警/原因/版本/状态流转检查失败 |
| 3 | pre 守卫失败 |

## 11. 已知限制

- 桩数据是确定性的合成数据，不能外推生产真实效果。
- `actual.csv` 必须是全量快照；只给变化行会判缺失。
- 分数漂移 >0.01 记录在 `compare.json` 并计为不匹配；单条漂移仍可能因 119/120=99.17% 通过 0.99 阈值，这是 AC1 的 ≥99% 口径。
- 本工具不调用生产 CRM、不发消息、不改状态。
