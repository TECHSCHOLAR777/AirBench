import { useEffect, useState } from "react";
import { AppIcon } from "./AppIcon";
import type { ApprovedNodeProfileReference, ApprovedNodeProfile } from "../platform/node/nodeConnection";
import { fetchQualificationRoster, type ModelQualificationStatus } from "../platform/node/qualificationBridge";

function stateClass(status: ModelQualificationStatus["status"]): string {
  if (status === "qualified") return "ready";
  if (status === "pending") return "attention";
  return "superseded";
}

export function ModelRoster({
  profile,
  connected
}: {
  profile: ApprovedNodeProfileReference | ApprovedNodeProfile | null;
  connected: boolean;
}) {
  const [targets, setTargets] = useState<ModelQualificationStatus[]>([]);
  const [configured, setConfigured] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!connected || !profile) {
      setTargets([]);
      setConfigured(false);
      setError(null);
      return;
    }
    let mounted = true;
    setLoading(true);
    fetchQualificationRoster(profile)
      .then((roster) => {
        if (mounted) {
          setTargets(roster.targets);
          setConfigured(roster.configured);
          setError(null);
        }
      })
      .catch((e: unknown) => {
        if (mounted) {
          setError(e instanceof Error ? e.message : String(e));
        }
      })
      .finally(() => {
        if (mounted) {
          setLoading(false);
        }
      });
    return () => {
      mounted = false;
    };
  }, [profile, connected]);

  if (!connected) return null;

  return <section className="node-identity-card" aria-label="Model Roster">
    <div className="node-identity-head">
      <AppIcon name="shield" size={17} />
      <div>
        <strong>Model Roster &amp; Qualification</strong>
        <span>{configured ? `${targets.length} targets declared by the Node` : "No qualification matrix configured on this Node"}</span>
      </div>
    </div>
    {loading && <div className="profile-empty">Checking qualifications...</div>}
    {error && <div className="profile-empty error-text">Failed to load roster: {error}</div>}
    {!loading && !error && targets.length === 0 && (
      <div className="profile-empty">{configured ? "No model targets are declared." : "Model qualification is not configured on this Node."}</div>
    )}
    {!loading && !error && targets.length > 0 && <ul className="worktrace-artifact-list">
      {targets.map((q) => (
        <li key={q.target_id}>
          <div className="proof-record-button" style={{ display: "flex", flexDirection: "column", alignItems: "flex-start", width: "100%", border: "none", background: "none" }}>
            <div style={{ display: "flex", justifyContent: "space-between", width: "100%" }}>
              <strong>{q.target_id}</strong>
              <span className={`artifact-record-state artifact-record-state-${stateClass(q.status)}`}>{q.status}</span>
            </div>
            <span>Tier: {q.routing_tier ?? "Unknown"}</span>
            <small>{q.reason ?? (q.measurement_pending ? "Measurement pending" : "Evaluated")}</small>
          </div>
        </li>
      ))}
    </ul>}
  </section>;
}
