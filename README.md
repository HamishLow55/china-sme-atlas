# China SME Atlas and analysis

Data and code behind a forthcoming Institute for AI Policy and Strategy (IAPS) report on how far China is from making high-bandwidth memory (HBM) with only domestic semiconductor manufacturing equipment (SME).

The repository has two layers:

| Layer | Path | What it holds |
|---|---|---|
| **Equipment Atlas** | [`sme-equipment-atlas/`](sme-equipment-atlas/README.md) | As-reported evidence from equipment makers' filings: 16,052 observations and 632 product records from 388 source documents, each traced to a page and a verbatim excerpt. Also public trade and industry statistics (China Customs, UN Comtrade, Eurostat, CEPEA). No judgement. |
| **Analysis** | repository root | Judgement tables in [`reference/`](reference/README.md), estimation rules in [`docs/estimation_standards.md`](docs/estimation_standards.md), and reproducible projects in `projects/` that turn the Atlas into the report's figures |

**Status.** This is working research, shared for review ahead of publication. Figures may change before the report is published. It is a snapshot taken on 16 November 2026 from the authors' working repositories, and has no earlier history.

## Projects

| Project | Question |
|---|---|
| [`china_imports`](projects/china_imports/README.md) | How much semiconductor equipment does China import, by equipment group, origin and importer province? |
| [`china_share_by_segment`](projects/china_share_by_segment/README.md) | What share of China's wafer-fab equipment market do domestic vendors supply, by equipment group? |
| [`unlisted_vendors`](projects/unlisted_vendors/README.md) | Bottom-up revenue ranges for significant vendors without regular filings: SMEE, SiCarrier, CETC's equipment units and a long tail of smaller firms |
| [`hbm_step_market`](projects/hbm_step_market/README.md) | For each step in the HBM tool stack, what are China's imports, domestic vendors' revenue and the domestic share? |
| [`hbm_process_flow`](projects/hbm_process_flow/README.md) | How the report's tools fit together, from DRAM wafer to HBM stack (diagram) |

Each project has a `README.md` (question, method, caveats), a `run.py` and committed `results/`, including a `manifest.json` that records the inputs, reference tables and assumptions used.

## Principles

- **The Atlas is as reported.** Company statements stay company claims; analyst figures are labelled estimates; qualifiers such as "over" and "approximately" carry through as bounds.
- **Every judgement lives in `reference/`**, with a basis, a source and a status (`proposed` or `reviewed`). Projects cite assumption IDs rather than hard-coding them.
- **Ranges over false precision.** Splits, geography adjustments and unlisted-vendor estimates follow method tiers with default low/base/high ranges ([estimation standards](docs/estimation_standards.md)).
- **No licensed third-party values.** Paid analyst and broker data are not stored or used.
- **AI-assisted, source-checked.** Much of the extraction and estimation was done with AI agents. Atlas rows record who verified them against the original page, and estimate rows record their author and review status.

## Not included

- Original filings and other source documents. Each Atlas source gives its URL, SHA-256 and page count.
- Internal working notes, agent briefs and review logs.

## Quick start

```sh
uv sync                                             # Python >= 3.12; pandas, matplotlib, markdown
uv run sme-analysis check                           # validate reference tables against the Atlas
uv run sme-analysis list
uv run sme-analysis run china_share_by_segment      # regenerate a project's results/
uv run python -m unittest discover -s tests

cd sme-equipment-atlas
python3 -m unittest discover -s tests               # standard library only
python3 -m atlas validate
python3 -m atlas build                              # build/all_observations.csv: every ledger row as one CSV
```

The `manifest.json` files under `projects/*/results/` were written in the authors' working repositories, so their commit hashes refer to those, not to this snapshot. Rerunning a project writes a fresh manifest.

## Licence and contact

Licence: to be confirmed. Questions and corrections: Hamish Low, IAPS.
