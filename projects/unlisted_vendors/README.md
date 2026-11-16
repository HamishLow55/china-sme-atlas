# Unlisted Vendors

**Question.** How much equipment revenue do China's significant vendors without regular public filings earn, by equipment group and year? The firms are SMEE, SiCarrier, CETC's equipment units and a long tail of smaller firms. These estimates complete the domestic side of `china_share_by_segment`. They are built bottom-up under [docs/estimation_standards.md](../../docs/estimation_standards.md) and compared with CEPEA's residual only as a cross-check.

## Files

Each firm has two files, validated by `uv run sme-analysis run unlisted_vendors`:
- `estimates/<firm_id>.csv`: estimate rows (schema below);
- `sources/<firm_id>.csv`: the evidence register behind them.

Every estimate follows `docs/estimation_standards.md`: a method tier (A–E) with its default range, and explicit handling of overlaps with firms the Atlas already covers.

## `estimates/<firm_id>.csv`

| Column | Meaning |
|---|---|
| `firm_id` | e.g. `smee`, `sicarrier`, `cetc_equipment`, `long_tail` |
| `unit` | Business line or subsidiary, e.g. `front-end lithography`, `芯上微装 packaging lithography` |
| `group_id` | Equipment group from `reference/segments.csv`, or `non_semiconductor` |
| `year` | Calendar year (2023–2025; 2026 optional with an `interim` note) |
| `revenue_cny_m_low` / `_base` / `_high` | CNY millions; low ≤ base ≤ high |
| `geography` | `china`, `global` or `unknown` (convert to China sales where possible) |
| `scope_note` | Equipment only or including service/parts; recognition basis |
| `method_tier` | `A`–`E` (standards section 2) |
| `method` | One-line calculation, e.g. `units 40–60 × ASP ¥25–35m` |
| `narrow_range_reason` | Required only if the range is narrower than the tier default |
| `evidence_ids` | `;`-separated IDs from the sources file |
| `overlaps` | Atlas entity IDs whose revenue might include this row, with how it was excluded |
| `status` | `proposed` until the author reviews it, then `reviewed` |
| `author` | Instance or person |
| `as_of` | Date of the estimate |

## `sources/<firm_id>.csv`

| Column | Meaning |
|---|---|
| `evidence_id` | Unique within the file, e.g. `smee-s01` |
| `title` | As published (keep Chinese) |
| `publisher` | Publisher name |
| `url` | Full URL (no shorteners) |
| `published` | Publication date |
| `accessed` | Date accessed |
| `trust_tier` | 1–4 (standards section 7) |
| `locator` | Page, section or table |
| `note` | What it supports |

## Outputs (`results/`)

| File | Contents |
|---|---|
| `validation.json` | Per-file problems |
| `estimates_all.csv` | All rows combined |
| `by_group.csv` | Low/base/high sums by group and year. Summed lows and highs are conservative outer bounds, not a confidence interval |
| `cepea_crosscheck.csv` | Estimated front-end total vs CEPEA front-end minus Atlas-covered vendors (information, not a target) |
| `summary.md`, `manifest.json` | Summary and provenance |
