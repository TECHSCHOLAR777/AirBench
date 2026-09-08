import { describe, expect, it } from "vitest";
import { buildShellCommands, filterShellCommands, shellShortcut } from "./commandPalette";

describe("local command palette", () => {
  it("offers only local navigation and presentation commands", () => {
    const commands = buildShellCommands(true);

    expect(commands.map((command) => command.id)).toEqual([
      "new_task",
      "current_task",
      "node_settings",
      "display_preferences",
    ]);
    expect(commands.some((command) => /approve|cancel|download|route|model/i.test(command.id))).toBe(false);
  });

  it("marks the current-task command unavailable without an authoritative task projection", () => {
    const currentTask = buildShellCommands(false).find((command) => command.id === "current_task");

    expect(currentTask).toMatchObject({ disabled: true, description: expect.stringContaining("No active task") });
  });

  it("filters commands by title, description, and local keywords", () => {
    const commands = buildShellCommands(true);

    expect(filterShellCommands(commands, "theme").map((command) => command.id)).toEqual(["display_preferences"]);
    expect(filterShellCommands(commands, "node profile").map((command) => command.id)).toEqual(["node_settings"]);
    expect(filterShellCommands(commands, "missing")).toEqual([]);
  });

  it("recognizes command and new-task shortcuts without accepting Alt or composition events", () => {
    expect(shellShortcut({ key: "K", ctrlKey: true, metaKey: false })).toBe("open_command_palette");
    expect(shellShortcut({ key: "n", ctrlKey: false, metaKey: true })).toBe("new_task");
    expect(shellShortcut({ key: "k", ctrlKey: true, metaKey: false, altKey: true })).toBeNull();
    expect(shellShortcut({ key: "n", ctrlKey: true, metaKey: false, isComposing: true })).toBeNull();
  });
});
