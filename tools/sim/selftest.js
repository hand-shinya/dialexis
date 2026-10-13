// harness の自己試験（§8.8「harness 自身を疑う」）。外部にも app にも触れない固定画面で、
// 観測関数が「人の目に見える物だけ」を返すかを確かめる。1つでも落ちたら harness を使わない。
//
// 2026-10-13: 閉じた <details> の中身を見えると判定していた（offsetHeight > 0 のため）。
// その結果、本走Aの Actor は人に見えない入力欄8つを見ていた。本走Aは無効にした。
"use strict";
const path = require("path");
const REPO = path.resolve(__dirname, "..", "..");
const { chromium } = require(path.join(REPO, "node_modules", "playwright-core"));
const { pageObserve } = require("./observe_page");
const { makeMask, typedAllowed } = require("./mask");
const EXE = process.env.DX_CHROMIUM || `${process.env.HOME}/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome`;

const FIXTURE = `<!doctype html><meta charset=utf-8><body>
<a href="/seen">SEEN-LINK</a>
<button>SEEN-BUTTON</button>
<input placeholder="SEEN-INPUT">
<details><summary>SEEN-SUMMARY</summary><input placeholder="HIDDEN-IN-CLOSED-DETAILS"><a href="/x">HIDDEN-LINK-IN-DETAILS</a></details>
<details open><summary>OPEN-SUMMARY</summary><input placeholder="SEEN-IN-OPEN-DETAILS"></details>
<a href="/n" style="display:none">HIDDEN-DISPLAY-NONE</a>
<a href="/v" style="visibility:hidden">HIDDEN-VISIBILITY</a>
<a href="/o" style="opacity:0">HIDDEN-OPACITY</a>
<div style="height:0;overflow:hidden"><a href="/z">HIDDEN-ZERO-HEIGHT</a></div>
<a href="/under" style="position:absolute;left:20px;top:300px">HIDDEN-UNDER-PANEL</a>
<div id="ov" style="position:fixed;left:0;top:250px;width:400px;height:400px;background:#fff;z-index:9"><button>SEEN-PANEL-CLOSE</button></div>
<div style="height:2000px"></div><a href="/below" style="position:relative;left:600px">SEEN-BELOW-FOLD</a>
<a href="/belowunder" style="position:absolute;left:30px;top:2400px">HIDDEN-BELOW-UNDER-PANEL</a>
</body>`;

(async () => {
  const R = []; const ok = (n, c, d) => { R.push(c); console.log(`${c ? "PASS" : "FAIL"}  ${n}${d ? "  — " + d : ""}`); };
  const b = await chromium.launch({ executablePath: EXE, headless: true });
  const p = await b.newPage({ viewport: { width: 1000, height: 700 } });
  await p.route("http://fixture.invalid/**", r => r.fulfill({ status: 200, contentType: "text/html; charset=utf-8", body: FIXTURE }));
  await p.goto("http://fixture.invalid/");
  const o = await p.evaluate(pageObserve);
  const labels = o.items.map(x => x.label);
  for (const s of ["SEEN-LINK", "SEEN-BUTTON", "SEEN-INPUT", "SEEN-SUMMARY", "OPEN-SUMMARY", "SEEN-IN-OPEN-DETAILS", "SEEN-BELOW-FOLD", "SEEN-PANEL-CLOSE"])
    ok(`見える物を返す: ${s}`, labels.includes(s), labels.join(","));
  for (const s of ["HIDDEN-IN-CLOSED-DETAILS", "HIDDEN-LINK-IN-DETAILS", "HIDDEN-DISPLAY-NONE", "HIDDEN-VISIBILITY", "HIDDEN-OPACITY", "HIDDEN-ZERO-HEIGHT", "HIDDEN-UNDER-PANEL", "HIDDEN-BELOW-UNDER-PANEL"])
    ok(`見えない物を返さない: ${s}`, !labels.includes(s));
  ok("画面の文に、閉じた details の中身が出ない", !/HIDDEN-LINK-IN-DETAILS/.test(o.text));
  ok("画面の文に、パネルの下に隠れた文が出ない", !/HIDDEN-UNDER-PANEL/.test(o.text) && /SEEN-PANEL-CLOSE/.test(o.text));
  ok("下の方の物には印が付く", (o.items.find(x => x.label === "SEEN-BELOW-FOLD") || {}).below === true);
  ok("見えている範囲の外の物は inview=false（Actor に渡さない）", (o.items.find(x => x.label === "SEEN-BELOW-FOLD") || {}).inview === false
     && (o.items.find(x => x.label === "SEEN-LINK") || {}).inview === true);
  ok("画面の文は見えている範囲だけ（下の方の文を含まない）", !/SEEN-BELOW-FOLD/.test(o.text) && /SEEN-LINK/.test(o.text));
  ok("下に続きがあることは知らせる", o.moreBelow === true);
  // 語彙マスク
  const kyo = makeMask({ scripts: ["latin", "kana", "kanji_kyoiku", "digits", "punct"] });
  ok("教育漢字の外の字は □ になる", kyo("疎外") === "□外");
  ok("教育漢字は読める", kyo("自由と時間") === "自由と時間");
  ok("ラテン文字だけのペルソナには仮名も漢字も □", makeMask({ scripts: ["latin", "digits", "punct"] })("time 時間 です") === "time □□ □□");
  ok("語単位の未知語は大文字小文字を問わず □ になる（評価資料 P-01）",
     makeMask({ scripts: ["any"], unknown_words: ["Reification", "物象化"] })("reification と Reification と 物象化") === "□□□□□□□□□□□ と □□□□□□□□□□□ と □□□");
  ok("打てない字を含む入力を拒む", !typedAllowed("疎外", ["latin", "kana", "kanji_kyoiku"]) && typedAllowed("ともだち", ["latin", "kana", "kanji_kyoiku"]));
  await b.close();
  const pass = R.filter(Boolean).length; console.log(`\n${pass}/${R.length} PASS`);
  process.exit(pass === R.length ? 0 : 1);
})().catch(e => { console.error("SELFTEST ERROR", e); process.exit(2); });
