import { describe, expect, it } from "vitest";
import { defaultPresentationPreferences, parsePresentationPreferences } from "./presentationPreferences";

describe("presentation preferences", () => {
  it("uses the dark sovereign shell by default", () => {
    expect(parsePresentationPreferences(null)).toEqual(defaultPresentationPreferences);
  });

  it("accepts only the local, presentation-only preference values", () => {
    expect(parsePresentationPreferences(JSON.stringify({
      theme: "ledger",
      density: "compact",
      highContrast: true,
      taskState: "completed",
    }))).toEqual({ theme: "ledger", density: "compact", highContrast: true });
  });

  it("fails closed to display defaults for malformed or unsupported values", () => {
    expect(parsePresentationPreferences("not-json")).toEqual(defaultPresentationPreferences);
    expect(parsePresentationPreferences(JSON.stringify({ theme: "external", density: "dense", highContrast: "yes" }))).toEqual(defaultPresentationPreferences);
  });
});
