// /desk の作成を、人がふつうにする操作（入力欄で Enter／ボタン）で確かめる（2026-10-14）。
// シミュレーションで、記録したい動機を持つペルソナ10本が /desk に着きながら記録0件だった。
// form が無く、入力欄で Enter を押しても要求0件・画面変化なし。台帳名が空なら黙って何もしなかった。
const { chromium } = require("playwright-core");
const EXE = process.env.DX_CHROMIUM || ((process.env.HOME || "") + "/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome");
const BASE = process.argv[2] || "http://127.0.0.1:8099";
(async () => {
  const b = await chromium.launch({ executablePath: EXE, headless: true });
  const R = []; const ok = (n, c, d) => { R.push(c); console.log(`${c ? "PASS" : "FAIL"}  ${n}${d ? "  — " + d : ""}`); };
  const fresh = async () => {
    const ctx = await b.newContext(); const p = await ctx.newPage(); const posts = [];
    p.on("request", r => { if (r.method() === "POST") posts.push(new URL(r.url()).pathname); });
    await p.goto(`${BASE}/desk?lang=ja`, { waitUntil: "networkidle" });
    return { ctx, p, posts };
  };

  // 1) 台帳名で Enter → POST /api/ledgers が1回
  let { ctx, p, posts } = await fresh();
  await p.fill("#nl-title", "Enterで作る台帳"); await p.press("#nl-title", "Enter");
  await p.waitForTimeout(1500);
  ok("台帳名で Enter を押すと台帳が1件作られる", posts.filter(x => x === "/api/ledgers").length === 1, JSON.stringify(posts));
  await ctx.close();
  // 対象語の欄で Enter でも同じ form が送られる（作成後は台帳のページへ移るので、新しいページで確かめる）
  ({ ctx, p, posts } = await fresh());
  await p.fill("#nl-title", "対象語の欄から"); await p.fill("#nl-subject", "責任"); await p.press("#nl-subject", "Enter");
  await p.waitForTimeout(1500);
  ok("別の欄で Enter を押しても同じ作成が1回起きる", posts.filter(x => x === "/api/ledgers").length === 1, JSON.stringify(posts));
  await ctx.close();

  // 2) ボタンで1回だけ（onclick と submit の二重発火がない）
  ({ ctx, p, posts } = await fresh());
  await p.fill("#nl-title", "ボタンで作る台帳");
  await p.click(".ledger-desk-card button >> nth=0");
  await p.waitForTimeout(1500);
  ok("ボタンを押すと台帳が1件だけ作られる", posts.filter(x => x === "/api/ledgers").length === 1, JSON.stringify(posts));
  await ctx.close();

  // 3) 台帳名が空 → 要求なし・欄に案内（ブラウザ標準の検証）
  ({ ctx, p, posts } = await fresh());
  await p.fill("#nl-subject", "責任"); await p.press("#nl-subject", "Enter");
  await p.waitForTimeout(800);
  const invalid = await p.evaluate(() => !document.getElementById("nl-title").checkValidity());
  ok("台帳名が空なら作らず、台帳名の欄が未入力として示される", posts.length === 0 && invalid, JSON.stringify(posts));
  await ctx.close();

  // 4) プロジェクトも Enter で作られ、そのページへ移る
  ({ ctx, p, posts } = await fresh());
  await p.fill("#np-title", "Enterで作るプロジェクト");
  await Promise.all([p.waitForURL(/\/project\//, { timeout: 8000 }).catch(() => {}), p.press("#np-title", "Enter")]);
  ok("プロジェクト名で Enter を押すとプロジェクトが作られ、そのページへ移る", posts.filter(x => x === "/api/projects").length === 1 && /\/project\//.test(p.url()), p.url());
  await ctx.close();

  const pass = R.filter(Boolean).length; console.log(`\n${pass}/${R.length} PASS`);
  await b.close(); process.exit(pass === R.length ? 0 : 1);
})().catch(e => { console.error("E2E ERROR", e); process.exit(2); });
