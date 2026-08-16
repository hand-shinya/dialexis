// ローカル実サイト相当E2Eランナー。
// shellのバックグラウンド分割に依存せず、UvicornをNodeの子プロセスとして起動し、
// 同じ実行空間からChromiumテストへBASEを渡す。
const path = require("path");
const { spawn } = require("child_process");

const ROOT = path.resolve(__dirname, "../..");
const SCRIPT = process.argv[2];
const PORT = Number(process.env.DX_PORT || 8815);
const BASE = `http://127.0.0.1:${PORT}`;
const PYTHON = process.env.DX_PYTHON || path.join(ROOT, ".venv/bin/python");

if (!SCRIPT) {
  console.error("usage: node tests/e2e/run_local.js tests/e2e/<test>.e2e.js");
  process.exit(2);
}

function delay(ms) { return new Promise(resolve => setTimeout(resolve, ms)); }
async function waitReady() {
  for (let i = 0; i < 80; i++) {
    try {
      const r = await fetch(`${BASE}/healthz`);
      if (r.ok) return;
    } catch (_) { /* startup window */ }
    await delay(150);
  }
  throw new Error("local server did not become ready");
}
function runNode(file) {
  return new Promise((resolve, reject) => {
    const p = spawn(process.execPath, [path.resolve(ROOT, file), BASE], { cwd: ROOT, stdio: "inherit", env: process.env });
    p.on("error", reject);
    p.on("exit", (code, signal) => resolve(code == null ? 1 : code || (signal ? 1 : 0)));
  });
}

(async () => {
  const server = spawn(PYTHON, ["-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", String(PORT)], {
    cwd: ROOT,
    env: { ...process.env, DIALEXIS_DB: process.env.DIALEXIS_DB || `/tmp/dx-e2e-${PORT}.db` },
    stdio: ["ignore", "pipe", "pipe"],
  });
  let log = "";
  server.stderr.on("data", b => { log += String(b); });
  try {
    await waitReady();
    const code = await runNode(SCRIPT);
    process.exitCode = code;
  } catch (e) {
    console.error("local E2E runner:", e.message);
    if (log) console.error(log.slice(-4000));
    process.exitCode = 1;
  } finally {
    server.kill("SIGTERM");
    await delay(150);
    if (!server.killed) server.kill("SIGKILL");
  }
})().catch(e => { console.error(e); process.exitCode = 1; });
