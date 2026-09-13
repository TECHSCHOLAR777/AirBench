---
name: spitgold
description: Write sharp, evidence-faithful AirBench slide content for product, technical, architecture, feature, impact, and demonstration sections. Use only when explicitly invoked for presentation copy.
metadata:
  short-description: AirBench presentation copy
---

# SpitGold

Create presentation-ready AirBench content that a product team can place directly on a slide. Write with precision, concrete product knowledge, and a natural professional voice. This skill writes copy only. It does not design slides, create layouts, invent performance figures, or make claims that the supporting material does not justify.

## Invocation

Use this skill explicitly.

```text
/spitgold Give me 5 features of this project.
/spitgold Write four 13-word USPs for a leadership presentation.
/spitgold Draft a 75-word speaker note explaining the evidence-bearing World Model.
```

If the request lacks context, infer these defaults.

- Audience. Industrial decision makers and technical evaluators.
- Product posture. The complete intended AirBench product.
- Output. Copy only, with no explanation of the writing process.
- Feature count. Five, when the request asks for features without a count.

For a sub-section request, write only the requested content. Use the complete system as context so that the subsection is accurate and substantial. Do not turn a request for one subsection into an entire deck.

Ask one concise question only when the required audience, requested format, or word count would materially change the result.

## Mandatory source reading

Before writing any sub-section, read `README.md`, `docs/README.md`, and [AirBench capability map](references/airbench_capability_map.md). Then read the topic-specific sources selected by [document routing](references/document_routing.md). Read [slide patterns](references/slide_patterns.md) when the requested output type has a defined pattern.

Do not use the capability map as a replacement for the architecture documents. It is a quick index. The selected governing document is the source of truth for the requested content.

## Complete-product narrative mode

For normal AirBench presentation requests, treat the system as the fully integrated product described by the architecture and complete-product research narrative. Write in present tense. Say what AirBench does, how it controls the work, and what evidence it provides. Do not frame the content around open tickets, partial implementation, future development, or missing hardware evidence unless the user explicitly asks for implementation status or a roadmap.

The complete-product narrative includes the desktop and AirBench Node, shared File Intake, OCR and visual evidence, P&ID extraction, clearance-aware retrieval, the evidence-bearing World Model, domain-pack ontology, deterministic orchestration, the worker-team harness, qualified local model routing, controlled tools and sandbox execution, verification, consistency, autonomy, DOCX, XLSX, PPTX, code and calculation deliverables, human review, signed ledger replay, and no-egress proof.

Completion language never authorizes fabricated evidence. Do not invent numerical outcomes, certification, deployment scale, customer use, benchmark results, model accuracy, or compliance approval.

## Grounding the content

Use present tense for a requested complete-product narrative. This permits clear descriptions of the intended finished system. It does not permit invented measurements, customer deployments, certification claims, compliance approvals, benchmark scores, or incident statistics. When no measured evidence exists, describe the mechanism and its operational consequence instead of implying a result.

Do not collapse distinct AirBench components. Retrieval is not the World Model. The router is not the orchestrator. A model proposal is not verified evidence. A signed ledger is not a final log sink. The P&ID pipeline is a controlled visual-intake adapter that returns coordinate-grounded graph evidence.

## Writing contract

- Use professional English and direct sentence construction.
- Use full stops and commas in normal prose. Do not use semicolons or em dashes.
- Do not use generic marketing language, abstract praise, inflated claims, or filler.
- Name the control or mechanism behind every material benefit.
- Use concrete nouns, active verbs, and AirBench terms only where they clarify meaning.
- Do not repeat a claim with altered adjectives or synonyms.
- Do not force every list into three items. Use the number that the request requires.
- Do not use a heading that merely repeats the slide title.
- Do not use "not just X, but Y" framing.
- Do not use phrases such as cutting edge, seamless, robust, revolutionary, game changing, future ready, unlock, empower, transformative, holistic, or state of the art.
- Do not describe a model as owning task state, authorizing a tool, or deciding completion.
- Do not describe uploaded content as trusted instructions.
- Do not describe numbers in a deliverable as model-written. The deterministic value record owns them.

For ordinary slide bullets, write 12 to 15 words each. If the user supplies a word count, meet it exactly. A title normally has 5 to 9 words. A subtitle normally has 10 to 16 words. Use one idea per bullet and keep the grammatical shape varied across a list.

For paragraphs, follow the user supplied word limit exactly. Each sentence must add a different fact, mechanism, consequence, or proof. Avoid short paragraph fragments, excessive line breaks, and repeated framing.

## Feature and USP selection

For an unspecified request for five AirBench features, lead with the value a non-technical decision maker sees. Return exactly these distinct ideas, in this order.

1. Sovereign on-premise operation.
2. Review-ready deliverables with visible evidence.
3. Controlled P&ID and visual-document understanding.
4. Clearance-aware retrieval and evidence-bearing World Model.
5. Deterministic task control, qualified routing, governed tools, and bounded worker teams.

Keep retrieval and the World Model in one bullet. Keep P&ID separate. Keep sovereignty and deliverables separate. Do not replace the final feature with a vague productivity claim.

For other feature lists, select ideas that cover different layers of the product. Use this order where relevant.

1. User outcome.
2. System mechanism.
3. Evidence or safety control.
4. Operational workflow advantage.
5. Product differentiator.

Do not make five variants of one capability. For example, a model-routing slide may separately cover qualification, capability selection, hardware admission, deterministic fallback, and route evidence.

## Output patterns

- Features or USPs. Give a title only if requested, then the requested number of bullets.
- Architecture. Name the component, what it owns, its input, and its control boundary.
- Workflow. Write each stage as an action and its observable result.
- Security or sovereignty. Name both the enforcement point and the evidence produced.
- P&ID. Mention source coordinates, extracted symbols and text, topology or graph fragments, confidence, and reviewability when relevant.
- Deliverables. Mention verified values, templates, rendering, checks, and the relevant DOCX, XLSX, PPTX, code, or calculation output.
- Benefits or impact. State the mechanism first, then the user or organizational consequence.
- Speaker notes. Explain the slide naturally. Do not repeat its bullets verbatim.

## Required final language pass

`unslop` is the pstack prose-discipline skill. Treat it as a skill within SpitGold. Use the installed `unslop` skill as the required final pass whenever it is available in the active agent environment. Read its `SKILL.md`, preserve technical meaning, and apply its rewrite and self-audit process.

If `unslop` is unavailable, apply this fallback before returning content.

1. Remove abstract praise and replace it with a named mechanism.
2. Remove superficial words ending in `ing` unless they state a real action.
3. Replace ornate terms with plain words.
4. Remove chatbot phrases, empty conclusions, rhetorical fragments, and vague attributions.
5. Split sentences that require backtracking.
6. Check that every sentence could not be pasted unchanged into an unrelated AI product deck.
7. Read the result once as a senior engineer and once as a non-technical decision maker. Keep only wording that both can understand.

Return the final copy only. Do not say that a skill was used. Do not include a rationale unless the user asks for one.
