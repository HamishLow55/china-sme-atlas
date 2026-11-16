# HBM Process Flow

**Question.** How do the tools in the report fit together, from DRAM wafer to finished HBM stack? It is an overview diagram for the report's tools section, accurate to the real flow rather than to the report's section order.

**Method.** A simplified via-middle flow in five stages: front-end DRAM (a loop repeated for each layer), TSV formation, front-side bumps, thinning and reveal on a carrier, and stacking and molding. Process control runs underneath as an enabler of every stage. Boxes are the tools the report covers, under their section names; grey text marks other steps. The sequence follows the process descriptions in the tool docs (`projects/hbm_tool_docs/docs`: `tsv_etch`, `tsv_cmp_reveal`, `temp_bond_debond`, `thinning`, `microbump_litho`, `singulation`, `stacking_tcb`, `molding`), which cite SK hynix and Amkor. Memory test is left out, as in the report.

**Outputs.** `results/process_flow.png`.

**Status.** Draft, Tier 3. No Atlas data is used.
