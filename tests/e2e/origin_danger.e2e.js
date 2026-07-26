// Danger-fix E2E: the origin card must NEVER assert a single definitive origin.
// For リゾーム it must surface the concept's real originators (Deleuze/Guattari),
// demote the Greek ῥίζωμα to word-form ETYMOLOGY with a warning, and offer a
// discourse link — instead of the old misleading "概念の原点: ギリシャ語" assertion.
const { chromium } = require("playwright-core");
const EXE = "/home/handa/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome";
const BASE = process.argv[2] || "http://127.0.0.1:8012";

(async () => {
  const browser = await chromium.launch({ executablePath: EXE, headless: true });
  const page = await browser.newPage();
  const R = [];
  const ok = (n, c, d) => { R.push(c); console.log(`${c ? "PASS" : "FAIL"}  ${n}${d ? "  — " + d : ""}`); };

  await page.goto(`${BASE}/origin?q=%E3%83%AA%E3%82%BE%E3%83%BC%E3%83%A0&lang=ja`, { waitUntil: "networkidle" });
  await page.waitForTimeout(1500);
  const card = await page.$eval("#card-origin", el => el.textContent);

  ok("原点カードに『この概念を立てた思想家』が出る", /この概念を立てた思想家/.test(card));
  ok("ドゥルーズが思想家として現れる（Googleが届く本命に到達）", /ドゥルーズ/.test(card), "");
  ok("ガタリが思想家として現れる", /ガタリ/.test(card));
  ok("ギリシャ語ρίζωμαは『語形の由来（語源』に降格されている", /語形の由来（語源/.test(card));
  ok("⚠『概念そのものの原点ではありません』の警告が出る（誤誘導の是正）",
     /概念そのものの原点ではありません/.test(card));
  ok("旧・危険な断定『概念の原点（この訳語が写した原語）: …ギリシャ語』が消えている",
     !/概念の原点（この訳語が写した原語）[^。]*ギリシャ語/.test(card), "");
  ok("『言説を広く調べる』入口がある（P4/P1）", /言説を広く調べる/.test(card));
  ok("『原点は一つに断定しません（無中心・P1）』が明示される", /一つに断定しません/.test(card));

  // グラフに思想家ノード
  const graphAuthors = await page.evaluate(() =>
    (typeof G !== "undefined" && G && G.nodes ? G.nodes.filter(n => n.kind === "author").map(n => n.label) : []));
  ok("グラフ第4階層に思想家ノード（ドゥルーズ/ガタリ）＝グラフ↔次元↔原点が一致",
     graphAuthors.some(a => /ドゥルーズ/.test(a)) && graphAuthors.some(a => /ガタリ/.test(a)),
     `authors=${JSON.stringify(graphAuthors)}`);

  // 思想家クリック→実データパネル（言説へ到達）。fetch完了まで gp-body の充填を待つ。
  await page.click("#card-origin .origin-thinker");
  let ptext = "";
  try {
    await page.waitForFunction(() => {
      const b = document.querySelector(".gp-body");
      return b && b.textContent && b.textContent.replace(/読み込み中|loading|…/g, "").trim().length > 120;
    }, null, { timeout: 12000 });
    ptext = await page.$eval(".gp-body", el => el.textContent);
  } catch (e) { ptext = (await page.$(".gp-body")) ? await page.$eval(".gp-body", el => el.textContent) : ""; }
  ok("思想家クリックで経歴・著作・情報源パネルが開く（言説へ到達）",
     ptext.length > 120 && /千のプラトー|アンチ|差異|ドゥルーズ/.test(ptext), `len=${ptext.length}`);

  const pass = R.filter(Boolean).length;
  console.log(`\n${pass}/${R.length} PASS`);
  await browser.close();
  process.exit(pass === R.length ? 0 : 1);
})().catch(e => { console.error("E2E ERROR", e); process.exit(2); });
