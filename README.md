# 健康分权重切换影响验证（S6-CAL-019）

对会员空间平台的健康分权重切换做**切换前预估、切换后验证**：同一批企业、同一组四维信号，分别用 v3 / v4 两套权重重算健康分，输出生命周期状态变化清单、一致率、冻结状态校验、预警任务关联和隐私扫描结果。

本仓库是 ClawHunt #2234 的交付物。数据全部为虚构桩数据（500 家企业（20 个虚构基名 + 3 位后缀，500 个唯一全名）、20 位会员经理、5 个会所），不包含真实企业、真实手机号或客户信息。

GitHub Actions 的 `clean-room` 工作流在公开 Ubuntu + Python 3.11/3.12 上重跑单测与一键验收，证据见 Actions 运行记录。

## 快速开始

要求 Python 3.11+，运行时只用标准库；测试用 pytest。CI 用 3.11/3.12 matrix 各跑一遍。

```bash
python -m pip install -r requirements.txt
python -m pip install -e .            # 安装 cal 命令入口（也可继续用 python -m cal.cli）
cal --help                            # 验证 console entry 可用
python scripts/crm_stub.py           # 可复现地重建 fixtures/（已提交，一般不需要）
python -m cal.cli verify-health-switch --from v3 --to v4 --mode pre --out out/report
python -m cal.cli verify-health-switch --from v3 --to v4 --mode post \
  --actual fixtures/actual.csv --estimate out/report/estimate.csv --out out/report
python scripts/scan_report.py --dir out/report --dir out/negative --dir artifacts \
  --blacklist fixtures/company_names.txt --log out/report/scan.log \
  --exclude artifacts/clean-room --min-files 12
python -m pytest -q
python scripts/run_acceptance.py   # 一键跑 pre/post/negative/scan/pytest 并写 artifacts/ACCEPTANCE.md
python scripts/run_clean_room.py   # 在无缓存/无 out 的干净副本里重跑 pytest + acceptance
```

示例（已提交的 fixtures）：

- pre：500 家企业，预计 120 家状态变化，6 家冻结状态企业的分数档位会变。
- post：一致率 100.00%（120/120），冻结状态错误 0，预警任务缺失 0，原因/版本错误 0。
- negative：把 2 家企业的切换后状态改回旧状态，一致率 118/120 = 98.33%，退出码 2。
- scan：扫描 out/report、out/negative、artifacts（`--exclude artifacts/clean-room`），企业名命中 0，退出码 0；任一目录无文本文件、或三个目录合计文件数低于 `--min-files` 时失败；acceptance 要求合计至少 12 个文件，验收前 20 个、复扫 24 个。
- clean room：复制仓库但不带缓存和 `out/`，57 passed + acceptance PASS（`artifacts/clean-room/`）。

## AC 对照

| AC | 要求 | 实现 | 证据 |
|---|---|---|---|
| AC1 | 虚构数据上切换后实际变化与预估清单一致率 ≥99%（脚本输出） | `post` 读取 pre 的 `estimate.csv` 与全量 `actual.csv`，按并集与四元匹配键计算**状态+分数**一致率（old/new 分数容差 0.01）；分数超差计为不匹配 | `out/report/compare.json`、`out/report/report.md`、`artifacts/ACCEPTANCE.md` |
| AC2 | 切换后续约与已流失状态的企业数量与切换前相同（测试断言） | 冻结状态不进入变化清单；post 逐家核对状态并比较 renewed/churned 计数 | `tests/test_frozen_states.py`、`compare.json` 的 `frozen_counts`、`artifacts/ACCEPTANCE.md` |
| AC3 | 每条状态变化记录都带触发原因与版本号（测试断言） | `changed.csv` 的 reason 固定为“权重版本切换”，weight_from/weight_to 为实际版本 | `tests/test_reason_version.py`、`out/report/changed.csv` |
| AC4 | 报告中只出现假名 id，扫描不到企业名称（扫描输出） | 报告只写 company_pid/manager_id/club_id；扫描 out/report、out/negative、artifacts 中的 20 个虚构企业名与名称后缀；任一目录无文本文件、或三目录合计文件数低于 12 时失败，验收后再做一次全量复扫 | `scripts/scan_report.py`、`out/report/scan.log`、`artifacts/ACCEPTANCE.md` |

## 数据与口径

- 状态：`active`（活跃）、`silent`（沉默）、`churn_warning`（流失预警）、`renewed`（已续约）、`churned`（已流失）。
- 阈值：`active_min=75.0`，`silent_min=60.0`；即 `>=75` 活跃、`60~74.99` 沉默、`<60` 流失预警。
- 四维信号：activity、transaction、engagement、tenure；健康分 = 四维加权和，四舍五入到 2 位小数。
- 四个变化方向：active→silent、silent→active、进入 churn_warning、退出 churn_warning。
- 续约与已流失是冻结状态：切换不改变其生命周期状态，不进入变化清单；若其分数档位会变，单独写入 `frozen_would_change.csv`，供人工确认。
- 进入 churn_warning 的变化必须能按 company_pid 关联到 `warn_tasks.json` 中的预警任务。
- 报告/日志只使用 company_pid、manager_id、club_id，不使用 company_name。

## 一致率与退出码

