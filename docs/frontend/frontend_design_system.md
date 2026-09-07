# AirBench Frontend Design System

## 1. Design character

AirBench should feel like a dependable task command application used in a plant, government office, or engineering review room. It should be calmer than a consumer chatbot and clearer than an infrastructure dashboard.

The visual direction is **disciplined operational clarity**:

- `Obsidian Signal` is the default: a deep blue-black desktop shell with a focused dark task canvas.
- `Ledger Paper` is the warm alternative: a document-review canvas in beige and restrained orange, with the same dark navigation rail.
- readable document-first layouts;
- teal for trusted and complete states;
- blue for active evidence and information;
- amber for attention and review;
- restrained red for stop or failure;
- no decorative AI gradients, fake typing, fake worker activity, or unexplained confidence scores.

Glass is reserved for elevated local controls such as the composer, menus, drawers, and dialogs. It is never used as a substitute for hierarchy, status, or provenance.

## 2. Design principles

1. **Outcome first**: the user describes what must be completed, not which model or tool should be called.
2. **Proof nearby**: every important result has a visible path to sources, confidence, clearance, and verification.
3. **One primary action**: each screen has one obvious next step and secondary actions stay secondary.
4. **Progressive disclosure**: technical routing, hashes, event payloads, and resource details are available without polluting ordinary work.
5. **Explicit authority**: draft, verified, approved, returned, blocked, and failed are different states.
6. **Honest activity**: the screen reflects the Node's events and never simulates work.
7. **Accessible by construction**: keyboard, screen reader, reduced-motion, high-contrast, and large-text behavior are part of the component contract.
8. **Sector-neutral core**: generic components render domain-pack labels and rules through contracts.

### 2.1 Simplification pass

The default workbench must not look like an AI operations dashboard.

- Home has one composer, one Continue work list, one review reminder, and one quiet node status line.
- GPU meters, model counts, worker rosters, and ledger statistics are administration or technical-detail views.
- Plan, Activity, Sources, and Technical are modes or drawers inside one task workspace, not peer destinations in the primary navigation.
- Use one high-emphasis action per screen. Avoid a row of equal-looking buttons.
- Keep status chips to the current state and one necessary qualifier. Prefer a sentence when a chip would become jargon.
- Use rows, dividers, and text links for repeated records. Reserve cards for bounded interactive fields, previews, or decisions.
- Never show internal capability names or exact model names before the user needs them.
- Remove fake typing, animated swarms, decorative gradients, large metric tiles, and unexplained scores.
- Product copy must be valid UTF-8. Mojibake or replacement characters are release-blocking defects.

## 3. Token foundation

### Color roles

| Token role | Initial direction | Use |
| --- | --- | --- |
| `nav` | blue-black or warm charcoal | Application shell and navigation |
| `ink` | high-contrast task text | Primary text |
| `ink-muted` | slate or warm gray | Secondary text and metadata |
| `canvas` | near-black or warm beige | Main work surface |
| `surface` | raised task surface | Cards, previews, dialogs |
| `line` | cool gray | Boundaries and dividers |
| `trust` | muted teal | Connected, verified, approved, complete |
| `info` | steel blue | Evidence, active work, links |
| `attention` | muted amber | Review, uncertainty, waiting |
| `danger` | restrained red | Stop, failure, blocked, destructive |

Color never carries meaning alone. Status text, an icon, shape, or layout position must reinforce it.

### Theme, density, and contrast

- `Obsidian Signal` and `Ledger Paper` use the same semantic status tokens. A `Verified` state does not change meaning when the theme changes.
- Theme, density, and high-contrast preferences are local presentation state only. They are never included in a Node command, task record, authority decision, or ledger claim.
- The default is `Obsidian Signal` with comfortable density. Compact density reduces whitespace without reducing the minimum pointer target for consequential controls.
- High contrast strengthens borders, muted copy, and focus rings. It does not rely on a different status vocabulary.

### Typography

- Never import a font, icon, image, stylesheet, or script from a network URL.
- The initial Windows shell uses the local system stack: Segoe UI Variable or Segoe UI for UI text, Georgia for high-value document-style headings, and Cascadia Mono or Consolas for technical values. These are local operating-system assets, not product evidence or network dependencies.
- If AirBench later bundles a font, the font must be legally distributable, included in the installer, version-pinned, hashed in the resource manifest, and covered by the offline installation test.
- Use readable body sizes for source and artifact review.
- Use medium weight for labels, semibold for actions, and bold only for important status or headings.
- Use monospace for event IDs, hashes, code, model versions, and technical addresses.
- Use tabular numerals for measurements, timestamps, and ledger tables where supported.

### Spacing and sizing

