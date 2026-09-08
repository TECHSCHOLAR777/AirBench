import { AppIcon } from "./AppIcon";
import type { ApprovedNodeProfileReference } from "../platform/node/nodeConnection";
import type { NodeConnectionView } from "../platform/node/nodeConnectionController";
import { buildNodeReadiness } from "../platform/node/nodeReadiness";

interface NodeReadinessPanelProps {
  connection: NodeConnectionView;
  profile: ApprovedNodeProfileReference | null;
}

export function NodeReadinessPanel({ connection, profile }: NodeReadinessPanelProps) {
  const readiness = buildNodeReadiness(connection, profile);
  const connectionIcon = readiness.connection.tone === "trusted" ? "shield" : "node";

  return <div className="node-readiness" data-testid="node-readiness-panel">
    <p className="sr-only" role="status">{readiness.connection.title}</p>
    <section className={`node-connection-proof tone-${readiness.connection.tone}`} aria-label="Node connection proof">
      <header className="node-readiness-head">
        <span className="node-readiness-icon" aria-hidden="true"><AppIcon name={connectionIcon} size={20} /></span>
        <div><p className="eyebrow">CONNECTION PROOF</p><h2>{readiness.connection.title}</h2><p>{readiness.connection.detail}</p></div>
      </header>
      {readiness.connection.proof.length > 0
        ? <dl className="node-proof-grid">{readiness.connection.proof.map((field) => <div key={field.label}><dt>{field.label}</dt><dd>{field.value}</dd></div>)}</dl>
        : <p className="node-proof-empty">No trusted handshake fields are shown while this connection needs attention.</p>}
    </section>

    <section className="node-readiness-explainer" aria-label="About an AirBench Node">
      <span className="node-readiness-explainer-icon" aria-hidden="true"><AppIcon name="node" size={17} /></span>
      <div><p className="eyebrow">WHAT IS AN AIRBENCH NODE?</p><p>An AirBench Node is the organization-run service that keeps task coordination, model work, tools, file intake, verification, and the audit ledger inside your approved environment. This desktop app connects only to that Node.</p></div>
    </section>

    <section className={`node-operational-gateway state-${readiness.operational.state}`} aria-label="Node operational status">
      <header className="node-readiness-head">
        <span className="node-readiness-icon" aria-hidden="true"><AppIcon name="sliders" size={20} /></span>
        <div><p className="eyebrow">NODE OPERATIONAL STATUS</p><h2>{readiness.operational.title}</h2><p>{readiness.operational.detail}</p></div>
      </header>
      <ul className="node-missing-list">{readiness.operational.missing.map((item) => <li key={item}><span>{item}</span><strong>{readiness.operational.state === "not_supplied" ? "Not supplied" : "Connection required"}</strong></li>)}</ul>
    </section>

    <section className="node-routing-boundary" aria-label="Model routing authority">
      <span className="node-readiness-explainer-icon" aria-hidden="true"><AppIcon name="route" size={17} /></span>
      <div><p className="eyebrow">MODEL ROUTING</p><h2>{readiness.routing.title}</h2><p>{readiness.routing.detail}</p></div>
    </section>
  </div>;
}
