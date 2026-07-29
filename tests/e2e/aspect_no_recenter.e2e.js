// 第2階層ノードのmenu(埋没/多言語/意味)は中心を変えずパネルで見せる（半田様指摘）＋gColloc否定ゼロ。
const { chromium } = require("playwright-core");
const EXE = process.env.DX_CHROMIUM || "/home/handa/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome";
const B = process.argv[2] || "http://127.0.0.1:8017";
(async () => {
  const b = await chromium.launch({ executablePath: EXE, headless: true }); const p = await b.newPage();
  const R=[]; const ok=(n,c,d)=>{R.push(c);console.log(`${c?"PASS":"FAIL"}  ${n}${d?"  — "+d:""}`);};
  await p.goto(`${B}/origin?q=%E5%BC%81%E8%A8%BC%E6%B3%95&lang=ja`,{waitUntil:"networkidle"});
  for(let i=0;i<20;i++){const v=await p.evaluate(()=>{const w=document.getElementById("origin-graph-wrap");return w&&getComputedStyle(w).display!=="none";});if(v)break;await p.waitForTimeout(600);}
  const rootBefore = await p.evaluate(()=>__dx.G.rootQ);
  // 矛盾ノードのmenuから「埋没/多言語/意味」→ 中心は弁証法のまま
  for (const [asp, kw] of [["collapse","埋没"],["breadth","多言語"],["meaning","意味"]]) {
    await p.evaluate((asp)=>{ gWordAspect("矛盾", asp); }, asp);
    await p.waitForTimeout(2200);
    const st = await p.evaluate(()=>({root:__dx.G.rootQ, panel:!!document.getElementById("graph-panel"),
      body:(document.querySelector("#graph-panel .gp-body")||{}).textContent||""}));
    ok(`「${kw}」で中心が弁証法のまま変わらない`, st.root===rootBefore, `root=${st.root}`);
    ok(`「${kw}」パネルが矛盾の情報を出す`, st.panel && st.body.length>0);
  }
  // gColloc 矛盾: 否定表現ゼロ＋続行フッター
  const BAD=["できません","引けません","特定でき","見つかり","失敗","ありません","unavailable","not found"];
  await p.evaluate(()=>gColloc("矛盾"));
  await p.waitForTimeout(2600);
  const col = await p.evaluate(()=>({body:(document.querySelector("#graph-panel .gp-body")||{}).textContent||"",
    cont:document.querySelectorAll("#graph-panel .gp-cont-b").length}));
  ok("gColloc(矛盾)に否定表現ゼロ", !BAD.some(w=>col.body.includes(w)), col.body.slice(0,60));
  ok("gColloc(矛盾)に続行フッターあり(行き止まりでない)", col.cont>=5);
  const pass=R.filter(Boolean).length; console.log(`\n${pass}/${R.length} PASS`);
  await b.close(); process.exit(pass===R.length?0:1);
})().catch(e=>{console.error("ERR",e);process.exit(2);});
