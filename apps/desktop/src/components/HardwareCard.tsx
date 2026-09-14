import { useEffect, useState } from "react";
import { AppIcon } from "./AppIcon";
import type { ApprovedNodeProfileReference, ApprovedNodeProfile } from "../platform/node/nodeConnection";
import { fetchNodeHardware, type HardwareStatus } from "../platform/node/hardwareBridge";

export function HardwareCard({
  profile,
  connected,
  hardware,
}: {
  profile: ApprovedNodeProfileReference | ApprovedNodeProfile | null;
  connected: boolean;
  hardware?: HardwareStatus | null;
}) {
  const [fetchedHardware, setFetchedHardware] = useState<HardwareStatus | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!connected || !profile) {
      setFetchedHardware(null);
      setError(null);
      return;
    }
    if (hardware !== undefined) return;
    fetchNodeHardware(profile)
      .then(setFetchedHardware)
      .catch((e: unknown) => {
        setError(e instanceof Error ? e.message : String(e));
      });
  }, [profile, connected, hardware]);

  const resolvedHardware = hardware !== undefined ? hardware : fetchedHardware;

  if (!connected) return null;
  if (error) {
    return <section className="hardware-card node-identity-card" aria-label="Node hardware">
      <div className="node-identity-head">
        <AppIcon name="cpu" size={17} />
        <div><strong>Hardware Profile</strong><span className="error-text">Failed to load: {error}</span></div>
      </div>
    </section>;
  }

  if (!resolvedHardware || !resolvedHardware.configured) {
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
        <span>{resolvedHardware.profile_id ?? "Default Profile"}</span>
      </div>
    </div>
    <dl className="node-identity-grid">
      <div><dt>GPU Model</dt><dd>{resolvedHardware.gpu_model ?? "None"}</dd></div>
      <div><dt>GPU Count</dt><dd>{resolvedHardware.gpu_count ?? 0}</dd></div>
      <div><dt>VRAM</dt><dd>{resolvedHardware.vram_bytes ? `${Math.round(resolvedHardware.vram_bytes / (1024 * 1024 * 1024))} GB` : "0"}</dd></div>
      <div><dt>CPU Model</dt><dd>{resolvedHardware.cpu_model ?? "Unknown"}</dd></div>
      <div><dt>CPU Cores</dt><dd>{resolvedHardware.cpu_cores ?? "Unknown"}</dd></div>
      <div><dt>Max Parallel Workers</dt><dd>{resolvedHardware.safe_parallel_slots ?? "Unknown"}</dd></div>
    </dl>
  </section>;
}
