# Refinery demonstration corpus

The local prototype can stage the synthetic Unit 4 corpus into the governed
knowledge path with the corpus-admission helper:

```powershell
.venv\Scripts\python.exe scripts\prepare_refinery_demo_corpus.py `
  C:\Users\ALG\Downloads\AirBench_Refinery_Demo_Corpus.zip `
  --destination .airbench-corpus --force
```

The helper validates every SHA-256 value in `document_catalog.yaml` and copies
only `01_knowledge_base_ingestion/`. The Node is configured to ingest the
resulting `01_knowledge_base_ingestion/` subtree, so presenter prompts,
expected answers, evaluator overlays/GraphML, and optional external-source
notes cannot enter retrieval by accident. The catalog is retained one level
above the Node ingest root for operator provenance, but is not indexed.

Start the local Node with retrieval enabled after staging the corpus:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start_demo_node.ps1 `
  -PrepareCorpus `
  -CorpusZip C:\Users\ALG\Downloads\AirBench_Refinery_Demo_Corpus.zip `
  -Retrieval
```

In the desktop Knowledge screen, choose the configured
`.airbench-corpus\01_knowledge_base_ingestion` folder when starting bulk
ingestion. Search remains Node-owned and returns cited, clearance-filtered,
tainted evidence. The corpus is synthetic demonstration data; it does not
authorize repair, isolation, plant operation, or external-source ingestion.

The `03_pid_review_assets/` files are evaluator-side references. Source P&ID
drawings may enter the File Intake path, but their extracted topology remains
a candidate until the qualified adapter, verification, consistency, and
review gates permit a World Model commit.
