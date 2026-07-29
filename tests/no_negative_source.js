// 静的gate（原理的普遍化・半田様2026-07-29）: ソース全体を走査し、ユーザーに見える「〜できません/
// 引けません/見つかりません/失敗」等の"否定的結末"文が残っていないことを機械保証する。実行時の語×
// パネル列挙(=外延的・漏れる)でなく、ソース全走査(=網羅的)で担保する。新規/変種/将来分も自動で捕える。
const fs = require("fs");
const path = require("path");
const FILES = ["app/static/app.js"];
// 否定的"結末"のパターン（できる/られる等の肯定は含めない・タイトに）。
const BAD = [
  /できませんでした/, /できません(?!か)/, /でき(ず|ない)[、。」\s]/, /引けま(せん|ない)/,
  /特定でき(ません|ず|ない)/, /見つかりませんでした/, /見つかりません/, /見つから(ない|ず)/,
  /取得でき(ませんでした|ません|ず|ない)/, /出題でき(ません|ない)/, /ありませんでした/,
  /失敗しました/, /失敗(?=[。」\s])/,
  /no data/i, /not found/i, /no result/i, /no usage/i, /no series/i, /no etymology/i, /unavailable/i, /\bfailed\b/i,
];
// 明示的に許可する行（否定でない・またはコメント内の設計記述）: 行末に /* neg-ok */ を付けた行のみ。
function stripComments(src) {
  // 行コメント //... と ブロック /* */ を空白化（文字列内の // を雑に消さないよう、素朴だが十分）
  src = src.replace(/\/\*[\s\S]*?\*\//g, m => m.replace(/[^\n]/g, " "));
  return src.split("\n").map(line => {
    // 行コメント: 文字列/正規表現の外の // を近似的に検出（" ' ` の対応が閉じている位置以降）
    let inS = null, esc = false, out = line;
    for (let i = 0; i < line.length - 1; i++) {
      const c = line[i];
      if (esc) { esc = false; continue; }
      if (c === "\\") { esc = true; continue; }
      if (inS) { if (c === inS) inS = null; continue; }
      if (c === '"' || c === "'" || c === "`") { inS = c; continue; }
      if (c === "/" && line[i + 1] === "/") { out = line.slice(0, i); break; }
    }
    return out;
  });
}
let violations = [];
for (const f of FILES) {
  const abs = path.join(process.cwd(), f);
  const lines = stripComments(fs.readFileSync(abs, "utf8"));
  lines.forEach((line, i) => {
    if (/neg-ok/.test(line)) return;
    for (const re of BAD) {
      if (re.test(line)) { violations.push(`${f}:${i + 1}  [${re}]  ${line.trim().slice(0, 100)}`); break; }
    }
  });
}
if (violations.length) {
  console.log(`FAIL  否定的結末の残存 ${violations.length} 件（ユーザーに見える否定表示は0でなければならない）:`);
  violations.forEach(v => console.log("  " + v));
  process.exit(1);
} else {
  console.log("PASS  ソース全走査: 否定的結末の表示は0件（原理的普遍化・網羅保証）");
  process.exit(0);
}
