# 最终复扫

- 时间：2026-11-23T01:11:05Z
- 命令：python scripts/scan_report.py --dir out/report --dir out/negative --dir artifacts --blacklist fixtures/company_names.txt --log <repo>/artifacts/final-scan.log --min-files 12
- 结果：PASS；scanned_files=24；hits=0；exit=0
- 覆盖：本轮 ACCEPTANCE.md、acceptance.json、artifacts/logs、out/report、out/negative；因此计数较验收前多。
- 边界：FINAL-SCAN.md 与 final-scan.log 在本次复扫之后写入，不声称被本次扫描覆盖。
