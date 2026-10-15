// 文 → 哲学概念の候補カード（2026-10-15・隔離試作）を実ブラウザで確かめる。応答は固定値（決定論）。
// 守ること: ①文が着かない／別の記事へずれたときにカードが出る ②候補は押すとその概念で新しく探す（P11）
// ③鍵不要の検索と、利用者の LLM の提案を札で区別する ④出所（Wikidata の項目）を示す
// ⑤候補が0件ならカードを残さない ⑥ふつうの語（自由）ではカードを出さない
const { chromium } = require("playwright-core");
const EXE = process.env.DX_CHROMIUM || ((process.env.HOME || "") + "/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome");
const BASE = process.argv[2] || "http://127.0.0.1:8099";
const ORIGIN = (q, found, rf) => ({ query: q, lang: "ja", queried_at: "t", word: { query: q }, found, resolved_from: rf, resolved_to: found ? "別記事" : null,
  suggestions: found ? [] : ["人間関係"], dimensions: [], general_meaning: [], segment_layers: [], concept_origin: [], originators: [], associated: [],
  relations: { near: [], opposite: [] }, named_after: [], chain: [], senses: [], breadth: [], breadth_count: 0, canon: {}, sources: [], confidence: {}, language_bridge: { applied: false } });
(async () => {
  const b = await chromium.launch({ executablePath: EXE, headless: true });
  const R = []; const ok = (n, c, d) => { R.push(c); console.log(`${c ? "PASS" : "FAIL"}  ${n}${d ? "  — " + d : ""}`); };
  const p = await (await b.newContext()).newPage();
  let bridgeCalls = 0;
  await p.route(/\/api\/origin\?/, r => {
    const q = new URL(r.request().url()).searchParams.get("q");
    const body = q === "自由" ? ORIGIN(q, true, null) : q === "人をモノとして扱う" ? ORIGIN(q, true, q) : ORIGIN(q, false, null);
    r.fulfill({ contentType: "application/json", body: JSON.stringify(body) });
  });
  await p.route(/\/api\/pivot\?/, r => r.fulfill({ contentType: "application/json", body: JSON.stringify({ data: { input_candidates: [], concept: null } }) }));
  await p.route(/\/api\/bridge\?/, r => {
    bridgeCalls++;
    const q = new URL(r.request().url()).searchParams.get("q");
    const body = q === "何もない文です" ? { keyless: [], llm: [] } : {
      keyless: [{ qid: "Q545825", title: "疎外", why: "辞書の説明", sources: ["意味検索（概念）"], level: 0 }],
      llm: [{ qid: "Q863448", title: "物象化", why: "人と人の関係が物の関係として現れる", sources: ["あなたの LLM（接地済み）"], level: 2 },
            { qid: "Q545825", title: "疎外", why: "重複", sources: ["あなたの LLM（接地済み）"], level: 2 }] };
    r.fulfill({ contentType: "application/json", body: JSON.stringify(body) });
  });
  const open = async (q) => { await p.goto(`${BASE}/origin?q=${encodeURIComponent(q)}&lang=ja`, { waitUntil: "domcontentloaded" });
    await p.waitForSelector(".word-card", { timeout: 15000 }).catch(() => {}); await p.waitForTimeout(1500); };

  await open("人間関係がモノのようになる");
  const items = await p.$$eval("#bridge-cands .bridge-cand", as => as.map(a => ({ t: a.textContent.trim(), h: a.getAttribute("href") })));
  ok("着かない文で候補カードが出る", items.length > 0, JSON.stringify(items));
  ok("候補は押すとその概念で新しく探すリンク（P11）", items.every(x => /^\/origin\?q=/.test(x.h)));
  ok("同じ項目は1回だけ（LLM と鍵不要で重複しない）", items.filter(x => x.t === "疎外").length === 1, JSON.stringify(items.map(x => x.t)));
  const txt = await p.$eval("#bridge-cands", e => e.innerText).catch(() => "");
  ok("LLM の提案と鍵不要の検索を札で区別する", /あなたのLLMの提案・実在を確認済み/.test(txt) && /鍵不要の検索/.test(txt));
  ok("出所の Wikidata 項目を示す", await p.$$eval("#bridge-cands a[href*='wikidata.org/wiki/Q']", a => a.length) >= 2);
  ok("候補であることを明示する", /候補/.test(txt));

  await open("人をモノとして扱う");
  ok("文が別の記事へずれて着いたときもカードが出る", !!(await p.$("#bridge-cands .bridge-cand")));

  await open("何もない文です");
  ok("候補が0件ならカードを残さない", !(await p.$("#bridge-cands")));

  const before = bridgeCalls;
  await open("自由");
  ok("ふつうの語（記事にそのまま着く）ではカードも問い合わせも出さない", !(await p.$("#bridge-cands")) && bridgeCalls === before);

  const pass = R.filter(Boolean).length; console.log(`\n${pass}/${R.length} PASS`);
  await b.close(); process.exit(pass === R.length ? 0 : 1);
})().catch(e => { console.error("E2E ERROR", e); process.exit(2); });
