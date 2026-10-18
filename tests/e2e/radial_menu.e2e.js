// 円形メニューと「その場で広げる」（所有者 2026-10-19 提案・プレビュー ?preview=1）を実ブラウザで確かめる。
// 応答は固定値（決定論）。守ること:
//  ①地図の語にマウスを乗せると、その語のまわりに操作が円形に開く（中心に据え直さずに選べる）
//  ②「その他」で外側の輪（サブメニュー）が開く ③項目は単一の受け口 dispatchAction を通る
//  ④「その場で広げる」は中心を変えずに語を足し、足した数とすでに在る数を一言で示す
//  ⑤プレビューでない通常表示は従来の縦の一覧（gMenu）のまま ⑥プレビューでは文字ボタンの列を出さない
//  ⑦プレビューでは地図が注意書きより上にある ⑧Esc で閉じる
const { chromium } = require("playwright-core");
const EXE = process.env.DX_CHROMIUM || ((process.env.HOME || "") + "/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome");
const BASE = process.argv[2] || "http://127.0.0.1:8099";
const ORIGIN = (q) => ({ query: q, lang: "ja", queried_at: "t", word: { query: q }, found: true, resolved_from: null, resolved_to: q,
  suggestions: [], dimensions: [], general_meaning: ["意味"], segment_layers: [], concept_origin: [], originators: [], associated: [],
  relations: { near: [], opposite: [] }, named_after: [], chain: [], senses: [], breadth: [], breadth_count: 0, canon: {}, sources: [],
  confidence: {}, language_bridge: { applied: false }, qid: "Q1" });
const GRAPH = (q) => q === "テスト語" ? { query: q, note: "fx", nodes: [
    { id: "root", label: "テスト語", kind: "word", layer: 1, weight: 3, q: "テスト語" },
    { id: "d1", label: "専門・思想の意味", kind: "domain", layer: 2, weight: 1.4 },
    { id: "a1", label: "子の語", kind: "related", layer: 3, weight: 1, q: "子の語" },
    { id: "a2", label: "別の子", kind: "related", layer: 3, weight: 1, q: "別の子" },
    { id: "p1", label: "ある思想家", kind: "author", layer: 3, weight: 1.5, q: "ある思想家" }],
  edges: [{ from: "root", to: "d1" }, { from: "d1", to: "a1" }, { from: "d1", to: "a2" }, { from: "d1", to: "p1" }] }
  : { query: q, note: "fx", nodes: [   // 「子の語」を中心にした地図: 孫3語＋既に在る1語（別の子）
    { id: "root", label: q, kind: "word", layer: 1, weight: 3, q },
    { id: "g1", label: "孫の語A", kind: "related", layer: 2, weight: 1, q: "孫の語A" },
    { id: "g2", label: "孫の語B", kind: "related", layer: 2, weight: 1, q: "孫の語B" },
    { id: "g3", label: "孫の語C", kind: "related", layer: 2, weight: 1, q: "孫の語C" },
    { id: "g4", label: "別の子", kind: "related", layer: 2, weight: 1, q: "別の子" }],
  edges: [{ from: "root", to: "g1" }, { from: "root", to: "g2" }, { from: "root", to: "g3" }, { from: "root", to: "g4" }] };
