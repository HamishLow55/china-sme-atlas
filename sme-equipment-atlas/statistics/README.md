# Public Statistics Layer

External, published statistics about China's semiconductor-equipment trade and domestic equipment industry, stored **as reported** so future analysis can start from clean, documented tables.

## Rules

- **Data only.** No mapping to atlas categories, currency conversion, market-share calculation, scenario or interpolation belongs in this folder or in `atlas/statistics.py`. Analysis lives outside the Atlas and cites these tables.
- **As reported.** Values, codes and labels keep the publisher's digits and wording, typos included. Thousands separators are removed; nothing else is changed. USD and CNY are each kept only where the publisher reported them.
- **Separate from the evidence ledger.** These tables are not observations. Do not copy rows into `data/observations/`. The datasets are registered in `data/datasets/_shared.json` for provenance only.
- **"China" means the publisher's geography.** Customs and Comtrade cover goods entering mainland China's customs territory, i.e. **all fabs located in mainland China, including foreign-owned fabs**. CEPEA covers sales by domestic equipment makers, exports included. Each README records its dataset's boundary.
- **One grain per file.** Never sum rows across files with different groupings.
- **Broker and analyst market data are not part of this layer.**

## Datasets

| Folder | Publisher | Content | Refresh |
|---|---|---|---|
| [`china_customs/`](china_customs/README.md) | General Administration of Customs (GACC) online query platform | Monthly imports by HS8 code, 2021–; by country of origin × importer province | Manual: every query needs a CAPTCHA |
| [`comtrade/`](comtrade/README.md) | UN Comtrade (China as reporter) | Annual HS6 imports and exports by partner, 2015–2025 | Scriptable public API |
| [`eurostat/`](eurostat/README.md) | Eurostat Comext and exchange rates | Monthly EU member-state exports to CN/HK (HS6); annual EUR rates | Scriptable public API |
| [`cepea/`](cepea/README.md) | China Electronics Production Equipment Industry Association (CEPEA) | Domestic semiconductor-equipment revenue by category, top 10 firms, H1; bulletin index | Monthly bulletins; PDFs held locally |

## Commands

```sh
python3 -m atlas statistics-build   # regenerate china_customs tables from raw/ exports
python3 -m atlas statistics-check   # hashes, exact rebuild, unique keys, cross-source totals
```

`statistics-check` also runs in the unit tests, so CI covers it. It checks integrity only, not interpretation. Cross-source agreement is a transcription and completeness check, not corroboration.

## Adding data

1. Add raw files only; never edit a table by hand when a raw source exists.
2. For customs: save the portal export to `china_customs/raw/`, named per that README. Run `statistics-build`, fill `pulled_on` and `notes` in `queries.csv`, then run `statistics-check`.
3. Move a superseded partial pull out of `raw/` rather than keeping overlapping files. The build refuses overlapping pulls that disagree.
4. For other datasets, record the exact query or source issue in the README and keep key columns unique.
