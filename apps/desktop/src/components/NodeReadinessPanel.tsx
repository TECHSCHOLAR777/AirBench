import { useEffect, useState } from "react";
import { AppIcon } from "./AppIcon";
import type { ApprovedNodeProfileReference } from "../platform/node/nodeConnection";
import type { NodeConnectionView } from "../platform/node/nodeConnectionController";
import { buildNodeReadiness } from "../platform/node/nodeReadiness";
import { buildOperationalProjection } from "../platform/node/operationalReadiness";
import { fetchNodeHardware, type HardwareStatus } from "../platform/node/hardwareBridge";
import { fetchModelServing, type ModelServingStatus } from "../platform/node/modelServingBridge";
import { fetchQualificationRoster, type QualificationRoster } from "../platform/node/qualificationBridge";
import { domainPackSignatureTone, fetchDomainPack, type DomainPackStatus } from "../platform/node/domainPack";

interface NodeReadinessPanelProps {
  connection: NodeConnectionView;
  profile: ApprovedNodeProfileReference | null;
}

export function NodeReadinessPanel({ connection, profile }: NodeReadinessPanelProps) {
  const readiness = buildNodeReadiness(connection, profile);
  const connectionIcon = readiness.connection.tone === "trusted" ? "shield" : "node";
  const verified = readiness.connection.tone === "trusted";
  const [domainPack, setDomainPack] = useState<DomainPackStatus | null>(null);
  const [domainPackUnavailable, setDomainPackUnavailable] = useState(false);
  const [hardware, setHardware] = useState<HardwareStatus | null>(null);
  const [modelServing, setModelServing] = useState<ModelServingStatus | null>(null);
  const [qualification, setQualification] = useState<QualificationRoster | null>(null);

  useEffect(() => {
    let active = true;
    if (!verified || !profile) {
      setHardware(null);
      setModelServing(null);
      setQualification(null);
      return () => { active = false; };
    }
    Promise.allSettled([
      fetchNodeHardware(profile),
      fetchModelServing(profile),
      fetchQualificationRoster(profile),
    ]).then(([hardwareResult, servingResult, qualificationResult]) => {
      if (!active) return;
      setHardware(hardwareResult.status === "fulfilled" ? hardwareResult.value : null);
      setModelServing(servingResult.status === "fulfilled" ? servingResult.value : null);
      setQualification(qualificationResult.status === "fulfilled" ? qualificationResult.value : null);
    });
    return () => { active = false; };
  }, [verified, profile]);

  useEffect(() => {
    let active = true;
    if (!verified || !profile) {
      setDomainPack(null);
      setDomainPackUnavailable(false);
      return () => { active = false; };
    }
    fetchDomainPack(profile)
      .then((status) => { if (active) { setDomainPack(status); setDomainPackUnavailable(false); } })
      .catch(() => { if (active) { setDomainPack(null); setDomainPackUnavailable(true); } });
    return () => { active = false; };
  }, [verified, profile]);

  const packTone = domainPack ? domainPackSignatureTone(domainPack) : "attention";
  const operational = buildOperationalProjection({ verified, hardware, modelServing, qualification });

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
      <dl className="node-recovery-guidance" aria-label="Safe Node connection recovery guidance">
        <div><dt>Preserved</dt><dd>{readiness.connection.recovery.preserved}</dd></div>
        <div><dt>Retry</dt><dd>{readiness.connection.recovery.retry}</dd></div>
        <div><dt>Next</dt><dd>{readiness.connection.recovery.nextAction}</dd></div>
      </dl>
    </section>

    {verified && <section className={`node-domain-pack tone-${packTone}`} aria-label="Domain pack status" data-testid="node-domain-pack">
      <header className="node-readiness-head">
        <span className="node-readiness-icon" aria-hidden="true"><AppIcon name="sliders" size={20} /></span>
        <div>
          <p className="eyebrow">DOMAIN PACK</p>
          <h2>{domainPack?.configured ? `${domainPack.pack_id} v${domainPack.pack_version}` : "Domain pack status unavailable"}</h2>
          <p>{domainPack?.configured
            ? "The Node's declared sector pack. Verification happens at Node startup; the desktop only displays the result and never loads the pack."
            : domainPackUnavailable
              ? "The desktop could not read the Node domain pack declaration. Consequential work stays governed by the Node."
              : "Reading the Node domain pack declaration."}</p>
        </div>
      </header>
      {domainPack?.configured && <dl className="node-proof-grid">
        <div><dt>Signature</dt><dd>{domainPack.signature_status === "signed" ? "Signed" : "Unsigned (development only)"}</dd></div>
        <div><dt>Active sections</dt><dd>{domainPack.active_sections.length}</dd></div>
        <div><dt>Field rules</dt><dd>{domainPack.counts.field_rules ?? 0}</dd></div>
        <div><dt>Risk mappings</dt><dd>{domainPack.counts.risk_mappings ?? 0}</dd></div>
      </dl>}
    </section>}

    <section className="node-readiness-explainer" aria-label="About an AirBench Node">
      <span className="node-readiness-explainer-icon" aria-hidden="true"><AppIcon name="node" size={17} /></span>
      <div><p className="eyebrow">WHAT IS AN AIRBENCH NODE?</p><p>An AirBench Node is the organization-run service that keeps task coordination, model work, tools, file intake, verification, and the audit ledger inside your approved environment. This desktop app connects only to that Node.</p></div>
    </section>

    <section className={`node-operational-gateway state-${operational.state}`} aria-label="Node operational status">
      <header className="node-readiness-head">
        <span className="node-readiness-icon" aria-hidden="true"><AppIcon name="sliders" size={20} /></span>
        <div><p className="eyebrow">NODE OPERATIONAL STATUS</p><h2>{operational.title}</h2><p>{operational.detail}</p></div>
      </header>
      <ul className="node-missing-list">{operational.items.map((item) => <li key={item.label}><span>{item.label}</span><strong className={item.supplied ? "operational-supplied" : "operational-missing"}>{item.value}</strong></li>)}</ul>
    </section>

    <section className="node-routing-boundary" aria-label="Model routing authority">
      <span className="node-readiness-explainer-icon" aria-hidden="true"><AppIcon name="route" size={17} /></span>
      <div><p className="eyebrow">MODEL ROUTING</p><h2>{readiness.routing.title}</h2><p>{readiness.routing.detail}</p></div>
    </section>
  </div>;
}
