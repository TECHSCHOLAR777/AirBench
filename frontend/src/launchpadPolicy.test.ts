import { describe, expect, it } from "vitest";
import { mayLaunchFromShortcut, sourceStatus, unavailableRoutingPreference } from "./launchpadPolicy";

describe("launchpad presentation policy", () => {
  it("does not allow a keyboard shortcut to bypass launch readiness", () => {
    expect(mayLaunchFromShortcut({ key: "Enter", ctrlKey: true, metaKey: false }, false)).toBe(false);
    expect(mayLaunchFromShortcut({ key: "Enter", ctrlKey: false, metaKey: true }, true)).toBe(true);
    expect(mayLaunchFromShortcut({ key: "x", ctrlKey: true, metaKey: false }, true)).toBe(false);
  });

  it("reports File Intake state without treating a selected file as ready", () => {
    expect(sourceStatus(false, "idle")).toBe("Add sources");
    expect(sourceStatus(true, "idle")).toBe("1 source added");
    expect(sourceStatus(true, "uploading")).toBe("Preparing source");
    expect(sourceStatus(true, "failed")).toBe("Source needs attention");
    expect(sourceStatus(true, "ready")).toBe("1 source ready");
  });

  it("keeps manual model preference unavailable without a Node-qualified catalog", () => {
    expect(unavailableRoutingPreference(false)).toEqual({
      available: false,
      status: "Connect a verified Node first",
      explanation: expect.stringContaining("advisory only"),
    });
    expect(unavailableRoutingPreference(true)).toMatchObject({
      available: false,
      status: "No qualified catalog supplied by this Node",
    });
  });
});
