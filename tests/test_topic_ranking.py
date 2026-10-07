"""入力文の主題を先頭に出す試験（2026-10-07）。

なぜ必要か（10人の入力文を本番に投げた実測）:
  先頭に出た語が本人の問いと一致したのは3人だけだった。
  45歳の「権利」は3番目、15歳の「ふつう」はかな書きのため1語も挙がらず、
  52歳の文からは「パスカル」が選ばれ、1手進むと「気圧」になった。
  語の希少さではなく、文の形が主題を示す。

外部取得なし・決定論。
"""
from app.main import promote_topics, synthetic_topics, topic_terms

S1 = "自然に振る舞うって何。ありのまま？でも人工物と反対の『自然環境』の自然と同じ字なのはなんで"
S4 = "校則っておかしくないですか。みんなが守るべき正義って言われるけど、決めた大人の都合でしかないじゃん。正義ってなんなの。"
S5 = "夫婦関係で愛が冷めたと言われた。家族愛、恋愛、無償の愛。全部『愛』で片付けるのは無理があるのでは。"
S6 = "時間はあるのに何をしていいかわからない。暇と退屈の違いについて。パスカルの退屈論の原典箇所の確認。"
S8 = "働くことと作ることの差ってどこにある？ 労働という言葉が苦役ばかりを想起させる。"
S10 = "みんな『ふつうこうでしょ』って言うけど、ふつうって誰が決めたの？多数派と正常って同じことなのかな。"


def _flag(*pairs):
    return [{"word": w, "count": c, "weight": 1, "tier": "参考"} for w, c in pairs]


def test_quoted_and_framed_terms_are_topics():
    assert "自然環境" in topic_terms(S1)
    assert "正義" in topic_terms(S4)
    assert "愛" in topic_terms(S5)
    assert "ふつう" in topic_terms(S10)


def test_pair_contrast_takes_both_sides():
    t = topic_terms(S6)
    assert "暇" in t and "退屈" in t


def test_frequency_beats_a_quoted_phrase():
    """『自然環境』より、2回書かれた「自然」が先に来る。"""
    flagged = _flag(("自然環境", 1), ("自然", 2), ("人工物", 1))
    out = promote_topics(flagged, topic_terms(S1))
    assert out[0]["word"] == "自然"


def test_asked_word_outranks_a_rarer_neighbour():
    """17歳の文で、先頭が「校則」ではなく「正義」になる。"""
    flagged = _flag(("校則", 1), ("正義", 2), ("大人", 1))
    out = promote_topics(flagged, topic_terms(S4))
    assert out[0]["word"] == "正義"


def test_kana_word_is_added_when_the_scanner_misses_it():
    """「ふつう」はかな書きで字種の走査に挙がらない。本人が問うているので足す。"""
    flagged = _flag(("多数派", 1), ("正常", 1))
    syn = synthetic_topics(flagged, topic_terms(S10))
    assert [s["word"] for s in syn] == ["ふつう"]
    assert syn[0]["tier"] == "主題"
    out = promote_topics(flagged + syn, topic_terms(S10))
    assert out[0]["word"] == "ふつう"


def test_single_char_word_is_added():
    """1字の「愛」も同じ理由で足す。"""
    flagged = _flag(("全部", 1), ("恋愛", 1), ("無償", 1))
    syn = synthetic_topics(flagged, topic_terms(S5))
    assert "愛" in [s["word"] for s in syn]
    out = promote_topics(flagged + syn, topic_terms(S5))
    assert out[0]["word"] == "愛"


def test_clauses_are_not_added_as_terms():
    """「働くこと」のような句は語として引けないので足さない。"""
    syn = synthetic_topics(_flag(("労働", 1)), topic_terms(S8))
    assert not any("こと" in s["word"] for s in syn)


def test_promotion_adds_the_reason_to_the_signals():
    flagged = _flag(("正義", 2))
    out = promote_topics(flagged, topic_terms(S4))
    ids = [s["id"] for s in out[0].get("signals", [])]
    assert "asked_in_text" in ids


def test_no_topics_leaves_the_order_alone():
    """問いの形が無い入力（語の羅列）では並べ替えない。"""
    flagged = _flag(("主張", 1), ("権利", 1))
    assert promote_topics(flagged, topic_terms("権利 主張 わがまま 義務 先")) == flagged
