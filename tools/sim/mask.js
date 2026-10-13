// 語彙マスク（決定論）。ペルソナが読めない字を □ に置き換え、打てない字を含む入力を拒む。
// prompt に「この字は読めない」と書くのでなく、Actor に届く文字そのものを変える（§8.4）。
"use strict";
const fs = require("fs");
const path = require("path");

const KYOIKU = new Set([...fs.readFileSync(path.join(__dirname, "kyoiku_kanji.txt"), "utf8")
  .split("\n").filter(l => l && !l.startsWith("#")).join("")]);

const CLASS = {
  latin: (c) => /[A-Za-zÀ-ɏḀ-ỿ]/.test(c),
  digits: (c) => /[0-9０-９]/.test(c),
  punct: (c) => /[\s\p{P}\p{S}]/u.test(c),
  kana: (c) => /[぀-ヿㇰ-ㇿｦ-ﾟ]/.test(c),
  kanji_all: (c) => /\p{Script=Han}/u.test(c),
  kanji_kyoiku: (c) => KYOIKU.has(c),
  georgian: (c) => /[Ⴀ-ჿᲐ-Ჿ]/.test(c),
};

function readable(c, scripts) {
  if (scripts.includes("any")) return true;
  return scripts.some(s => CLASS[s] && CLASS[s](c));
}

function makeMask(reader) {
  const s = reader.scripts;
  if (s.includes("any")) return (t) => t || "";
  return (t) => [...(t || "")].map(c => readable(c, s) ? c : "□").join("");
}

function typedAllowed(text, scripts) {
  // □ はマスクの記号で、人が打つ字ではない（\p{S} に入るので punct が通していた）
  if (text.includes("□")) return false;
  return [...text].every(c => readable(c, scripts));
}

module.exports = { makeMask, typedAllowed, KYOIKU_SIZE: KYOIKU.size };
