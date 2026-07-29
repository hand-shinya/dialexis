// 普遍性の境界: graph取得失敗・root-only・人物ノード・ホバー帰路でも、操作帯(共通メニュー)と
// 戻る/進むが消えず同じmenuが使える（Codex対審E2の是正＋半田様の新バグ指摘の検査）。
const { chromium } = require("playwright-core");
const EXE = process.env.DX_CHROMIUM || "/home/handa/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome";
const BASE = process.argv[2] || "http://127.0.0.1:8012";
(async () => {
  const b = await chromium.launch({ executablePath: EXE, headless: true });
  const R=[]; const ok=(n,c,d)=>{R.push(c);console.log(`${c?"PASS":"FAIL"}  ${n}${d?"  — "+d:""}`);};
  async function shellState(page){
    return await page.evaluate(()=>({
      shell:(()=>{const s=document.getElementById("origin-shell");return s&&getComputedStyle(s).display!=="none";})(),
      chips:[...document.querySelectorAll("#graph-lens .tm-chip")].length,
      navBack:!!document.getElementById("nav-back"),
      navFwd:!!document.getElementById("nav-fwd"),
      thin:(()=>{const t=document.getElementById("graph-thin");return t&&getComputedStyle(t).display!=="none";})(),
    }));
  }
  // A) graph APIをroot-only(1ノード)に固定 → shell・共通メニュー・戻る/進むは出る、薄い表示に切替
  { const page=await b.newPage();
    await page.route("**/api/origin/graph**", r=>r.fulfill({status:200,contentType:"application/json",
      body:JSON.stringify({query:"X",nodes:[{id:"root",label:"X",kind:"word",layer:1,q:"X"}],edges:[],note:""})}));
    await page.goto(`${BASE}/origin?q=%E5%BC%81%E8%A8%BC%E6%B3%95&lang=ja`,{waitUntil:"networkidle"});
    await page.waitForTimeout(3000);
    const s=await shellState(page);
    ok("root-only: 操作shellが出る", s.shell, JSON.stringify(s));
    ok("root-only: 共通メニュー(帯)が消えない", s.chips>=6, `chips=${s.chips}`);
    ok("root-only: 戻る/進むが存在する", s.navBack&&s.navFwd);
    ok("root-only: 地図は薄い表示に切替(操作は残す)", s.thin);
    await page.close(); }
  // B) graph APIを失敗(abort)に固定 → 同上（操作帯と帰路が消えない）
  { const page=await b.newPage();
    await page.route("**/api/origin/graph**", r=>r.abort());
    await page.goto(`${BASE}/origin?q=%E5%BC%81%E8%A8%BC%E6%B3%95&lang=ja`,{waitUntil:"networkidle"});
    await page.waitForTimeout(3000);
    const s=await shellState(page);
    ok("graph失敗: 操作shell＋共通メニュー＋戻る進むが残る", s.shell&&s.chips>=6&&s.navBack&&s.navFwd, JSON.stringify(s));
    ok("graph失敗: 薄い/失敗表示に切替", s.thin);
    await page.close(); }
  // C) ホバー追従で対象変更後の「←メニュー」は"変更後のノード"へ戻る（MENUCTX更新・Codex E2）
  { const page=await b.newPage();
    await page.goto(`${BASE}/origin?q=%E5%BC%81%E8%A8%BC%E6%B3%95&lang=ja`,{waitUntil:"networkidle"});
    for(let i=0;i<20;i++){const v=await page.evaluate(()=>{const w=document.getElementById("origin-graph-wrap");return w&&getComputedStyle(w).display!=="none";});if(v)break;await page.waitForTimeout(600);}
    const title = await page.evaluate(()=>{
      gMenu(200,200,{kind:"word",label:"語A",q:"語A"});        // 最初のノードでメニュー
      gMenuRetarget({kind:"word",label:"語B",q:"語B"});         // ホバー追従で語Bへ差替
      const it=[...document.querySelectorAll("#graph-menu .gm-item")].find(e=>/解剖/.test(e.textContent));
      // メニュー項目クリックを模擬（_panelFromMenuを立てて解剖パネルを開く）
      __dx.setPanelFromMenu(true); document.querySelector("#graph-menu").remove(); gAnatomyPanel("語B");
      __dx.setPanelFromMenu(false);
      // パネルの「←メニュー」を押す
      const bk=document.querySelector("#graph-panel .gp-back"); if(bk) bk.click();
      const m=document.getElementById("graph-menu");
      return m?m.querySelector(".gm-title").textContent:"(none)";
    });
    ok("ホバー変更後の←メニューは変更後ノード(語B)へ戻る", /語B/.test(title), `title=${title}`);
    await page.close(); }
  // D) 人物(カール・マルクス)ノード: 壊れ記号ノードが無い＋原語を辿っても行き止まりでない
  { const page=await b.newPage();
    await page.goto(`${BASE}/origin?q=%E5%BC%81%E8%A8%BC%E6%B3%95&lang=ja`,{waitUntil:"networkidle"});
    for(let i=0;i<25;i++){const v=await page.evaluate(()=>__dx.G&&__dx.G.nodes&&__dx.G.nodes.some(n=>n.kind==="author"));if(v)break;await page.waitForTimeout(500);}
    // カール・マルクスに再中心
    const okc = await page.evaluate(async ()=>{ const n=(__dx.G.nodes||[]).find(x=>x.kind==="author"&&/マルクス/.test(x.label)); if(!n) return false; await originRecenter(n.q||n.label); return true; });
    await page.waitForTimeout(2500);
    const marx = await page.evaluate(()=>({
      garbage:(__dx.G_raw&&__dx.G_raw.nodes||[]).filter(n=>/\{\{|Post-nominal/.test(n.label)).map(n=>n.label),
      origs:(__dx.G_raw&&__dx.G_raw.nodes||[]).filter(n=>n.kind==="original").map(n=>n.label),
    }));
    ok("人物グラフに壊れ記号ノード({{Post-nominals)が無い", okc && marx.garbage.length===0, `garbage=${JSON.stringify(marx.garbage)}`);
    ok("人物の原語ノードが正常(Karl Marx等・行き止まりの記号でない)", marx.origs.every(l=>!/\{\{/.test(l)), `origs=${JSON.stringify(marx.origs)}`);
    // 原語ノードへ再中心してもnav戻るが有効（帰路が壊れない）
    const navOk = await page.evaluate(async ()=>{ const o=(__dx.G_raw.nodes||[]).find(n=>n.kind==="original"); if(o) await originRecenter(o.q||o.label); const nb=document.getElementById("nav-back"); return nb && !nb.disabled; });
    await page.waitForTimeout(1500);
    ok("原語へ再中心後も『戻る』が有効（帰路が普遍に保たれる）", navOk);
    await page.close(); }
  const pass=R.filter(Boolean).length;
  console.log(`\n${pass}/${R.length} PASS`);
  await b.close(); process.exit(pass===R.length?0:1);
})().catch(e=>{console.error("ERR",e);process.exit(2);});
