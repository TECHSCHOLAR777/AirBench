import { describe, expect, it } from "vitest";
import { classifyIntakeFailure, intakeStateFromManifest, intakeStatusCopy } from "./intakeState";

describe("File Intake presentation state", () => {
  it("recognizes processing manifests without treating them as ready", () => {
    expect(intakeStateFromManifest({ ocr_status: "running", vision_status: "completed" })).toBe("processing");
    expect(intakeStateFromManifest({ ocr_status: "completed", vision_status: "not_applicable" })).toBe("ready");
  });

  it("maps Node rejection categories to safe user-facing states", () => {
    expect(classifyIntakeFailure("The File Intake Layer returned HTTP 415.")).toBe("unsupported");
    expect(classifyIntakeFailure("The selected file is larger than the query-upload limit.")).toBe("oversized");
    expect(classifyIntakeFailure("The Node returned intake clearance above the approved profile clearance.")).toBe("clearance_mismatch");
    expect(classifyIntakeFailure("The File Intake Layer returned HTTP 400.")).toBe("rejected");
  });

  it("preserves accepted-manifest context when preview work is incomplete", () => {
    expect(classifyIntakeFailure(new Error("The approved Node preview request failed."), true)).toBe("partial");
    expect(intakeStatusCopy("partial").retryable).toBe(true);
    expect(intakeStatusCopy("clearance_mismatch").retryable).toBe(false);
  });
});
