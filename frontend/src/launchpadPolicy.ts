export type LaunchpadIntakeState = "idle" | "uploading" | "ready" | "failed";

export interface ShortcutInput {
  key: string;
  ctrlKey: boolean;
  metaKey: boolean;
}

export function sourceStatus(hasSelectedFile: boolean, intakeState: LaunchpadIntakeState): string {
  if (!hasSelectedFile) return "Add sources";
  if (intakeState === "ready") return "1 source ready";
  if (intakeState === "uploading") return "Preparing source";
  if (intakeState === "failed") return "Source needs attention";
  return "1 source added";
}

export function mayLaunchFromShortcut(input: ShortcutInput, canLaunch: boolean): boolean {
  return canLaunch && input.key === "Enter" && (input.ctrlKey || input.metaKey);
}

export interface RoutingPreferencePresentation {
  available: false;
  status: string;
  explanation: string;
}

/**
 * The current task-create contract has no Node-supplied, clearance-filtered
 * capability catalog. The UI therefore exposes no model name or endpoint
 * control. This helper is deliberately fail-closed until that contract exists.
 */
export function unavailableRoutingPreference(nodeConnected: boolean): RoutingPreferencePresentation {
  return {
    available: false,
    status: nodeConnected ? "No qualified catalog supplied by this Node" : "Connect a verified Node first",
    explanation: "When available, a preference is advisory only. Node policy may accept, narrow, ignore, queue, or reject it.",
  };
}
