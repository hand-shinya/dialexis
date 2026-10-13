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
  // 語単位の未知語（評価資料 P-01 の語彙マスク）。指定があるときだけ働く。字の数だけ □ にする
  const unknown = (reader.unknown_words || []).slice().sort((x, y) => y.length - x.length);
  const esc = (w) => w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const wordMask = (t) => unknown.reduce((acc, w) => acc.replace(new RegExp(esc(w), "gi"), (m) => "□".repeat([...m].length)), t || "");
  if (s.includes("any")) return (t) => wordMask(t);
  return (t) => [...wordMask(t)].map(c => c === "□" || readable(c, s) ? c : "□").join("");
}

function typedAllowed(text, scripts, unknownWords) {
  // 知らない語は打てない（見えていないので）
  if ((unknownWords || []).some(w => text.toLowerCase().includes(w.toLowerCase()))) return false;
  // □ はマスクの記号で、人が打つ字ではない（\p{S} に入るので punct が通していた）
  if (text.includes("□")) return false;
  return [...text].every(c => readable(c, scripts));
}

module.exports = { makeMask, typedAllowed, KYOIKU_SIZE: KYOIKU.size };
