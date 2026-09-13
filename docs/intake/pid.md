<<<<<<< HEAD
# Engineering drawing and P&ID pipeline

## Purpose

The engineering drawing and Piping and Instrumentation Diagram, P&ID, pipeline converts an approved local drawing into bounded, coordinate-grounded evidence. It identifies symbols, labels, line geometry, connections, and candidate topology so AirBench can reason over reviewable graph fragments rather than an opaque image or unsupported model description.

The pipeline is a controlled visual-intake adapter. It does not make engineering decisions, grant authority, overwrite the World Model, or turn a drawing into trusted instructions. Its output is evidence for the World Model, Verification Framework, Consistency Engine, Deliverable Engine, and human reviewer.

This document preserves the intended technical design from the engineering-drawing branch and defines the contract required before that code becomes an active AirBench integration.

## Architecture position

The pipeline sits after the File Intake Layer and before the World Model Engine.

```text
Approved local drawing
  -> File Intake Layer
  -> manifest and rendered root canvas
  -> controlled P&ID visual adapter
  -> candidate graph fragment and review artifacts
  -> provenance, verification, consistency, and ledger gates
  -> World Model commit or human review
```

The File Intake Layer remains the only file entry point. Bulk knowledge ingestion and a drawing uploaded during a task use the same parsing, manifest, clearance, taint, source, and no-network boundary. The P&ID adapter receives only an intake-produced manifest, bounded page or canvas bytes, declared visual profile, and scoped output location. It never opens an arbitrary host path, parses a container independently, or downloads a model at runtime.

For CAD input, File Intake must first create an approved, versioned normalized rendering and retain the original file manifest. The adapter works from that rendered root canvas. Unsupported CAD formats fail closed instead of being silently converted by an uncontrolled utility.

## Ownership boundary

| Concern | Owner |
| --- | --- |
| File identity, type detection, container parsing, rendering, clearance, taint, and isolation | File Intake Layer |
| Symbol types, engineering legend, authoritative drawing classes, thresholds, topology semantics, and required checks | Active signed domain pack |
| Tiles, local detector and OCR calls, masks, geometry processing, coordinate restoration, and candidate graph assembly | Controlled P&ID visual adapter |
| Candidate-fact gating, graph reconciliation, time model, clearance-filtered graph queries, and commits | World Model Engine |
| Engineering limits, graph checks, deviation checks, approval requirement, and completion | Verification, Consistency, Autonomy Governor, and deterministic Orchestrator |
| Model artifact identity, supported role, host profile, and acceptance thresholds | Model Qualification Framework and signed model registry |
| Event history, artifact hashes, evidence references, review actions, and replay | Memory and Audit Ledger |

The core engine contains no refinery symbol taxonomy. A pump, valve, vessel, instrument, line class, off-page connector, tag pattern, or allowed connection is a domain-pack declaration. The reusable adapter works with pack-supplied legend, schema, extraction targets, and rules.

## End-to-end pipeline

### 1. Admission and intake

The user or bulk connector supplies a P&ID through File Intake. Intake records the immutable source manifest, document revision, source identity, uploader or connector, clearance, trust class, taint, content hash, effective date where present, and processing profile. The drawing is untrusted data. Text found in notes, title blocks, labels, or callouts cannot alter policy, add tools, or instruct the system.

The intake profile checks file structure, size, page or canvas limits, rendering success, image dimensions, and supported format. It produces a root canvas with a stable coordinate system. Every later detection maps back to this canvas.

### 2. Visual quality preflight

The adapter records canvas width, height, scale, orientation, color mode, estimated line density, blur or compression warnings, and rendering warnings. It may denoise, deskew, normalize contrast, convert to grayscale, or apply controlled stroke reinforcement before a reduced-resolution operation. Such processing is recorded as derivation metadata. It improves detectability but does not prove that every original line survives.

If quality prevents reliable extraction, the adapter returns a bounded `needs_review` result with the affected regions. It does not fabricate a connected process graph.

### 3. Overlapping tile matrix

