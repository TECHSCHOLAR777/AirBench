import type { AppIconName } from "../../components/AppIcon";

export type ShellCommandId = "new_task" | "current_task" | "node_settings" | "display_preferences";

export interface ShellCommand {
  id: ShellCommandId;
  title: string;
  description: string;
  icon: AppIconName;
  keywords: string[];
  shortcut?: string;
  disabled?: boolean;
}

export interface ShellShortcutInput {
  key: string;
  ctrlKey: boolean;
  metaKey: boolean;
  altKey?: boolean;
  isComposing?: boolean;
}

export type ShellShortcut = "open_command_palette" | "new_task" | null;

export function buildShellCommands(hasCurrentTask: boolean): ShellCommand[] {
  return [
    {
      id: "new_task",
      title: "New task",
      description: "Open a fresh outcome brief and focus the task field.",
      icon: "plus",
      keywords: ["home", "launch", "brief", "start"],
      shortcut: "Ctrl N",
    },
    {
      id: "current_task",
      title: "Current task",
      description: hasCurrentTask ? "Open the current server-authoritative task workspace." : "No active task is available in this desktop session.",
      icon: "tasks",
      keywords: ["work", "trace", "activity", "live"],
      disabled: !hasCurrentTask,
    },
    {
      id: "node_settings",
      title: "Node and settings",
      description: "Inspect approved Node profiles and local connection state.",
      icon: "node",
      keywords: ["connect", "profile", "health", "administration"],
    },
    {
      id: "display_preferences",
      title: "Display preferences",
      description: "Adjust local theme, density, and contrast preferences.",
      icon: "display",
      keywords: ["theme", "contrast", "density", "appearance"],
    },
  ];
}

export function filterShellCommands(commands: ShellCommand[], query: string): ShellCommand[] {
  const terms = query.trim().toLocaleLowerCase().split(/\s+/).filter(Boolean);
  if (terms.length === 0) return commands;
  return commands.filter((command) => {
    const searchable = [command.title, command.description, ...command.keywords].join(" ").toLocaleLowerCase();
    return terms.every((term) => searchable.includes(term));
  });
}

export function shellShortcut(input: ShellShortcutInput): ShellShortcut {
  if (input.isComposing || input.altKey || !(input.ctrlKey || input.metaKey)) return null;
  const key = input.key.toLocaleLowerCase();
  if (key === "k") return "open_command_palette";
  if (key === "n") return "new_task";
  return null;
}
