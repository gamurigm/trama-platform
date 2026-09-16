import { createCliRenderer } from "@opentui/core";
import { createRoot } from "@opentui/react";
import { App } from "./App";
import { TramaApiClient } from "./api/client";

const client = new TramaApiClient(process.env.TRAMA_API_URL ?? "http://127.0.0.1:8090");
const renderer = await createCliRenderer();
createRoot(renderer).render(<App client={client} />);
