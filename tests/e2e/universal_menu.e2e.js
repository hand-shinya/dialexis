// 案C: 上部帯＝中心語の共通メニューパッケージを常時表示。全語・全ノードで同一UI（普遍性・P11）。
const { chromium } = require("playwright-core");
const EXE = "/home/handa/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome";
const BASE = process.argv[2] || "http://127.0.0.1:8012";
const CORE = ["中心に据える","組み合わせ","見方","外部で調べる","棚","深掘り"]; // 帯に必ず在る普遍コア(短縮)
(async () => {
  const b = await chromium.launch({ executablePath: EXE, headless: true });
  const p = await b.newPage();
  const R=[]; const ok=(n,c,d)=>{R.push(c);console.log(`${c?"PASS":"FAIL"}  ${n}${d?"  — "+d:""}`);};
  async function topChips(q){
    await p.goto(`${BASE}/origin?q=${encodeURIComponent(q)}&lang=ja`,{waitUntil:"networkidle"});
    for(let i=0;i<20;i++){const v=await p.evaluate(()=>{const w=document.getElementById("origin-graph-wrap");return w&&getComputedStyle(w).display!=="none";});if(v)break;await p.waitForTimeout(600);}
    return await p.evaluate(()=>[...document.querySelectorAll("#graph-lens .tm-chip")].map(c=>c.textContent));
  }
  // 1) 豊富な語（弁証法）で帯にコアが揃う
  const rich = await topChips("弁証法");
  ok("弁証法: 上部帯に共通メニューパッケージ", CORE.every(k=>rich.some(c=>c.includes(k))), `chips=${rich.length}`);
  // 2) 貧しい語（διαλεκτική）でも 帯は全く同じコア（0だらけの帯でなく同一パッケージ）
  const thin = await topChips("διαλεκτική");
  ok("διαλεκτική: 貧しい語でも同一の共通パッケージ", CORE.every(k=>thin.some(c=>c.includes(k))), `chips=${thin.length}`);
  ok("豊富/貧しいで帯のコア項目が一致（普遍・同一UI）", CORE.every(k=>rich.some(c=>c.includes(k))&&thin.some(c=>c.includes(k))));
  // 3) 「👓見方」を帯から開くとレンズ一覧（思想家/世界の言語/…）が出る
  await p.goto(`${BASE}/origin?q=${encodeURIComponent("弁証法")}&lang=ja`,{waitUntil:"networkidle"});
  for(let i=0;i<20;i++){const v=await p.evaluate(()=>{const w=document.getElementById("origin-graph-wrap");return w&&getComputedStyle(w).display!=="none";});if(v)break;await p.waitForTimeout(600);}
  await p.evaluate(()=>{const c=[...document.querySelectorAll("#graph-lens .tm-chip")].find(x=>x.textContent.includes("見方"));c&&c.click();});
  await p.waitForTimeout(400);
  const lensRows = await p.$$eval(".lens-row b", els=>els.map(e=>e.textContent));
  ok("👓見方＝レンズ一覧（思想家/世界の言語 等）が出る", lensRows.some(t=>/思想家/.test(t))&&lensRows.some(t=>/世界の言語/.test(t)), `rows=${lensRows.length}`);
  // 4) レンズを選ぶと描画が切替（俯瞰以外へ）— <b>ラベルで厳密に「思想家と著作」を選ぶ
  await p.evaluate(()=>{const r=[...document.querySelectorAll(".lens-row")].find(x=>x.querySelector("b").textContent.trim()==="思想家と著作");r&&r.click();});
  await p.waitForTimeout(2500);
  const noteAfter = await p.evaluate(()=>(document.getElementById("graph-note")||{}).textContent||"");
  ok("レンズ適用で見方が『思想家と著作』へ切替（graph-note）", /見方：思想家と著作/.test(noteAfter), `note=${noteAfter.slice(0,24)}`);
  // 5) gActions が全kindで同一コアを返す（プログラム的・普遍の核）
  const kinds = await p.evaluate(()=>{
    const ks=["word","original","language","related","author"];
    const has=(n)=>{const a=gActions({kind:n,label:"X",q:"X"});return ["中心に据え直す","組み合わせ","見方","外部","棚","深掘り"].every(k=>a.some(i=>i.t.includes(k)||(i.s||"").includes(k.slice(0,2))));};
    return ks.map(k=>[k,has(k)]);
  });
  ok("gActionsが全kind(word/original/language/related/author)で共通コアを持つ", kinds.every(([k,v])=>v), JSON.stringify(kinds));
  // 6) ノードをクリック→同じ共通パッケージがポップアップ（帯と同一UI）→パネルに「←メニュー」戻る導線
  await p.goto(`${BASE}/origin?q=${encodeURIComponent("弁証法")}&lang=ja`,{waitUntil:"networkidle"});
  for(let i=0;i<20;i++){const v=await p.evaluate(()=>{const w=document.getElementById("origin-graph-wrap");return w&&getComputedStyle(w).display!=="none";});if(v)break;await p.waitForTimeout(600);}
  // ルートノード(中心語)をプログラム的にメニュー表示（座標クリックの不安定を避け、gMenuを直接）
  const popupItems = await p.evaluate(()=>{ const n=(window.G&&window.G.nodes||[]).find(x=>x.kind==="word")||{kind:"word",label:"弁証法",q:"弁証法"}; gMenu(200,200,n); return [...document.querySelectorAll("#graph-menu .gm-item")].map(e=>e.textContent); });
  ok("ノードのポップアップメニューが共通パッケージ（解剖/並置/外部/棚）", ["解剖","並べて比べる","外部","棚"].every(k=>popupItems.some(t=>t.includes(k))), `items=${popupItems.length}`);
  // 解剖を選ぶ→パネルに「←メニュー」戻るボタンが在る
  await p.evaluate(()=>{const it=[...document.querySelectorAll("#graph-menu .gm-item")].find(e=>/解剖/.test(e.textContent));it.click();});
  await p.waitForTimeout(600);
  const hasBack = await p.evaluate(()=>!!document.querySelector("#graph-panel .gp-back"));
  ok("メニューから開いたパネルに『←メニュー』戻る導線がある", hasBack);
  // 戻る→ポップアップメニューが再表示（別メニューを選び直せる）
  await p.evaluate(()=>{const bk=document.querySelector("#graph-panel .gp-back");bk&&bk.click();});
  await p.waitForTimeout(400);
  const reopened = await p.evaluate(()=>!!document.querySelector("#graph-menu"));
  ok("『←メニュー』でノードのメニューが再表示（別項目を選び直せる）", reopened);
  const pass=R.filter(Boolean).length;
  console.log(`\n${pass}/${R.length} PASS`);
  await b.close(); process.exit(pass===R.length?0:1);
})().catch(e=>{console.error("ERR",e);process.exit(2);});
