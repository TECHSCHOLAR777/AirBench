import { describe, expect, it } from "vitest";
import { activityWindow } from "./activityWindow";

describe("activity DOM window", () => {
  it("keeps the newest records visible and reports older records without mutation", () => {
    const records = [1, 2, 3, 4, 5];
    const window = activityWindow(records, 2);

    expect(window).toEqual({ visible: [4, 5], hiddenCount: 3, totalCount: 5 });
    expect(records).toEqual([1, 2, 3, 4, 5]);
  });

  it("does not hide a short task", () => {
    expect(activityWindow(["plan", "work"], 100)).toEqual({
      visible: ["plan", "work"],
      hiddenCount: 0,
      totalCount: 2,
    });
  });

  it("falls back to the safe default for an invalid limit", () => {
    const window = activityWindow(Array.from({ length: 101 }, (_, index) => index), 0);
    expect(window.visible).toHaveLength(100);
    expect(window.visible[0]).toBe(1);
    expect(window.hiddenCount).toBe(1);
  });
});
