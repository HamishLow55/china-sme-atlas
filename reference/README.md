# Reference (Judgement) Tables

Research judgements, not data. Each row has a basis/source and a `status`: `proposed` (drafted, not yet reviewed) or `reviewed` (approved by the author). `uv run sme-analysis check` validates structure and checks category and entity IDs against the pinned Atlas.

| Table | Purpose |
|---|---|
| `segments.csv` | WFE segments (Gartner-style names, used as a method reference) mapped to Atlas categories. Each segment belongs to a `group_id` that customs data can resolve; e.g. cleaning and dry strip share customs 84862049, so they form one group |
| `customs_segment_map.csv` | HS8 codes (optionally by origin rule) → group, with `full`, `amount_usd:<assumption>`, `residual` or `excluded` allocation. Encodes the 2026-09-23 CMP classification test |
| `assumptions.csv` | Named assumptions with value/low/high, unit, basis and source. Projects cite these IDs in their manifests |
| `vendors.csv` | Which Atlas entities count as domestic vendors, and parent/subsidiary overlaps to avoid double counting |
| `scope_group_map.csv` | Mixed reporting baskets (e.g. Hwatsing "CMP + thinning") assigned to one group where no category-level figure exists, with the direction of any bias |
| `hbm_tool_stack.csv` | HBM process steps → tool families, Atlas categories, customs codes, domestic candidates (from the Atlas HBM Landscape Map) and foreign incumbents (draft; verify before citing) |
| `product_splits.csv` | Allocations of a reported basket to groups, as low/base/high shares with a method tier (estimation standards §4–5). A split supersedes the category or scope rows it covers. Holds NAURA's bounded lines, Kingsemi 2025, Hwatsing CMP vs thinning, Yitang 2025 strip and ACM Shanghai 2023–24 |
| `geography_splits.csv` | Named exceptions to A-GEO-ALL-AS-CHINA: the mainland share applied to a vendor's rows in a year (Yitang, ACM Shanghai) |
