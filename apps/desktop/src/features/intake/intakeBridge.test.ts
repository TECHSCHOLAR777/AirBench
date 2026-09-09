import { describe, expect, it } from "vitest";
import { validateDownloadReceipt, type DownloadReceipt } from "./intakeBridge";

const receipt: DownloadReceipt = {
  artifact_id: "artifact-1",
  destination: "C:/Users/operator/approval-note.pdf",
  content_hash: `sha256:${"a".repeat(64)}`,
  ledger_event_ref: "ledger-download-1",
  byte_size: 128,
};

describe("download receipt boundary", () => {
  it("accepts a complete receipt for the requested artifact", () => {
    expect(validateDownloadReceipt(receipt, "artifact-1")).toBe(receipt);
  });

  it("rejects a receipt for a different artifact or with an invalid hash", () => {
    expect(() => validateDownloadReceipt({ ...receipt, artifact_id: "artifact-2" }, "artifact-1")).toThrow("does not match");
    expect(() => validateDownloadReceipt({ ...receipt, content_hash: "sha256:not-a-digest" }, "artifact-1")).toThrow("valid content hash");
  });

  it("rejects incomplete local save or ledger information", () => {
    expect(() => validateDownloadReceipt({ ...receipt, destination: "" }, "artifact-1")).toThrow("incomplete");
    expect(() => validateDownloadReceipt({ ...receipt, byte_size: -1 }, "artifact-1")).toThrow("incomplete");
    expect(() => validateDownloadReceipt({ ...receipt, ledger_event_ref: "" }, "artifact-1")).toThrow("incomplete");
  });
});
