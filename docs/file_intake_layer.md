# File Intake Layer

## Purpose

Every file that enters AirBench, whether it is one of a thousand documents loaded into the knowledge base or a single spreadsheet a user drags into a question, goes through this one layer. It is the single, hardened place that understands file types and turns any file into clean, structured, sourced content. Having one layer instead of two is what stops the common failure where a system reads many file types at bulk ingestion but chokes on a file uploaded mid task.

## Where it sits

Core engine. It is used by two callers: the Knowledge and Retrieval Engine for bulk ingestion into the permanent stores, and the Orchestration Engine for a file uploaded at query time. Both call the same layer. What counts as a known file type and how each is profiled comes from the domain pack's document profiles. It writes through the Memory and Audit Ledger.

## What it handles

All file type coverage lives here, in one place, so a new format is added once and both callers get it. The layer covers, at least:

- Digital PDFs, read directly for text, tables, and structure.
- Scanned PDFs and images, read with OCR, with coordinates and confidence.
- Word and other rich text documents.
- Excel, CSV, and other spreadsheets, read as structured tables with headers, units, and formulas kept intact.
- Photographs, read by the vision model.
- A reserved drawing-adapter interface; engineering drawing parsing is not in the first scope and will be supplied later by the separate drawing pipeline.
- Plain text and markup.

Adding a new type means adding one parser to this layer. Nothing else in the system changes, and neither caller can drift out of sync with the other, because there is only one path.

## What it produces

For any file, the layer produces the same shape of output regardless of caller: the parsed structure, the extracted content in clean pieces with tables and numbers kept whole, and a manifest. The manifest is the file's identity: type, version, effective date, source and how trusted that source is, clearance, and a content fingerprint for catching duplicates.

Each extracted piece is an `UntrustedEvidence` record until a later provenance gate promotes a fact. It carries a `FactEnvelope`-compatible reference containing the source document/version, page or sheet, table/cell or bounding box when available, extraction method, confidence, trust class, clearance, and valid/observed/ingested time. A derived fact points to its parent evidence rather than replacing it. No parser may return bare text or bare numbers to the trusted side.

## The one path, two callers

The machinery is identical for both callers. What differs is only three switches the caller sets, not the parsing.

1. **Destination.** Bulk ingestion writes into the permanent stores and, for authoritative documents, feeds the World Model Engine. A query time upload writes into the session scratch scope for that task only.

2. **Trust and persistence.** Bulk ingested files become permanent knowledge. A query time upload is marked untrusted and low trust, is used only within its task, and is discarded when the task ends, unless the user explicitly promotes it, which sends it back through this same layer with the ingestion destination and the confirmation gate.

3. **Latency profile.** A query time upload is parsed on the spot and fast, with heavier enrichment skipped. Bulk ingestion can run the heavier offline enrichment, since it is not blocking a person waiting on an answer.

Everything else, the type coverage, the table and unit handling, the manifest, the safety treatment, is the same, because it is the same layer.

## Safety

Every file that enters is untrusted until cleared, and a query time upload especially so. Content is treated as data, never as instructions. Files are parsed in the isolated intake space with no network, screened for hidden instructions and unsafe embedded content, and only clean, structured, sourced output crosses into the working context. A query upload inherits the uploader's clearance and can never widen what that user is allowed to see.

The intake layer does not decide what a document is allowed to do. It preserves taint and provenance. A model may read `UntrustedEvidence` to summarize it, but the evidence cannot add instructions, permissions, tools, or plan steps. Promotion into trusted knowledge requires the ledger provenance gate and an explicit policy decision.

The first scope covers digital/scanned PDF, DOCX or rich text, XLSX/CSV, PNG/JPEG, plain text, and markup. Engineering drawings are reserved for the later drawing-pipeline adapter; the generic intake layer must not pretend to understand drawing topology.

## Interfaces

Input: a file, plus the caller's three switches, destination, trust and persistence, and latency profile.

Output: parsed structured content and a manifest, written to the permanent stores or the session scope depending on the destination, and recorded through the Memory and Audit Ledger.

## Failure handling

A file that cannot be parsed goes to a review queue for bulk ingestion, or returns a clear, honest error to the user for a query upload, never a silent drop. A partially parsed file surfaces what was and was not read, rather than pretending it read all of it. An unknown file type is reported as unsupported with the reason, which is also the signal to add a parser for it.

## What is core and what is pack

Core: the whole layer, every parser, the manifest, the two caller switches, the isolated parsing and screening.

Pack: the document profiles, which files are authoritative, and the clearance model.
