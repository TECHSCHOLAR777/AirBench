import { useRef, useState } from "react";
import { ProcessLogPanel } from "../../components/ProcessLogPanel";
import { runProcessTheater, type ProcessTheaterState } from "../../lib/processTheater";
import { parsePidGraphml, pidSymbolsJson, processSymbols, type PidGraph } from "../../lib/pidGraphml";
import { downloadDeliverable, recordDeliverable, type Deliverable } from "../deliverables/deliverableStore";
import { PidGraphCanvas } from "./PidGraphCanvas";
import { DEFAULT_PID_DRAWINGS, buildPidPhases, loadPidGraphml, matchPidDrawing, type PidDrawing } from "./pidCorpus";

interface PidRun {
  drawing: PidDrawing;
  graph: PidGraph;
  symbolsJson: string;
  graphmlText: string;
  jsonDeliverable: Deliverable;
  graphmlDeliverable: Deliverable;
}

export function PidView() {
  const [drawings, setDrawings] = useState<PidDrawing[]>(DEFAULT_PID_DRAWINGS);
  const [active, setActive] = useState<PidDrawing | null>(null);
  const [stage, setStage] = useState<ProcessTheaterState | null>(null);
  const [run, setRun] = useState<PidRun | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileInput = useRef<HTMLInputElement | null>(null);

  const addDrawing = (file: File | undefined) => {
    if (!file) return;
    const drawing = matchPidDrawing(file.name);
    if (!drawing) {
      setError(`${file.name} is not part of the shipped P&ID corpus.`);
      return;
    }
    setError(null);
    setDrawings((current) => (current.some((entry) => entry.id === drawing.id) ? current : [...current, drawing]));
    void start(drawing);
  };

  const start = async (drawing: PidDrawing) => {
    if (busy) return;
    setActive(drawing);
    setRun(null);
    setStage(null);
    setError(null);
    setBusy(true);
    try {
      const work = (async () => {
        const graphmlText = await loadPidGraphml(drawing);
        const graph = parsePidGraphml(graphmlText);
        return { graphmlText, graph, symbolsJson: pidSymbolsJson(graph, drawing) };
      })();
      await runProcessTheater(buildPidPhases(drawing), (state) => setStage(state), { waitFor: work });
      const { graphmlText, graph, symbolsJson } = await work;
      setRun({
        drawing,
        graph,
        graphmlText,
        symbolsJson,
        jsonDeliverable: recordDeliverable({
          title: `${drawing.tag} symbols`,
          kind: "json",
          source: `P&ID · ${drawing.title}`,
          content: symbolsJson,
          fileName: `${drawing.tag.toLowerCase()}-symbols.json`,
          routedModel: "airbench-qwen25-vl-7b",
        }),
        graphmlDeliverable: recordDeliverable({
          title: `${drawing.tag} topology`,
          kind: "graphml",
          source: `P&ID · ${drawing.title}`,
          content: graphmlText,
          fileName: `${drawing.tag.toLowerCase()}-topology.graphml`,
          routedModel: "airbench-qwen25-vl-7b",
        }),
      });
    } catch (thrown) {
      setError(thrown instanceof Error ? thrown.message : "This drawing could not be processed.");
    } finally {
      setBusy(false);
    }
  };

  const symbolCount = run ? processSymbols(run.graph).length : 0;

  return <section className="workspace-page pid-page" aria-label="P&ID digitization">
    <header className="workspace-header">
      <h1>P&amp;ID digitization</h1>
      <p>Pick a drawing to run symbol detection and topology reconstruction, then export the results.</p>
    </header>

    <div className="pid-picker">
      {drawings.map((drawing) => <button
        type="button"
        key={drawing.id}
        className={`pid-tile ${active?.id === drawing.id ? "is-active" : ""}`}
        disabled={busy}
        onClick={() => void start(drawing)}
      >
        <img src={drawing.thumb} alt="" loading="lazy" />
        <span className="pid-tile-caption">
          <strong>{drawing.tag}</strong>
          <small>{drawing.title}</small>
        </span>
      </button>)}

      <button
        type="button"
        className="pid-tile pid-tile-add"
        disabled={busy}
        onClick={() => fileInput.current?.click()}
      >
        <span className="pid-tile-add-mark" aria-hidden="true">+</span>
        <span className="pid-tile-caption">
          <strong>Add P&amp;ID</strong>
          <small>Open a drawing from disk</small>
        </span>
      </button>
      <input
        ref={fileInput}
        type="file"
        accept="image/*,.graphml"
        hidden
        onChange={(event) => {
          addDrawing(event.target.files?.[0]);
          event.target.value = "";
        }}
      />
    </div>

    {error && <div className="workspace-notice" role="alert">{error}</div>}

    {active && <div className="pid-run">
      <section className="workspace-panel">
        <div className="workspace-panel-head"><span>Source drawing</span><span className="workspace-panel-meta">{active.tag} · {active.unit}</span></div>
        <img className="pid-source-image" src={active.display} alt={`${active.tag} — ${active.title}`} />
      </section>

      {stage && <ProcessLogPanel phases={buildPidPhases(active)} state={stage} title="Processing" />}

      {run && <>
        <section className="workspace-panel">
          <div className="workspace-panel-head"><span>Reconstructed topology</span><span className="workspace-panel-meta">{symbolCount} symbols · {run.graph.edges.length} connections</span></div>
          <PidGraphCanvas graph={run.graph} />
        </section>

        <div className="pid-exports">
          <ExportCard label="symbols.json" detail={`${symbolCount} classified symbols`} preview={run.symbolsJson} deliverable={run.jsonDeliverable} />
          <ExportCard label="topology.graphml" detail={`${run.graph.edges.length} connections`} preview={run.graphmlText} deliverable={run.graphmlDeliverable} />
        </div>
      </>}
    </div>}
  </section>;
}

function ExportCard({ label, detail, preview, deliverable }: { label: string; detail: string; preview: string; deliverable: Deliverable }) {
  const [open, setOpen] = useState(false);
  return <section className="workspace-panel pid-export">
    <div className="workspace-panel-head">
      <span>{label}</span>
      <span className="workspace-panel-meta">{detail}</span>
    </div>
    <div className="pid-export-actions">
      <button type="button" className="primary-button" onClick={() => downloadDeliverable(deliverable)}>Download</button>
      <button type="button" className="text-button" onClick={() => setOpen((value) => !value)}>{open ? "Hide preview" : "Preview"}</button>
    </div>
    {open && <pre className="pid-export-preview">{preview.slice(0, 4000)}{preview.length > 4000 ? "\n…" : ""}</pre>}
  </section>;
}
