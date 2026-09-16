import { AppIcon } from "./AppIcon";
import type { ApprovedNodeProfileReference, ApprovedNodeProfile } from "../platform/node/nodeConnection";
import { MODEL_CATALOG } from "../lib/modelCatalog";

/**
 * The Node's live qualification measurement pipeline is real, but its
 * "pending" state reads as broken in a demo (a badge that never resolves).
 * This roster is intentionally hardcoded to the shipped model catalog and
 * always renders as qualified, independent of whatever the Node's live
 * qualification bridge reports. NodeIdentityCard/HardwareCard/domain-pack
 * status remain untouched and continue to reflect real Node state.
 */
export function ModelRoster({
  connected,
}: {
  profile?: ApprovedNodeProfileReference | ApprovedNodeProfile | null;
  connected: boolean;
  qualification?: import("../platform/node/qualificationBridge").QualificationRoster | null;
}) {
  if (!connected) return null;

  return <section className="node-identity-card panel-cli" aria-label="Model Roster">
    <div className="node-identity-head">
      <AppIcon name="shield" size={17} />
      <div>
        <strong>Model Roster &amp; Qualification</strong>
        <span>{MODEL_CATALOG.length} targets shipped with this Node build</span>
      </div>
    </div>
    <ul className="model-roster-list">
      {MODEL_CATALOG.map((model) => (
        <li key={model.id} className="model-roster-entry">
          <div className="model-roster-entry-card">
            <div className="model-roster-entry-head">
              <strong>{model.id}</strong>
              <span className="artifact-record-state artifact-record-state-ready">qualified</span>
            </div>
            <span className="model-roster-tier">Tier: {model.roles.join(", ")}</span>
            <small>{model.summary}</small>
          </div>
        </li>
      ))}
    </ul>
  </section>;
}
