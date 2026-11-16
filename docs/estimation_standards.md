# Estimation Standards

How the analysis layer fills gaps the Atlas cannot: revenue splits, geography, bounded or interim figures, and firms without filings. These rules apply to every assumption in `reference/` and every estimate file in `projects/*/estimates/`.

## 1. Principles

- **Bottom-up first, cross-check second.** Build each estimate from evidence about that firm or product line. Aggregate benchmarks (e.g. CEPEA totals) are **checks, never plugs**. A gap to a benchmark is reported, not filled.
- **Every number has a method tier, a range and sources.** No bare point estimates. Ranges are low/base/high in the file.
- **Prefer the Atlas.** If the Atlas holds a reported figure for the exact scope and period, use it and do not estimate. When the Atlas later gains a reported figure, it supersedes the estimate.
- **Source limits.** Licensed sell-side reports are never inputs, anchors or range-setters. Anything on the open internet may be used, including Chinese broker reports, sell-side figures in media coverage and SemiAnalysis. Attribute it, and treat a broker's or analyst's number as an estimate, not a reported fact.
- **Sources as named hyperlinks**, with date and trust tier (section 7). Record Chinese titles as published.

## 2. Method tiers and default ranges

| Tier | Method | Example | Default range around base |
|---|---|---|---|
| **A: Reported** | The quantity itself is disclosed for this scope and period | Bond prospectus gives the subsidiary's revenue; equity-method note discloses investee revenue | As reported (keep qualifiers such as "over") |
| **B: Derived from reported parts** | Arithmetic on reported components | Reported units × reported ASP; reported total × reported segment share | ±15% |
| **C: Anchored inference** | A reported figure for a related scope or period, adjusted by an explicit factor | Group figure minus identified non-front-end lines; prior-year revenue × reported growth; own historical split carried forward | ±30% |
| **D: Analogue/proxy** | Ratios or signals from peers or indirect indicators | Tender wins × typical tool price; headcount × peer revenue per employee; supplier sales to the firm ÷ bill-of-materials share | −40% / +60% |
| **E: Judgement** | Stated claims without a traceable basis, or expert judgement | Press "industry sources say ~¥X bn"; interview remarks | ×0.5 / ×2 |

- A range may be narrower than the default only with a written `narrow_range_reason`.
- A sum of components takes the **weakest tier of any component that is ≥20% of the base**.
- Two independent methods that agree within their ranges may justify a tier upgrade by one step. Record both.

## 3. China vs overseas revenue

- **Default:** domestic Chinese equipment vendors' revenue is treated as China sales (assumption `A-GEO-ALL-AS-CHINA`). CEPEA front-end exports were 8–9% of front-end revenue in 2024–25, and most of that is concentrated in a few firms.
- **Named exceptions** use the firm's reported regional split, applied pro rata to product lines unless a line-level split is reported:
  - **Yitang Semiconductor** (Mattson Technology's overseas sales);
  - **ACM Shanghai** (Korea/Taiwan customers). Measured mainland share is 97–99.5% (2023–25), so this exception moves little.
- Exceptions live in `reference/geography_splits.csv`, one row per vendor and year.
- To add an exception, show overseas revenue above ~10% of the relevant revenue from a Tier 1 source, and review the change in `reference/`.

## 4. Product-line splits

When a firm reports a mixed basket (e.g. Hwatsing "CMP + thinning"), apply the first method that is available:

1. **Reported split** for that period (tier A).
2. **Units × ASP** from reported shipments or orders and reported or well-sourced prices (tier B).
3. **Own split carried forward or back** from the nearest reported period, adjusted for known launches or exits (tier C).
4. **Peer or product-mix analogue** (tier D).
5. **Judgement prior** with the tier E range.

Record splits as rows in a reference table (`reference/product_splits.csv`, created when first needed) with shares low/base/high, tier and sources. Never let a split exceed the basket or leave unallocated residue silently.

## 5. Bounded, approximate and interim figures

- **"Over / at least X"** is a floor. Use X as `low`. Set `base` above X only with evidence (e.g. a later exact figure, or a sibling product total that constrains it). Never use a midpoint to an arbitrary cap.
- **"About X"** is approximate: base X, with range at least ±5% unless the source states precision.
- **Interim to annual** (e.g. H1 only):
  - use the firm's own H1/FY ratio from the last two to three years (tier C);
  - otherwise the median of the firm's peers in the same segment (tier D).
- **Missing year between two reported years:** interpolate on the firm's growth path (tier C). Never extrapolate more than one year beyond the last reported point without a new anchor.

## 6. Firms without filings (SMEE, SiCarrier, CETC units, long tail)

- **Estimate bottom-up** by product line and equipment group (`reference/segments.csv` groups, plus `backend`, `test`, `wafer_making` and `non_semiconductor`), so totals reconcile with any known group-level figure (e.g. CETC's CEPEA total).
- **Revenue, not orders or capacity.** Orders, tender wins and production capacity are inputs to a method, never the estimate itself. State the recognition assumption (acceptance lag).
- **Scope:** China sales of new equipment. Show service, parts and overseas revenue as separate rows where material.
- **Overlaps:** name any Atlas entity whose revenue may already include part of the estimate, e.g. CETC's CMP unit Jingyi Jingwei (`jingyi_jingwei`). The aggregator subtracts nothing automatically; the estimate file must exclude overlapping revenue and say so.
- **CEPEA cross-check:** the aggregator compares estimates with CEPEA's front-end total minus Atlas-covered vendors. CEPEA's survey may exclude non-reporting or loss-making firms: its 2021 ranking states it excludes loss-making units. So a large gap in either direction is information, not an error to force closed.

## 7. Evidence tiers

| Tier | Examples | Use |
|---|---|---|
| 1 | Company, bond and IPO filings; shareholder filings (equity-method notes); government registries; tender award notices; industry-association statistics | Can anchor tier A–C estimates |
| 2 | Established trade press with named sources (JW Insights/集微, DigiTimes, Nikkei, Reuters, Bloomberg, FT), think-tank research | Can anchor tier C–D estimates; corroborate tier 1 |
| 3 | Company PR, state media, conference talks, company websites | Leads, unit milestones, product lists; tier D–E only unless corroborated |
| 4 | WeChat accounts, forums, unattributed reposts | Leads only; never the sole basis for a base value |

## 8. Records and review

- Every estimate row carries: `method_tier`, `method`, `evidence_ids`, `overlaps`, `status` (`proposed` → `reviewed`), `author` (the instance or person) and `as_of`.
- The author reviews estimates and promotes rows to `reviewed`. Superseded rows are replaced in a later PR, never edited silently. Git history keeps the prior version.
- Working notes (`notes/<firm>.md`) are Tier 3. They explain reasoning, discarded leads and open questions.
