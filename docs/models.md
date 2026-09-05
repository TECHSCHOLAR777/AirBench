# Reference Model Roster

## How to read this document

The AirBench engine does not hard code any model. Which models run is a configuration that the domain pack supplies and the Model Qualification Framework clears, so this roster is the reference configuration for the first deployment, not a fixed part of the system. A model appears here only in terms of the role it fills and the jobs it is cleared for. Any model can be swapped for a better one later by qualifying the new one for the same jobs, and the router will only use it for jobs it passed. See `model_qualification_framework.md` and `serving_and_routing.md`.

## The roster

This is the reference capability pool, not a promise that every target is resident in the first deployment. The first scope may ship a smaller qualified target set appropriate to the available GPU. Routing selects by capability certificate and hardware profile, never by model name alone.

### Reasoner and planner, the main brain
- Model: Gemma 4 31B
- Role: planning, reasoning, drafting prose, driving tool use.
- Precision: kept at a safer precision, not aggressively compressed, because the whole system leans on the quality of its planning.
- Residency: hot, always resident.
- Qualified for: task planning, general reasoning, writing the prose in deliverables, tool use. Not qualified to produce final numbers, numbers are computed, not written by a model.

### Fast lane
- Model: Gemma 4 26B-A4B, a mixture of experts model with about 4B active.
- Role: quick queries and cheap sub steps where full strength is not needed.
- Precision: aggressively compressed, since it is the speed tier.
- Residency: hot.
- Qualified for: short lookups, simple sub steps, low stakes drafting. A fast lane answer that fails an external check is escalated to the reasoner automatically.

### Coder
- Model: Qwen3-Coder-30B-A3B-Instruct, a mixture of experts coder with about 3B active.
- Role: writing and running code, and doing calculations as real executed code in the sandbox.
- Precision: compressed to fit alongside the others.
- Residency: hot if budget allows, otherwise in the fast waking sleep slot, since coding is bursty.
- Qualified for: code generation, code execution tasks, and calculations that must show real steps. This is the model that makes the deliverable engine's numbers trustworthy, because the figures come from its executed code, not from prose.

### Scanned document and image reading
- Model: Qwen2.5-VL-7B
- Role: reading scanned text documents and answering questions about photographs and images.
- Residency: hot.
- Qualified for: scanned document reading and general image understanding. Explicitly not qualified as the extractor for engineering drawings, that is the drawing pipeline's job, because general vision models are unreliable at recovering drawing topology.

### Retrieval embeddings
- Model: BGE-M3, producing both meaning based and keyword based representations.
- Role: turning text into searchable form for the Knowledge and Retrieval Engine.
- Residency: hot, small, always on.

### Reranking
- Model: bge-reranker-v2-m3
- Role: reordering search results by true relevance before they reach the reasoner.
- Residency: hot, small, always on.

## Models owned by the drawing pipeline

The engineering drawing pipeline is specified separately and owns its own models. It is not part of the first scope and is not routed to by the general model router. When supplied later, it will register a signed extractor adapter that hands the World Model Engine structured graph fragments with confidence scores.

## Fitting the machine

This reference roster was sized for a large single-card deployment. The first scope may ship a smaller qualified subset chosen for the available GPU; no model is assumed resident until its memory and latency are measured on that target. Rare or oversized models live in the sleep slot only when the hardware profile can support it. Full hardware profiles and capacity guarantees are deferred to `future_full_fledged_must_have.md`.

## The rule that governs this list

Nothing on this list is trusted because it is named here. Each model is trusted only for the jobs it has been qualified for, and the router enforces that. Replacing or upgrading a model means qualifying the new one for those jobs first. This is what lets the roster improve over time without changing the engine, and it is what lets the organization say that nothing runs that was not cleared for the exact job it is doing.

Sources: Qwen3-Coder ( https://github.com/QwenLM/Qwen3-Coder ), Qwen3-Coder-30B-A3B-Instruct ( https://huggingface.co/Qwen/Qwen3-Coder-30B-A3B-Instruct ).
