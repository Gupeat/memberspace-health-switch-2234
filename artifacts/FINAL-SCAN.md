# 最终复扫

- 时间：2026-11-23T00:21:42Z
- 命令：python scripts/scan_report.py --dir out/report --dir out/negative --dir artifacts --blacklist fixtures/company_names.txt --log <repo>/artifacts/final-scan.log --min-files 12
- 结果：PASS；scanned_files=29；hits=0；exit=0
- 覆盖：本轮 ACCEPTANCE.md、acceptance.json、artifacts/logs、out/report、out/negative，以及上一代 artifacts/clean-room（5 个文件）；因此计数较验收前多。
- 边界：FINAL-SCAN.md 与 final-scan.log 在本次复扫之后写入，不声称被本次扫描覆盖。
