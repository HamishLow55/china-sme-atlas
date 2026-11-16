# SME Equipment Atlas

An as-reported evidence ledger for China's semiconductor manufacturing equipment (SME) industry. It records what equipment makers' own filings say (revenue, shipments, installed base, customers, product families, qualification milestones and process-node claims), with enough provenance to check every number against the original page. It holds no judgement: mappings, estimates and findings live in the analysis layer at the repository root.

The ledger currently holds 16,052 observations and 632 product/platform records from 388 registered source documents, covering 76 entities (60 Chinese equipment makers, 11 foreign incumbents and a few reference entities).

## Layout

| Path | What it is |
|---|---|
| `data/schema.json` | The observation schema; validation loads it |
| `data/observations/` | One row per reported value: entity, metric, value, unit, period, scope and the evidence behind it |
| `data/sources/`, `data/datasets/` | Source documents (title, URL, publication date, SHA-256 and page count of the original) and the datasets they belong to |
| `data/entities/`, `data/categories.json`, `data/reporting_scopes/`, `data/metrics.json` | Firms, the equipment taxonomy, each firm's reporting scopes and metric definitions |
| `data/platforms/`, `data/application_links/` | Named product families and dated maturity claims; source-backed links to applications such as TSV and HBM |
| `data/series/`, `data/reconciliations.json` | Selected time series and explicit reconciliation recipes |
| `data/coverage/`, `data/coverage_targets/`, `data/research_tasks.json`, `data/unresolved_claims/` | What was searched and what remains unresolved, so gaps are visible rather than read as zero |
| `statistics/` | Published trade and industry statistics, as reported: China Customs, UN Comtrade, Eurostat, CEPEA ([README](statistics/README.md)) |
| `atlas/`, `tests/` | Validation, build and calculation code (standard library only) and its tests |

## How evidence is recorded

- Each numeric observation keeps the native value and unit as printed, the page locator and a short verbatim excerpt in the original language. Any unit conversion is explicit and exact.
- Qualifiers such as "over", "approximately" and "approaching" are kept, and carried through calculations as bounds or approximations.
- Company operational statements remain company claims. Analyst figures are labelled estimates.
- Systems, chambers, reaction stations, customers and production lines are kept distinct, as are annual flows and cumulative milestones.
- Extraction was AI-assisted. Each row's review fields record its status and who checked it against the original (for example "Codex independent verifier" or "Terra independent verifier", which are AI verification roles). Rows still `pending` have not been independently verified.
- Entity overlaps (for example NAURA consolidating Kingsemi from 23 June 2025) are recorded, and aggregation code refuses to double count them.

## Not included

- **Original documents.** Filings are not redistributed. Each source record gives its URL, SHA-256 and page count, so the cited page can be retrieved and checked.
- **Licensed data.** No values from paid analyst or broker products are stored. The validator rejects observations from any dataset not cleared for the repository (`git_values_allowed`).

## Commands

Python 3.10+ with no dependencies (CI used 3.12).

```sh
python3 -m unittest discover -s tests
python3 -m atlas validate          # schema, registries and evidence checks
python3 -m atlas build             # writes build/ (ignored): observation CSV, reconciliation results, manifest
python3 -m atlas statistics-check  # hashes, exact rebuild from raw exports, cross-source totals
```

`python3 -m atlas build` writes `build/all_observations.csv`, a flat export of every ledger row with bounds, scope, time basis and review metadata. That is the easiest way to browse the data.

Commands that read the original PDFs (`verify-assets`, `check-pages`, `search`, `discover`) need a local archive of the filings, which is not part of this repository.
