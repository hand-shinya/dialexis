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
async function clickNode(p, pred) {
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
  // 描画完了まで待つ（固定待ちにすると初回取得が遅い語＝breadth 200件超で「読み込み中」を判定してしまう）
  for (let i = 0; i < 40; i++) {
    const done = await p.evaluate(() => { const b = document.querySelector("#graph-panel .gp-body"); return !!b && !/読み込み中|loading panorama/.test(b.innerText); }).catch(() => false);
    if (done) break; await sleep(700);
  }
  await sleep(300);
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
    if (opts.colloc) {   // 共起を実行→空なら節と目次項目が静かに消える（失敗説明を出さない）
      const cr = await p.evaluate(async () => {
        const btn = document.querySelector(".pano-load"); if (!btn) return { skipped: true };
        btn.click(); await new Promise(r => setTimeout(r, 9000));
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
    const tj = await tocClickWorks(p);
    ok(`${label}: 目次クリックで実際にスクロールしactiveが変わる`, tj.ok === true, JSON.stringify(tj));
    const bf = await backForward(p);
    ok(`${label}: 戻る→選択前・進む→全景（履歴を壊さない）`, bf.backNull && bf.fwdPanorama, JSON.stringify(bf));
  }

  // A 弁証法そのもの（対比の明示根拠なし＝見落とし枠を出さない・来歴あり）
  await runPath("A[弁証法]", "弁証法", "n.layer===1", /弁証法/, { expectOverlook: false, expectHistory: true });
  // B 弁証法の中の「一般の意味」（domainノード→親rootの全景）
  await runPath("B[一般の意味]", "弁証法", "n.kind==='domain' && /一般の意味/.test(n.label)", /弁証法/, { expectOverlook: false });
  // C 「アリストテレス」（authorノード・コペルニクスと同じ系譜グラフ上）
  await runPath("C[アリストテレス]", "弁証法", "n.kind==='author' && /アリストテレス/.test(n.label)", /アリストテレス/, { expectOverlook: false });
  // D 「矛盾」（周代の冠・one+sort・表層漢字分解などが出ないこと＝根拠なき見落とし枠ゼロ）
  await runPath("D[矛盾]", "弁証法", "n.kind==='related' && /矛盾/.test(n.label)", /矛盾/, { expectOverlook: false, expectHistory: true });
  // E 「疎外」（両側の明示根拠がある語＝見落とし枠が出る／共起は実データが返る語）
  await runPath("E[疎外]", "疎外", "n.layer===1", /疎外/, { expectOverlook: true, colloc: true });
  // F 「dialectic」（弁証法グラフのoriginalノード＝DWDS共起が空になる語。節も目次項目も静かに消えること）
  await runPath("F[dialectic]", "弁証法", "n.kind==='original' && n.label==='dialectic'", /dialectic/, { expectOverlook: false, colloc: true, expectCollocEmpty: true });

  const pass = R.filter(Boolean).length; console.log(`\n${pass}/${R.length} PASS`);
  await b.close(); process.exit(pass === R.length ? 0 : 1);
})().catch(e => { console.error("ERR", e); process.exit(2); });
