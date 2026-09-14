import { describe, expect, it } from "vitest";
import { classifyIntakeFailure, intakeConfidenceCopy, intakeStateFromManifest, intakeStatusCopy, isIntakeConfidenceBand } from "./intakeState";

describe("File Intake presentation state", () => {
  it("recognizes processing manifests without treating them as ready", () => {
    expect(intakeStateFromManifest({ ocr_status: "running", vision_status: "completed" })).toBe("processing");
    expect(intakeStateFromManifest({ ocr_status: "completed", vision_status: "not_applicable" })).toBe("ready");
    expect(intakeStateFromManifest({ ocr_status: "failed", vision_status: "completed" })).toBe("partial");
    expect(intakeStateFromManifest({ ocr_status: "unknown", vision_status: "completed" })).toBe("partial");
    expect(intakeStatusCopy("processing").retryable).toBe(false);
    expect(intakeStatusCopy("partial").retryable).toBe(false);
  });

  it("maps Node rejection categories to safe user-facing states", () => {
    expect(classifyIntakeFailure("The File Intake Layer returned HTTP 415.")).toBe("unsupported");
    expect(classifyIntakeFailure("The selected file is larger than the query-upload limit.")).toBe("oversized");
    expect(classifyIntakeFailure("The Node returned intake clearance above the approved profile clearance.")).toBe("clearance_mismatch");
    expect(classifyIntakeFailure("The File Intake Layer returned HTTP 400.")).toBe("rejected");
  });

  it("preserves accepted-manifest context when preview work is incomplete", () => {
    expect(classifyIntakeFailure(new Error("The approved Node preview request failed."), true)).toBe("partial");
    expect(intakeStatusCopy("partial").retryable).toBe(false);
    expect(intakeStatusCopy("partial").recovery).toEqual({
      preserved: "The accepted manifest and source provenance remain available; launch remains paused.",
      retry: "Do not replace the accepted manifest with a local or unverified preview.",
      nextAction: "Wait for a Node-authorized preview result or remove the source.",
    });
    expect(intakeStatusCopy("clearance_mismatch").retryable).toBe(false);
    expect(intakeStatusCopy("clearance_mismatch").recovery.nextAction).toContain("required clearance");
  });

  it("maps extraction confidence bands to review guidance", () => {
    expect(intakeConfidenceCopy("green").reviewRecommended).toBe(false);
    expect(intakeConfidenceCopy("amber").reviewRecommended).toBe(true);
    expect(intakeConfidenceCopy("red").reviewRecommended).toBe(true);
    expect(intakeConfidenceCopy("red").detail).toContain("below 65%");
    expect(isIntakeConfidenceBand("red")).toBe(true);
    expect(isIntakeConfidenceBand("blue")).toBe(false);
    expect(isIntakeConfidenceBand(undefined)).toBe(false);
  });
});
