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
  connected,
  qualification,
}: {
  profile: ApprovedNodeProfileReference | ApprovedNodeProfile | null;
  connected: boolean;
  qualification?: import("../platform/node/qualificationBridge").QualificationRoster | null;
}) {
  const [targets, setTargets] = useState<ModelQualificationStatus[]>([]);
  const [configured, setConfigured] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (qualification !== undefined) return;
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
  }, [profile, connected, qualification]);

  const resolvedTargets = qualification !== undefined ? (qualification?.targets ?? []) : targets;
  const resolvedConfigured = qualification !== undefined ? Boolean(qualification?.configured) : configured;

  if (!connected) return null;

  return <section className="node-identity-card" aria-label="Model Roster">
    <div className="node-identity-head">
      <AppIcon name="shield" size={17} />
      <div>
        <strong>Model Roster &amp; Qualification</strong>
        <span>{resolvedConfigured ? `${resolvedTargets.length} targets declared by the Node` : "No qualification matrix configured on this Node"}</span>
      </div>
    </div>
    {loading && <div className="profile-empty">Checking qualifications...</div>}
    {error && <div className="profile-empty error-text">Failed to load roster: {error}</div>}
    {!loading && !error && resolvedTargets.length === 0 && (
      <div className="profile-empty">{resolvedConfigured ? "No model targets are declared." : "Model qualification is not configured on this Node."}</div>
    )}
    {!loading && !error && resolvedTargets.length > 0 && <ul className="model-roster-list">
      {resolvedTargets.map((q) => (
        <li key={q.target_id} className="model-roster-entry">
          <div className="model-roster-entry-card">
            <div className="model-roster-entry-head">
              <strong>{q.target_id}</strong>
              <span className={`artifact-record-state artifact-record-state-${stateClass(q.status)}`}>{q.status}</span>
            </div>
            <span className="model-roster-tier">Tier: {q.routing_tier ?? "Unknown"}</span>
            <small>{q.reason ?? (q.measurement_pending ? "Measurement pending" : "Evaluated")}</small>
          </div>
        </li>
      ))}
    </ul>}
  </section>;
}
