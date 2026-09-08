export type ConnectionState = "offline" | "not_connected" | "connected";
export type Screen = "home" | "tasks" | "review" | "artifacts" | "history" | "audit" | "node";

export interface NodeStatus {
  state: ConnectionState;
  displayName: string;
  address: string;
  lastCheckedAt: string | null;
  sovereignty: "unknown" | "verified";
}

export interface TaskSummary {
  taskId: string;
  title: string;
  project: string;
  status: "needs_review" | "running" | "completed" | "blocked";
  updatedAt: string;
  artifactType: "approval_note" | "code" | "calculation";
}

export interface AirBenchPresentationState {
  node: NodeStatus;
  recentTasks: TaskSummary[];
  screen: Screen;
}

export const initialPresentationState: AirBenchPresentationState = {
  node: {
    state: "not_connected",
    displayName: "No AirBench Node selected",
    address: "Approved Node profile required",
    lastCheckedAt: null,
    sovereignty: "unknown",
  },
  recentTasks: [],
  screen: "home",
};
