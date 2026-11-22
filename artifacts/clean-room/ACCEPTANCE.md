# 验收记录（AC1–AC4）

- 生成时间：2026-11-22T23:30:23Z
- 总体：PASS
- 预估值：120 家；实际变化：120 家；并集：120 家
- 一致率：100.00%（120/120），阈值 99.00%
- 冻结：{"actual": {"churned": 30, "renewed": 30}, "baseline": {"churned": 30, "renewed": 30}}；reason 错误 0；set_drift 0
- 扫描（验收前）：20 个文件（要求 ≥12），命中 0；最终复扫见 artifacts/FINAL-SCAN.md；negative：0.983333（exit 2）
- 测试：37/37 passed，skipped 0（exit 0）；run.log 回读错误 0

## 命令与退出码

| 步骤 | 命令 | 退出码 | 期望 |
|---|---|---:|---:|
| pre | python -m cal.cli verify-health-switch --from v3 --to v4 --mode pre --asof 2026-11-22 --out out/report | 0 | 0 |
| post | python -m cal.cli verify-health-switch --from v3 --to v4 --mode post --asof 2026-11-22 --actual fixtures/actual.csv --estimate out/report/estimate.csv --out out/report | 0 | 0 |
| negative（预期 2） | python -m cal.cli verify-health-switch --from v3 --to v4 --mode post --asof 2026-11-22 --actual fixtures/negative_actual.csv --estimate out/report/estimate.csv --out out/negative | 2 | 2 |
| scan | python scripts/scan_report.py --dir out/report --dir out/negative --dir artifacts --blacklist fixtures/company_names.txt --log out/report/scan.log --min-files 12 | 0 | 0 |
| pytest | python -m pytest -q | 0 | 0 |

## 四组证据

1. 一致率（状态+分数）：120/120 = 1.000000，阈值 0.99；分数漂移 0 个（计为不匹配）。
2. 冻结集合：{"actual": {"churned": 30, "renewed": 30}, "baseline": {"churned": 30, "renewed": 30}}，逐家错误 0。
3. 原因/版本：changed.csv 每条 reason=权重版本切换、weight_from=v3、weight_to=v4；错误 0。
4. 企业名扫描（验收前）：out/report、out/negative、artifacts 共 20 个文本文件，命中 0；ACCEPTANCE.md/acceptance.json 写出后的最终复扫见 FINAL-SCAN.md。

## 日志

- artifacts/logs/pre.log / post.log / negative.log / scan.log / pytest.log
- out/report/pre-report.md 为 pre 预估样例；out/report/report.md 为 post 核对样例。
- out/report/run.log 末行 mode=acceptance，checks 同时包含上述四组证据、post 退出码与测试数。
- out/report/compare.json 与 out/report/report.md 由同一 checks 生成；run.log 末行可回读对账。
