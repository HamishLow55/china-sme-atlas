# UN Comtrade: China-Reported SME Trade (HS6, annual)

Source: UN Comtrade public API, China (M49 156) as reporter, pulled 2026-09-23. One call per year × flow × code, with the second partner, transport mode and customs procedure collapsed:

```
https://comtradeapi.un.org/public/v1/preview/C/A/HS?reporterCode=156&period={year}&cmdCode={hs6}&flowCode={M|X}&partner2Code=0&motCode=0&customsCode=C00
```

Partner names come from <https://comtradeapi.un.org/files/v1/app/reference/partnerAreas.json>.

**Geography:** China's customs territory, as for the portal data. For imports, the partner is the **country of origin**.

## `china_hs6_annual.csv`

**Grain:** year × flow × hs6 × partner. Codes held: 848610, 848620, 848630, 848640, 848690, 903141 and 903082, for 2015–2025. 903082 was pulled 2026-09-29 with the same call.

| Column | Meaning |
|---|---|
| `flow` | M = imports, X = exports |
| `partner_m49` | M49 partner code. `0` = World. `490` is published as "Other Asia, nes", Comtrade's label for Taiwan |
| `value_usd` | Comtrade `primaryValue` |
| `cif_usd`, `fob_usd` | As published; blank where not reported |
| `qty` | Quantity |
| `qty_unit_code` | Quantity unit: 5 = number of items, 8 = kg, −1 = not available |
| `net_weight_kg` | Net weight |

**Notes:**
- 2015–2017 import quantities are published as 0, meaning not reported.
- China's monthly Comtrade series ended at 2024-12 when pulled, so only annual data is held.
- HS6 is too coarse to split equipment types; use `china_customs/` for 8-digit detail.
