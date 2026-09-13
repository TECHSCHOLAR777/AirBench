import { useEffect, useState } from "react";
import { AppIcon } from "./AppIcon";
import type { ApprovedNodeProfileReference, ApprovedNodeProfile } from "../platform/node/nodeConnection";
import { fetchNodeHardware, type HardwareStatus } from "../platform/node/hardwareBridge";

export function HardwareCard({
  profile,
  connected
}: {
  profile: ApprovedNodeProfileReference | ApprovedNodeProfile | null;
  connected: boolean;
}) {
  const [hardware, setHardware] = useState<HardwareStatus | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!connected || !profile) {
      setHardware(null);
      setError(null);
      return;
    }
    fetchNodeHardware(profile)
      .then(setHardware)
      .catch((e: unknown) => {
        setError(e instanceof Error ? e.message : String(e));
      });
  }, [profile, connected]);

  if (!connected) return null;
  if (error) {
    return <section className="hardware-card node-identity-card" aria-label="Node hardware">
      <div className="node-identity-head">
        <AppIcon name="cpu" size={17} />
        <div><strong>Hardware Profile</strong><span className="error-text">Failed to load: {error}</span></div>
      </div>
    </section>;
  }

  if (!hardware || !hardware.configured) {
    return <section className="hardware-card node-identity-card" aria-label="Node hardware">
      <div className="node-identity-head">
        <AppIcon name="cpu" size={17} />
        <div><strong>Hardware Profile</strong><span>No specific hardware profile configured on this Node.</span></div>
      </div>
    </section>;
  }

  return <section className="hardware-card node-identity-card" aria-label="Node hardware">
    <div className="node-identity-head">
      <AppIcon name="cpu" size={17} />
      <div>
        <strong>Hardware Profile</strong>
        <span>{hardware.profile_id ?? "Default Profile"}</span>
      </div>
    </div>
    <dl className="node-identity-grid">
      <div><dt>GPU Model</dt><dd>{hardware.gpu_model ?? "None"}</dd></div>
      <div><dt>GPU Count</dt><dd>{hardware.gpu_count ?? 0}</dd></div>
      <div><dt>VRAM</dt><dd>{hardware.vram_bytes ? `${Math.round(hardware.vram_bytes / (1024 * 1024 * 1024))} GB` : "0"}</dd></div>
      <div><dt>CPU Model</dt><dd>{hardware.cpu_model ?? "Unknown"}</dd></div>
      <div><dt>CPU Cores</dt><dd>{hardware.cpu_cores ?? "Unknown"}</dd></div>
      <div><dt>Max Parallel Workers</dt><dd>{hardware.safe_parallel_slots ?? "Unknown"}</dd></div>
    </dl>
  </section>;
}
