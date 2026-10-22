"""深掘りのプロンプトの原型（所有者 2026-10-23）。

所有者の操作: 実存 → アリストテレス → 深掘り探索プロンプト で、別ページに名前だけが入り、
目的は空、プロンプトは「生成」を押すまで出なかった。生成器も、目的の文を読点で12の断片に切り、
人名の表記（Aristotle / Ἀριστοτέλης）を「日本語に埋没した原語」として扱っていた。
"""
from app import deepsearch

TRAIL = {"center": "実存", "path": ["実存", "関係 アリストテレス"],
         "evidence": [{"text": "アリストテレス及びスコラ哲学では、実存を本質に抗する概念としてとらえている。",
                       "article": "実存主義", "retrieved_at": "2026-10-22T14:58:11+00:00"}]}


def test_goal_is_split_only_at_sentence_ends():
    g = "「実存」を探るなかで、アリストテレスとのつながりを確かめたい。第一実体と、後世の existentia の区別は、どこで別物か？"
    assert deepsearch._sub_questions(g) == ["「実存」を探るなかで、アリストテレスとのつながりを確かめたい",
                                            "第一実体と、後世の existentia の区別は、どこで別物か"]


def test_path_and_evidence_lead_the_prompt_with_source_and_date():
    t = deepsearch.generate("アリストテレス", "", "claude", "ja", dict(TRAIL))
    assert "# 調査依頼: 「実存」と「アリストテレス」のつながり" in t
    assert "## 0-1. Dialexis で辿った経路と、そこで得た根拠" in t
    assert "辿った経路: 実存 → 関係 アリストテレス" in t
    assert "実存を本質に抗する概念としてとらえている。」（実存主義、取得 2026-10-22）" in t
    # 目的が空でも、つながりそのものが問いになる
    assert "1. 「実存」と「アリストテレス」は、どこでつながり、どこで別物か" in t
    assert "私が「実存」と「アリストテレス」のつながりで本当に知りたいこと" in t


def test_two_section_zeros_are_numbered_apart_and_references_follow():
    ctx = dict(TRAIL, debate=["Category Theory"], description="古代ギリシアの哲学者")
    t = deepsearch.generate("アリストテレス", "", "claude", "ja", ctx)
    heads = [line for line in t.split("\n") if line.startswith("## 0")]
    assert heads[0].startswith("## 0-1.") and heads[1].startswith("## 0-2.")
    assert "上の §0-2 の論争構造" in t


def test_person_names_are_transliterations_not_buried_words():
    ctx = {"is_person": True, "orig_labels": {"en": "Aristotle", "el": "Αριστοτέλης"}, "description": "古代ギリシアの哲学者"}
    t = deepsearch.generate("アリストテレス", "", "claude", "ja", ctx)
    assert "転写であって訳語ではない" in t
    assert "埋没していないか" not in t
    assert "訳される近縁の別語" not in t
    assert "主要著作を原題・成立年・校訂版で挙げ" in t


def test_lead_does_not_say_nothing_is_attached_when_the_path_is():
    t = deepsearch.generate("アリストテレス", "", "claude", "ja", dict(TRAIL))
    assert "手がかりを付けていません" not in t
    e = deepsearch.generate("Aristotle", "", "claude", "en", {"center": "existence", "evidence": TRAIL["evidence"]})
    assert "No machine-retrieved leads" not in e and "the connection between “existence” and “Aristotle”" in e


def test_without_a_path_the_prompt_keeps_its_previous_shape():
    t = deepsearch.generate("疎外", "", "claude", "ja", {"orig_labels": {"de": "Entfremdung"}})
    assert "# 調査依頼: 「疎外」（Entfremdung（独））" in t
    assert "## 0-1." not in t and "埋没していないか" in t
