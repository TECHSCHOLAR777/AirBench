import { describe, expect, it } from "vitest";
import { buildOperationalProjection, formatVram } from "./operationalReadiness";
import type { HardwareStatus } from "./hardwareBridge";

const hardware: HardwareStatus = {
  configured: true,
  profile_id: "workstation-04",
  gpu_model: "NVIDIA RTX PRO 6000",
  gpu_count: 1,
  vram_bytes: 96 * 1024 ** 3,
  cpu_model: "Xeon",
  cpu_cores: 24,
  ram_bytes: 128 * 1024 ** 3,
  safe_parallel_slots: 4,
  egress_policy: "deny-all",
  sandbox_runtime: "firejail",
  measurement_pending: false,
};

describe("buildOperationalProjection", () => {
  it("requires a verified connection before exposing operational detail", () => {
    const projection = buildOperationalProjection({ verified: false, hardware: null, modelServing: null, qualification: null });
    expect(projection.state).toBe("connection_required");
    expect(projection.items.every((item) => item.value === "Connection required")).toBe(true);
  });

  it("reports real hardware, sandbox, catalog, and router values", () => {
    const projection = buildOperationalProjection({
      verified: true,
      hardware,
      modelServing: { configured: true, status: "ready", endpoints: [
        { target_id: "a", health: "healthy", readiness: "ready", reason: "" },
        { target_id: "b", health: "healthy", readiness: "ready", reason: "" },
      ] },
      qualification: { configured: true, count: 2, targets: [
        { target_id: "a", status: "qualified", routing_tier: "efficient", measurement_pending: false, reason: null },
        { target_id: "b", status: "qualified", routing_tier: "capable", measurement_pending: false, reason: null },
      ] },
    });
    expect(projection.state).toBe("reported");
    const byLabel = Object.fromEntries(projection.items.map((item) => [item.label, item.value]));
    expect(byLabel["Hardware and capacity"]).toContain("NVIDIA RTX PRO 6000");
    expect(byLabel["Hardware and capacity"]).toContain("96.0 GB VRAM");
    expect(byLabel["Sandbox health"]).toBe("firejail / egress deny-all");
    expect(byLabel["Qualified capability catalog"]).toBe("2 of 2 targets qualified");
    expect(byLabel["Router decision history"]).toBe("Ready / 2 of 2 endpoint(s)");
  });

  it("keeps missing values as Not supplied instead of guessing", () => {
    const projection = buildOperationalProjection({ verified: true, hardware: null, modelServing: null, qualification: null });
    expect(projection.state).toBe("reported");
    expect(projection.items.every((item) => item.value === "Not supplied")).toBe(true);
  });
});

describe("formatVram", () => {
  it("returns null for missing or zero capacity", () => {
    expect(formatVram(null)).toBeNull();
    expect(formatVram(0)).toBeNull();
  });
});
