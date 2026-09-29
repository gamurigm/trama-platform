import { useState } from "react";
import { useKeyboard } from "@opentui/react";
import { useConsole, useLoad } from "../console";
import { restartManagedApi } from "../lifecycle";
import { statusColor, statusLabel, theme } from "../theme";
import { Action, Detail, Hint, RecordList } from "./Primitives";

const labels: Record<string, string> = {
  environment: "Entorno", organization_id: "Organización", coordination_backend: "Coordinador",
  api_host: "API · Dirección", api_port: "API · Puerto", api_url: "API · URL", state_dir: "Datos · Directorio",
  api_token: "API · Token", gateway_token: "Gateway · Token", utopia_token: "Utopia · Token",
  cccc_executable: "CCCC · Ejecutable", cccc_timeout_seconds: "CCCC · Tiempo límite (s)",
  queue_capacity: "Cola · Capacidad", max_concurrency: "Cola · Concurrencia", dispatch_timeout_seconds: "Tareas · Tiempo límite (s)",
  hermes_executable: "Hermes · Ejecutable", hermes_config_path: "Hermes · Archivo de configuración",
  semantica_kg_path: "Semantica · Ruta del grafo", utopia_url: "Utopia · URL", utopia_kb_id: "Utopia · ID de base",
  colibri_url: "Colibri · URL", colibri_model: "Colibri · Modelo", gateway_url: "Gateway · URL",
  nats_url: "NATS · URL", nats_stream: "NATS · Stream", nats_subject: "NATS · Subject", nats_durable: "NATS · Consumidor",
};
const sourceLabel = (value?: string) => ({ environment: "variable de entorno", user: "configuración guardada", vault: "Credenciales de Windows", default: "predeterminado" }[value ?? "default"] ?? value);

