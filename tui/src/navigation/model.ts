export type ScreenId =
  | "dashboard"
  | "projects"
  | "tasks"
  | "agents"
  | "queues"
  | "workers"
  | "events"
  | "memory"
  | "health";

export type Overlay = "none" | "palette" | "help" | "project-picker" | "confirm";

export type Notice = {
  kind: "info" | "success" | "warning" | "error";
  message: string;
};

export type NavigationState = {
  screen: ScreenId;
  projectId?: string;
  selectedIndex: number;
  selectedId?: string;
  overlay: Overlay;
  filter: string;
  notice?: Notice;
};

export type NavigationAction =
  | { type: "key"; key: string; itemCount: number }
  | { type: "open-screen"; screen: ScreenId }
  | { type: "select-id"; id: string | undefined; index: number }
  | { type: "open-overlay"; overlay: Exclude<Overlay, "none"> }
  | { type: "close-overlay" }
  | { type: "set-project"; projectId: string | undefined }
  | { type: "set-filter"; filter: string }
  | { type: "set-notice"; notice: Notice }
  | { type: "clear-notice" };