Large drawings are partitioned into overlapping tiles. The tile plan records root-canvas dimensions, tile size, overlap, tile identifiers, tile coordinates, scale, preprocessing profile, and adapter version. Overlap lets symbols, labels, and lines crossing a tile edge be reconciled later.

Tiles are processing views, not new authoritative drawings. Every tile result retains a reversible map to the root canvas.

### 4. Component detection

A qualified local detector proposes component regions on each tile. Each candidate includes a pack-independent class identifier, detector score, bounding box, tile identifier, model artifact hash, quantization, serving runtime, qualification reference, and source coordinate transformation.

Global non-maximum suppression reconciles duplicate detections from overlapping tiles. It records the retained candidate and the discarded duplicates. A model score is not a final engineering classification.

### 5. Domain-pack classification

The adapter maps a detected class to the active pack legend and world-schema target. The pack may map a visual class to a broad type, require a tag for a precise type, prohibit automatic classification, or require review below a threshold. Ambiguous symbols remain candidates and are routed for clarification. They are never silently assigned a convenient type.

### 6. OCR and text localization

A qualified local OCR worker extracts text regions from the intake-produced tiles. Each result contains text, OCR confidence, oriented bounding polygon or box, tile identifier, root-canvas coordinates, language profile, and model qualification reference. The adapter treats OCR output as untrusted evidence. A tag, note, specification, or instruction found in a drawing cannot become task policy.

Text regions can be associated with nearby candidate components only through declared geometric rules. The association retains its own confidence and derivation, separate from the detector and OCR confidence.

### 7. Exclusion masks

The adapter creates masks for component and text regions before line tracing. The masks prevent symbol contours, label characters, stamps, revision tables, and title-block content from being mistaken for process or instrument lines. Masks are derived artifacts. The original root canvas remains available for review.

### 8. Line, junction, and connector tracing

The line stage works from a controlled grayscale or binary representation and the exclusion masks. It traces permitted geometry classes, including solid, dashed, and dotted lines where the active pack profile permits them. It identifies candidate segments, endpoints, intersections, junctions, crossings, line style, direction indicators, and off-page connectors.

Gap bridging and geometric snapping use pack-declared tolerances. A gap outside those tolerances stays disconnected or ambiguous. The adapter must not infer a connection merely because it would produce a cleaner graph.

### 9. Root-coordinate reconstruction

The adapter maps components, text, line segments, junctions, and connectors from each tile to root-canvas coordinates. It reconciles duplicate regions, stitches compatible line segments at tile boundaries, and records every merge and transformation. A reconciliation failure marks the affected region for review.

### 10. Candidate topology assembly

The adapter creates a candidate graph fragment. Candidate nodes represent detected components, labels, junctions, off-page connectors, or other pack-declared objects. Candidate edges represent traced relationships, connections, containment, tag association, or pack-declared relations. Every node and edge points to the supporting source regions, extraction methods, confidence inputs, clearance, taint, times, model qualification references, and derivation chain.

The graph fragment is not a trusted World Model update. It enters the same candidate-fact, provenance, verification, consistency, and ledger gates as other extracted evidence.

### 11. Verification and review

The Verification Framework checks pack-defined requirements such as allowed symbols, identifier format, units, connection constraints, expected tag pattern, line-style rules, and source support. The Consistency Engine can compare the fragment with current authorized records and prior revisions. The Autonomy Governor determines whether a conflict, low-confidence region, or topology change requires human review.

The original drawing, root-coordinate overlays, localized crops, candidate graph, confidence values, check results, and unresolved regions must be available to the reviewer. A visual worker can propose evidence. It cannot certify an engineering conclusion.

### 12. World Model and deliverable use

Only a verified candidate passes to the World Model Engine. The engine reconciles it using pack-declared stable identifiers, source revision, effective date, authority, confidence, clearance, taint, and time. Conflicts remain visible rather than overwriting an earlier record.

