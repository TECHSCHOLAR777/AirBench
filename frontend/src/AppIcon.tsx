export type AppIconName =
  | "airbench"
  | "archive"
  | "attachment"
  | "audit"
  | "chevron-down"
  | "display"
  | "document"
  | "history"
  | "home"
  | "node"
  | "plus"
  | "review"
  | "route"
  | "shield"
  | "sliders"
  | "tasks";

interface AppIconProps {
  name: AppIconName;
  size?: number;
}

export function AppIcon({ name, size = 18 }: AppIconProps) {
  const common = {
    fill: "none",
    height: size,
    stroke: "currentColor",
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    strokeWidth: 1.7,
    viewBox: "0 0 24 24",
    width: size,
  };

  switch (name) {
    case "airbench":
      return <svg aria-hidden="true" {...common}><path d="M5.5 18.5 10.7 5.5h2.6l5.2 13" /><path d="M8 13.1h8" /><path d="m4.4 18.5 1.9-4.8m11.4 0 1.9 4.8" /></svg>;
    case "archive":
      return <svg aria-hidden="true" {...common}><path d="M4 7.5h16v11H4z" /><path d="M3 4h18v3.5H3zM9 12h6" /></svg>;
    case "attachment":
      return <svg aria-hidden="true" {...common}><path d="m8.2 12.8 6.1-6.1a3.1 3.1 0 0 1 4.4 4.4l-7.9 7.9a4.7 4.7 0 0 1-6.6-6.6l7.3-7.3" /></svg>;
    case "audit":
      return <svg aria-hidden="true" {...common}><path d="M6 3.5h9l3 3V20.5H6z" /><path d="M15 3.5v3h3M9 11h6M9 15h6" /></svg>;
    case "chevron-down":
      return <svg aria-hidden="true" {...common}><path d="m7.5 9.5 4.5 4.5 4.5-4.5" /></svg>;
    case "display":
      return <svg aria-hidden="true" {...common}><rect x="3.5" y="4.5" width="17" height="12" rx="2" /><path d="M8.5 20h7M12 16.5V20" /></svg>;
    case "document":
      return <svg aria-hidden="true" {...common}><path d="M6 3.5h8.5L18 7v13.5H6z" /><path d="M14.5 3.5V7H18M9 11h6M9 15h6" /></svg>;
    case "history":
      return <svg aria-hidden="true" {...common}><path d="M4.5 12a7.5 7.5 0 1 0 2.2-5.3L4.5 9" /><path d="M4.5 4.5V9H9M12 8v4l2.8 1.8" /></svg>;
    case "home":
      return <svg aria-hidden="true" {...common}><path d="m3.5 10 8.5-6.5 8.5 6.5v9.5H14v-5h-4v5H3.5z" /></svg>;
    case "node":
      return <svg aria-hidden="true" {...common}><rect x="4" y="4" width="16" height="6" rx="1.5" /><rect x="4" y="14" width="16" height="6" rx="1.5" /><path d="M7 7h.01M7 17h.01M10 7h5M10 17h5" /></svg>;
    case "plus":
      return <svg aria-hidden="true" {...common}><path d="M12 5v14M5 12h14" /></svg>;
    case "review":
      return <svg aria-hidden="true" {...common}><path d="M5 4.5h14v15H5z" /><path d="m8 12 2.2 2.2L16 8.5" /></svg>;
    case "route":
      return <svg aria-hidden="true" {...common}><path d="M5 6.5h5.5a2.5 2.5 0 0 1 0 5H9a2.5 2.5 0 0 0 0 5h10" /><path d="m16 13.5 3 3-3 3M8 3.5 5 6.5l3 3" /></svg>;
    case "shield":
      return <svg aria-hidden="true" {...common}><path d="M12 3.5 19 6v5.5c0 4.2-2.8 7.2-7 9-4.2-1.8-7-4.8-7-9V6z" /><path d="m8.8 12 2.1 2.1 4.3-4.3" /></svg>;
    case "sliders":
      return <svg aria-hidden="true" {...common}><path d="M4 7h16M4 17h16M8 7v0M16 17v0" /><circle cx="8" cy="7" r="2" /><circle cx="16" cy="17" r="2" /></svg>;
    case "tasks":
      return <svg aria-hidden="true" {...common}><path d="M5 5.5h14v13H5z" /><path d="m8 10 1.6 1.6L12 8.8M14 10h2M8 15l1.6 1.6 2.4-2.8M14 15h2" /></svg>;
  }
}
