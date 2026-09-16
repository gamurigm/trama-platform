import { expect, test } from "bun:test";
import { initialNavigation, reduceNavigation } from "./reducer";

test("moves with j and wraps at the end", () => {
  const next = reduceNavigation(
    { ...initialNavigation, selectedIndex: 2 },
    { type: "key", key: "j", itemCount: 3 },
  );

  expect(next.selectedIndex).toBe(0);
});

test("keeps project context but clears screen-local selection", () => {
  const next = reduceNavigation(
    { ...initialNavigation, projectId: "demo", selectedId: "task-1" },
    { type: "open-screen", screen: "events" },
  );

  expect(next).toMatchObject({
    screen: "events",
    projectId: "demo",
    selectedId: undefined,
  });
});

test("opens and closes the command palette", () => {
  const opened = reduceNavigation(initialNavigation, {
    type: "open-overlay",
    overlay: "palette",
  });
  const closed = reduceNavigation(opened, { type: "close-overlay" });

  expect(opened.overlay).toBe("palette");
  expect(closed.overlay).toBe("none");
});
