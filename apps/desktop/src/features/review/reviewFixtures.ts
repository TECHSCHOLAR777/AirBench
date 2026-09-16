/**
 * Hardcoded sample deliverables for the Review gallery. These are fixed,
 * fake demo content — no backend call is made to produce them — mirroring
 * the same pattern as features/showcase_assistant/fixtures.ts. They exist
 * so Review has something legible to show instead of an empty state, while
 * being clearly labeled as samples rather than real Node-verified records.
 */

export type ReviewFixtureKind = "code" | "markdown" | "binary-preview";

export interface ReviewFixture {
  id: string;
  title: string;
  kind: ReviewFixtureKind;
  routedModel: string;
  updatedAt: string;
  /** Used for code/markdown kinds; rendered through ChatMessage's markdown renderer. */
  content?: string;
  /** Used for binary-preview kind: a file type label like "PPTX" and a short note. */
  fileType?: string;
  note?: string;
}

export const REVIEW_FIXTURES: ReviewFixture[] = [
  {
    id: "code-sample",
    title: "Leak-rate calculation (Python)",
    kind: "code",
    routedModel: "airbench-qwen3-8b",
    updatedAt: "2026-09-10",
    content: [
      "```python",
      "def leak_rate(pressure_drop_kpa: float, orifice_mm: float) -> float:",
      "    \"\"\"Returns an estimated leak rate in kg/h for a small orifice.\"\"\"",
      "    area_m2 = 3.14159 * (orifice_mm / 2000) ** 2",
      "    return round(area_m2 * pressure_drop_kpa * 0.62, 4)",
      "",
      "print(leak_rate(35.0, 2.5))",
      "```",
    ].join("\n"),
  },
  {
    id: "markdown-report",
    title: "Unit 4 management review note",
    kind: "markdown",
    routedModel: "airbench-gemma-4-12b",
    updatedAt: "2026-09-12",
    content: [
      "# Unit 4 management review",
      "",
      "**Scope:** Findings from the latest inspection pass on the feed transfer train.",
      "",
      "## Key findings",
      "- Two isolation valves flagged for tag mismatch",
      "- One instrument loop pending recalibration",
      "",
      "## Recommendation",
      "Proceed with a scoped shutdown to correct the tag mismatch before the next inspection window.",
    ].join("\n"),
  },
  {
    id: "presentation-sample",
    title: "Quarterly readiness deck",
    kind: "binary-preview",
    routedModel: "airbench-gemma-4-12b",
    updatedAt: "2026-09-08",
    fileType: "PPTX",
    note: "Sample preview only — this build does not render a live slide deck.",
  },
  {
    id: "spreadsheet-sample",
    title: "Finding totals workbook",
    kind: "binary-preview",
    routedModel: "airbench-qwen3-8b",
    updatedAt: "2026-09-09",
    fileType: "XLSX",
    note: "Sample preview only — open the real artifact from the Tasks tab for a Node-verified workbook.",
  },
  {
    id: "document-sample",
    title: "Approval note (Word)",
    kind: "binary-preview",
    routedModel: "airbench-gemma-4-12b",
    updatedAt: "2026-09-11",
    fileType: "DOCX",
    note: "Sample preview only — this build does not render a live Word document.",
  },
];