(async () => {
  const b = await chromium.launch({ executablePath: EXE, headless: true });
  const R = []; const ok = (n, c, d) => { R.push(c); console.log(`${c ? "PASS" : "FAIL"}  ${n}${d ? "  — " + d : ""}`); };
  const fresh = async () => {
    const ctx = await b.newContext({ viewport: { width: 1366, height: 768 } }); const p = await ctx.newPage();
    await p.route(/\/api\/origin\/graph\?/, r => { const q = new URL(r.request().url()).searchParams.get("q"); r.fulfill({ contentType: "application/json", body: JSON.stringify(GRAPH(q)) }); });
    await p.route(/\/api\/origin\?/, r => { const q = new URL(r.request().url()).searchParams.get("q"); r.fulfill({ contentType: "application/json", body: JSON.stringify(ORIGIN(q)) }); });
    await p.route(/\/api\/(pivot|dimensions|anatomy|collocations|bridge)\?/, r => r.fulfill({ contentType: "application/json", body: JSON.stringify({ data: { input_candidates: [], concept: null }, found: false, dimensions: [], components: [], keyless: [], llm: [] }) }));
    return { ctx, p };
  };
  const nodeAt = (p, label) => p.evaluate((lb) => { const G = window.__dx.G, r = G.cv.getBoundingClientRect();
    const n = G.nodes.find(x => x.label === lb); const s = { x: n.x * G.view.k + G.view.x, y: n.y * G.view.k + G.view.y };
    return { x: r.left + s.x, y: r.top + s.y }; }, label);
  const ready = async (p, pv) => {
    await p.goto(`${BASE}/origin?q=${encodeURIComponent("テスト語")}&lang=ja${pv}`, { waitUntil: "domcontentloaded" });
    await p.waitForFunction(() => window.__dx && window.__dx.G && window.__dx.G.nodes.length >= 5, null, { timeout: 20000 });
    await p.waitForTimeout(2500);   // 力学配置が落ち着くまで
  };

  // ── プレビュー ──
  let { ctx, p } = await fresh();
  await ready(p, "&preview=1");
  const tops = await p.evaluate(() => ({ map: document.getElementById("origin-shell").getBoundingClientRect().top + scrollY,
    note: (document.getElementById("scope-boundary") || { getBoundingClientRect: () => ({ top: 1e9 }) }).getBoundingClientRect().top + scrollY }));
  ok("⑦ プレビューでは地図が注意書きより上にある", tops.map < tops.note, JSON.stringify(tops));
  ok("⑥ プレビューでは文字ボタンの列を出さず、円形メニューの入口を出す", (await p.$$(".tm-chip")).length === 0 && !!(await p.$("#tm-radial")));
  let pos = await nodeAt(p, "子の語");
  await p.mouse.move(pos.x - 40, pos.y - 40); await p.mouse.move(pos.x, pos.y, { steps: 4 });
  const opened = await p.waitForSelector("#radial-menu .rad-in", { timeout: 3000 }).catch(() => null);
  const inner = await p.$$eval("#radial-menu .rad-in .rad-label", xs => xs.map(x => x.textContent)).catch(() => []);
  ok("① 子の語にマウスを乗せると、中心に据え直さずに円形メニューが開く", !!opened && inner.length >= 5 && await p.evaluate(() => window.__dx.G.rootQ) === "テスト語", JSON.stringify(inner));
  await p.click("#radial-menu .rad-more");
  const outer = await p.$$eval("#radial-menu .rad-out", xs => xs.filter(x => x.offsetParent !== null).length);
  ok("② 「その他」で外側の輪（サブメニュー）が開く", outer >= 5, String(outer));
  await p.keyboard.press("Escape"); await p.waitForTimeout(200);
  ok("⑧ Esc で閉じる", !(await p.$("#radial-menu")));
  // ③ 単一の受け口
  pos = await nodeAt(p, "子の語");
  await p.mouse.click(pos.x, pos.y); await p.waitForSelector("#radial-menu", { timeout: 3000 }).catch(() => {});
  await p.click("#radial-menu .rad-in[data-action='meaning']"); await p.waitForTimeout(800);
  const ld = await p.evaluate(() => window.__dx.lastDispatch);
  ok("③ 項目は dispatchAction を通る（surface=radial・対象は押した語）", !!ld && ld.actionId === "meaning" && ld.surface === "radial" && ld.target && ld.target.term === "子の語", JSON.stringify(ld && { a: ld.actionId, s: ld.surface, t: ld.target && ld.target.term }));
  // ④ その場で広げる
  await ready(p, "&preview=1");   // 「意味」で開いたパネルが語の上に重なるので、読み直してから試す
  const n0 = await p.evaluate(() => window.__dx.G.nodes.length);
  pos = await nodeAt(p, "子の語");
  await p.mouse.click(pos.x, pos.y); await p.waitForSelector("#radial-menu", { timeout: 3000 }).catch(() => {});
  await p.click("#radial-menu .rad-in[data-action='expand']");
  await p.waitForFunction((n) => window.__dx.G.nodes.length > n, n0, { timeout: 8000 }).catch(() => {});
  const after = await p.evaluate(() => ({ n: window.__dx.G.nodes.length, root: window.__dx.G.rootQ, grown: window.__dx.G.nodes.filter(x => x.grown).map(x => x.label) }));
  ok("④ その場で広げると、中心を変えずに孫の語が足される（既に在る語は重ねない）", after.n === n0 + 3 && after.root === "テスト語" && after.grown.join() === "孫の語A,孫の語B,孫の語C", JSON.stringify(after));
  const note = await p.$eval("#dx-grow-note", e => e.textContent).catch(() => "");
  ok("④ 足した数と、すでに地図に在る数を一言で示す", /3 語/.test(note) && /1 語は、すでに/.test(note), note);
  await ctx.close();

  // ── 通常表示 ──
  ({ ctx, p } = await fresh());
  await ready(p, "&preview=0");
  pos = await nodeAt(p, "子の語");
  await p.mouse.click(pos.x, pos.y); await p.waitForTimeout(600);
  ok("⑤ 通常表示では従来の縦の一覧が開き、円形メニューは出ない", !!(await p.$(".gm-item")) && !(await p.$("#radial-menu")) && (await p.$$(".tm-chip")).length > 0);
  await ctx.close();

  const pass = R.filter(Boolean).length; console.log(`\n${pass}/${R.length} PASS`);
  await b.close(); process.exit(pass === R.length ? 0 : 1);
})().catch(e => { console.error("E2E ERROR", e); process.exit(2); });
