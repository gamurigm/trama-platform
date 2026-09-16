import type { NavigationAction, NavigationState } from "./model";

export const initialNavigation: NavigationState = {
  screen: "dashboard",
  selectedIndex: 0,
  overlay: "none",
  filter: "",
};

function moveSelection(state: NavigationState, direction: 1 | -1, itemCount: number): NavigationState {
  if (itemCount <= 0) {
    return { ...state, selectedIndex: 0, selectedId: undefined };
  }

  return {
    ...state,
    selectedIndex: (state.selectedIndex + direction + itemCount) % itemCount,
    selectedId: undefined,
  };
}

export function reduceNavigation(state: NavigationState, action: NavigationAction): NavigationState {
  switch (action.type) {
    case "key":
      if (action.key === "j" || action.key === "ArrowDown") return moveSelection(state, 1, action.itemCount);
      if (action.key === "k" || action.key === "ArrowUp") return moveSelection(state, -1, action.itemCount);
      if (action.key === "/") return { ...state, overlay: "palette" };
      if (action.key === "?") return { ...state, overlay: "help" };
      if (action.key === "p") return { ...state, overlay: "project-picker" };
      if (action.key === "f") return { ...state, filter: "" };
      return state;
    case "open-screen":
      return {
        ...state,
        screen: action.screen,
        selectedIndex: 0,
        selectedId: undefined,
        filter: "",
        overlay: "none",
      };
    case "select-id":
      return { ...state, selectedIndex: Math.max(0, action.index), selectedId: action.id };
    case "open-overlay":
      return { ...state, overlay: action.overlay };
    case "close-overlay":
      return { ...state, overlay: "none" };
    case "set-project":
      return { ...state, projectId: action.projectId, selectedIndex: 0, selectedId: undefined };
    case "set-filter":
      return { ...state, filter: action.filter, selectedIndex: 0, selectedId: undefined };
    case "set-notice":
      return { ...state, notice: action.notice };
    case "clear-notice":
      return { ...state, notice: undefined };
  }
}
