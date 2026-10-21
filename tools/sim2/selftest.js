// オラクル自身の試験。悪い例で FAIL を出せないオラクルは使わない（参考資料 ステップ9 変異試験）
"use strict";
const O = require("./oracles");
let pass = 0, fail = 0; const t = (n, c) => { c ? pass++ : fail++; console.log(`${c ? "PASS" : "FAIL"}  ${n}`); };
const anat = "語全体 existentialism 語源的なまとまり existential ＋ -ism From existential + -ism (suffix forming the names of schools of thought), modelled after German Existentialismus.";
t("写し（解剖と同じ中身）を重複と判定する", O.duplicate("主要な源では十分な結果が得られなかったため、別の情報源に自動で切り替えて取得しました。 " + anat, [{ label: "anatomy", text: anat }]).fail);
t("別の内容は重複としない", !O.duplicate("Kurdish: Hebûnparêzî アイスランド語: tilvistarstefna ウェールズ語: Dirfodaeth", [{ label: "anatomy", text: anat }]).fail);
const ti = new O.TemplateIndex();
const tmpl = "中心命題から派生した項目を、同じ意味の語としてではなく、著作・思想・歴史・受容の接続として確認する。人物名の表記差、著作題名の翻訳差、引用・影響関係を別々の証拠単位で確認する。";
["ヘーゲル", "精神現象学", "親密性"].forEach(w => ti.add(w, tmpl));
t("3語に同じ文が出る＝定型文率が高い", ti.ratio(tmpl) > 0.9);
t("語に固有の文は定型文としない", ti.ratio("マルクスは、この疎外Entfremdungという用語をヘーゲルの『精神現象学』（1807年）から継承した。") < 0.1);
t("関係の根拠: 両方の語を含む文を数える", O.specificity("マルクスは疎外という用語をヘーゲルの『精神現象学』から継承した。", "疎外", "G.W.F. ヘーゲル") === 1);
t("関係の根拠: 定型文は0", O.specificity(tmpl, "疎外", "G.W.F. ヘーゲル") === 0);
t("同一性: 転送を検出する", O.identity("実存", { title: "実存主義" }).status === "redirected");
t("行き止まり: 語1つで戻り道なしは FAIL", O.deadEnd({ map: { n: 3, kinds: { word: 1, language: 1, domain: 1 } }, smallMap: false, decomp: [] }).fail);
t("行き止まり: 戻り道があれば FAIL にしない", !O.deadEnd({ map: { n: 3, kinds: { word: 1, language: 1, domain: 1 } }, smallMap: true, decomp: [] }).fail);
t("新規性: 地図に無い語を数える", O.novelty("フォイエルバッハ と キリスト教の本質", new Set(["疎外"])).n >= 2);
// 関係の根拠: 語だけ違う定型文は、伏せ字にすると同じ文になる＝根拠に数えない
const ti2 = new O.TemplateIndex();
const rel = (c, t) => `中心命題「${c}」から派生した「${t}」を、同じ意味の語としてではなく、著作・思想・歴史・受容の接続として確認する。`;
[["疎外", "カール・マルクス"], ["実存", "existentialism"], ["疎外", "精神現象学"]].forEach(([c, t], i) => ti2.add("n" + i, O.normTerms(rel(c, t), [c, t])));
const normed = O.sentences(O.normTerms(rel("疎外", "G.W.F. ヘーゲル"), ["疎外", "G.W.F. ヘーゲル"]))[0];
t("関係の根拠: 語だけ違う定型文は、伏せ字で同じ文になり数えない", (ti2.seen.get(normed) || new Set()).size >= 2);
console.log(`\n${pass}/${pass + fail} PASS`); process.exit(fail ? 1 : 0);
