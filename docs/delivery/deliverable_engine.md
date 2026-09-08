# Deliverable Engine

## Purpose

AirBench does not stop at an answer, it produces the finished document the work actually needs, an approval note, a case summary, a memo, a spreadsheet, a slide deck. The Deliverable Engine turns verified facts into that finished file in a way that is trustworthy, because in a serious setting a wrong number in a signed document is not a bug, it is an incident.

## Where it sits

Core engine. The shapes of the outputs, the templates, come from the domain pack's deliverable templates. It is called by the Orchestration Engine near the end of a task, it draws only on verified facts, and it hands its output to a human review step. Full identity-bound sign-off is deferred.

## First-scope rendering stack

The first scope uses a server-side Python artifact service over standard Office Open XML formats:

- DOCX templates are rendered with `docxtpl`/`python-docx` and reopened with `python-docx` for structural checks.
- XLSX templates are populated with `openpyxl`; formulas are preserved and recalculated in a pinned headless LibreOffice runtime before verification.
- PPTX templates are populated with `python-pptx`; charts use template-owned series ranges rather than model-created chart definitions.
- LibreOffice headless renders DOCX, XLSX, and PPTX to PDF for visual regression checks. Approved fonts are bundled with the deployment and recorded in the artifact manifest.
- Macros, external links, embedded executable objects, and uncontrolled formula references are stripped or rejected in the first scope.

Templates have a stable ID, version, schema, required fields, allowed value types, and compatible pack version. The model never designs layout. The renderer owns field placement, formulas, chart ranges, and final artifact hashes. This is the practical first stack; broader Office compatibility and richer chart semantics remain future hardening.

## The core rule: separate the words from the numbers

The model writes the prose. The system owns the numbers and the layout. The model never types a figure into a document. Every value comes from a single verified record of facts, and the template places it. This one rule is what stops a fluent document from carrying a made up number, and it is not optional.

## How a deliverable is built

1. **Assemble the source of truth.** Before any writing, the verified facts for this deliverable are gathered into one record. Every value in it is either quoted from a cited source or computed by the code tool in the sandbox, and each carries its source. Nothing that has not been verified is allowed in.

2. **Choose the template.** A fixed template for this deliverable type, from the pack, so the output takes a shape the organization already trusts. The model does not design the layout.

3. **Write the prose.** The model drafts the sections and refers to values by typed names or placeholders. The first scope enforces named value fields in the template and rejects unbound required fields; exhaustive numeric-token enforcement across every prose and chart case is a later hardening item.

4. **Render.** Template code merges the record and the prose into the file. In spreadsheets the live formulas are kept, recalculated in the pinned LibreOffice runtime, and checked against the computed source record. Any calculation's shown steps come from the actual sandbox run, not from the model describing what it thinks it did. Charts are bound to verified ranges and are checked after rendering.

5. **Verify the file.** The finished file is reopened and checked structurally, recalculated where needed, rendered to PDF, and compared against the template's visual baseline. Required fields, bound values, formulas, chart ranges, claims, tables, fonts, and page/slide overflow are checked. This runs through the Verification Framework.

6. **Human review.** In the first scope the file is presented as a verified draft with its sources and check results attached. The full identity-bound electronic sign-off workflow is deferred. If a person records a review or sign-off, that event is still appended to the ledger.

## Why the same engine works for every field

Because the templates and the field checks come from the pack, the engine renders a refinery approval note, a hospital discharge summary, or a bank credit memo with the same machinery. The engine's job is the discipline, source of truth, words not numbers, render, verify, sign, and that discipline is identical everywhere. Only the template and the checks change.

## Interfaces

Input: the verified facts for the deliverable and its type.

Output: a finished, verified file, plus its source and check record, handed to sign off and recorded in the Memory and Audit Ledger.

## Failure handling

If a required value is missing or unverified, the deliverable is not produced, the gap is surfaced, because a confident document with a hole is worse than no document. If the rendered file fails its own verification, it does not go to sign off until it is fixed. A number that cannot be traced to the source record blocks the deliverable.

## What is core and what is pack

Core: the source of truth discipline, the words versus numbers rule, the render machinery, the file verification, the sign off flow.

Pack: the deliverable templates and the field checks that apply to them.

## Deliverables in a worker team

In team mode, generation workers may propose prose and named field bindings, while the Deliverable Engine remains the only component that owns layout, formulas, numeric values, chart ranges, and artifact hashes. A render worker cannot write a final number or mark an artifact verified.

The render stage consumes verified facts and accepted WorkPackets. The finished file then goes through structural, numeric, visual, and independent review checks from a fresh context. A team that produces prose but cannot complete the artifact checks remains incomplete and cannot pass the completion gate.
