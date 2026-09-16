import { expect, test } from "bun:test";
import { act } from "react";
import { testRender } from "@opentui/react/test-utils";
import { KeyHints } from "./KeyHints";
import { ConfirmDialog } from "./ConfirmDialog";
import { Panel } from "./Panel";
import { StatusBadge } from "./StatusBadge";

test("renders a titled panel and explicit blocked status", async () => {
  const setup = await testRender(
    <box flexDirection="column">
      <Panel title="Queues" accent="attention"><text>queue depth: 2</text></Panel>
      <StatusBadge state="blocked" label="blocked" />
    </box>,
    { width: 40, height: 8 },
  );

  await act(async () => { await setup.renderOnce(); });
  const frame = setup.captureCharFrame();
  expect(frame).toContain("Queues");
  expect(frame).toContain("! blocked");
  await act(async () => { setup.renderer.destroy(); });
});

test("renders keyboard hints in sentence case", async () => {
  const setup = await testRender(<KeyHints items={[{ key: "Enter", label: "abrir" }]} />, { width: 30, height: 3 });

  await act(async () => { await setup.renderOnce(); });
  expect(setup.captureCharFrame()).toContain("[Enter] abrir");
  await act(async () => { setup.renderer.destroy(); });
});

test("keeps destructive confirmation behind an explicit decision", async () => {
  let confirmed = 0;
  let cancelled = 0;
  const setup = await testRender(
    <ConfirmDialog action="cancel" target="task-1" consequence="Changes the task state" onConfirm={() => { confirmed += 1; }} onCancel={() => { cancelled += 1; }} />,
    { width: 60, height: 10 },
  );
  await act(async () => { await setup.renderOnce(); });
  expect(setup.captureCharFrame()).toContain("Confirmar cancel");
  expect(confirmed).toBe(0);
  expect(cancelled).toBe(0);
  setup.mockInput.pressKey("n");
  await setup.waitFor(() => cancelled === 1);
  expect(confirmed).toBe(0);
  await act(async () => { setup.renderer.destroy(); });
});
