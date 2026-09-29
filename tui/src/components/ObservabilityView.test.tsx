import { act, useState } from "react";
import { expect, test } from "bun:test";
import { testRender } from "@opentui/react/test-utils";
import type { ConsoleState, FormSpec } from "../console";
import { ConsoleContext } from "../console";
import type { TramaApiClient } from "../api/client";
import { ObservabilityView } from "./ObservabilityView";
import { FormFields } from "./FormFields";

test("keeps the activity view mounted and applies its filter after form confirmation", async () => {
  const requests: Record<string, string | undefined>[] = [];
  const client = { getLogs: async (filters: Record<string, string | undefined>) => { requests.push(filters); return []; } };
  function Harness() {
    const [form, setForm] = useState<FormSpec>();
    const [version, setVersion] = useState(0);
    const state: ConsoleState = {
      client: client as unknown as TramaApiClient, version, locked: Boolean(form), setProject: () => {},
      form: setForm, inspect: () => {}, run: async (action) => { await action(); }, refresh: () => setVersion((n) => n + 1),
    };
    return <ConsoleContext.Provider value={state}>
      <box flexDirection="column" width="100%" height="100%">
        <box flexGrow={1} visible={!form}><ObservabilityView /></box>
        {form && <box flexGrow={1}><FormFields spec={form} onClose={() => setForm(undefined)} onSuccess={() => {
          setForm(undefined); setVersion((n) => n + 1);
        }} /></box>}
      </box>
    </ConsoleContext.Provider>;
  }
  const setup = await testRender(<Harness />, { width: 84, height: 24 });
  await act(async () => { await setup.renderOnce(); });
  await act(async () => { setup.mockInput.pressKey("f"); await setup.renderOnce(); });
  for (let i = 0; i < 3; i++) await act(async () => { setup.mockInput.pressTab(); await setup.renderOnce(); });
  await act(async () => { await setup.mockInput.typeText("task-42"); await setup.renderOnce(); });
  for (let i = 0; i < 2; i++) await act(async () => { setup.mockInput.pressTab(); await setup.renderOnce(); });
  await act(async () => { await setup.waitFor(() => setup.captureCharFrame().includes("REVISAR Y CONFIRMAR")); });
  expect(setup.captureCharFrame()).toContain("REVISAR Y CONFIRMAR");
  await act(async () => { setup.mockInput.pressTab(); });
  await setup.waitFor(() => requests.some((item) => item.task_id === "task-42"));
  expect(requests.at(-1)?.task_id).toBe("task-42");
  await act(async () => { setup.renderer.destroy(); });
});

test("masks a secret in every form state and submits only after explicit review", async () => {
  const secret = "DO-NOT-DISPLAY-9014";
  let submitted: Record<string, string> | undefined;
  const spec: FormSpec = { title: "Credencial", description: "Prueba de secreto", fields: [
    { name: "token", label: "Token API", required: true, secret: true },
  ], onSubmit: async (values) => { submitted = values; } };
  const setup = await testRender(<FormFields spec={spec} onClose={() => {}} onSuccess={() => {}} />, { width: 78, height: 18 });
  await act(async () => { await setup.renderOnce(); });
  await act(async () => { await setup.mockInput.typeText(secret); await setup.renderOnce(); });
  expect(setup.captureCharFrame()).not.toContain(secret);
  await act(async () => { setup.mockInput.pressTab(); });
  await setup.waitFor(() => setup.captureCharFrame().includes("REVISAR Y CONFIRMAR"));
  expect(setup.captureCharFrame()).toContain("REVISAR Y CONFIRMAR");
  expect(setup.captureCharFrame()).toContain("••••••••");
  expect(submitted).toBeUndefined();
  expect(setup.captureCharFrame()).not.toContain(secret);
  await act(async () => { setup.mockInput.pressTab(); await setup.waitFor(() => submitted !== undefined); });
  expect(submitted?.token).toBe(secret);
  expect(setup.captureCharFrame()).not.toContain(secret);
  await act(async () => { setup.renderer.destroy(); });
});
