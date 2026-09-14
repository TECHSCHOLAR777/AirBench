/**
 * Read-only projection of the Node's operational status.
 *
 * The project composes values the Node actually reports through its hardware,
 * model-serving, and qualification endpoints. It never infers operational
 * health from the connection handshake, and a missing value stays "Not
 * supplied" rather than being guessed.
 */
import type { HardwareStatus } from "./hardwareBridge";
import type { ModelServingStatus } from "./modelServingBridge";
import type { QualificationRoster } from "./qualificationBridge";

export interface OperationalInput {
  verified: boolean;
  hardware: HardwareStatus | null;
  modelServing: ModelServingStatus | null;
  qualification: QualificationRoster | null;
}

export interface OperationalItem {
  label: string;
  value: string;
  supplied: boolean;
}

export interface OperationalProjection {
  state: "connection_required" | "reported";
  title: string;
  detail: string;
  items: OperationalItem[];
}

const NOT_SUPPLIED = "Not supplied";

const LABELS = {
  hardware: "Hardware and capacity",
  sandbox: "Sandbox health",
  catalog: "Qualified capability catalog",
  router: "Router decision history",
} as const;

export function formatVram(bytes: number | null): string | null {
  if (bytes === null || bytes <= 0) return null;
  return `${(bytes / (1024 ** 3)).toFixed(1)} GB VRAM`;
}

function hardwareValue(hardware: HardwareStatus | null): string {
  if (!hardware || !hardware.configured) return NOT_SUPPLIED;
  const parts = [hardware.gpu_model, formatVram(hardware.vram_bytes)];
  if (hardware.safe_parallel_slots !== null) parts.push(`${hardware.safe_parallel_slots} parallel slots`);
  const text = parts.filter((part): part is string => Boolean(part && part.trim())).join(" / ");
  return text || NOT_SUPPLIED;
}

function sandboxValue(hardware: HardwareStatus | null): string {
  if (!hardware || !hardware.configured) return NOT_SUPPLIED;
  const parts: string[] = [];
  if (hardware.sandbox_runtime) parts.push(hardware.sandbox_runtime);
  if (hardware.egress_policy) parts.push(`egress ${hardware.egress_policy}`);
  return parts.join(" / ") || NOT_SUPPLIED;
}

function catalogValue(qualification: QualificationRoster | null): string {
  if (!qualification || !qualification.configured) return NOT_SUPPLIED;
  const total = qualification.targets.length;
  if (total === 0) return "No targets declared";
  const qualified = qualification.targets.filter((target) => target.status === "qualified").length;
  return `${qualified} of ${total} targets qualified`;
}

function routerValue(modelServing: ModelServingStatus | null): string {
  if (!modelServing || !modelServing.configured) return NOT_SUPPLIED;
  const count = modelServing.endpoints.length;
  const healthy = modelServing.endpoints.filter(
    (endpoint) => endpoint.health === "healthy" && endpoint.readiness === "ready",
  ).length;
  return modelServing.status === "ready"
    ? `Ready / ${healthy} of ${count} endpoint(s)`
    : `Degraded / ${healthy} of ${count} endpoint(s) ready`;
}

export function buildOperationalProjection(input: OperationalInput): OperationalProjection {
  if (!input.verified) {
    return {
      state: "connection_required",
      title: "Operational status requires a verified Node",
      detail: "Hardware, sandbox, qualification, and router detail stay hidden until an approved Node connection is verified.",
      items: Object.values(LABELS).map((label) => ({ label, value: "Connection required", supplied: false })),
    };
  }

  const items: OperationalItem[] = [
    { label: LABELS.hardware, value: hardwareValue(input.hardware), supplied: Boolean(input.hardware?.configured) },
    { label: LABELS.sandbox, value: sandboxValue(input.hardware), supplied: Boolean(input.hardware?.configured) },
    { label: LABELS.catalog, value: catalogValue(input.qualification), supplied: Boolean(input.qualification?.configured) },
    { label: LABELS.router, value: routerValue(input.modelServing), supplied: Boolean(input.modelServing?.configured) },
  ];

  return {
    state: "reported",
    title: "Node operational status reported by the Node",
    detail: "These values are projected from the Node's own hardware, model-serving, and qualification endpoints. The desktop does not infer them from the handshake.",
    items,
  };
}
