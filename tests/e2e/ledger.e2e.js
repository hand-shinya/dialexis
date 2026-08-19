// Reusable-ledger E2E: create one ledger, reuse it from two projects, and
// verify the browser exposes the relationship without copying the ledger.
const { chromium } = require("playwright-core");
const EXE = process.env.DX_CHROMIUM || "/home/handa/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome";
const B = process.argv[2] || "http://127.0.0.1:8815";

(async () => {
  const browser = await chromium.launch({ executablePath: EXE, headless: true });
  const page = await browser.newPage();
  const R = [];
  const ok = (name, condition, detail) => { R.push(condition); console.log(`${condition ? "PASS" : "FAIL"}  ${name}${detail ? "  — " + detail : ""}`); };

  await page.goto(`${B}/desk?lang=ja`, { waitUntil: "domcontentloaded" });
  const ids = await page.evaluate(async () => {
    const l = await fetch("/api/ledgers", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title: "E2E共有台帳", subject: "哲学", central_question: "同じ台帳を複数研究で使えるか" }) }).then(r => r.json());
    const lid = l.ledger.id;
    const e = await fetch(`/api/ledgers/${lid}/entries`, { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ kind: "term", title: "共有する記録", evidence_level: "candidate" }) }).then(r => r.json());
    const p1 = await fetch("/api/projects", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title: "E2E研究A" }) }).then(r => r.json());
    const p2 = await fetch("/api/projects", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title: "E2E研究B" }) }).then(r => r.json());
    for (const [pid, role] of [[p1.id, "evidence"], [p2.id, "background"]]) {
      await fetch(`/api/projects/${pid}/ledgers`, { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ledger_id: lid, role }) });
      await fetch(`/api/projects/${pid}/ledger-entries`, { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ entry_id: e.id, relation: role }) });
    }
    return { lid, eid: e.id, p1: p1.id, p2: p2.id };
  });

  await page.goto(`${B}/ledger/${ids.lid}?lang=ja`, { waitUntil: "networkidle" });
  const ledgerText = await page.locator("#ledger-detail").textContent();
  ok("台帳画面が開く", /E2E共有台帳/.test(ledgerText));
  ok("台帳が複数プロジェクト利用中と表示される", /利用中のプロジェクト/.test(ledgerText) && /E2E研究A/.test(ledgerText) && /E2E研究B/.test(ledgerText));
  ok("台帳内の記録からプロジェクト利用へ進める", /共有する記録/.test(ledgerText) && /この記録をプロジェクトで使う/.test(ledgerText));

  await page.goto(`${B}/project/${ids.p1}?lang=ja`, { waitUntil: "networkidle" });
  const projectText = await page.locator("#project-ledgers").textContent();
  ok("プロジェクト側に参照台帳が表示される", /参照中の研究台帳/.test(projectText) && /E2E共有台帳/.test(projectText));
  ok("プロジェクト側に台帳を変更しない説明がある", /台帳本体を変更しません/.test(projectText));

  const pass = R.filter(Boolean).length;
  console.log(`\n${pass}/${R.length} PASS`);
  await browser.close();
  process.exit(pass === R.length ? 0 : 1);
})().catch(e => { console.error("ERR", e); process.exit(2); });
