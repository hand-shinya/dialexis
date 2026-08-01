// 概念全景の機械確認（gate外・半田様指定の4点のみ）。弁証法(層1)→矛盾(層2)を実マウスクリックで選ぶ。
//  1) 実マウスで弁証法→矛盾を選ぶと概念全景が開く
//  2) 語源(来歴)・並置(焦点)・埋没・共起が別の意味契約になり、別カテゴリで穴埋めされない
//  3) 戻る・進むで選択前後の状態を復元できる
//  4) 同一endpointの重複取得と同一事実の重複表示がない
// グラフは決定論のためfixture（弁証法→矛盾）。概念全景の中身はプレビューの実API（/api/origin?q=矛盾 等）。
const { chromium } = require("playwright-core");
const EXE = process.env.DX_CHROMIUM || "/home/handa/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome";
const B = process.argv[2] || "http://127.0.0.1:8060";
(async () => {
  const b = await chromium.launch({ executablePath: EXE, headless: true });
  const p = await b.newPage(); await p.setViewportSize({ width: 1280, height: 900 });
  const R = []; const ok = (n, c, d) => { R.push(c); console.log(`${c ? "PASS" : "FAIL"}  ${n}${d ? "  — " + d : ""}`); };
  // 同一endpoint重複取得の計測（矛盾に対する /api/origin と /api/anatomy の回数）
  let originHits = 0, anatomyHits = 0;
  p.on("request", (req) => { const u = req.url();
    if (/\/api\/origin\?/.test(u) && /%E7%9F%9B%E7%9B%BE/.test(u)) originHits++;   // q=矛盾
    if (/\/api\/anatomy\?/.test(u) && /%E7%9F%9B%E7%9B%BE/.test(u)) anatomyHits++; });

  await p.route("**/api/origin/graph**", r => r.fulfill({ status: 200, contentType: "application/json",
    body: JSON.stringify({ query: "弁証法", note: "fx", nodes: [
      { id: "n1", label: "弁証法", kind: "word", layer: 1, q: "弁証法" },
      { id: "n2", label: "矛盾", kind: "related", layer: 2, q: "矛盾" }],
      edges: [{ from: "n1", to: "n2", strength: 1 }] }) }));
  // 概念全景の契約分離を決定論的に検証するため、矛盾の origin/anatomy は canonical をmock（実データの揺れは
  // previewで人間が見る）。collapse_warning=null＝焦点区画は非表示／concept_origin=英語のみ＝共起は非表示、を保証。
  const MOU = "%E7%9F%9B%E7%9B%BE";   // 矛盾
  await p.route("**/api/origin?**", r => { const u = r.request().url();
    if (!u.includes(MOU)) return r.continue();
    r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({
      query: "矛盾", found: true, general_meaning: ["つじつまが合わないこと。複数の命題が同時に真にならないこと。"],
      concept_origin: [{ name: "英語", term: "contradiction" }], collapse_warning: null,
      relations: { near: ["対立"], opposite: ["整合"] }, associated: [{ label: "ヘーゲル", is_person: true }, { label: "弁証法", is_person: false }],
      breadth: [{ name: "英語", term: "contradiction" }, { name: "ドイツ語", term: "Widerspruch" }, { name: "フランス語", term: "contradiction" }],
      queried_at: "2026-07-30T00:00:00+00:00", wikidata_url: "https://www.wikidata.org/wiki/Q1" }) }); });
  await p.route("**/api/anatomy?**", r => { const u = r.request().url();
    if (!u.includes(MOU)) return r.continue();
    r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({
      term: "矛盾", own: true, components: [{ part: "矛", meaning: "spear" }, { part: "盾", meaning: "shield" }],
      chain: [], summary: "From a tale in Han Feizi first attested c. 2nd century BCE.",
      queried_at: "2026-07-30T00:00:00+00:00", wiktionary_url: "https://en.wiktionary.org/wiki/矛盾" }) }); });

  await p.goto(`${B}/origin?q=%E5%BC%81%E8%A8%BC%E6%B3%95&lang=ja`, { waitUntil: "networkidle", timeout: 45000 });
  for (let i = 0; i < 25; i++) { const v = await p.evaluate(() => { const w = document.getElementById("origin-graph-wrap"); return w && getComputedStyle(w).display !== "none"; }).catch(() => 0); if (v) break; await p.waitForTimeout(500); }
  // 決定論: 2ノードを離して置き sim凍結・fit
  const freeze = () => p.evaluate(() => { const g = __dx.G; if (g.raf) cancelAnimationFrame(g.raf); g.running = false; g.alpha = 0;
    const pos = { n1: [180, 300], n2: [560, 300] }; g.nodes.forEach(n => { const q = pos[n.id]; if (q) { n.x = q[0]; n.y = q[1]; n.vx = 0; n.vy = 0; } n.r = n.r || 20; }); g.W = g.cv.clientWidth || 900; g.H = g.cv.clientHeight || 600; return __dx.fit(); });
  await freeze();

  // (1) 派生ノード「矛盾」を実マウスクリック→**既存ノードメニュー**が開き、「全体像を見る」で概念全景へ
  const c = await p.evaluate(() => __dx.nodeClientXY(n => n.layer === 2));
  await p.mouse.click(c.x, c.y);
  await p.waitForTimeout(400);
  const menu = await p.evaluate(() => { const m = document.getElementById("graph-menu");
    return { open: !!m, items: m ? [...m.querySelectorAll(".gm-item")].map(e => e.textContent) : [],
      disabled: m ? [...m.querySelectorAll("button,[disabled]")].length : 0 }; });
  ok("(1) 派生ノード(矛盾)の実クリックで既存ノードメニューが開く", menu.open && menu.items.length > 0, (menu.items[0] || "") + " …" + menu.items.length + "項目");
  ok("(1) メニューに無効項目(soon/灰色)が無い", menu.disabled === 0 && !menu.items.some(t => /次段|準備中|整備中/.test(t)));
  const first = await p.evaluate(() => { const it = [...document.querySelectorAll("#graph-menu .gm-item")].find(e => /全体像/.test(e.textContent)); if (!it) return null; it.click(); return it.textContent; });
  ok("(1) 第一候補「全体像を見る」がメニューにある", !!first, first || "見つからない");
  await p.waitForTimeout(2500);
  const pano = await p.evaluate(() => { const el = document.getElementById("graph-panel"); if (!el) return null;
    return { wide: el.classList.contains("gp-wide"), title: (el.querySelector(".gp-head b") || {}).textContent || "",
      secs: [...el.querySelectorAll(".pano-sec")].map(s => s.id),
      hasHistory: !!document.getElementById("pano-history"), hasFocus: !!document.getElementById("pano-focus"),
      hasColloc: !!document.getElementById("pano-colloc"),
      text: (el.innerText || "") }; });
  ok("(1) 実マウスで弁証法→矛盾を選ぶと概念全景(gp-wide)が開く", !!(pano && pano.wide && pano.secs.length >= 2), pano ? pano.secs.join(",") : "no panel");
  ok("(1) 文脈が保たれる（タイトルに『弁証法の中の』）", !!(pano && /弁証法の中の/.test(pano.title)), pano && pano.title);
  const disp = await p.evaluate(() => __dx.lastDispatch);
  ok("(1) 単一Dispatcher経由(panorama)・target=矛盾", !!(disp && disp.actionId === "panorama" && disp.target && disp.target.term === "矛盾"), JSON.stringify(disp && { a: disp.actionId, t: disp.target && disp.target.term }));

  // (2) 意味契約の分離＋UX整理（操作行なし・目次=見出し一致・番号なし・英語散文なし・無関係な意外差なし）
  const c2 = await p.evaluate(() => {
    const panel = document.getElementById("graph-panel");
    const hist = document.getElementById("pano-history");
    const histHtml = hist ? hist.querySelector(".pano-in").innerHTML : "";
    const ownHistory = /矛|盾|spear|shield|韓非|Han\s*Feizi/.test(histHtml);
    const translationEty = /anat-part[^>]*>contra|dicere/.test(histHtml);
    const spearElsewhere = (() => { let n = 0; document.querySelectorAll(".pano-sec").forEach(s => { if (s.id !== "pano-history" && /(矛＝|盾＝|>spear|>shield)/.test(s.querySelector(".pano-in").innerHTML)) n++; }); return n; })();
    const bodyHtml = panel.innerHTML;
    const secHeads = [...panel.querySelectorAll(".pano-sec .pano-h")].map(h => h.textContent.trim());
    const tocLinks = [...panel.querySelectorAll(".pano-toc-a")];
    const tocHeads = tocLinks.map(a => a.textContent.trim());
    const tocSecIds = tocLinks.map(a => "pano-" + a.dataset.sec);
    const tocMatchesBody = tocHeads.length === secHeads.length && tocHeads.every((t, i) => secHeads.includes(t)) && tocSecIds.every(id => !!document.getElementById(id));
    return {
      histHasFormation: ownHistory && !translationEty,
      focusPresent: !!document.getElementById("pano-focus"),
      collocPresent: !!document.getElementById("pano-colloc"),
      overlookPresent: !!panel.querySelector(".pano-overlook"),
      forbiddenPhrase: /原語の意味空間/.test(bodyHtml),
      spearElsewhere,
      hasOpButtons: !!panel.querySelector(".pano-op") || [...panel.querySelectorAll("button")].some(b => b.disabled),
      hasKukaku: /区画/.test(panel.innerText),
      tocExists: !!panel.querySelector(".pano-toc") && /この語の見どころ/.test(panel.innerText),
      tocMatchesBody, tocHeads, secHeads,
      hasNumberedHeads: /class="pano-n"/.test(bodyHtml) || secHeads.some(h => /^[0-9０-９]/.test(h)),
      rawEnglishEty: /Borrowed from|By surface analysis|surface analysis/.test(panel.innerText),
    };
  });
  ok("(2) 語の来歴に語自身の来歴（矛/盾・韓非子）が入り訳語Latin語源が紛れない", c2.histHasFormation);
  ok("(2) 埋没根拠が無い矛盾では『翻訳で変わった焦点』を穴埋めせず非表示", c2.focusPresent === false);
  ok("(2) 独語コーパスの無い矛盾では『実際の用法・共起』を穴埋めせず非表示", c2.collocPresent === false);
  ok("(2) 同一事実(矛/盾)は来歴に一度だけ・他節へ複製しない", c2.spearElsewhere === 0, "elsewhere=" + c2.spearElsewhere);
  ok("(2) 対比が成立しない矛盾では『この語で見落としやすいこと』を出さない（無関係な意外差なし）", c2.overlookPresent === false);
  ok("(2) パネル内に灰色の操作ボタン/操作行がない", c2.hasOpButtons === false);
  ok("(2) 『区画』という語が残っていない", c2.hasKukaku === false);
  ok("(2) 目次『この語の見どころ』が存在", c2.tocExists);
  ok("(2) 目次と本文の見出しが一致・表示されない節は目次にも無い", c2.tocMatchesBody, "toc=" + JSON.stringify(c2.tocHeads) + " sec=" + JSON.stringify(c2.secHeads));
  ok("(2) 番号と番号抜けがない（見出しに番号なし）", c2.hasNumberedHeads === false);
  ok("(2) raw Englishの語源説明がない（Borrowed from等）", c2.rawEnglishEty === false);
  ok("(2) 『原語の意味空間』という誤呼称を使わない", c2.forbiddenPhrase === false);
  // 目次クリック＝実動作の検証。**全項目**を順に実DOMクリックし、押した項目がactiveのままで
  // 別項目へ誤反転しないこと・見出しが表示領域に入ることを、実スクロールコンテナ(#graph-panel)で確かめる。
  const tocAll = await p.evaluate(async () => {
    const panel = document.getElementById("graph-panel");
    const links = [...panel.querySelectorAll(".pano-toc-a")]; if (!links.length) return null;
    const out = [];
    for (const a of links) {
      const sec = "pano-" + a.dataset.sec, el = document.getElementById(sec);
      panel.scrollTop = 0; await new Promise(r => setTimeout(r, 250));
      const before = panel.scrollTop;
      a.click();
      const immediate = (panel.querySelector(".pano-toc-a.active") || {}).dataset?.sec;
      await new Promise(r => setTimeout(r, 1500));   // スクロール完了＋ロック解除判定後
      const act = (panel.querySelector(".pano-toc-a.active") || {}).dataset?.sec;
      const pr = panel.getBoundingClientRect(), hr = el.querySelector(".pano-h").getBoundingClientRect();
      out.push({ sec: a.dataset.sec, immediate, after: act, moved: panel.scrollTop !== before,
        inView: hr.top >= pr.top - 4 && hr.top <= pr.bottom });
    }
    return out;
  });
  ok("(2) 全目次項目: クリックした項目がactive（別項目へ誤反転しない）",
    !!tocAll && tocAll.every(r => r.immediate === r.sec && r.after === r.sec),
    JSON.stringify(tocAll && tocAll.map(r => `${r.sec}:${r.immediate}/${r.after}`)));
  ok("(2) 全目次項目: 対応する見出しがパネル表示領域内にある",
    !!tocAll && tocAll.every(r => r.inView), JSON.stringify(tocAll && tocAll.map(r => `${r.sec}:${r.inView}`)));

  // (3) 戻る/進むで選択前後を復元
  const before = await p.evaluate(() => __dx.viewState());
  await p.evaluate(() => navGo(-1)); await p.waitForTimeout(1200);
  const back = await p.evaluate(() => ({ vs: __dx.viewState(), panel: !!document.getElementById("graph-panel") }));
  await p.evaluate(() => navGo(1)); await p.waitForTimeout(2000);
  const fwd = await p.evaluate(() => ({ vs: __dx.viewState(), wide: !!document.querySelector("#graph-panel.gp-wide") }));
  ok("(3) 戻るで選択前（パネル無し）へ復元", back.vs && back.vs.panel === null, JSON.stringify(back.vs && back.vs.panel));
  ok("(3) 進むで概念全景(選択後)へ復元", !!(fwd.vs && fwd.vs.panel && fwd.vs.panel.action === "panorama" && fwd.wide), JSON.stringify(fwd.vs && fwd.vs.panel));

  // (4) 同一endpointの重複取得なし（矛盾の origin/anatomy は各1回・open＋forward復元を跨いでも）
  ok("(4) /api/origin?q=矛盾 の取得は1回だけ（区画間・復元で重複しない）", originHits === 1, "originHits=" + originHits);
  ok("(4) /api/anatomy?q=矛盾 の取得は1回だけ", anatomyHits === 1, "anatomyHits=" + anatomyHits);

  const pass = R.filter(Boolean).length; console.log(`\n${pass}/${R.length} PASS`);
  await b.close(); process.exit(pass === R.length ? 0 : 1);
})().catch(e => { console.error("ERR", e); process.exit(2); });
