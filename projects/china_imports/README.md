# China Equipment Imports

**Question.** How much semiconductor equipment does China import, by equipment group, origin and importer province? These are the settled customs figures the other projects and the HBM report draw on.

**Method.**
- Customs imports come from the Atlas `statistics/china_customs/`. They're allocated to groups with `reference/customs_segment_map.csv`, the same allocation `china_share_by_segment` uses.
- Mixed codes are split by scenario assumptions:
  - CMP inside 84862090: `A-CMP-IN-84862090`;
  - wet cleaning and back-end tools inside 84862090: `A-CLEAN-IN-84862090`, `A-BACKEND-IN-84862090`;
  - fab automation inside 84864039: `A-WAFER-HANDLING-IN-84864039`.
- Every group carries low/base/high values. Classification evidence is in `docs/customs_code_evidence.md`.
- Origin and province mixes come from the filtered table (8 origins × 14 provinces). They're shares of the covered value, applied to each group in proportion to its code allocation, and the coverage is reported.

**Periods.** Calendar years 2021–2025, plus 2025 and 2026 from January to the latest month held (now September), for a like-for-like comparison. The window follows the customs data. Fixed annual amounts are scaled to the months covered, now 9/12.

**Outputs (`results/`).**

| File | Contents |
|---|---|
| `imports_by_group.csv` | Period × group, USD m by scenario case (low/base/high) plus min/max across cases, with a WFE flag. For residual groups the low case gives the highest value |
| `imports_by_code.csv` | Period × HS8 totals, with each code's group allocation |
| `origin_mix.csv`, `province_mix.csv` | Group × period × origin/province share of the covered value, plus coverage |
| `summary.md`, `manifest.json` | Summary and provenance |

**Status.** Tier 3. The following are all `proposed`: the scenario shares, the test code as a floor, and mixed codes that are not separable (e-beam inspection, X-ray).