- Base unit: 4 px.
- Standard consequential control height: 44 px.
- Coarse pointer target: 44 px minimum.
- Panel padding: 16 to 24 px.
- Content width: about 1,120 px for ordinary task work.
- Evidence and audit tables may use the full available width with virtualization.
- Keep document preview dominant on review screens.

### Shape and elevation

- Small radius for controls and status chips.
- Medium radius for cards and drawers.
- No excessive pills. Use pills only for compact status or capability labels.
- Use a low-opacity shadow for elevated drawers and document pages, not for every card.
- Borders should carry hierarchy; shadows should not become the hierarchy.

## 4. Component vocabulary

### Shell

- `AppShell`
- `SideRail`
- `TopBar`
- `NodeStatusChip`
- `SovereigntyStatus`
- `CommandMenu`
- `NotificationCenter`
- `AppearanceMenu`

### Work

- `TaskComposer`
- `IntakeManifest`
- `PlanGraph`
- `WorkerRoleCard`
- `ExecutionTimeline`
- `TaskStatusHeader`
- `TaskQuestionCard`

### Proof

- `EvidenceRow`
- `ProvenanceStrip`
- `SourceDrawer`
- `ConfidenceIndicator`
- `ClearanceLabel`
- `TaintIndicator`
- `VerificationChecklist`
- `LedgerReference`

### Deliverables

- `ArtifactCard`
- `ArtifactPreview`
- `DocumentOutline`
- `SheetPreview`
- `SlidePreview`
- `CodeReviewPane`
- `CalculationBreakdown`
- `ApprovalBar`

### Administration

- `NodeHealthPanel`
- `HardwareCapacityPanel`
- `ModelQualificationRow`
- `PolicyChangeDialog`
- `ConnectionProfileCard`

Each component must state which data is authoritative, which actions it can issue, and what it renders when the data is unavailable.

## 5. Shared status vocabulary

Use the same terms everywhere:

- `Queued`
- `Running`
- `Waiting for you`
- `Waiting for capacity`
- `Needs review`
- `Verified`
- `Approved`
- `Returned`
- `Blocked`
- `Failed`
- `Stopped`
- `Archived`

Do not call a draft `complete`. Do not call a rendered artifact `approved` before the required human action is recorded.

## 6. Provenance presentation

Every fact, finding, calculated value, or evidence-backed claim uses `ProvenanceStrip`.

### Compact form

Show:

- source label or document;
- confidence band or calibrated value;
- clearance compatibility;
- verification state.

### Expanded form

Show:

- exact source page, span, cell, or image region;
- source hash and version;
- extraction or derivation method;
- confidence and uncertainty reason;
- clearance and taint;
- observed, valid, or ingested time;
- parent facts for derived values;
- ledger event reference.

Never create a generic “AI generated” badge in place of provenance.

## 7. Interaction rules

- Primary buttons use verbs: `Start task`, `Approve`, `Return for changes`, `Reconnect`, `Verify chain`.
- Destructive actions require confirmation that states the impact and task ID.
- A disabled consequential action explains exactly what is missing.
- No infinite scroll without a visible loading and end state.
- Display preferences use local semantic tokens and must not change task state or send a command.
- No optimistic approval, stop, release, or artifact deletion state.
- A task stream shows server event time and local receipt time only when the difference matters.
- Long-running actions expose pause or stop only if the Node says the current state supports it.
- Upload progress shows intake status, not just bytes transferred.
- Reconnect notices are persistent until the event stream is current again.

## 8. Accessibility contract

- All controls have accessible names and correct roles.
- Tab order follows the work order, not DOM accident.
- Focus is trapped in dialogs and returned to the invoking control.
- Keyboard shortcuts never override text entry unexpectedly.
- Status changes are announced without flooding screen readers.
- Tables provide row and column headers, sort state, and a non-color status label.
- Evidence source regions have text alternatives and a linked source label.
- Preview zoom and selection do not trap keyboard focus.
- Reduced motion removes timeline pulses and decorative transitions.
- High contrast keeps borders, focus rings, and disabled states legible.

## 9. Empty, loading, and error states

Every screen needs a real state for:

- first use;
- no results;
- loading snapshot;
- reconnecting;
- blocked by policy;
- insufficient clearance;
- stale event cursor;
- backend failure;
- preview failure;
- permission denied.

The state explains what is known, what is preserved, whether retry is safe, and the next permitted action.

## 10. Content style

- Use direct, calm language.
- Explain technical facts in one short sentence before exposing detail.
- Say `AirBench is waiting for evidence verification`, not `agent stalled`.
- Say `This action needs approval from an authorized reviewer`, not `human in the loop`.
- Say `No external route was permitted by the node policy`, not `100% secure`.
- Never imply that a model has intention, authority, or certainty it does not have.
