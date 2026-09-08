# Clean evaluator procedure

1. Start from a clean local environment with the signed bundle and network
   observer already staged.
2. Verify the domain-pack, hardware, model, runtime, and fixture hashes before
   loading any model.
3. Run the scanned-report workflow in admitted parallel mode, then repeat it
   in serial virtual-team mode with the same worker roles and completion gates.
4. Verify intake provenance, retrieval citations, deterministic calculations,
   independent verification, DOCX structure, DOCX rendering, and human review.
5. Export the append-only ledger, stop networking, and replay the export from
   an offline evaluator.
6. Mark the run complete only when every matrix row has an evidence reference;
   otherwise record `needs_review` or `blocked`.

The evaluator must not replace missing model, hardware, network, artifact, or
review evidence with deterministic fixtures.
