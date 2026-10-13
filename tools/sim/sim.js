// シミュレーション harness（引き継ぎ第7世代 §8.4）。1回の走行 = 1ペルソナ × 1 seed。
//
// 層を分ける。強制は JS（この file）、判断は Actor（LLM）。
//   強制（偽装されない）: 語彙マスク・可視判定・手数上限・入口固定・打てる文字・誤入力
//   判断（偽装されうる）: 次の1手と、その手で何が起きると思うかの予測
// マスクを prompt に書かない。Actor が見る文字そのものを JS が □ に置き換える。
// Actor が返せる手は、JS が列挙した番号のどれかだけ。直接 URL は受け付けない。入口は / に固定。
// 生 DOM は Actor に渡さない。渡すのは、人の目に見える文字と、押せる物の一覧だけ。
//
// usage: node tools/sim/sim.js <scenario.json> <seed> <baseURL> <outdir> [condition]
//   env: DX_CHROMIUM, SIM_ACTOR_MODEL（既定 claude-haiku-5-5）, SIM_ACTOR_CMD（既定 claude）
"use strict";
const fs = require("fs");
const path = require("path");
const crypto = require("crypto");
const { spawnSync } = require("child_process");
const REPO = path.resolve(__dirname, "..", "..");
const { chromium } = require(path.join(REPO, "node_modules", "playwright-core"));
const { makeMask, typedAllowed } = require("./mask");
const { pageObserve } = require("./observe_page");

const [scenFile, seedArg, BASE, OUTDIR, COND = "A"] = process.argv.slice(2);
if (!scenFile || !seedArg || !BASE || !OUTDIR) { console.error("usage: sim.js <scenario> <seed> <base> <outdir> [condition]"); process.exit(64); }
const EXE = process.env.DX_CHROMIUM || `${process.env.HOME}/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome`;
const MODEL = process.env.SIM_ACTOR_MODEL || "claude-haiku-5-5";
const ACTOR_CMD = process.env.SIM_ACTOR_CMD || "claude";
const SEED = parseInt(seedArg, 10);
const scenRaw = fs.readFileSync(scenFile, "utf8");
const P = JSON.parse(scenRaw);
const host = new URL(BASE).host;

// seed 付き乱数（mulberry32）。誤入力と概念の選択に使う。LLM の揺らぎは固定できないので記録で扱う
function rng(a) { return () => { a |= 0; a = a + 0x6D2B79F5 | 0; let t = Math.imul(a ^ a >>> 15, 1 | a); t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; }; }
const R = rng(SEED * 2654435761 ^ crypto.createHash("md5").update(P.id).digest().readUInt32LE(0));
const concept = P.concept_pool[SEED % P.concept_pool.length];
const situation = P.situation[concept];
const mask = makeMask(P.reader);

const runId = `${P.id}_s${SEED}_${COND}`;
fs.mkdirSync(OUTDIR, { recursive: true });
const tracePath = path.join(OUTDIR, `${runId}.jsonl`);
const T = fs.openSync(tracePath, "w");
const rec = (o) => fs.writeSync(T, JSON.stringify({ t: Date.now(), ...o }) + "\n");

const SCHEMA = {
  type: "object", additionalProperties: false,
  required: ["note_now", "expect", "action"],
  properties: {
    note_now: { type: "string", description: "この瞬間に考えていること（80字以内）" },
    expect: { type: "string", enum: ["new_page", "more_on_same_page", "menu_or_panel_opens", "external_site", "nothing_changes"] },
    action: {
      type: "object", additionalProperties: false, required: ["kind"],
      properties: {
        kind: { type: "string", enum: ["click", "type_submit", "scroll_down", "back", "stop"] },
        id: { type: "integer" }, text: { type: "string" },
        stop_reason: { type: "string", enum: ["found_what_i_wanted", "found_something_else_useful", "gave_up", "confused"] },
      },
    },
  },
};

