# Reference Model Roster

## How to read this document

The AirBench engine does not hard code any model. Which models run is a configuration that the domain pack supplies and the Model Qualification Framework clears, so this roster is the reference configuration for the first deployment, not a fixed part of the system. A model appears here only in terms of the role it fills and the jobs it is cleared for. Any model can be swapped for a better one later by qualifying the new one for the same jobs, and the router will only use it for jobs it passed. See `docs/assurance/model_qualification_framework.md` and `docs/foundations/07_serving_and_routing.md`.

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

This reference roster was sized for a large single-card deployment. The first scope may ship a smaller qualified subset chosen for the available GPU; no model is assumed resident until its memory and latency are measured on that target. Rare or oversized models live in the sleep slot only when the hardware profile can support it. Full hardware profiles and capacity guarantees are deferred to `docs/future/future_full_fledged_must_have.md`.

## The rule that governs this list

Nothing on this list is trusted because it is named here. Each model is trusted only for the jobs it has been qualified for, and the router enforces that. Replacing or upgrading a model means qualifying the new one for those jobs first. This is what lets the roster improve over time without changing the engine, and it is what lets the organization say that nothing runs that was not cleared for the exact job it is doing.

Sources: Qwen3-Coder ( https://github.com/QwenLM/Qwen3-Coder ), Qwen3-Coder-30B-A3B-Instruct ( https://huggingface.co/Qwen/Qwen3-Coder-30B-A3B-Instruct ).

## Worker role mapping

The roster supplies targets for worker roles, but a model name is never a role contract by itself. A target must be separately qualified for each worker capability it fills.

- Gemma 4 31B may fill lead, reasoning, or prose-drafting assignments only under the certificates it holds.
- Gemma 4 26B-A4B may fill efficient low-risk assignments only when the step and risk policy allow it.
- Qwen3-Coder may fill code and executable-calculation assignments through the sandbox.
- Qwen2.5-VL may fill vision and scanned-document assignments after qualification for the relevant document profiles.
- BGE-M3 and the reranker serve retrieval roles through their typed interfaces, not as general worker chat targets.
- The independent verifier may use a different model target when the measured hardware permits it. If it uses the same model family, it still receives a separate call, fresh context, separate assignment, and independent qualification.

For a complex task, the router makes a decision for each worker assignment. It does not select one model for the whole team. A single-GPU deployment may run these assignments serially while preserving their separate identities and audit events.

## Initial target choices for the first deployment

These are the deliberate reference targets for the first AirBench vertical slice. They are selected for the stated problem: local reasoning and drafting, coding and executable calculations, scanned inspection reports and images, and local retrieval. Exact artifact commits, quantization files, runtime versions, and capability certificates are frozen by the P1-3 implementation issue before a target is allowed to run.

| Capability | Reference target | Preferred execution profile |
|---|---|---|
| Lead reasoning, planning, and high-quality prose | `google/gemma-4-31b-it-q4` | Q4 on a large server profile; not assumed on a mid-range workstation |
| Workstation lead, fast reasoning, and low-risk substeps | `google/gemma-4-26b-a4b-it` | Q4_0 or the measured equivalent on a mid-range profile |
| Coding and executable calculations | `Qwen/Qwen3-Coder-30B-A3B-Instruct` | A qualified 4-bit AWQ or GPTQ artifact in the serial slot unless measured hardware supports more |
| Scanned documents, photographs, handwriting, and image understanding | `Qwen/Qwen2.5-VL-7B-Instruct` | A qualified 4-bit vision artifact with page and image limits |
| Dense and sparse retrieval embeddings | `BAAI/bge-m3` | CPU or a small dedicated local service |
| Retrieval reranking | `BAAI/bge-reranker-v2-m3` | CPU or a small dedicated local service |

The 31B target is the quality ceiling for the lead role, while the 26B A4B target is the practical default for a mid-range workstation. A smaller target is an explicit hardware profile decision, not a silent quality downgrade. Coding remains assigned to the coder target even though Gemma 4 supports coding, because the coding role requires its own tool-use and sandbox qualification.

## One-copy model storage

The runtime has one canonical model store, supplied through the trusted
`AIRBENCH_MODEL_STORE` configuration. The model server and Node never use a
Hugging Face cache as a fallback and never download during task execution.
The Hugging Face hub cache is an acquisition-only staging mechanism. It is
removed after the staged files have been verified against the canonical store;
keeping both stores indefinitely is not part of the deployment design.

The signed roster's `artifact_path` is the canonical relative directory name.
Provisioning must stage into that directory, verify the declared artifact and
component files, and then run the repository-local model-store audit. The
audit compares file content and size rather than trusting cache filenames,
which may be Git object identifiers or incomplete-download markers. It
deletes nothing unless the explicit prune command is used, and it retains any
unmatched or incomplete cache data.

The operational procedure and commands live in `models/README.md`. This
separates connected acquisition from the air-gapped serving phase and avoids
the previous failure mode where a global Hugging Face cache and a copied
`C:\AirBench-models` tree both remained indefinitely.