Workers retrieve P&ID facts through clearance-filtered World Model or Retrieval interfaces. They do not read the drawing or graph store directly. A deliverable may cite a drawing region or use verified graph facts, but a model cannot write an unsupported engineering value into a Word document, workbook, slide, or calculation. The Deliverable Engine owns deterministic values, templates, rendering, validation, and artifact hashes.

## Evidence and artifact contract

The eventual typed `PIDRecord` must contain at least the following groups.

| Group | Required content |
| --- | --- |
| Source identity | Manifest ID, document revision, content hash, source identity, root-canvas reference, page or sheet where applicable |
| Processing identity | Adapter version, tile plan, preprocessing profile, detector, OCR, and geometry worker qualification references |
| Visual evidence | Detection regions, text regions, masks, line segments, junctions, connector regions, overlays, and coordinate transforms |
| Candidate objects | Pack-mapped type, identifier or label association, geometry, source regions, confidence, clearance, taint, valid, observed, and ingested times |
| Candidate relations | Endpoint references, relation type, line style, path evidence, confidence inputs, ambiguity state, and source regions |
| Review state | Verification results, consistency findings, autonomy decision, unresolved regions, reviewer actions, and supersession information |
| Provenance | Parent evidence references, derivation chain, ledger event references, model artifact hashes, and content hashes |

GraphML and JSON may be generated as bounded local interchange artifacts. They must be treated as artifacts with hashes and manifests, not as permission to bypass World Model, verification, or ledger controls.

## Security and sovereignty requirements

- The adapter runs locally inside the approved no-egress intake or execution boundary.
- It loads only pinned, locally present, signed, and qualified detector and OCR artifacts.
- Missing weights, OCR models, or dependencies return a typed unavailable result. They never trigger a network download.
- It receives only scoped intake outputs and writes only to its approved task or ingestion workspace.
- It does not execute drawing content, macros, embedded objects, instructions, or uncontrolled external references.
- It emits typed evidence and artifacts through the ledger. It does not mutate task state, World Model state, or approval state.
- Model output, OCR text, and geometry inference remain evidence proposals until the governing gates accept them.

## Failure and escalation behavior

| Condition | Required behavior |
| --- | --- |
| Unsupported or malformed drawing | Fail closed with a clear intake result and ledger event |
| Missing or unqualified local model artifact | Return unavailable. Do not download or substitute an unqualified target |
| Low-confidence symbol, label, or relation | Preserve the candidate, mark it unresolved, and request review when policy requires |
| Unreconciled tile seam | Preserve tile evidence and flag the affected root-canvas region |
| Line gap beyond permitted tolerance | Keep endpoints disconnected and report ambiguity |
| Conflict with authoritative World Model fact | Record the candidate and route it through verification, consistency, and review. Do not overwrite |
| Clearance mismatch | Filter or deny before evidence reaches a worker or output |
| Verification cannot run | Return `needs_review`, never pass by omission |
| Ledger failure | Prevent the next consequential transition or graph commit |

## Qualification and acceptance evidence

The P&ID adapter is qualified as a visual worker, not trusted merely because it produces a graph. Qualification records the exact model artifact hash, quantization, runtime, host profile, prompt or tool contract where relevant, active pack version, thresholds, and evaluation data version.

Acceptance evidence includes representative local drawings with controlled splits, detector precision and recall by symbol family, OCR character and word error, tag association quality, root-coordinate localization error, line and junction precision and recall, endpoint and connector accuracy, topology edge precision, recall and F1, graph edit distance, calibration, abstention behavior, clearance behavior, no-egress evidence, replayable ledger trace, and domain-expert review of sampled output.

The acceptance run must include failure fixtures such as a thin or broken line, a false crossing, a tile seam conflict, an unclear symbol, a misleading note, a missing local weight, and a conflicting revision. A successful happy path is insufficient.

## Implementation integration checklist

Before P&ID code is enabled in AirBench, it must satisfy all of the following.

