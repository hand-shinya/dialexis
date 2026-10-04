// Fix後のUX整理を、localhost:8060の実プレビュー・実データ・実マウスクリックで3経路確認（半田様item7）。
//   A: 弁証法そのもの（word中心ノード）
//   B: 弁証法の中の「一般の意味」（domainノード＝カテゴリ→親rootの全景を開く）
//   C: 「アリストテレス」（authorノード／コペルニクスと同じ弁証法グラフの系譜から）
// 各経路で: 灰色操作ボタンなし／地図操作がパネル内に重複なし／「区画」語なし／目次と本文見出し一致／
//   番号と番号抜けなし／表示されない節が目次に残らない／raw English語源なし／目次クリックで移動／
//   ノード選択から全景が開く／戻る・進むで履歴を壊さない。
const { chromium } = require("playwright-core");
const EXE = process.env.DX_CHROMIUM || "/home/handa/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome";
const B = process.argv[2] || "http://127.0.0.1:8060";
const sleep = (ms) => new Promise(r => setTimeout(r, ms));

async function loadGraph(p, q) {
  await p.goto(`${B}/origin?q=${encodeURIComponent(q)}&lang=ja`, { waitUntil: "networkidle", timeout: 45000 });
  for (let i = 0; i < 30; i++) { const v = await p.evaluate(() => { const w = document.getElementById("origin-graph-wrap"); return w && getComputedStyle(w).display !== "none"; }).catch(() => 0); if (v) break; await sleep(600); }
  for (let i = 0; i < 20; i++) { const a = await p.evaluate(() => (window.__dx && __dx.G) ? (__dx.G.alpha || 0) : 1).catch(() => 1); if (a < 0.05) break; await sleep(400); }
  await p.evaluate(() => { const g = __dx.G; if (g && g.raf) cancelAnimationFrame(g.raf); if (g) { g.running = false; g.alpha = 0; } });   // その場で凍結（再配置しない）
}
// 全景パネル内の全クリック可能要素を実DOMから列挙し、A/B/C/D のどれか一つに分類する（未分類=違反）。
//  A=目次(.pano-toc-a) B=構造ラベル(=クリック不可でなければ違反) C=実体(.pano-ent) D=開閉/外部出典
async function classifyClickables(p) {
  return await p.evaluate(() => {
    const panel = document.getElementById("graph-panel"); if (!panel) return null;
    panel.querySelectorAll("details:not([open]) > summary").forEach(s => { s.parentElement.open = true; });  // 折り畳みも展開して数える
    const ENT = ["word", "original", "language", "related", "opposite", "author", "work", "application", "concept"];
    const nodes = [...panel.querySelectorAll('a, button, summary, [role="button"], [tabindex]')];
    const rows = nodes.map(el => {
      const isA = el.classList.contains("pano-toc-a");
      const isC = el.classList.contains("pano-ent");
      const isD = el.tagName === "SUMMARY" || (el.tagName === "A" && el.getAttribute("target") === "_blank");
      const isX = el.classList.contains("gp-x");   // 閉じるボタン（パネル制御）
      const cls = [isA && "A", isC && "C", isD && "D", isX && "X"].filter(Boolean);
      const full = (el.textContent || "").trim();
      return { tag: el.tagName, text: full.slice(0, 24), full, cls,
        term: el.dataset ? (el.dataset.term || "") : "", kind: el.dataset ? (el.dataset.kind || "") : "",
        eid: el.dataset ? (el.dataset.eid || "") : "" };
    });
    const ents = rows.filter(r => r.cls.includes("C"));
    return {
      total: rows.length,
      A: rows.filter(r => r.cls.includes("A")).length,
      C: ents.length,
      D: rows.filter(r => r.cls.includes("D")).length,
      X: rows.filter(r => r.cls.includes("X")).length,
      unclassified: rows.filter(r => r.cls.length === 0).map(r => `${r.tag}:${r.text}`),
      multi: rows.filter(r => r.cls.length > 1).map(r => `${r.tag}:${r.text}:${r.cls}`),
      emptyTarget: ents.filter(r => !r.term || !r.eid).map(r => r.text),
      badKind: ents.filter(r => !ENT.includes(r.kind)).map(r => `${r.text}(${r.kind})`),
      mismatch: ents.filter(r => r.full && r.term && r.full.replace(/\s/g, "") !== r.term.replace(/\s/g, "")).map(r => `${r.text}≠${r.term}`),
      entTerms: ents.map(r => r.term),
    };
  });
}
// 派生実体ノード＝既存ノードメニューが開く。メニュー項目を実DOMクリックして進む。
async function menuState(p) {
  return await p.evaluate(() => { const m = document.getElementById("graph-menu");
    return { open: !!m, items: m ? [...m.querySelectorAll(".gm-item")].map(e => e.textContent.trim()) : [],
      noDisabled: m ? ![...m.querySelectorAll("button")].some(b => b.disabled) : true,
      noSoon: m ? ![...m.querySelectorAll(".gm-item")].some(e => /次段|準備中|整備中/.test(e.textContent)) : true }; });
}
async function menuClick(p, re) {
  return await p.evaluate((r) => { const rx = new RegExp(r);
    const it = [...document.querySelectorAll("#graph-menu .gm-item")].find(e => rx.test(e.textContent));
    if (!it) return null; it.click(); return it.textContent.trim(); }, re.source || re);
}
async function waitPanel(p) {   // 概念全景の描画完了を待つ（固定待ちだと取得の遅い語で「読み込み中」を判定する）
  for (let i = 0; i < 40; i++) {
    const done = await p.evaluate(() => { const b = document.querySelector("#graph-panel .gp-body"); return !!b && !/読み込み中|loading panorama/.test(b.innerText); }).catch(() => false);
    if (done) break; await sleep(700);
  }
  await sleep(400);
}
async function clickNode(p, pred, opts) {
  opts = opts || {};
  // 密なグラフでも確実に当てるため、対象ノードをビュー中心へパンしてから実マウスクリックする（simは凍結のまま）
  const found = await p.evaluate((ps) => {
    const f = new Function("n", "return (" + ps + ")"); const g = __dx.G; if (!g) return false;
    const n = g.nodes.find(f); if (!n) return false;
    if (g.raf) cancelAnimationFrame(g.raf); g.running = false; g.alpha = 0;
    g.view.x = g.W / 2 - n.x * g.view.k; g.view.y = g.H / 2 - n.y * g.view.k; gDraw();
    return true;
  }, pred);
  if (!found) return null;
  const c = await p.evaluate((ps) => { const f = new Function("n", "return (" + ps + ")"); return __dx.nodeClientXY(f); }, pred);
  if (!c) return null;
  await p.mouse.click(c.x, c.y);
  if (opts.menu) { await sleep(500); return c; }   // 派生ノード＝メニューが開くので全景を待たない
  await waitPanel(p);
  return c;
}
async function checkPanorama(p) {
  return await p.evaluate(() => {
    const panel = document.getElementById("graph-panel"); if (!panel) return { opened: false };
    const secHeads = [...panel.querySelectorAll(".pano-sec .pano-h")].map(h => h.textContent.trim());
    const tocLinks = [...panel.querySelectorAll(".pano-toc-a")];
    const tocHeads = tocLinks.map(a => a.textContent.trim());
    const tocIds = tocLinks.map(a => "pano-" + a.dataset.sec);
    const txt = panel.innerText;
    // 語の来歴の中で、英語訳が原語の意味として主表示されていないか（＝原語表記＝英単語 の形が無い）
    const hist = document.getElementById("pano-history");
    const engAsMeaning = hist ? [...hist.querySelectorAll(".anat-part, .anat-gloss")]
      .some(el => /[＝「][ \t]*[A-Za-z][A-Za-z ,'\-]*[」]?$/.test(el.textContent.trim()) && !/[ぁ-んァ-ヶ一-龥]/.test(el.textContent.replace(/^[^＝「]*/, ""))) : false;
    return {
      opened: panel.classList.contains("gp-wide"),
      title: (panel.querySelector(".gp-head b") || {}).textContent || "",
      noOpButtons: !panel.querySelector(".pano-op") && ![...panel.querySelectorAll("button")].some(b => b.disabled),
      noKukaku: !/区画/.test(txt),
      tocExists: !!panel.querySelector(".pano-toc") && /この語の見どころ/.test(txt),
      tocMatches: tocHeads.length === secHeads.length && tocHeads.every(t => secHeads.includes(t)) && tocIds.every(id => !!document.getElementById(id)),
      noNumbers: !/class="pano-n"/.test(panel.innerHTML) && !secHeads.some(h => /^[0-9０-９]/.test(h)),
      noRawEnglish: !/Borrowed from|By surface analysis|surface analysis/.test(txt),
      // 否定的な取得失敗文言（取得できませんでした／見つかりませんでした／失敗 等）を出さない
      noNegative: !/取得できません|見つかりません|できませんでした|取得に失敗|ありませんでした/.test(txt),
      overlook: !!panel.querySelector(".pano-overlook"),
      overlookText: (panel.querySelector(".pano-overlook") || {}).innerText || "",
      engAsMeaning, secHeads, hasHistory: !!hist, hasColloc: !!document.getElementById("pano-colloc"),
    };
  });
}
// 目次クリック＝実動作（#graph-panel の scrollTop が実際に動き、見出しが表示領域へ入り、activeが変わる）
async function tocClickWorks(p) {
  return await p.evaluate(async () => {
    const panel = document.getElementById("graph-panel");
    const links = [...panel.querySelectorAll(".pano-toc-a")]; if (!links.length) return { ok: false, why: "no toc" };
    const a = links[links.length - 1], sec = document.getElementById("pano-" + a.dataset.sec);
    if (!sec) return { ok: false, why: "no section" };
    const scrollable = panel.scrollHeight > panel.clientHeight + 4;
    const before = panel.scrollTop;
    a.click(); await new Promise(r => setTimeout(r, 800));
    const after = panel.scrollTop;
    const pr = panel.getBoundingClientRect(), hr = sec.querySelector(".pano-h").getBoundingClientRect();
    const inView = hr.top >= pr.top - 4 && hr.top <= pr.bottom;
    const active = !!panel.querySelector(".pano-toc-a.active");
    return { ok: inView && active && (!scrollable || after > before), scrollable, before, after, inView, active };
  });
}
async function backForward(p) {
  await p.evaluate(() => navGo(-1)); await sleep(2500);
  const back = await p.evaluate(() => __dx.viewState().panel);
  await p.evaluate(() => navGo(1));
  for (let i = 0; i < 25; i++) { const done = await p.evaluate(() => { const b = document.querySelector("#graph-panel .gp-body"); return !!b && !/読み込み中|loading panorama/.test(b.innerText); }).catch(() => false); if (done) break; await sleep(700); }
  await sleep(300);
  const fwd = await p.evaluate(() => ({ panel: __dx.viewState().panel, wide: !!document.querySelector("#graph-panel.gp-wide") }));
  return { backNull: back === null, fwdPanorama: !!(fwd.panel && fwd.panel.action === "panorama" && fwd.wide) };
}

(async () => {
  const b = await chromium.launch({ executablePath: EXE, headless: true });
  const p = await b.newPage(); await p.setViewportSize({ width: 1360, height: 940 });
  const R = []; const ok = (n, c, d) => { R.push(c); console.log(`${c ? "PASS" : "FAIL"}  ${n}${d ? "  — " + d : ""}`); };

  async function runPath(label, loadQ, pred, expectTitleRe, opts) {
    opts = opts || {};
    await loadGraph(p, loadQ);
    const c = await clickNode(p, pred);
    const v = await checkPanorama(p);
    ok(`${label}: ノード選択で概念全景が開く`, !!(c && v.opened), c ? (v.title || "") : "node not found");
    if (!v.opened) return;
    if (expectTitleRe) ok(`${label}: 主題が期待どおり（${expectTitleRe}）`, expectTitleRe.test(v.title), v.title);
    ok(`${label}: 灰色操作ボタン/操作行がパネル内に無い`, v.noOpButtons);
    ok(`${label}: 「区画」語が残っていない`, v.noKukaku);
    ok(`${label}: 目次『この語の見どころ』が本文見出しと一致`, v.tocExists && v.tocMatches, JSON.stringify(v.secHeads));
    ok(`${label}: 番号と番号抜けがない`, v.noNumbers);
    ok(`${label}: raw Englishの語源説明がない`, v.noRawEnglish);
    ok(`${label}: 否定的な取得失敗文言が出ない`, v.noNegative);
    ok(`${label}: 日本語UIで英語訳が原語の意味として主表示されない`, v.engAsMeaning === false);
    if (opts.expectOverlook === false) ok(`${label}: 根拠のない「見落としやすいこと」が出ない`, v.overlook === false, v.overlookText.slice(0, 60));
    if (opts.expectOverlook === true) ok(`${label}: 根拠のある「見落としやすいこと」が出る（両側の焦点＋出典）`, v.overlook === true && /原語では次のように/.test(v.overlookText), v.overlookText.slice(0, 80).replace(/\n/g, " "));
    if (opts.expectHistory) ok(`${label}: 「語の来歴」が存在する`, v.hasHistory && v.secHeads.includes("語の来歴"), JSON.stringify(v.secHeads));
    if (opts.colloc) {   // 共起は描画後に自動取得される（ボタン無し）。空なら節と目次項目が静かに消える
      const cr = await p.evaluate(async () => {
        await new Promise(r => setTimeout(r, 9000));   // 自動取得の完了を待つ
        const panel = document.getElementById("graph-panel");
        return { skipped: false, secLeft: !!document.getElementById("pano-colloc"),
          tocLeft: !!panel.querySelector('.pano-toc-a[data-sec="colloc"]'),
          negative: /見つかりません|取得できません|ありませんでした/.test(panel.innerText),
          hasBranches: !!document.getElementById("pano-branches"),
          rows: document.querySelectorAll("#pano-colloc .orig-collo tr").length };
      });
      if (!cr.skipped) {
        const emptied = !cr.secLeft;
        if (opts.expectCollocEmpty) {   // 空になる語＝節と目次項目の両方が消えること（失敗説明も出さない）
          ok(`${label}: 共起が空→節が本文から消える`, emptied, JSON.stringify(cr));
          ok(`${label}: 共起が空→目次項目も消える`, cr.tocLeft === false, JSON.stringify(cr));
        } else {
          ok(`${label}: 共起が空なら節も目次項目も残らない（空でなければ実データ表示）`,
            (emptied && !cr.tocLeft) || (!emptied && cr.rows > 0), JSON.stringify(cr));
        }
        ok(`${label}: 共起の失敗説明を出さず「次にたどれる言葉」は残る`, cr.negative === false && cr.hasBranches, JSON.stringify({ neg: cr.negative, br: cr.hasBranches }));
      }
    }
    // 第1階層: 全クリック可能要素の閉包検証（未分類0・複数分類0・構造ラベルのentity化0・空target0・不一致0）
    const cz = await classifyClickables(p);
    ok(`${label}: 全クリック要素がA/B/C/Dのいずれか一つ（未分類0・複数分類0）`,
      !!cz && cz.unclassified.length === 0 && cz.multi.length === 0,
      cz ? `総${cz.total} A${cz.A}/C${cz.C}/D${cz.D}/閉じる${cz.X} 未分類:${JSON.stringify(cz.unclassified)} 複数:${JSON.stringify(cz.multi)}` : "no panel");
    ok(`${label}: 構造ラベルがentity target化0・空target0・表示名とtargetの不一致0`,
      !!cz && cz.badKind.length === 0 && cz.emptyTarget.length === 0 && cz.mismatch.length === 0,
      cz ? `badKind:${JSON.stringify(cz.badKind)} empty:${JSON.stringify(cz.emptyTarget)} mismatch:${JSON.stringify(cz.mismatch)}` : "");
    ok(`${label}: 区分名・件数表示がentityに混入しない（一般の意味/専門・思想の意味/世界の言語◯◯）`,
      !!cz && !cz.entTerms.some(t => /^(一般の意味|専門・思想の意味|世界の言語|語源の連鎖|近い概念|対立|関連)/.test(t) || /^世界の言語\s*\d+/.test(t)),
      JSON.stringify((cz && cz.entTerms || []).slice(0, 8)));
    const tj = await tocClickWorks(p);
    ok(`${label}: 目次クリックで実際にスクロールしactiveが変わる`, tj.ok === true, JSON.stringify(tj));
    const bf = await backForward(p);
    ok(`${label}: 戻る→選択前・進む→全景（履歴を壊さない）`, bf.backNull && bf.fwdPanorama, JSON.stringify(bf));
  }

  // ── 規則①中心語/root → 概念全景を直接
  await runPath("A[弁証法・root]", "弁証法", "n.layer===1", /弁証法/, { expectOverlook: false, expectHistory: true });
  // ── 規則②domain → 中心語の全景（該当節へ）
  await runPath("B[一般の意味・domain]", "弁証法", "n.kind==='domain' && /一般の意味/.test(n.label)", /弁証法/, { expectOverlook: false });
  // ── 規則③派生実体ノード → 既存ノードメニュー（全階層・種別横断）
  const DERIVED = [
    ["C[矛盾・第3層related]", "n.kind==='related' && /矛盾/.test(n.label)", /矛盾/],
    ["D[Karl Marx・author]", "n.kind==='author' && /マルクス/.test(n.label)", /マルクス/],
    ["E[レーニン・author]", "n.kind==='author' && /レーニン/.test(n.label)", /レーニン/],
    ["F[dialectic・original]", "n.kind==='original' && n.label==='dialectic'", /dialectic/],
    ["G[多言語ノード・language]", "n.kind==='language'", null],
  ];
  for (const [label, pred, titleRe] of DERIVED) {
    await loadGraph(p, "弁証法");
    const c = await clickNode(p, pred, { menu: true });
    const m = await menuState(p);
    ok(`${label}: 実クリックで既存ノードメニューが実DOMとして開く`, !!c && m.open && m.items.length > 0, m.items.slice(0, 2).join(" / "));
    if (!m.open) continue;
    ok(`${label}: 無効項目・soon・灰色の押せない項目が無い`, m.noDisabled && m.noSoon);
    // 「全体像を見る」→ その語の概念全景
    const lenBefore = await p.evaluate(() => __dx.nav.len);
    const clicked = await menuClick(p, /全体像/);
    await waitPanel(p);
    const v = await checkPanorama(p);
    ok(`${label}: 「全体像を見る」でその語の概念全景が開く`, !!clicked && v.opened && (!titleRe || titleRe.test(v.title)), v.title);
    ok(`${label}: 全景に否定文言・番号・raw Englishが無い`, v.noNegative && v.noNumbers && v.noRawEnglish);
    ok(`${label}: 目次と本文見出しが一致`, v.tocExists && v.tocMatches, JSON.stringify(v.secHeads));
    const lenAfter = await p.evaluate(() => __dx.nav.len);
    ok(`${label}: 一操作＝履歴commit 1回`, lenAfter - lenBefore === 1, `len ${lenBefore}→${lenAfter}`);
    const tj = await tocClickWorks(p);
    ok(`${label}: 目次クリックで実スクロール＋active`, tj.ok === true, JSON.stringify(tj));
    const bf = await backForward(p);
    ok(`${label}: 戻る→選択前・進む→全景`, bf.backNull && bf.fwdPanorama, JSON.stringify(bf));
  }
  // ── 「この語を中心にする」＝実際に中心語とグラフが変わり、戻る/進むで復元できる
  {
    await loadGraph(p, "弁証法");
    const rootBefore = await p.evaluate(() => __dx.G.rootQ);
    await clickNode(p, "n.kind==='related' && /矛盾/.test(n.label)", { menu: true });
    const lenBefore = await p.evaluate(() => __dx.nav.len);
    const clicked = await menuClick(p, /中心に据え/);
    for (let i = 0; i < 30; i++) { const r = await p.evaluate(() => __dx.G && __dx.G.rootQ).catch(() => null); if (r && r !== rootBefore) break; await sleep(700); }
    await sleep(600);
    const after = await p.evaluate(() => ({ root: __dx.G.rootQ, nodes: __dx.G.nodes.length, len: __dx.nav.len }));
    ok("H[中心に据える]: メニューから中心語が実際に変わる", !!clicked && after.root === "矛盾" && after.nodes > 1, `root ${rootBefore}→${after.root} / nodes ${after.nodes}`);
    ok("H[中心に据える]: 一操作＝履歴commit 1回", after.len - lenBefore === 1, `len ${lenBefore}→${after.len}`);
    await p.evaluate(() => navGo(-1));
    for (let i = 0; i < 30; i++) { const r = await p.evaluate(() => __dx.G && __dx.G.rootQ).catch(() => null); if (r === rootBefore) break; await sleep(700); }
    const back = await p.evaluate(() => __dx.G.rootQ);
    await p.evaluate(() => navGo(1));
    for (let i = 0; i < 30; i++) { const r = await p.evaluate(() => __dx.G && __dx.G.rootQ).catch(() => null); if (r === "矛盾") break; await sleep(700); }
    const fwd = await p.evaluate(() => __dx.G.rootQ);
    ok("H[中心に据える]: 戻るで元の弁証法グラフ・進むで矛盾中心グラフを復元", back === rootBefore && fwd === "矛盾", `back=${back} fwd=${fwd}`);
  }
  // ── 第2階層: 全景内の全entity linkを実マウスで押し、メニュー対象がクリックしたstable ID・termと一致
  {
    await loadGraph(p, "弁証法");
    await clickNode(p, "n.layer===1");   // 弁証法の全景
    const ents = await p.evaluate(() => {
      const panel = document.getElementById("graph-panel");
      panel.querySelectorAll("details:not([open]) > summary").forEach(s => { s.parentElement.open = true; });
      return [...panel.querySelectorAll(".pano-ent")].map((e, i) => ({ i, term: e.dataset.term, kind: e.dataset.kind, eid: e.dataset.eid }));
    });
    let mismatch = 0, opened = 0, skipped = 0, retried = 0; const badSamples = [];
    for (const e of ents) {
      // 位置決め→安定待ち→直前に座標を再測定してから実クリック（スクロール未完了での取りこぼしを防ぐ）
      const locate = async () => await p.evaluate(async (i) => {
        const m0 = document.getElementById("graph-menu"); if (m0) m0.remove();
        const el = [...document.querySelectorAll("#graph-panel .pano-ent")][i];
        el.scrollIntoView({ block: "center" });
        await new Promise(r2 => setTimeout(r2, 200));
        // 折り返した inline リンクは bounding box の中心が行間（親要素）に落ちる。実際の行矩形から
        // 「その点で本当にこの要素が最前面になる」座標を選ぶ（実マウスクリックのまま当たり判定を正す）。
        const rects = [...el.getClientRects()];
        const cands = (rects.length ? rects : [el.getBoundingClientRect()]);
        let pick = null;
        for (const b of cands) {
          if (!(b.width > 0 && b.height > 0 && b.top >= 0 && b.bottom <= innerHeight)) continue;
          const x = Math.round(b.left + Math.min(b.width / 2, 30)), y = Math.round(b.top + b.height / 2);
          const mid = document.elementFromPoint(x, y);
          if (mid && mid.closest && mid.closest(".pano-ent") === el) { pick = { x, y, visible: true, hit: true }; break; }
          if (!pick) pick = { x, y, visible: true, hit: false };
        }
        return pick || { x: 0, y: 0, visible: false, hit: false };
      }, e.i);
      let r = await locate();
      if (!r.visible) { skipped++; continue; }                     // 実クリック不能な位置は計上して除外
      await p.mouse.click(r.x, r.y); await sleep(220);
      let got = await p.evaluate(() => { const m = document.getElementById("graph-menu");
        return { open: !!m, title: m ? (m.querySelector(".gm-title") || {}).textContent || "" : "",
          ctxTerm: (window.__dx && __dx.MENUCTX && __dx.MENUCTX.n) ? (__dx.MENUCTX.n.q || __dx.MENUCTX.n.label) : null }; });
      if (!got.open) {                                             // 座標競合の取りこぼしは1回だけ再試行
        retried++;
        r = await locate();
        if (r.visible) { await p.mouse.click(r.x, r.y); await sleep(280);
          got = await p.evaluate(() => { const m = document.getElementById("graph-menu");
            return { open: !!m, title: m ? (m.querySelector(".gm-title") || {}).textContent || "" : "",
              ctxTerm: (window.__dx && __dx.MENUCTX && __dx.MENUCTX.n) ? (__dx.MENUCTX.n.q || __dx.MENUCTX.n.label) : null }; }); }
      }
      if (got.open) opened++;
      if (!got.open || got.ctxTerm !== e.term || !got.title.includes(e.term)) {
        mismatch++;
        if (badSamples.length < 6) badSamples.push({ term: e.term, kind: e.kind, eid: e.eid, open: got.open, ctxTerm: got.ctxTerm, title: got.title.slice(0, 40) });
      }
    }
    ok(`第2階層: 全entity link(${ents.length}件)の実クリックでメニューが開く`, ents.length > 0 && opened === ents.length - skipped,
      `opened=${opened}/${ents.length - skipped}（列挙${ents.length}・位置不能${skipped}・再試行${retried}）`);
    ok("第2階層: メニュー対象がクリックしたstable ID・termと完全一致（不一致0）", mismatch === 0, `mismatch=${mismatch}/${ents.length - skipped} ${JSON.stringify(badSamples)}`);
    await p.evaluate(() => { const m = document.getElementById("graph-menu"); if (m) m.remove(); });
  }
  // ── 第2階層: entity種別ごとの代表について、メニュー全項目を実クリック（無作用0・commit1回・対象は自分自身）
  for (const [kindLabel, pred, expectTerm] of [
    ["related(矛盾)", "n.kind==='related' && /矛盾/.test(n.label)", "矛盾"],
    ["author(マルクス)", "n.kind==='author' && /マルクス/.test(n.label)", "カール・マルクス"],
    ["original(dialectic)", "n.kind==='original' && n.label==='dialectic'", "dialectic"],
  ]) {
    await loadGraph(p, "弁証法");
    await clickNode(p, pred, { menu: true });
    const items = await p.evaluate(() => [...document.querySelectorAll("#graph-menu .gm-item")].map((e, i) => ({ i, t: e.textContent.trim() })));
    const acted = [], noop = [];
    for (const it of items) {
      if (/新しいタブ|新タブ/.test(it.t)) continue;   // 新タブは状態遷移でない（別ウィンドウを開くため除外）
      await loadGraph(p, "弁証法");
      await clickNode(p, pred, { menu: true });
      const before = await p.evaluate(() => ({ len: __dx.nav.len, root: __dx.G.rootQ }));
      const disp = await p.evaluate(async (i) => {
        const el = [...document.querySelectorAll("#graph-menu .gm-item")][i]; if (!el) return null;
        el.click(); await new Promise(r => setTimeout(r, 2500));
        return __dx.lastDispatch ? { a: __dx.lastDispatch.actionId, t: __dx.lastDispatch.target && __dx.lastDispatch.target.term } : null;
      }, it.i);
      await sleep(1200);
      const after = await p.evaluate(() => ({ len: __dx.nav.len, root: __dx.G.rootQ, panel: __dx.viewState().panel }));
      if (!disp || !disp.a) { noop.push(it.t); continue; }
      acted.push({ item: it.t.slice(0, 12), action: disp.a, target: disp.t, dLen: after.len - before.len, root: after.root });
    }
    ok(`第2階層[${kindLabel}]: メニュー全項目に無作用0`, noop.length === 0, JSON.stringify(noop));
    ok(`第2階層[${kindLabel}]: 全操作の対象がクリックした語自身（${expectTerm}）`,
      acted.every(a => a.target === expectTerm), JSON.stringify(acted.map(a => `${a.action}:${a.target}`)));
    ok(`第2階層[${kindLabel}]: 各操作の履歴commitは1回以内（0=状態変化なし操作を含む）`,
      acted.every(a => a.dLen >= 0 && a.dLen <= 1), JSON.stringify(acted.map(a => `${a.action}:${a.dLen}`)));
    const center = acted.find(a => a.action === "center");
    if (center) ok(`第2階層[${kindLabel}]: 「中心に据える」でその語自身が中心語になる`, center.root === expectTerm, `root=${center.root}`);
    const pano = acted.find(a => a.action === "panorama");
    if (pano) ok(`第2階層[${kindLabel}]: 「全体像を見る」がその語自身の全景`, pano.target === expectTerm, `target=${pano.target}`);
  }
  // ── 意味契約（実データ）: 疎外＝根拠ある見落とし枠＋共起実データ／dialectic＝共起が空で節と目次が消える
  await runPath("I[疎外]", "疎外", "n.layer===1", /疎外/, { expectOverlook: true, colloc: true });

  const pass = R.filter(Boolean).length; console.log(`\n${pass}/${R.length} PASS`);
  await b.close(); process.exit(pass === R.length ? 0 : 1);
})().catch(e => { console.error("ERR", e); process.exit(2); });
