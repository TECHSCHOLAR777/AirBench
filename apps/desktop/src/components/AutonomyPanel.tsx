import { useEffect, useState } from "react";
import { AppIcon } from "./AppIcon";
import type { ApprovedNodeProfileReference, ApprovedNodeProfile } from "../platform/node/nodeConnection";
import { fetchTaskAutonomy, authorizeAutonomyEscalation, type AutonomyStatus } from "../platform/node/autonomyBridge";
import type { TaskStatus } from "../platform/events/protocol";

export function AutonomyPanel({
  profile,
  taskId,
  operatorId,
  taskStatus
}: {
  profile: ApprovedNodeProfileReference | ApprovedNodeProfile;
  taskId: string;
  operatorId: string;
  taskStatus: TaskStatus;
}) {
  const [status, setStatus] = useState<AutonomyStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [authorizing, setAuthorizing] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;
    setLoading(true);
    fetchTaskAutonomy(profile, taskId)
      .then(res => {
        if (mounted) {
          setStatus(res);
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
  }, [profile, taskId, taskStatus]); // Re-fetch when task status changes

  const onAuthorize = async (actionId: string) => {
    setAuthorizing(actionId);
    try {
      await authorizeAutonomyEscalation(profile, taskId, operatorId, actionId);
      // Re-fetch autonomy status
      const res = await fetchTaskAutonomy(profile, taskId);
      setStatus(res);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setAuthorizing(null);
    }
  };

  if (loading && !status) return null; // Keep it silent while loading initially
  if (!status || status.decisions.length === 0) return null;

  return <section className="worktrace-detail-card" aria-label="Task Autonomy Status">
    <div className="worktrace-detail-head">
      <div><h2>Autonomy Escalations</h2><p>Node requested human authorization.</p></div>
      <span>{status.decisions.length} decisions</span>
    </div>
    
    {error && <div className="worktrace-empty error-text">{error}</div>}
    
    <ul className="worktrace-question-list">
      {status.decisions.map((dec) => (
        <li key={dec.action_id} className="autonomy-decision">
          <div className="autonomy-decision-head">
            <AppIcon name={dec.outcome === "escalate" ? "shield" : "review"} size={16} />
            <strong>{dec.action_kind}</strong>
            <span className={`artifact-record-state artifact-record-state-${dec.outcome === "allow" ? "ready" : "superseded"}`}>
              {dec.outcome.toUpperCase()}
            </span>
          </div>
          <p className="autonomy-decision-reason">{dec.reason}</p>
          <small className="autonomy-decision-authority">Authority required: {dec.required_authority}</small>
          
          {dec.outcome === "escalate" && status.is_blocked && (
            <button 
              type="button" 
              className="primary-button compact-button autonomy-authorize-button"
              onClick={() => { void onAuthorize(dec.action_id); }}
              disabled={authorizing === dec.action_id}
            >
              {authorizing === dec.action_id ? "Authorizing..." : "Authorize Action"}
            </button>
          )}
        </li>
      ))}
    </ul>
  </section>;
}
