import { expect, multiremotebrowser } from "@wdio/globals";

describe("AirBench multiremote boundary", () => {
  it("keeps two local app instances independently addressable", async () => {
    await expect(multiremotebrowser.operatorA.$("h1")).toHaveText("What should AirBench complete?");
    await expect(multiremotebrowser.operatorB.$("h1")).toHaveText("What should AirBench complete?");
    const windowsA = await multiremotebrowser.operatorA.tauri.listWindows();
    const windowsB = await multiremotebrowser.operatorB.tauri.listWindows();
    expect(windowsA).toContain("main");
    expect(windowsB).toContain("main");
  });
});