- 匹配键：`company_pid + old_status + new_status + direction`；old/new 分数差超过 0.01 也计为不匹配。
- 分母：预估变化行与实际变化行的并集（不是 500，也不是单侧 120）。
- 只在一侧出现的变化行写入 `set_drift`（`actual_only` / `estimate_only`），计入并集分母；old/new/direction 只在两侧交集上比较。
- 阈值默认 0.99，只允许 0.99–1.0；低于 0.99 的 `--threshold` 直接按输入错误拒绝。
- 退出码：
  - `0`：一致率达标且冻结/预警/原因/版本/状态流转检查全部通过。
  - `1`：输入、配置或扫描错误（文件缺失、权重非法、阈值越界、from=to 等）。
  - `2`：一致率低于阈值，或冻结状态/预警任务/原因版本/快照完整性检查失败。
  - `3`：pre 守卫失败（配置里的 `active_version` 不等于 `--from`）。

## 输出

`out/report/`：

| 文件 | 内容 |
|---|---|
| `estimate.csv` | pre 预计变化清单，字段与 changed.csv 相同 |
| `actual.csv` | post 输出的切换后 CRM 全量快照（company_pid/state/score） |
| `changed.csv` | post 实际变化清单，含 reason 与版本号 |
| `pivot.csv` | 按会所、会员经理、四方向分组的计数 |
| `frozen_would_change.csv` | 冻结状态中分数档位会变的企业 |
| `summary.json` / `compare.json` | 机器可读汇总与校验结果 |
| `pre-report.md` | pre 预估报告样例（独立文件，不会被 post 覆盖） |
| `report.md` | post 人读核对报告；set_drift 行标 WARN、不单独判失败，但计入并集分母，可能拉低一致率并触发退出码 2 |
| `run.log` | 运行记录；末行 `mode=acceptance` 的 `checks` 同时包含一致率、冻结、reason/版本、扫描、negative、测试；`check_log_consistency` 回读校验 |
| `scan.log` | 企业名称扫描命中数 |
| `../artifacts/ACCEPTANCE.md` | 一键验收记录（命令、退出码、四组证据） |
| `../artifacts/acceptance.json` | 验收机器可读结果 |
| `../artifacts/FINAL-SCAN.md` / `final-scan.log` | 验收产物写出后的最终全量复扫；本文件与日志在复扫之后写入，不声称被本次扫描覆盖 |
| `../artifacts/clean-room/` | 干净副本重跑日志与验收记录 |

## 真实 CRM 对接

示例数据是 `fixtures/companies.json` 的 JSON 快照。生产环境把 S2-CRM 的读取结果映射为同一字段：

- `company_pid`、`state`、`club_id`、`manager_id`、`key_member`
- `signals.activity` / `transaction` / `engagement` / `tenure`

真实对接点有三处，不是只有一个文件：

- 企业基础快照（切换前状态、四维信号）：`cal/adapters/crm_source.py` 的 `load_companies_from_snapshot`，CLI 的 pre/post 都经它读取。
- 切换后全量状态快照（company_pid/state/score）：`--actual` 的 CSV，由 `cal/compare.py` 的 `load_actual_snapshot` 读取。
- 流失预警任务（company_pid 列表）：`--warn-tasks` 的 JSON，由 `cal/compare.py` 的 `load_warn_task_pids` 读取。

接真实 CRM 时按这三处的字段映射替换输入；CRM 形状的行（`pid`/`lifecycle_status`/`*_score`）经 `_normalize_record` 调用 `map_crm_record` 映射，只有已含四个 `signals` 的内部快照样本不触发映射。本工具不自己写 CRM，也不读取生产数据库；切换执行与回滚由 CRM 负责，本工具只做离线验证。

## 测试

```bash
python -m pytest -q
```

测试覆盖：正例 120/120、错 1 家 119/120 仍过线、错 2 家 118/120 退出 2、分数漂移计为不匹配、冻结状态集合与篡改、原因与版本号、报告扫描命中/未命中/多目录/空目录/`--min-files`/`--exclude`、pre 守卫与旧产物清理、post 拒绝 `--config`、from=to 拒绝、阈值下限、重复运行哈希稳定、post 输出 actual.csv、set_drift WARN、run.log 回读篡改检测、pivot 计数、CRM 形状映射与缺分数/布尔严格解析、非法 asof（含 20261123 这类非 ISO 写法）/null/NaN/布尔权重/空快照/非法 warn_tasks 行（含空 pid）拒绝、post 失败清理旧 PASS 但保留 estimate、全新 out 仍写 post-failed、CLI 解析失败清理旧产物、超长 CSV 字段转输入错误、acceptance 早期失败不保留旧 PASS 证据、clean-room 失败不保留旧 PASS 证据。

## 已知限制

- fixtures 是合成的确定性桩数据；一致率只证明本工具与该桩数据自洽，不证明生产 CRM 的真实切换结果。
- 实际快照必须是切换后的**全量**状态（500 家）；只给变化行会因缺失冻结状态而失败。
- `actual.csv` 是输入快照的规范化副本，不是 CRM 的权威数据源；权威数据仍在 S2-CRM。
- AC1 的一致率同时比较状态/方向与 old/new 分数（容差 0.01）；分数超差会在 compare.json 中列为 score_drift 并计为不匹配，因此会拉低 ratio。old_score 由同一份 baseline 企业快照重算，所以它主要验证展示值一致；真正独立来自切换后快照的是 new_score。
- 权重文件必须四键齐全且和为 1.0。