import { expect, test } from "bun:test";
import { testRender } from "@opentui/react/test-utils";
import { act } from "react";

test("renders TRAMA in the OpenTUI test renderer", async () => {
  const setup = await testRender(<text>TRAMA</text>, { width: 20, height: 5 });

  await act(async () => {
    await setup.renderOnce();
  });
  expect(setup.captureCharFrame()).toContain("TRAMA");
  setup.renderer.destroy();
});
