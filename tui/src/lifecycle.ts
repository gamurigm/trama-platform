/** Operates only the Python supervisor's registered local API process. */
export async function restartManagedApi(pythonExecutable: string, appRoot: string): Promise<void> {
  for (const action of ["down", "up"]) {
    const process = Bun.spawn([pythonExecutable, "-m", "trama_platform", action, "--json"], {
      cwd: appRoot, env: { ...Bun.env, TRAMA_APP_ROOT: appRoot }, stdin: "ignore", stdout: "pipe", stderr: "ignore",
    });
    const output = await new Response(process.stdout).text();
    const exit = await process.exited;
    let result: { status?: string } = {};
    try { result = JSON.parse(output); } catch {}
    if (exit !== 0 || !result.status || result.status === "foreign_process") {
      throw new Error("No se pudo reiniciar la API administrada por TRAMA. Revisa trama doctor.");
    }
  }
}