1. Register as a File Intake drawing adapter. No direct path or standalone ingestion entry point remains.
2. Load symbol legends, class mappings, thresholds, relation semantics, and engineering rules from the signed domain pack.
3. Replace runtime download behavior with a local signed-artifact and qualification lookup.
4. Expose typed `PIDRecord` and candidate graph-fragment contracts that preserve source, confidence, clearance, taint, derivation, time, model identity, and review state.
5. Record intake, worker calls, candidate creation, reconciliation, verification, review, artifact, and commit events through the signed ledger.
6. Submit graph fragments through World Model candidate-fact gates. The adapter cannot commit facts itself.
7. Route all tool execution through the deterministic orchestrator and Tool Gateway.
8. Add unit, contract, failure, provenance, clearance, no-egress, replay, and representative visual acceptance tests.
9. Keep model weights and runtime dependencies outside ordinary Git history unless the supply-chain policy explicitly approves an artifact mechanism.
10. Demonstrate the full local path from drawing upload through reviewed graph evidence and a verified downstream deliverable.

## Relationship to the engineering branch

The engineering branch is the source of the current algorithmic design, including overlapping tiles, detector and OCR stages, component and text masks, line tracing, root-coordinate reconstruction, topology assembly, and GraphML or JSON export. It is not yet an approved active integration because its current code bypasses several AirBench boundaries. This document is the source of truth for the required integration shape. Future implementation must preserve the pipeline stages while conforming to this contract.

## Appendix: P&ID extraction engine algorithm (engineering branch design)

# P&ID Extraction Engine

## Purpose

The P&ID Extraction Engine converts CAD drawings, PDFs, and images of P&IDs into a structured representation of their components, text, geometry, and connections so that the resulting information can be understood and consumed by an LLM. The engine must preserve the meaning and relationships represented in the drawing, because a missed component, incorrect classification, misplaced label, or false connection can change the process represented by the P&ID.

## Where it sits

The P&ID Extraction Engine operates as a dedicated visual intake and graph-extraction subsystem. It bridges raw engineering drawings and structured knowledge representation by feeding typed graph fragments, spatial metadata, and connectivity attributes directly into downstream reasoning frameworks and the World Model Engine.

## The core rule: the original P&ID coordinate system remains the source of truth

Every patch-level detection, OCR result, component classification, and traced line must remain mappable to the original P&ID coordinates, because patching is only a processing mechanism and not a new representation of the drawing. The original image remains the reference throughout extraction and reconstruction.

```text
CAD / PDF / Image Ingestion
         │
Preprocessing (Denoise / Deskew / Normalize / Ink Density Boosting -> Resize -> Grayscale Binarization)
         │
Overlapping Patch Matrix Partitioning
   ┌─────┴─────────────────────┐
   ▼                           ▼
Component Detection     Text OCR & Localization
   │                           │
Component Classification       │
   └─────┬─────────────────────┘
         ▼
Component & Text Mask Generation (Exclusion Layers)
         │
Line & Connection Tracing (Grayscale Binarization, Solid/Dashed/Dotted, Junctions)
         │
Coordinate Remapping & Patch Boundary Stitching
         │
Topology Reconstruction (Nodes, Edges, Attributes)
         │
LLM-Readable Serialization (PIDRecord / GraphML / JSON)
```

## Pipeline stages

1. **Ingest the P&ID.** The engine accepts CAD, PDF, and image inputs and converts them into a processable representation while retaining the information required to map results back to the original P&ID.

2. **Preprocess the image.**
   - **Ink Density Boosting & Controlled Resizing:** To reduce computational overhead, the image size is decreased. However, directly downscaling engineering drawings creates a major issue: thin process lines (often only 1–2 pixels wide), subtle dashed signal lines, small component contours, and delicate junction connection points can interpolate into the background and disappear or break into disconnected fragments. To prevent this data loss, the engine first increases the ink density across all points, lines, and components (via morphological dilation and stroke reinforcement) to thicken fine features. Only after the ink density is reinforced is the image size decreased, guaranteeing that fine-stroke continuity, small symbols, text characters, dotted lines, and connection points remain fully preserved during resizing.
   - **Grayscale Binarization:** Strips all other colors from the image so line detection does not get confused.
   - **Additional Preprocessing Operations:** Denoising, Deskewing, Contrast Normalization.

