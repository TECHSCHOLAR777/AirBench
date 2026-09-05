---
name: airbench-deliverable-guard
description: Review AirBench Word, Excel, PowerPoint, code, and calculation outputs for deterministic values, provenance, rendering quality, and verification evidence.
metadata:
  short-description: Protect real deliverables and computed values
---

# AirBench deliverable guard

Use when changing artifact generation, calculations, document rendering, spreadsheets, charts, approval notes, or code outputs.

Check that:

- models write prose and refer to named values;
- numeric values come from deterministic computation or verified source facts;
- formulas, units, assumptions, and intermediate steps are inspectable;
- every claim has evidence references and clearance;
- output files are valid real artifacts, not text pretending to be files;
- rendering, structural checks, and visual regression checks run where applicable;
- artifact hashes and generator versions are recorded;
- failed checks result in needs-review or stop, not a polished but invalid file.