export function IntegrationsView() {
  const { client, locked, form, run, inspect } = useConsole();
  const [mode, setMode] = useState<"connections" | "settings">("connections");
  const [selected, select] = useState(0);
  const loaded = useLoad(async () => { const [config, connections] = await Promise.all([client.getConfig(), client.getIntegrations()]); return { config, connections }; });
  const data = loaded.data;
  const settings = data?.config.settings ?? [];
  const secrets = data?.config.secrets ?? [];
  const integration = data?.connections.integrations[selected];
  const setting = settings[selected];
  const secret = selected >= settings.length ? secrets[selected - settings.length] : undefined;
  const change = (next: typeof mode) => { setMode(next); select(0); };
  const edit = () => {
    if (mode === "connections") {
      const index = settings.findIndex((s) => s.name.startsWith((integration?.id ?? "") + "_"));
      setMode("settings"); select(Math.max(index, 0)); return;
    }
    if (secret) {
      form({ title: `Guardar ${labels[secret.name] ?? secret.name}`, description: "El valor se guardará en Credenciales de Windows. Nunca se mostrará su contenido.",
        fields: [{ name: "value", label: "Nueva credencial", secret: true, required: true, hint: "Escribe o pega el valor · Ctrl+U limpia · Enter continúa" }],
        onSubmit: async (v) => { await client.setSecret(secret.name, v.value!); if (secret.name === "api_token" && secret.source !== "environment") client.stageToken(v.value!); } });
    } else if (setting && !setting.read_only) {
      form({ title: labels[setting.name] ?? setting.name,
        description: setting.source === "environment" ? "Una variable de entorno tiene prioridad. El valor guardado se aplicará cuando retires esa variable y reinicies TRAMA." : "Guarda el valor; aplica el reinicio si aparece como pendiente.",
        fields: [{ name: "value", label: "Valor", initial: String(setting.value ?? ""), required: true,
          hint: setting.name === "coordination_backend" ? "memory / cccc" : "Las URLs no admiten credenciales: utiliza el campo de token.",
          validate: (v) => typeof setting.value === "number" && (!/^\d+$/.test(v) || +v < 1) ? "Introduce un entero positivo" : undefined }],
        onSubmit: (v) => client.saveConfig({ [setting.name]: typeof setting.value === "number" ? +v.value! : v.value! }) });
    }
  };
  const clear = () => {
    if (mode !== "settings" || (!secret && (!setting || setting.read_only))) return;
    const name = secret?.name ?? setting!.name;
    form({ title: `Borrar valor guardado · ${labels[name] ?? name}`, description: "Se elimina el valor guardado. Si existe una variable de entorno, seguirá teniendo prioridad.", fields: [],
      submitLabel: "Borrar valor", onSubmit: async () => {
        if (secret) { await client.deleteSecret(name); if (name === "api_token" && secret.source !== "environment") client.stageToken(null); }
        else await client.saveConfig({ [name]: null });
      } });
  };
  const check = () => {
    if (mode !== "connections" || !integration) return;
    void run(async () => { const report = await client.checkIntegration(integration.id);
      inspect(`Diagnóstico · ${report.label}`, [statusLabel(report.status), report.detail, `Comprobado: ${report.checked_at}`]); }, "Diagnóstico actualizado");
  };
  const restart = () => form({ title: "Aplicar configuración", description: "Reinicia únicamente la API administrada por TRAMA. Los cambios guardados se aplicarán al nuevo proceso.", fields: [],
    submitLabel: "Reiniciar API", onSubmit: async () => {
      const python = process.env.TRAMA_PYTHON_EXECUTABLE;
      const root = process.env.TRAMA_APP_ROOT;
      if (!python || !root) throw new Error("Abre la consola con trama para reiniciar su API administrada.");
      await restartManagedApi(python, root);
      client.activateStagedToken();
      for (let attempt = 0; attempt < 20; attempt++) {
        try { await client.getStatus(); return; } catch { await new Promise((resolve) => setTimeout(resolve, 500)); }
      }
      throw new Error("La API no respondió después del reinicio. Revisa trama doctor o vuelve a abrir trama.");
    } });
  const hermes = () => form({ title: "Preparar Hermes MCP", description: "Actualiza la entrada trama y la política de aprobación manual. Conserva las demás claves del archivo de Hermes.", fields: [],
    submitLabel: "Guardar entrada MCP", onSubmit: () => client.configureHermes() });
  const daemon = (action: "start" | "stop") => form({ title: `${action === "start" ? "Iniciar" : "Detener"} CCCC`, description: "Cambia el daemon local. El backend activo de TRAMA se configura por separado.", fields: [], onSubmit: () => client.cccc(action) });
  useKeyboard((key) => {
    if (locked) return;
    if (key.name === "tab") { key.preventDefault(); change(mode === "connections" ? "settings" : "connections"); }
    if (key.name === "e") edit(); if (key.name === "x") clear(); if (key.name === "t") check();
    if (key.name === "p") restart();
    if (mode === "connections" && integration?.id === "hermes" && key.name === "h") hermes();
    if (mode === "connections" && integration?.id === "cccc" && key.name === "s") daemon("start");
    if (mode === "connections" && integration?.id === "cccc" && key.name === "d") daemon("stop");
  });
  const rows = mode === "connections" ? (data?.connections.integrations ?? []).map((x) => ({ id: x.id, name: x.label, description: statusLabel(x.status) }))
    : [...settings.map((x) => ({ id: x.name, name: labels[x.name] ?? x.name, description: `${x.read_only ? "Solo lectura · " : ""}${x.value ?? "Sin configurar"}${x.restart_required ? " · pendiente" : ""}` })),
      ...secrets.map((x) => ({ id: x.name, name: labels[x.name] ?? x.name, description: x.configured ? "● Credencial configurada" : "○ Sin credencial" }))];
  return <box flexDirection="column" flexGrow={1} gap={1} minHeight={0}>
    <box flexDirection="row" gap={1} flexWrap="wrap"><Action label={`${mode === "connections" ? "● " : ""}Conexiones`} onPress={() => change("connections")} />
      <Action label={`${mode === "settings" ? "● " : ""}Configuración`} onPress={() => change("settings")} />
      {data?.config.restart_required && <Action label="P Aplicar reinicio" onPress={restart} />}</box>
    <Hint>Tab Cambiar lista · E Editar · T Diagnóstico · X Borrar valor</Hint>
    <RecordList title={mode === "connections" ? "Integraciones" : "Configuración"} rows={rows} selected={selected} onSelect={select}
      onOpen={() => mode === "connections" ? check() : edit()} loading={loaded.loading} error={loaded.error}>
      {mode === "connections" && integration && <>
        <text fg={statusColor(integration.status)}>● {statusLabel(integration.status)}</text>
        <Detail values={[["Diagnóstico", integration.detail], ["Comprobado", integration.checked_at], ["Configurado", integration.configured ? "Sí" : "No"]]} />
        <box flexDirection="row" gap={1}><Action label="T Comprobar" onPress={check} /><Action label="E Configurar" onPress={edit} /></box>
        {integration.id === "hermes" && <Action label="H Preparar MCP" onPress={hermes} />}
        {integration.id === "cccc" && <box flexDirection="row" gap={1}><Action label="S Iniciar daemon" onPress={() => daemon("start")} /><Action label="D Detener" onPress={() => daemon("stop")} /></box>}
        {["hermes", "mcp"].includes(integration.id) && <Detail values={[[integration.id === "mcp" ? "Herramientas ofrecidas por TRAMA" : "Allowlist configurada en Hermes", integration.id === "mcp" ? data?.connections.tools ?? [] : integration.tools]]} />}
      </>}
      {mode === "settings" && (setting || secret) && <>
        <Detail values={[["Parámetro", labels[setting?.name ?? secret!.name]], ["Origen", sourceLabel(setting?.source ?? secret?.source)],
          ["Valor efectivo", secret ? (secret.configured ? "Credencial configurada · valor protegido" : "Sin credencial") : setting?.value],
          ...(setting ? [["Valor del proceso activo", setting.active_value]] as [string, unknown][] : []),
          ["Reinicio", (setting?.restart_required ?? secret?.restart_required) ? "Pendiente de aplicar" : "Sin cambios pendientes"]]} />
        {setting?.read_only ? <Hint>Parámetro de arranque. Se cambia al iniciar TRAMA para mantener estables la API y su base de datos.</Hint>
          : <box flexDirection="row" gap={1}><Action label="E Editar" onPress={edit} /><Action label="X Borrar guardado" onPress={clear} /></box>}
      </>}
    </RecordList>
  </box>;
}
