# Eurostat: EU Exports to China and Exchange Rates

Pulled 2026-09-23 from the Eurostat SDMX 2.1 API (SDMX-CSV format). Values as published.

## `eu_exports_to_china_hk_monthly.csv`

Comext dataset DS-045409 (EU trade by HS2-4-6 and CN8). Exports (`flow` 2), monthly, 2015-01 → 2026-07.

- **Reporters:** NL, DE, FR, IT, AT, BE, IE, SE, FI, DK, ES, CZ.
- **Partners:** CN, HK.
- **HS6 codes:** 848620, 848640, 848690, 903141.
- **Indicators:** `VALUE_IN_EUROS`, `QUANTITY_IN_100KG`.
- `last_update` is Eurostat's release stamp.

```
https://ec.europa.eu/eurostat/api/comext/dissemination/sdmx/2.1/data/DS-045409/M.NL+DE+FR+IT+AT+BE+IE+SE+FI+DK+ES+CZ.CN+HK.848620+848690+903141+848640.2.VALUE_IN_EUROS+QUANTITY_IN_100KG?startPeriod=2015-01&format=SDMX-CSV
```

**Notes:**
- The EU CN8 nomenclature does not subdivide 848620 (only 84862000).
- Partner = destination country as recorded by the EU exporter. Mirror comparisons with China's imports mix FOB and CIF valuation, shipping versus origin country, and EUR versus USD.

## `fx_annual_per_eur.csv`

Dataset `ert_bil_eur_a`: annual average (`statistic` AVG) units of national currency per EUR, for USD and CNY, 2015–2025. Stored as published. Any cross rate (e.g. CNY per USD) is a derivation for the analysis layer, not stored here.

```
https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/data/ert_bil_eur_a/A.AVG.NAC.USD+CNY?startPeriod=2015&format=SDMX-CSV
```
