# HBM Step Market

**Question.** For each of the 25 HBM process steps in `reference/hbm_tool_stack.csv`, what are China's imports, domestic vendors' revenue and the domestic share, and on what basis?

**Method.** `reference/hbm_step_market_map.csv` gives each step a basis:
- **group:** the step inherits its equipment group from `china_share_by_segment` (TSV etch within dry etch, for example). The share describes the group.
- **pool:** named customs codes against named domestic vendors' revenue in the back-end or test group (thinning, singulation, bonding, molding, test). Pools include tools from outside the step, so read them as bounds.
- **none:** no customs code isolates the tool and no domestic revenue line exists.

Domestic revenue reuses `china_share_by_segment.domestic_by_vendor` (Atlas layer with product splits and geography exceptions); group rows also report the share with the unlisted-vendor estimate layer. A like-for-like process-control row compares optical imports with a numerator excluding e-beam vendors.

**Outputs.** `results/step_market.csv` (2023–25, low/base/high) and `results/step_lookup.md` (2025 lookup with import trend and year-to-date change).

**Status.** First pass, Tier 3. All mappings `proposed`.
