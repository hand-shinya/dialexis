// D: ビュー遷移(見方切替・この分岐を中心に)も戻る/進むで辿れる（半田様指摘）＋Aの文言＋C言語名。
const { chromium } = require("playwright-core");
const EXE = "/home/handa/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome";
const B = process.argv[2] || "http://127.0.0.1:8020";
(async () => {
  const b = await chromium.launch({ executablePath: EXE, headless: true }); const p = await b.newPage();
  const R=[]; const ok=(n,c,d)=>{R.push(c);console.log(`${c?"PASS":"FAIL"}  ${n}${d?"  — "+d:""}`);};
  const waitG=async()=>{for(let i=0;i<25;i++){const v=await p.evaluate(()=>{const w=document.getElementById("origin-graph-wrap");return w&&getComputedStyle(w).display!=="none";});if(v)return;await p.waitForTimeout(600);}};
  await p.goto(`${B}/origin?q=%E5%BC%81%E8%A8%BC%E6%B3%95&lang=ja`,{waitUntil:"networkidle"}); await waitG();
  // 見方→世界の言語 に切替
  await p.evaluate(()=>{[...document.querySelectorAll("#graph-lens .tm-chip")].find(x=>x.textContent.includes("見方")).click();});
  await p.waitForTimeout(300);
  await p.evaluate(()=>{const r=[...document.querySelectorAll(".lens-row")].find(x=>x.querySelector("b").textContent.trim()==="世界の言語");r.click();});
  await p.waitForTimeout(1800);
  const lensKinds=await p.evaluate(()=>[...new Set((__dx.G.nodes||[]).map(n=>n.kind))]);
  ok("世界の言語レンズが適用(language中心)", lensKinds.includes("language"), JSON.stringify(lensKinds));
  const backEnabled1=await p.evaluate(()=>!document.getElementById("nav-back").disabled);
  ok("見方切替後、戻るボタンが有効になる", backEnabled1);
  // 俯瞰へ戻す（focusテストは俯瞰のdomainノードで＝実ユーザー導線）
  await p.evaluate(()=>navGo(-1)); await p.waitForTimeout(1500);
  // 俯瞰の 世界の言語 domainノードで「この分岐を中心に」
  const focused=await p.evaluate(()=>{const idx=(__dx.G.nodes||[]).findIndex(n=>n.kind==="domain"&&/世界の言語/.test(n.label));if(idx<0)return "no-domain";gFocusSubtree(idx);return __dx.G.focusLabel;});
  await p.waitForTimeout(800);
  ok("俯瞰の『この分岐を中心に』でfocusされる", /世界の言語/.test(String(focused)), `focus=${focused}`);
  const backEnabled2=await p.evaluate(()=>!document.getElementById("nav-back").disabled);
  ok("focus後も戻るボタンが有効（画面遷移が履歴に乗る）", backEnabled2);
  // 戻る → focus解除（俯瞰へ）
  await p.evaluate(()=>navGo(-1)); await p.waitForTimeout(1500);
  const afterBack=await p.evaluate(()=>({focus:__dx.G.focusLabel, kinds:[...new Set((__dx.G.nodes||[]).map(n=>n.kind))]}));
  ok("戻るでfocusが解除され俯瞰へ（普遍的な画面遷移）", !afterBack.focus && afterBack.kinds.length>=3, `focus=${afterBack.focus} kinds=${JSON.stringify(afterBack.kinds)}`);
  // A: softLineの文言が実フッター表記と齟齬しない（「この語で続ける」literalを本文に出さない）
  await p.evaluate(()=>gWordAspect("矛盾","collapse")); await p.waitForTimeout(2000);
  const body=await p.evaluate(()=>(document.querySelector("#graph-panel .gp-body")||{}).textContent||"");
  ok("A: 本文に実在しない「この語で続ける」literalを出さない", !body.includes("この語で続ける"), body.slice(0,50));
  // C: 弁証法breadthに生コード言語が残らない（API）
  const raw=await p.evaluate(async()=>{const d=await(await fetch("/api/origin?q=%E5%BC%81%E8%A8%BC%E6%B3%95&lang=ja")).json();return d.breadth.filter(b=>b.name.length<=4&&/^[a-z-]+$/.test(b.name)).map(b=>b.name);});
  ok("C: breadthに生コード言語が残らない", raw.length===0, `raw=${JSON.stringify(raw.slice(0,8))}`);
  const pass=R.filter(Boolean).length; console.log(`\n${pass}/${R.length} PASS`);
  await b.close(); process.exit(pass===R.length?0:1);
})().catch(e=>{console.error("ERR",e);process.exit(2);});
