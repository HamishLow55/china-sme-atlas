# China Share by Segment

**Question.** What share of China's wafer-fab equipment market do domestic vendors supply, by equipment segment? This is a public-data reconstruction of the sell-side "Chinese suppliers by segment / self-sufficiency" chart (e.g. brokers' CY2025 China WFE segment charts), used as a **method reference only**. No third-party values are used.

**Method.**
- China market (group, year) = customs imports mapped to the group (`reference/customs_segment_map.csv`) + domestic vendors' revenue in the group (Atlas).
- Fab automation: AMHS imports (84864031) count in full in `track_automation_other`. 84864039 (other handling) counts only in the high case, up to half (`A-WAFER-HANDLING-IN-84864039`), because it mixes flat-panel handling and robots imported as tool modules.
- Domestic revenue has two layers, reported separately:
  - **Atlas layer.** Category-level Atlas observations. Mixed baskets are used only through `reference/scope_group_map.csv`. A mapped scope overrides its Atlas category, and several mapped scopes in one group are summed, so map only non-overlapping scopes. Scopes with `in_share: no` are reported as `held_out_usd_m` and kept out of the shares; `in_share: exclude` drops totals, parts and service lines that would otherwise double count.
  - **Estimate layer.** Bottom-up estimates from `projects/unlisted_vendors/estimates/` (tiers A–E, `proposed` until reviewed). A row is dropped when its `overlaps` field leads with an entity the Atlas numerator covers that year, or when its geography is `global`.
- Parent/child categories are never double counted, and vendor overlaps follow `reference/vendors.csv`.
- Exchange rates: Eurostat-derived CNY/USD (`A-FX-CNY-USD`).
- Geography: revenue without a China split is treated as China supply, an upper bound (`A-GEO-ALL-AS-CHINA`).
- CMP imports include a scenario range for CMP declared under 84862090 (`A-CMP-IN-84862090`).
- The domestic numerator is checked against CEPEA's domestic front-end total (`numerator_coverage.csv`).

**Groups.** litho · deposition · dry_etch · process_control · cleaning_strip · cmp · doping · thermal · track_automation_other. These merge segments that customs cannot separate.

**Outputs (`results/`).**

| File | Contents |
|---|---|
| `segment_table.csv` | Imports, Atlas domestic revenue and provisional share (min/max across import scenarios); estimate layer low/base/high; `share_with_estimates` with min/max; held-out revenue; vendors with pending Atlas evidence |
| `estimates_layer.csv` | Every estimate row in USD, with the reason for any drop |
| `automation_subview.csv` | Domestic wafer-handling (AMHS, sorter) revenue against AMHS imports (84864031), with the 84864039 sensitivity |
| `imports_by_group.csv`, `imports_by_hs8_allocation.csv` | Import side |
| `domestic_revenue_by_vendor.csv` | Numerator rows with basis (reported, approximate, lower bound, mapped basket) and observation IDs |
| `numerator_coverage.csv` | Coverage of the numerator against CEPEA's front-end total |
| `summary.md` | Human summary with gaps |
| `manifest.json` | Provenance |

**Status (2026-09-24, Atlas `2f4b6a3`).** The import side is solid. Coverage of CEPEA's front-end total:

| | 2023 | 2024 | 2025 |
|---|---|---|---|
| Atlas layer | 75% | 90% | 71% |
| With the estimate base | 83% | 97% | 79% |

The Atlas layer now includes the long-tail listed firms (Atlas PR #101: Leuven, Yadian, Mifei, Jingyi Automation, CFMEE and test firms). Their rows are pending independent verification. Many NAURA lines are floors. Main blockers:
- product-line revenue for NAURA and Kingsemi (2025);
- ACM Shanghai 2023–24 product-line revenue (2025 cleaning is now in the Atlas);
- review of the estimate layer: lithography and doping rest almost entirely on SMEE and CETC estimates;
- China/overseas splits for the named exceptions (Yitang/Mattson, ACM Shanghai; see `docs/estimation_standards.md`);
- track/automation separation on the import side.

Treat every share as provisional. Foreign vendors' segment shares (the sell-side companion chart) are out of scope: that needs data that isn't public.
