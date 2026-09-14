import { AppIcon } from "./AppIcon";
import type { NodeRouteTrace } from "../generated/core_contracts";

interface ModelIndicatorCardProps {
  routeTrace: NodeRouteTrace | null;
}

export function ModelIndicatorCard({ routeTrace }: ModelIndicatorCardProps) {
  if (!routeTrace || routeTrace.entries.length === 0) {
    return (
      <section className="model-indicator-card tone-idle" aria-label="Model in use">
        <AppIcon name="shield" size={16} />
        <span>No model call yet</span>
      </section>
    );
  }

  const latest = routeTrace.entries[routeTrace.entries.length - 1];
  
  let stateLabel = "Selecting...";
  let tone = "idle";
  let icon: "shield" | "cpu" | "close" = "cpu";
  
  if (latest.status === "failed" || latest.status === "rejected") {
    stateLabel = "Unavailable";
    tone = "warning";
    icon = "close";
  } else if (latest.selectedModelName) {
    stateLabel = `Active: ${latest.selectedModelName}`;
    tone = "active";
    icon = "cpu";
  } else if (latest.selectedTarget) {
    stateLabel = "Active: Approved Model";
    tone = "active";
    icon = "cpu";
  }

  return (
    <section className={`model-indicator-card tone-${tone}`} aria-label="Model in use">
      <AppIcon name={icon as any} size={16} />
      <span>{stateLabel}</span>
    </section>
  );
}
