import { useEffect, useState } from "react";
import { AppIcon } from "./AppIcon";
import type { ApprovedNodeProfileReference, ApprovedNodeProfile } from "../platform/node/nodeConnection";
import { fetchTaskConsistency, justifyConsistencyDeviation, type ConsistencyReport } from "../platform/node/consistencyBridge";

export function ConsistencyPanel({
  profile,
  taskId,
  operatorId
}: {
  profile: ApprovedNodeProfileReference | ApprovedNodeProfile;
  taskId: string;
  operatorId: string;
}) {
  const [report, setReport] = useState<ConsistencyReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [justification, setJustification] = useState("");
  const [justifying, setJustifying] = useState(false);

  useEffect(() => {
    let mounted = true;
    setLoading(true);
    fetchTaskConsistency(profile, taskId)
      .then(res => {
        if (mounted) {
          setReport(res);
          setError(null);
        }
      })
      .catch((e: unknown) => {
        if (mounted) setError(e instanceof Error ? e.message : String(e));
      })
      .finally(() => {
        if (mounted) setLoading(false);
      });
    return () => { mounted = false; };
  }, [profile, taskId]);

  const onJustify = async () => {
    if (!justification.trim()) return;
    setJustifying(true);
    try {
      const updated = await justifyConsistencyDeviation(profile, taskId, operatorId, justification);
      setReport(updated);
      setJustification("");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setJustifying(false);
    }
  };

  if (loading && !report) {
    return <div className="worktrace-empty">Loading consistency report...</div>;
  }
  if (error) {
    return <div className="plan-warning" role="alert"><strong>Consistency Check Failed</strong><span>{error}</span></div>;
  }
  if (!report || report.status === "not_evaluated") {
    return null;
  }

  return <section className="consistency-panel" aria-label="Task Consistency Report">
    <div className="consistency-panel-head">
      <AppIcon name="shield" size={17} />
      <h3>Consistency Report</h3>
      {report.deviation && !report.justified && <span className="intake-badge plan-state-needs_review">Deviation Detected</span>}
      {!report.deviation && <span className="intake-badge plan-state-ready">Consistent</span>}
      {report.justified && <span className="intake-badge plan-state-ready">Justified</span>}
    </div>
    
    {report.material_differences.length > 0 && <div className="plan-stages consistency-differences">
      <span>Material Differences</span>
      {report.material_differences.map((diff, idx) => (
        <div className="plan-stage" key={idx}>
          <strong>{diff.feature}</strong>
          <small>Was {diff.previous_value}, now {diff.current_value}</small>
        </div>
      ))}
    </div>}
    
    {report.reason && <p className="plan-muted">{report.reason}</p>}
    
    {report.deviation && !report.justified && (
      <div className="consistency-justification">
        <input 
          type="text" 
          aria-label="Operator justification"
          value={justification} 
          onChange={e => setJustification(e.target.value)}
          placeholder="Provide operator justification..." 
          className="consistency-justification-input"
          disabled={justifying}
        />
        <button 
          type="button" 
          className="secondary-button" 
          onClick={() => { void onJustify(); }}
          disabled={justifying || !justification.trim()}
        >
          {justifying ? "Justifying..." : "Justify"}
        </button>
      </div>
    )}
  </section>;
}
