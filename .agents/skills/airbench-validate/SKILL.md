---
name: airbench-validate
description: Challenge an AirBench request before implementation by clarifying the user outcome, scope, architecture ownership, risks, and measurable acceptance criteria.
metadata:
  short-description: Validate product and engineering scope
---

# AirBench validate

Use for a new feature, a vague request, or a request that may expand scope. Read the relevant issue and documents first.

Challenge the request against the actual AirBench problem: confidential industrial knowledge work, local models, agentic tools, multimodal intake, grounded retrieval, real deliverables, and visible sovereignty proof.

Resolve:

- the concrete user outcome;
- the smallest meaningful vertical slice;
- the M1-M10 owner and blocking edges;
- core-engine versus domain-pack responsibility;
- safety, audit, and provenance requirements;
- normal and failure-path acceptance tests;
- explicit non-goals and deferred requirements.

Return a concise decision record. Do not create abstractions or code while requirements remain unresolved.