// ---- 画面の観測（ブラウザ内で実行。可視判定は offsetHeight と bounding box） ----
async function observe(page) {
  let o;
  for (let i = 0; ; i++) {
    try { o = await page.evaluate(pageObserve); break; }
    catch (e) { if (i >= 2) throw e; await page.waitForLoadState("domcontentloaded", { timeout: 10000 }).catch(() => {}); await settle(page); }
  }
  o.textHash = crypto.createHash("md5").update(o.text).digest("hex");
  o.elemSig = crypto.createHash("md5").update(o.items.map(x => x.label).join("|")).digest("hex");
  return o;
}

// 画面の文字が 800ms 変わらなくなるまで待つ（最大 12 秒）。待った時間は trace に残る
async function settle(page) {
  let last = "", same = 0;
  for (let i = 0; i < 60; i++) {
    const h = await page.evaluate(() => (document.body.innerText || "").length + ":" + document.querySelectorAll("*").length).catch(() => "");
    if (h === last) { if (++same >= 4) return; } else { same = 0; last = h; }
    await page.waitForTimeout(200);
  }
}

// Actor に見せる形。ここで語彙マスクを掛ける（JS が強制）。
// 枠の文言もペルソナの言語で出す（枠が日本語だと、日本語を読めないペルソナに日本語が漏れる）
const FRAME = {
  ja: { addr: "アドレス", title: "題", text: "画面に見えている文", top: "先頭", scrolled: "下へ送った位置", items: "押せる物（番号で選ぶ）",
        input: "入力欄", link: "リンク", button: "ボタン", ext: "（外のサイト）", below: "（下の方）", empty: "（文字なし）",
        nodes: "図の中の語（番号で押せる）", node: "図の語", hist: "これまでの手" },
  zh: { addr: "地址", title: "标题", text: "画面上看到的文字", top: "顶部", scrolled: "已向下滚动", items: "可以点的东西（用编号选择）",
        input: "输入框", link: "链接", button: "按钮", ext: "（外部网站）", below: "（在下方）", empty: "（无文字）",
        nodes: "图中的词（可用编号点击）", node: "图中的词", hist: "到目前为止的操作" },
  en: { addr: "Address", title: "Title", text: "Text visible on screen", top: "top", scrolled: "scrolled down", items: "Things you can press (choose by number)",
        input: "input box", link: "link", button: "button", ext: " (external site)", below: " (further down)", empty: "(no text)",
        nodes: "Words in the diagram (pressable by number)", node: "diagram word", hist: "Your actions so far" },
};
const OBS_TEXT = {
  ja: { new_page: "別の画面になった", more_on_same_page: "同じ画面で中身が変わった", menu_or_panel_opens: "何かが開いた", external_site: "外のサイトが開いた", nothing_changes: "何も変わらなかった", rejected: "受け付けられなかった",
        clicked: (l) => `「${l}」を押した`, node: (l) => `図の語「${l}」を押した`, typed: (t) => `「${t}」と入れて送った`, scroll: "下へ送った", back: "戻った" },
  zh: { new_page: "换到了别的画面", more_on_same_page: "同一画面的内容变了", menu_or_panel_opens: "打开了什么", external_site: "打开了外部网站", nothing_changes: "什么都没变", rejected: "没有被接受",
        clicked: (l) => `点了「${l}」`, node: (l) => `点了图中的词「${l}」`, typed: (t) => `输入「${t}」并发送`, scroll: "向下滚动", back: "返回" },
  en: { new_page: "a different screen appeared", more_on_same_page: "the same screen changed", menu_or_panel_opens: "something opened", external_site: "an external site opened", nothing_changes: "nothing changed", rejected: "not accepted",
        clicked: (l) => `pressed "${l}"`, node: (l) => `pressed diagram word "${l}"`, typed: (t) => `typed "${t}" and submitted`, scroll: "scrolled down", back: "went back" },
};
const F = FRAME[P.situation_lang] || FRAME.en, OT = OBS_TEXT[P.situation_lang] || OBS_TEXT.en;
function render(o, history) {
  const L = [];
  let shown = o.path; try { shown = decodeURIComponent(o.path); } catch (e) {}
  L.push(`${F.addr}: ${mask(shown).slice(0, 120)}`);
  L.push(`${F.title}: ${mask(o.title)}`);
  L.push(`--- ${F.text}（${o.scrollY > 0 ? F.scrolled : F.top}）---`);
  L.push(mask(o.text).slice(0, 1800));
  L.push(`--- ${F.items} ---`);
  const lines = o.items.slice(0, 70).map(x => `[${x.i}] ${x.input ? F.input : x.tag === "a" ? F.link : F.button}${x.ext ? F.ext : ""}${x.below ? F.below : ""}: ${mask(x.label) || F.empty}`);
  L.push(...lines);
  if (o.nodes.length) {
    L.push(`--- ${F.nodes} ---`);
    o.nodes.forEach((n, k) => L.push(`[${1000 + k}] ${F.node}: ${mask(n.label)}`));
  }
  if (history.length) {
    // 履歴にも同じマスクを掛ける（smoke 1回目で、ここから未マスクのラベルが漏れていた）
    L.push(`--- ${F.hist} ---`);
    history.slice(-6).forEach(h => L.push(`${h.step}. ${mask(h.adesc)} → ${h.aobs}`));
  }
  return L.join("\n");
}

