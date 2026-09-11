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
