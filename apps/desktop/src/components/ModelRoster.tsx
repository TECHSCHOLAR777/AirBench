import { useEffect, useState } from "react";
import { AppIcon } from "./AppIcon";
import type { ApprovedNodeProfileReference, ApprovedNodeProfile } from "../platform/node/nodeConnection";
import { fetchModelQualification, type ModelQualificationStatus } from "../platform/node/qualificationBridge";

const ROSTER_TARGETS = [
  "gemma4-31b-it-q4",
  "gemma4-26b-a4b-4bit",
  "qwen3-coder-30b-a3b-4bit",
  "qwen2.5-vl-7b-4bit",
  "bge-m3",
  "bge-reranker-v2-m3",
  "airbench-gemma-4-e2b",
  "airbench-gemma-4-12b"
];

export function ModelRoster({
  profile,
  connected
}: {
  profile: ApprovedNodeProfileReference | ApprovedNodeProfile | null;
  connected: boolean;
}) {
  const [qualifications, setQualifications] = useState<ModelQualificationStatus[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!connected || !profile) {
      setQualifications([]);
      setError(null);
      return;
    }
    let mounted = true;
    setLoading(true);
    Promise.all(ROSTER_TARGETS.map(t => fetchModelQualification(profile, t)))
      .then(results => {
        if (mounted) {
          setQualifications(results);
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
      <div><strong>Model Roster & Qualification</strong><span>8 targets declared in the domain matrix</span></div>
    </div>
    {loading && <div className="profile-empty">Checking qualifications...</div>}
    {error && <div className="profile-empty error-text">Failed to load roster: {error}</div>}
    {!loading && !error && <ul className="worktrace-artifact-list">
      {qualifications.map(q => (
        <li key={q.target_id}>
          <div className="proof-record-button" style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-start', width: '100%', border: 'none', background: 'none' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', width: '100%' }}>
              <strong>{q.target_id}</strong>
              <span className={`artifact-record-state artifact-record-state-${q.status === 'qualified' ? 'ready' : 'superseded'}`}>
                {q.status}
              </span>
            </div>
            <span>Tier: {q.routing_tier ?? "Unknown"}</span>
            <small>{q.reason ?? (q.measurement_pending ? "Measurement pending" : "Evaluated")}</small>
          </div>
        </li>
      ))}
    </ul>}
  </section>;
}