3. **Create overlapping patches.** Every image is divided using a fixed patch matrix with overlapping regions, regardless of the original image size. Each patch retains its position relative to the original P&ID so that patch-level results can later be reconstructed into the original coordinate system.

4. **Detect components.** Component detection identifies P&ID symbols such as pumps, valves, vessels, instruments, and other relevant components. Each detection retains its location, geometry, and detection information.

5. **Classify components.** Classification is applied only to detected components. If the user provides a P&ID legend, the detected symbols are classified according to that legend; otherwise the default component classification approach is used. If the classification is ambiguous, the engine asks the user to identify the component rather than assigning an unsupported type.

6. **Perform OCR and text localization.** OCR extracts text from each patch and preserves the location of every detected text element. The localization is required both to associate text with components and to identify the regions that must be excluded during line tracing.

7. **Create component and text masks.** Detected component regions and localized text regions are converted into exclusion masks for the line-tracing stage. The masks prevent symbol boundaries and text strokes from being interpreted as process or instrument lines, while the original image remains unchanged.

8. **Trace lines and connections.** Line tracing is performed only after component detection, component classification, OCR, and text localization have been completed. The masked, grayscale binarized representation is used so that tracing algorithms focus strictly on structural process and signal geometry without being confused by colored annotations or background noise. The engine detects and traces solid, dashed, and dotted lines, bridges appropriate gaps, and identifies connectors, junctions, endpoints, and continuous connection paths.

9. **Reconstruct the original P&ID.** Patch-level components, text, and line paths are mapped back to the original P&ID coordinate system. Duplicate detections created by overlapping patches are merged, and line segments crossing patch boundaries are stitched together so that the result represents one coherent P&ID rather than independent patches.

10. **Reconstruct topology.** The extracted information is converted into relationships that describe the structure of the P&ID. Components become nodes, traced connections become edges, localized text becomes identifiers or attributes, and off-page connectors become explicit cross-reference relationships.

11. **Create the LLM-readable representation.** The reconstructed P&ID is serialized into a structured representation such as GraphML or JSON containing components, component types, identifiers, text, locations, geometry, connections, and relationships. This representation is the interface between visual extraction and downstream LLM reasoning.

## Interfaces

- **Input:** CAD, PDF, or image P&ID input, with an optional user-supplied component legend.
- **Output:** A structured `PIDRecord` containing detected and classified components, localized text, geometry, traced connections, and topology in an LLM-readable GraphML, JSON, or equivalent representation.

## Failure handling

- **Ambiguous symbols and classifications:** When a detected symbol cannot be resolved against the active legend or classifier confidence thresholds, the engine halts automatic type assignment and routes the symbol for human-in-the-loop clarification instead of propagating an unsupported or hallucinated type.
- **Line tracing gaps:** Gaps beyond approved orthogonal bridging tolerances are flagged as disconnected or ambiguous rather than silently synthesized.
- **Thin line dropout during downscaling:** Directly reducing image size causes fine 1–2px process lines, dashed signals, and small junctions to dissolve or fragment due to anti-aliasing. Boosting ink density across all points, lines, and components prior to resizing guarantees that critical connectivity and fine symbols survive resolution reduction.
- **Patch seam misalignments:** Discrepancies at overlapping patch seams are resolved through global non-maximum suppression (NMS) and coordinate verification against the root canvas; if alignment cannot be reconciled deterministically, the region is tagged for review.
- **Confidence propagation:** Every node, edge, and label retains calibrated detection confidence and source bounding coordinates so downstream consumers can evaluate provenance.

## What is core and what is pipeline

- **Core / Consumer:** Ingests the normalized `PIDRecord`, builds the relational World Model graph, verifies engineering constraints against domain rules, and drives LLM reasoning.
- **Pipeline:** Owns input file ingestion, patch matrix generation, computer vision inference (YOLO/classifier), OCR localization, mask generation, line vectorization, and geometric snapping to global coordinates.
