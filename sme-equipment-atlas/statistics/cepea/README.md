# CEPEA: Domestic Semiconductor Equipment Industry Statistics

Publisher: 中国电子专用设备工业协会 (China Electronics Production Equipment Industry Association, CEPEA), a national industry association supervised by MIIT. Figures are transcribed from its monthly members' bulletin 行业简讯, marked 行业内交流 ("for industry exchange").

- **Access:** full reports on <https://www.cepea.com/> require a members' login. Bulletins are reposted publicly by member Jiangsu Sujing Group at <https://sjjt.com/news.aspx?cateid=71>.
- **PDFs are not committed.** They are held in a local archive with its own index; match files by `sha256` in `bulletins.csv`.

## Boundary and survey

- **Who is covered:** CEPEA surveys domestic manufacturers with semiconductor-equipment revenue of at least ¥10m: 58 firms (2021), 77 (2022), 84 (2023), 82 (2024), 87 (2025). Unlisted firms appear only if they report.
- **What is measured:** sales revenue (销售收入, VAT-exclusive), export delivery value (出口交货值) and total profit, in ¥100m (亿元). Revenue includes exports.
- **"半导体设备 (semiconductor equipment)" includes solar-cell equipment, LED, SiC and other device equipment.** IC equipment (集成电路设备) = silicon-wafer equipment + wafer/chip fab (front-end) equipment + packaging and test; the sub-split is published from 2024.
- **Scope differs by firm** because it is self-reported. Compared with filings for 2025:
  - Piotech's CEPEA figure equals its semiconductor-equipment segment.
  - Hwatsing's equals whole-company revenue including services.
  - Yitang's is about 98% of company revenue.
  - NAURA's and AMEC's are below company revenue.

## Files

| File | Grain | Notes |
|---|---|---|
| `semiconductor_equipment_annual.csv` | year × level × category | Taken from each June bulletin's annual semiconductor-equipment analysis (《X年中国半导体设备经济运行分析》), **as first reported**. `n_firms`, `source_bulletin` and `note` hold sample size and later revisions (e.g. 2022 IC 288.92 later cited as 319; 2024 restated on the 2025 sample) |
| `semiconductor_equipment_top10.csv` | year × rank | Top 10 by semiconductor-equipment revenue, with profit. Includes solar-equipment makers |
| `semiconductor_equipment_h1.csv` | year × scope | H1 totals and IC growth/share from September bulletins. Where a bulletin gives only growth and share, the revenue cell is blank and the share is in `note` |
| `bulletins.csv` | one row per issue, 2022-01 → 2026-08 (44 issues) | Repost URL, sha256, page count, issue date, and `contents` flags from text search (indicative only) |

Values were transcribed by hand from the PDFs (2026-09-23). Each row names its bulletin issue.
