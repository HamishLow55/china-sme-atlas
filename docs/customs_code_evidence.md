# Customs Code Evidence: Which Tools Sit in Which HS Codes

*Compiled 2026-09-28 by Claude Code.* This note records the classification evidence behind `reference/customs_segment_map.csv` and the `customs_codes` column of `reference/hbm_tool_stack.csv`. It answers which China HS codes carry each tool type, and how mixed each code is.

## Sources and how far to trust them

- **US Customs (CBP) rulings.** Official classification rulings ([CROSS](https://rulings.cbp.gov/)). They classify under the US tariff, but the first six digits are the international HS, which China also uses. Only rulings from 2007 onward that haven't been revoked are used, because heading 8486 dates from HS2007. These are authoritative for the HS6 heading. They say nothing about China's 8-digit split or actual declaration practice.
- **China portal labels.** The official 8-digit descriptions, as held in the Atlas `statistics/china_customs/codes_hs8.csv`.
- **Chinese declaration examples** (申报实例). These are examples of goods declared under each 10-digit code, as listed by [365area.com](https://www.365area.com/hscode/case/8486209000-1), with a cross-check on [transcustoms.cn](https://www.transcustoms.cn/China_HS_code.asp?HS_Code=8486209000). This is third-party, unverified evidence (Tier 4). The examples show classification practice, including misdeclarations. They are not weighted by value, and many are old (used equipment, 2000s–2010s models). Counts by tool type are in `customs_declaration_examples_tally.csv`, from keyword matching on the Chinese product text, so they're approximate.

## Findings by tool type

| Tool | Where declared | Evidence | Confidence |
|---|---|---|---|
| ATE / semiconductor testers | **90308200** | Test equipment ruled 9030.82 ([N337433](https://rulings.cbp.gov/ruling/N337433), 2024). 209 of 476 examples under 9030820000 are testers | High |
| Test handlers | **90308200** | Advantest dynamic test handlers ruled 9030.82 even though the handler itself doesn't measure ([N280220](https://rulings.cbp.gov/ruling/N280220), 2016). Examples include Hontech, Tripod and Eletech handlers | High |
| Wafer probers | **90308200** | Cascade and other probers appear among the 9030820000 examples | Medium |
| Probe cards | 90308200 or 90309000 (parts) | Rulings differ: 9030.82 ([H192481](https://rulings.cbp.gov/ruling/H192481), 2014) and 9030.90 as parts ([H268513](https://rulings.cbp.gov/ruling/H268513), 2016) | Low |
| Dicing saws (blade) | 84861030 and 84862090 | A DISCO DAD3430 was ruled 8486.20, explicitly **not** 8486.40 assembly ([N361145](https://rulings.cbp.gov/ruling/N361145), 2026). In practice China declares DISCO/Accretech dicers under both 8486103000 (62 dicing examples, also including ingot wire saws) and 8486209000 (18) | High that it's 8486.10/.20, not .40 |
| Laser dicing/scribing | 84861030, 84862090, sometimes 8456 | Laser dicers appear under 8486103000. A Hans Laser scriber was declared under 8456 | Medium |
| Back-grinding / thinning | **84861020** (mostly), also 84862090 | DISCO DFG8540 and 821F thinning grinders appear among the 8486102000 examples (25 grinding) and 8486209000 (7) | Medium–high |
| Die bonders | 84864029 and 84862090 | ASM AD-series and Esec die bonders appear under both (34 under 8486402900, 21 under 8486209000) | High that it's split |
| Flip-chip / TCB / hybrid bonders | Probably 84864029 (or 84862090) | No specific examples or rulings found | Low |
| Molding | **84864021** | 35 of 52 examples are molding/encapsulation | High |
| Wire bonders | 84864022 | Explicit tariff label; no examples listed | High (from the label) |
| Fab AMHS / wafer robots | 84864031; 84864039 | 84864031 examples are wafer-transfer robots and fab handling robots. 84864039's wafer-handling examples are mostly **tool modules and spares** (Lam wafer lifters, Applied Materials part-numbered transfer units, KLA robot arms), alongside flat-panel handling | Medium |
| Wet cleaning (single-wafer, batch, SRD) | **84862090** and 84862049 | SCREEN/DNS SS-3000-AR and FC-3000 cleaners and Semitool spin-rinse dryers appear under 8486209000 (31 cleaning examples). Wet etch, strip and cleaning appear under 8486204900 | High that cleaning is split across both codes |
| Coater/developer (tracks) | 84862090 (also 84862029) | TEL Mark-8 and other coaters appear under both | High |
| E-beam inspection, CD-SEM, review SEM | 90121000 or 90318090 | SEMs ruled 9012.10 / 9031.80 ([N084236](https://rulings.cbp.gov/ruling/N084236)); a dual-beam semiconductor tool ruled 9031.80 ([N013658](https://rulings.cbp.gov/ruling/N013658)). The 9012100000 examples are mostly lab SEMs, and 9031809090 holds 3,000+ general instruments | Medium on codes; **not separable** |
| X-ray package inspection / X-ray metrology | 90221990 | Only 4 of 115 examples under 9022199090 are semiconductor-related (e.g. wire-bond X-ray); the rest is general industrial and analytical X-ray | **Not separable** |
| Electroplating (TSV fill, microbumps) | Unresolved (84862029 or 84862090?) | No declaration examples or rulings found | Low |
| Packaging lithography (steppers for bumps/RDL) | 84862031 / 84862039 | Heading 8486.20 covers all semiconductor lithography; the 8-digit codes don't separate packaging from front-end | Medium |

## What this changes

- **84862090 is not just "tracks, automation, other".** It also carries wet cleaners, dicing saws, back-grinders and die bonders, plus PCB and solar kit declared as semiconductor equipment (36 and 28 examples). Japan supplies 63–73% of its value (2023–25), which fits TEL tracks, SCREEN cleaners and DISCO tools.
  - Consequence 1: our `track_automation_other` residual overstates front-end tracks and automation.
  - Consequence 2: cleaning imports are understated.
  - This is the likely main reason our cleaning market is smaller than sell-side figures. A value split needs vendor-side anchors, such as a cleaning allocation scenario like `A-CMP-IN-84862090`.
- **The wafer-making codes carry back-end tools.** 84861020 (grinding) and 84861030 (sawing) hold device-wafer back-grinders and dicing saws, alongside ingot and wafer-making equipment. They stay out of the WFE shares either way, but they're the main import codes for the HBM **thinning** and **singulation** steps.
- **84862049 is wet-dominated.** It's mostly wet etch, strip and cleaning. Older examples include solar wet lines (RENA, Schmid, from Germany). German origin has been ≤1% of its value since 2023, so solar is now small.
- **Test is clean.** ATE, handlers and probers all sit in **90308200**. That's the one code worth pulling for HBM memory test and probe/handling.
- **E-beam process control and X-ray are not separable** at 8 digits. Their codes are dominated by lab and industrial instruments. Keep process-control imports optical-only (90314100), and split or flag the e-beam part of the domestic numerator rather than widening the import side.
