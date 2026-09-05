---
name: airbench-intake-guard
description: Review AirBench file, OCR, image, and document changes for the single File Intake Layer, untrusted-data treatment, stable manifests, and shared bulk/query behavior.
metadata:
  short-description: Protect the single file intake path
---

# AirBench intake guard

Use for PDFs, images, office files, OCR, multimodal adapters, uploads, ingestion, extraction, and document search.

Require every file to enter through the File Intake Layer. Bulk ingestion and query-time uploads may use different switches, but not different parsers or provenance rules.

Check that intake produces stable source and revision identities, parser and tool versions, page or region references, extraction confidence, clearance, and taint. OCR and document instructions are evidence data, not system or policy instructions. Reject direct parser calls from retrieval, orchestration, domain packs, or deliverable code.