function actorPrompt(view, stepNo) {
  const sys = P.situation_lang === "ja"
    ? `あなたはウェブサイトを使っている一人の人です。次の状況にいます。\n状況: ${situation}\n\nあなたに見えているのは下の画面だけです。□ はあなたには読めない字です。読めない字の意味を推測で補ってはいけません。\n次に何をするかを1つだけ選んでください。番号は一覧にあるものだけ使えます。文字を入れるときは、あなたが自分で打てる言葉だけを使ってください。やめたくなったら stop を選んでください。\nexpect には、その手で何が起きると今思っているかを選んでください。`
    : P.situation_lang === "zh"
      ? `你是一个正在使用网站的人。你的情况：${situation}\n\n你只能看到下面的画面。□ 是你读不懂的字，不要猜它的意思。\n选择下一步要做的一件事。只能使用列表中的编号。输入文字时只用你自己会打的词。想放弃时选 stop。\nexpect：选择你现在认为这一步会发生什么。`
      : `You are a person using a website. Your situation: ${situation}\n\nYou can only see the screen below. □ marks characters you cannot read; do not guess their meaning.\nChoose exactly one next action. Use only numbers from the list. When typing, use only words you could type yourself. Choose stop when you want to quit.\nIn expect, choose what you think will happen as a result of this action.`;
  return `${sys}\n\n(${stepNo})\n${view}`;
}

function callActor(prompt) {
  const cwd = path.join(require("os").tmpdir(), "dx-sim-actor"); fs.mkdirSync(cwd, { recursive: true });
  const t0 = Date.now();
  const r = spawnSync(ACTOR_CMD, ["-p", "--restricted", "--strict-mcp-config", "--no-session-persistence", "--tools", "",
    "--model", MODEL, "--output-format", "json", "--json-schema", JSON.stringify(SCHEMA)],
    { input: prompt, cwd, encoding: "utf8", timeout: 120000, maxBuffer: 16 << 20 });
  const ms = Date.now() - t0;
  try { const d = JSON.parse(r.stdout); return { ok: !d.is_error && !!d.structured_output, out: d.structured_output, ms, cost: d.total_cost_usd, model: Object.keys(d.modelUsage || {}) }; }
  catch (e) { return { ok: false, ms, err: (r.stderr || "").slice(0, 300) + (r.error ? String(r.error) : "") }; }
}

function typo(s) {
  if (!P.writer.typo_rate) return s;
  return [...s].map(c => { if (R() >= P.writer.typo_rate) return c; const k = R();
    return k < 0.34 ? "" : k < 0.67 ? c + c : String.fromCodePoint(c.codePointAt(0) + 1); }).join("");
}

