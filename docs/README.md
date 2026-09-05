# AirBench Architecture Documentation

A sovereign AI worker that runs entirely inside an organization's walls, learns its world from its own documents, checks its work against the rules of the field, decides how much to do on its own by risk, and proves every step. Built as one core engine plus a swappable domain pack, so the same system serves any regulated field by loading a new pack rather than being rebuilt.

Start with `architecture_design.md`. It explains the whole system and points to every part.

## The documents

- `architecture_design.md` - the master overview, the core versus pack idea, how the parts fit, the request lifecycle.
- `domain_pack_framework.md` - the boundary that makes AirBench multi sector, and exactly what a pack contains.
- `world_model_engine.md` - the structured, time aware picture of the organization's world, built from its own records.
- `file_intake_layer.md` - the one shared layer that parses every file type, used by both bulk ingestion and query time uploads.
- `knowledge_and_retrieval_engine.md` - document indexing and cited retrieval, built on the file intake layer.
- `models.md` - the reference model roster and what each model is qualified for.
- `orchestration_engine.md` - the deterministic controller and the agent loop.
- `serving_and_routing.md` - hosting the models and sending each task to the right one.
- `verification_framework.md` - checking that an answer is valid by the field's rules.
- `consistency_engine.md` - keeping decisions consistent and flagging unjustified deviations.
- `autonomy_governor.md` - deciding how much to do alone, by harm, reversibility, and confidence.
- `model_qualification_framework.md` - clearing a model for a specific job before it runs.
- `memory_and_audit_ledger.md` - the append only, signed record of what the system knows and did.
- `sovereignty_and_security.md` - enforcing and proving that no data leaves, and defending against manipulation.
- `deliverable_engine.md` - turning verified facts into finished documents.
- `deployment_and_scale.md` - packaging, offline install and update, fixed hardware, and many sites.
- `future_full_fledged_must_have.md` - deliberately deferred hardening, production, and fleet requirements.

## Owned separately

- The Engineering Drawing Pipeline is one input to the World Model Engine and is documented elsewhere. The rest of the architecture treats it as a producer of structured graph fragments with confidence scores and does not depend on how it works inside.

## The three properties that hold across every part

1. Authority is deterministic, intelligence is not. The controller owns the loop, models are workers.
2. Confidence, source, and clearance travel with every fact and are never dropped at a boundary.
3. Everything is provable after the fact, offline, by someone who trusts neither the vendor nor a network.