function classify(before, after, popupHosts) {
  let afterHost = host; try { afterHost = new URL(after.url).host; } catch (e) {}
  if (popupHosts.some(x => x.host !== host) || afterHost !== host) return "external_site";
  if (before.path !== after.path) return "new_page";
  if (before.textHash === after.textHash && before.elemSig === after.elemSig && before.scrollY === after.scrollY) return "nothing_changes";
  if (after.items.length > before.items.length && Math.abs(after.text.length - before.text.length) < 400) return "menu_or_panel_opens";
  return "more_on_same_page";
}

(async () => {
  const b = await chromium.launch({ executablePath: EXE, headless: true });
  const ctx = await b.newContext({ viewport: P.viewport || { width: 1280, height: 900 }, locale: P.situation_lang === "ja" ? "ja-JP" : P.situation_lang === "zh" ? "zh-CN" : "en-US" });
  const page = await ctx.newPage();
  // 変異試験（§8.8）。SIM_MUTATE が空なら何もしない。trace の start に記録する
  const MUT = process.env.SIM_MUTATE || "";
  if (MUT === "nav_remove") await ctx.addInitScript(() => document.addEventListener("DOMContentLoaded", () => document.querySelectorAll("nav a, header a").forEach(a => a.remove())));
  if (MUT === "display_none") await ctx.addInitScript(() => document.addEventListener("DOMContentLoaded", () => { const st = document.createElement("style"); st.textContent = "form.searchbox, .searchbox input{display:none!important}"; document.head.appendChild(st); }));
  if (MUT === "api_block") await ctx.route("**/api/**", r => r.abort());
  const net = [];
  page.on("response", (res) => { const rq = res.request(); const u = new URL(rq.url());
    if (u.host === host && (u.pathname.startsWith("/api/") || rq.resourceType() === "document"))
      net.push({ m: rq.method(), p: u.pathname, s: res.status() }); });
  page.on("requestfailed", (rq) => { const u = new URL(rq.url());
    if (u.host === host && u.pathname.startsWith("/api/")) net.push({ m: rq.method(), p: u.pathname, s: 0 }); });
  const pageErrors = []; page.on("pageerror", e => pageErrors.push(String(e).slice(0, 200)));
  // 別タブ: 開いた瞬間に数え、host は読み込み後に確定する（分類が host 確定を待てるように）
  let popupHosts = [], popupOpened = 0;
  // 2026-10-13 修正: 空の URL で new URL が投げ、未処理の例外で走行全体が落ちていた（本走A3で1本）。
  // 開いた手の番号を札として持たせ、遅れて確定した別タブが次の手に数えられないようにする。
  let curStep = 0;
  ctx.on("page", async (pg) => { if (pg === page) return; const st = curStep; popupOpened++;
    try { await pg.waitForURL(u => !String(u).startsWith("about:"), { timeout: 8000 }); } catch (e) {}
    let url = "", h = "invalid"; try { url = pg.url(); h = new URL(url).host; } catch (e) {}
    rec({ ev: "popup", step: st, url, host: h });
    if (st === curStep) popupHosts.push({ host: h, url });
    await pg.close().catch(() => {}); });

  rec({ ev: "start", run: runId, persona: P.id, group: P.group, seed: SEED, concept, condition: COND, base: BASE, model: MODEL, mutate: process.env.SIM_MUTATE || null,
        scenario_sha256: crypto.createHash("sha256").update(scenRaw).digest("hex"), max_steps: P.max_steps });
  const t0 = Date.now();
  await page.goto(BASE + "/", { waitUntil: "networkidle", timeout: 30000 }).catch(e => rec({ ev: "goto_error", err: String(e).slice(0, 200) }));
  await settle(page);
  const history = []; let end = "step_limit";
  for (let step = 1; step <= P.max_steps; step++) {
    const before = await observe(page);
    const view = render(before, history);
    const a = callActor(actorPrompt(view, step));
    if (!a.ok) { rec({ ev: "actor_error", step, ...a }); end = "actor_error"; break; }
    const act = a.out.action || {}; let desc = "", adesc = "", rejected = null;
    curStep = step; popupHosts = []; popupOpened = 0; net.length = 0; const ts = Date.now();
    try {
      if (act.kind === "stop") { rec({ ev: "step", step, view_chars: view.length, actor: a.out, actor_ms: a.ms, model: a.model }); end = "stop:" + (act.stop_reason || "unspecified"); break; }
      if (act.kind === "click") {
        if (act.id >= 1000 && before.nodes[act.id - 1000]) { const n = before.nodes[act.id - 1000];
          await page.mouse.click(n.x, n.y); desc = `図の語「${n.label}」を押した`; adesc = OT.node(n.label); }
        else if (before.items[act.id] && !before.items[act.id].input) { const it = before.items[act.id];
          await page.evaluate((i) => window.__simEls[i].scrollIntoView({ block: "center" }), act.id);
          const h = await page.evaluateHandle((i) => window.__simEls[i], act.id);
          await h.asElement().click({ timeout: 5000 }); desc = `「${it.label}」を押した`; adesc = OT.clicked(it.label); }
        else rejected = "no_such_clickable";
      } else if (act.kind === "type_submit") {
        const it = before.items[act.id]; let text = (act.text || "").trim();
        if (!P.writer.can_type) rejected = "persona_cannot_type";
        else if (!it || !it.input) rejected = "not_an_input";
        else if (!text) rejected = "empty_text";
        else if (text.length > P.writer.max_len) rejected = "too_long_for_persona";
        else if (!typedAllowed(text, P.writer.scripts)) rejected = "script_not_typable_by_persona";
        else { const typed = typo(text);
          const h = await page.evaluateHandle((i) => window.__simEls[i], act.id);
          await h.asElement().fill(""); await h.asElement().type(typed, { delay: 5 }); await h.asElement().press("Enter");
          desc = `「${typed}」と入れて送った${typed !== text ? `（打ち間違い: 意図は「${text}」）` : ""}`; adesc = OT.typed(typed); }
      } else if (act.kind === "scroll_down") { await page.mouse.wheel(0, Math.round(before.viewH * 0.8)); desc = "下へ送った"; adesc = OT.scroll; }
      else if (act.kind === "back") { await page.goBack({ timeout: 10000 }).catch(() => {}); desc = "戻った"; adesc = OT.back; }
      else rejected = "unknown_kind";
    } catch (e) { rejected = "action_failed:" + String(e).split("\n")[0].slice(0, 120); }
    if (!rejected) { await page.waitForLoadState("networkidle", { timeout: 15000 }).catch(() => {}); await settle(page);
      for (let i = 0; i < 40 && popupHosts.length < popupOpened; i++) await page.waitForTimeout(200);
      // 同じサイトの新しいタブ（例 /origin?q=… を _blank で開く）は、人ならそのタブへ移って読む
      const same = popupHosts.find(x => x.host === host);
      if (same) { await page.goto(same.url, { waitUntil: "networkidle", timeout: 30000 }).catch(() => {}); await settle(page); } }
    const after = await observe(page);
    const observed = rejected ? "rejected" : classify(before, after, popupHosts);
    history.push({ step, adesc: adesc || `${act.kind} ${act.id ?? ""}`, aobs: rejected ? `${OT.rejected} (${rejected})` : OT[observed] });
    rec({ ev: "step", step, view_chars: view.length, actor: a.out, actor_ms: a.ms, model: a.model, cost: a.cost,
          rejected, desc, expect: a.out.expect, observed, act_ms: Date.now() - ts,
          from: before.path, to: after.path, n_items: after.items.length, n_nodes: after.nodes.length,
          text_len: after.text.length, masked_ratio: (mask(after.text).match(/□/g) || []).length / Math.max(1, after.text.length),
          net: net.slice(), popups: popupHosts.map(x => x.host), page_errors: pageErrors.splice(0) });
  }
  rec({ ev: "end", end, wall_ms: Date.now() - t0 });
  fs.closeSync(T);
  await b.close();
  console.log(`${runId}\t${end}\t${tracePath}`);
})().catch(e => { try { rec({ ev: "harness_error", err: String(e).slice(0, 400) }); } catch (_) {} console.error("SIM ERROR", e); process.exit(2); });
