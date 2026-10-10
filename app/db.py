"""Dialexis database layer.

Single-file SQLite with a graph-shaped schema. This is deliberate (GENESIS.md
axiom 7: exit-ability): everything here exports to Markdown / JSON-LD, and the
whole store is one copyable file. Migration path to a graph DB is documented
in docs/ROADMAP.md.
"""
import sqlite3
import os
import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.environ.get("DIALEXIS_DB", os.path.join(BASE_DIR, "data", "dialexis.db"))

NODE_TYPES = ("question", "claim", "evidence", "counterclaim", "uncertainty",
              "interpretation", "decision", "note", "source",
              # 2026-10-08 追加。所有者の「非有機的肉体」研究の復元から。
              # 研究を実際に進めた3つの動きが、systemに1つも無かった。
              #   provisional 暫定定義と、そこから落ちた契機（自分で却下する段）
              #   memory      自分の記憶を、出典なしの独立した枝として立てる段
              #   naming      命名を保留したまま、問いを言い換えて進む段
              # いずれも人の判断であり、AIが代行すると価値が消える（下記 HUMAN_ONLY_TYPES）。
              "provisional", "memory", "naming")
# 人の判断を記録する型。**追記のみ**で、作成後は内容・型・確度・statusを変えられない。
#
# 2026-10-08 の敵対的検証で、当初の設計（origin != human を入口で拒否する）が
# 守れないことが実証された。requestの発信者が人かAIかを判定する機構はこのsystemに
# 存在せず、`origin` はclientの自己申告である。originを書かなければ既定で human になり、
# 型を後から付け替えれば確度も status も迂回でき、人が書いた欄も3往復で洗えた。
# 「AIが書けない」という宣言は実装の実力を超えていた（公理3違反）。
#
# よって保証する内容を、守れるものに置き換えた。
#   保証する : 一度記録した人の判断は、黙って書き換えられない（追記のみ・型変換禁止）
#   保証しない: 発信者が人であること（`origin` は自己申告である）
# 訂正は上書きでなく、新しいnodeと `supersedes` 辺で表す。命名の採用も、naming を
# `adopted` に書き換えるのではなく、別の `decision` node を日付つきで足して表す。
#
# 根拠（実測）: 所有者の研究で分岐を作った3つの瞬間の引き金は、すべて人の動きだった
# （資料0件・AI0件）。AIが暫定定義を書けば、却下が「移動」でなく「修正」になる。
# AIは正しいものしか書かないため、誤った記憶から枝が生まれる余地も消える。
# 誤る権利は人の側にある。守るべきはその記録が消えないことである。
HUMAN_ONLY_TYPES = ("provisional", "memory", "naming")
# `origin` は自己申告である。この事実をpayloadと画面から落とさない（公理3）。
# 報告の種別。利用者が選ぶ。自由記述だけにすると、何の報告か分けられない。
REPORT_KINDS = ("表示が事実と合わない", "取得が進まない", "意味が分かりにくい",
                "こう変えてほしい", "その他")

ORIGIN_IS_SELF_DECLARED = (
    "origin はclientの自己申告であり、systemは発信者が人かAIかを判定しない。"
    "保証されるのは、記録が追記のみで黙って書き換えられないことである。")
CONFIDENCE = ("confirmed", "high_probability", "unverified",
              "interpretive_hypothesis", "speculation")
ORIGINS = ("human", "ai", "external")
STATUSES = ("open", "adopted", "held", "rejected")
# supersedes は 2026-10-08 追加。追記のみの記録を「訂正」するための唯一の手段で、
# 409 の文がこの辺を指示している。語彙に無いまま指示していた（公理3違反）。
RELATIONS = ("supports", "contradicts", "answers", "refines", "derives_from",
             "supersedes",
             "cites", "about", "responds_to")
# Argument-reconstruction vocabularies (E1-E5). These are NEW domain vocabularies
# for the argument layer; they do not touch the confidence classification that
# GENESIS axiom 6 fixes, nor NODE_TYPES/RELATIONS. Validity and soundness are
# kept as SEPARATE fields on purpose (妥当性 ≠ 健全性 must never be conflated).
VALIDITY = ("valid", "invalid", "unassessed")
SOUNDNESS = ("sound", "unsound", "unassessed")
# "voice" (whose philosophical claim a premise reconstructs) is distinct from
# nodes.origin (who created the row in the tool: human/ai/external).
VOICES = ("author", "commentator", "self")

# Research ledgers are reusable evidence assets, distinct from projects (the
# user's arguments and interpretations).  These vocabularies are deliberately
# kept separate from NODE_TYPES/CONFIDENCE: a ledger record can be a candidate
# translation without becoming a confirmed project claim.
# A ledger may begin with a word, but a later research pass can attach a
# sentence/quotation/excerpt without creating a second, unrelated workspace.
# These are target types, not claims of evidence or confirmation.
LEDGER_SUBJECT_TYPES = ("term", "concept", "discipline", "person", "work",
                        "translation", "research_question", "text", "excerpt")
LEDGER_STATUSES = ("draft", "active", "reviewed", "archived")
LEDGER_ENTRY_KINDS = ("term", "edition", "translation", "source_text",
                      "reception", "claim", "interpretation", "open_question",
                      "note")
LEDGER_ENTRY_STATUSES = ("candidate", "confirmed", "disputed", "rejected", "open")
LEDGER_EVIDENCE_LEVELS = (
    "dictionary_confirmed", "bibliography_confirmed", "primary_text_confirmed",
    "translation_text_confirmed", "reception_confirmed", "strong",
    "interpretive", "candidate", "unverified")
LEDGER_LINK_ROLES = ("background", "evidence", "translation", "counterargument",
                     "method", "context")
LEDGER_RELATIONS = ("translated_as", "appears_in", "revised_in", "cited_by",
                    "criticized_by", "derived_from", "supports", "contradicts",
                    "related_to")

SCHEMA = """
CREATE TABLE IF NOT EXISTS projects(
  id INTEGER PRIMARY KEY,
  title TEXT NOT NULL,
  description TEXT DEFAULT '',
  question TEXT DEFAULT '',
  is_public INTEGER DEFAULT 0,
  workspace_id TEXT DEFAULT '',
  created_at TEXT, updated_at TEXT);

CREATE TABLE IF NOT EXISTS nodes(
  id INTEGER PRIMARY KEY,
  project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  type TEXT NOT NULL,
  title TEXT NOT NULL,
  body TEXT DEFAULT '',
  confidence TEXT DEFAULT 'unverified',
  origin TEXT DEFAULT 'human',
  status TEXT DEFAULT 'open',
  created_at TEXT, updated_at TEXT);

CREATE TABLE IF NOT EXISTS edges(
  id INTEGER PRIMARY KEY,
  project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  src INTEGER NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
  dst INTEGER NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
  rel TEXT NOT NULL,
  created_at TEXT);

CREATE TABLE IF NOT EXISTS provenance(
  id INTEGER PRIMARY KEY,
  node_id INTEGER NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
  source_name TEXT DEFAULT '',
  source_url TEXT DEFAULT '',
  retrieved_at TEXT DEFAULT '',
  quote TEXT DEFAULT '',
  note TEXT DEFAULT '');

CREATE TABLE IF NOT EXISTS watches(
  id INTEGER PRIMARY KEY,
  label TEXT NOT NULL,
  kind TEXT NOT NULL DEFAULT 'query',
  openalex_id TEXT DEFAULT '',
  query TEXT DEFAULT '',
  workspace_id TEXT DEFAULT '',
  created_at TEXT,
  last_checked TEXT DEFAULT '');

CREATE TABLE IF NOT EXISTS watch_hits(
  id INTEGER PRIMARY KEY,
  watch_id INTEGER NOT NULL REFERENCES watches(id) ON DELETE CASCADE,
  external_id TEXT,
  title TEXT,
  year TEXT DEFAULT '',
  url TEXT DEFAULT '',
  source TEXT DEFAULT '',
  found_at TEXT,
  seen INTEGER DEFAULT 0,
  UNIQUE(watch_id, external_id));

CREATE TABLE IF NOT EXISTS api_cache(
  url TEXT PRIMARY KEY,
  fetched_at TEXT,
  body TEXT);

CREATE TABLE IF NOT EXISTS ai_ledger(
  id INTEGER PRIMARY KEY,
  ts TEXT,
  provider TEXT,
  model TEXT,
  task TEXT,
  project_id INTEGER,
  workspace_id TEXT DEFAULT '',
  summary TEXT);

-- 匿名の報告（2026-10-10）。
-- 名前・連絡先・IP・workspace の識別子は列として持たない。
-- 持たない列は、後から「うっかり入れる」ことができない（公理6: 外部に置く）。
CREATE TABLE IF NOT EXISTS reports(
  id INTEGER PRIMARY KEY,
  ts TEXT,
  code TEXT UNIQUE,          -- 報告者が状態を見るための参照番号（本人以外は知らない）
  kind TEXT,                 -- 種別（REPORT_KINDS）
  page TEXT,                 -- どの画面から出したか
  body TEXT,                 -- 利用者が書いた本文
  context TEXT,              -- 利用者が添付を選んだときだけ入る（受領証など・JSON）
  status TEXT DEFAULT 'open',-- open / read / closed（所有者が手元で更新する）
  handled_at TEXT DEFAULT '');

CREATE TABLE IF NOT EXISTS ledgers(
  id INTEGER PRIMARY KEY,
  title TEXT NOT NULL,
  description TEXT DEFAULT '',
  central_question TEXT DEFAULT '',
  subject TEXT DEFAULT '',
  subject_type TEXT NOT NULL DEFAULT 'term',
  domain TEXT DEFAULT 'philosophy',
  status TEXT NOT NULL DEFAULT 'draft',
  is_public INTEGER DEFAULT 0,
  workspace_id TEXT DEFAULT '',
  parent_ledger_id INTEGER REFERENCES ledgers(id) ON DELETE SET NULL,
  version INTEGER NOT NULL DEFAULT 1,
  created_at TEXT, updated_at TEXT);

CREATE TABLE IF NOT EXISTS ledger_versions(
  ledger_id INTEGER NOT NULL REFERENCES ledgers(id) ON DELETE CASCADE,
  version INTEGER NOT NULL,
  snapshot_json TEXT NOT NULL,
  note TEXT DEFAULT '',
  created_at TEXT,
  PRIMARY KEY(ledger_id, version));

CREATE TABLE IF NOT EXISTS ledger_entries(
  id INTEGER PRIMARY KEY,
  ledger_id INTEGER NOT NULL REFERENCES ledgers(id) ON DELETE CASCADE,
  kind TEXT NOT NULL,
  title TEXT NOT NULL,
  body TEXT DEFAULT '',
  source_term TEXT DEFAULT '',
  target_term TEXT DEFAULT '',
  source_language TEXT DEFAULT '',
  target_language TEXT DEFAULT '',
  author TEXT DEFAULT '',
  translator TEXT DEFAULT '',
  work TEXT DEFAULT '',
  edition TEXT DEFAULT '',
  year TEXT DEFAULT '',
  locator TEXT DEFAULT '',
  original_quote TEXT DEFAULT '',
  translated_quote TEXT DEFAULT '',
  preserved_meaning TEXT DEFAULT '',
  lost_meaning TEXT DEFAULT '',
  added_meaning TEXT DEFAULT '',
  evidence_level TEXT NOT NULL DEFAULT 'candidate',
  status TEXT NOT NULL DEFAULT 'candidate',
  origin TEXT NOT NULL DEFAULT 'external',
  created_at TEXT, updated_at TEXT);

CREATE TABLE IF NOT EXISTS ledger_sources(
  id INTEGER PRIMARY KEY,
  ledger_id INTEGER NOT NULL REFERENCES ledgers(id) ON DELETE CASCADE,
  external_id TEXT DEFAULT '',
  role TEXT NOT NULL DEFAULT 'candidate_index',
  source_name TEXT DEFAULT '',
  source_url TEXT DEFAULT '',
  citation TEXT DEFAULT '',
  retrieved_at TEXT DEFAULT '',
  locator TEXT DEFAULT '',
  quote TEXT DEFAULT '',
  note TEXT DEFAULT '');

CREATE TABLE IF NOT EXISTS ledger_entry_sources(
  entry_id INTEGER NOT NULL REFERENCES ledger_entries(id) ON DELETE CASCADE,
  source_id INTEGER NOT NULL REFERENCES ledger_sources(id) ON DELETE CASCADE,
  PRIMARY KEY(entry_id, source_id));

CREATE TABLE IF NOT EXISTS ledger_relations(
  id INTEGER PRIMARY KEY,
  ledger_id INTEGER NOT NULL REFERENCES ledgers(id) ON DELETE CASCADE,
  src_entry_id INTEGER NOT NULL REFERENCES ledger_entries(id) ON DELETE CASCADE,
  dst_entry_id INTEGER NOT NULL REFERENCES ledger_entries(id) ON DELETE CASCADE,
  relation TEXT NOT NULL,
  note TEXT DEFAULT '',
  created_at TEXT,
  UNIQUE(ledger_id, src_entry_id, dst_entry_id, relation));

CREATE TABLE IF NOT EXISTS ledger_tasks(
  id INTEGER PRIMARY KEY,
  ledger_id INTEGER NOT NULL REFERENCES ledgers(id) ON DELETE CASCADE,
  entry_id INTEGER REFERENCES ledger_entries(id) ON DELETE SET NULL,
  title TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'open',
  priority INTEGER NOT NULL DEFAULT 0,
  created_at TEXT, updated_at TEXT);

CREATE TABLE IF NOT EXISTS project_ledger_links(
  project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  ledger_id INTEGER NOT NULL REFERENCES ledgers(id) ON DELETE CASCADE,
  role TEXT NOT NULL DEFAULT 'background',
  pinned_version INTEGER NOT NULL DEFAULT 1,
  status TEXT NOT NULL DEFAULT 'active',
  note TEXT DEFAULT '',
  created_at TEXT, updated_at TEXT,
  PRIMARY KEY(project_id, ledger_id));

CREATE TABLE IF NOT EXISTS project_ledger_entries(
  project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  entry_id INTEGER NOT NULL REFERENCES ledger_entries(id) ON DELETE CASCADE,
  relation TEXT NOT NULL DEFAULT 'evidence',
  adopted_version INTEGER NOT NULL DEFAULT 1,
  use_note TEXT DEFAULT '',
  created_at TEXT,
  PRIMARY KEY(project_id, entry_id));

CREATE TABLE IF NOT EXISTS arguments(
  id INTEGER PRIMARY KEY,
  project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  title TEXT NOT NULL,
  conclusion TEXT DEFAULT '',
  conclusion_node_id INTEGER REFERENCES nodes(id) ON DELETE SET NULL,
  validity TEXT DEFAULT 'unassessed',
  soundness TEXT DEFAULT 'unassessed',
  note TEXT DEFAULT '',
  created_at TEXT, updated_at TEXT);

CREATE TABLE IF NOT EXISTS argument_premises(
  id INTEGER PRIMARY KEY,
  argument_id INTEGER NOT NULL REFERENCES arguments(id) ON DELETE CASCADE,
  seq INTEGER NOT NULL DEFAULT 0,
  text TEXT DEFAULT '',
  hidden INTEGER DEFAULT 0,
  voice TEXT DEFAULT 'author',
  node_id INTEGER REFERENCES nodes(id) ON DELETE SET NULL,
  locator TEXT DEFAULT '',
  source_name TEXT DEFAULT '',
  source_url TEXT DEFAULT '',
  quote TEXT DEFAULT '',
  retrieved_at TEXT DEFAULT '');

"""


def now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def get_conn() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(os.path.abspath(DB_PATH)), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _column_exists(conn, table: str, col: str) -> bool:
    return any(r["name"] == col
              for r in conn.execute(f"PRAGMA table_info({table})"))


def _add_column_if_missing(conn, table: str, column: str, definition: str) -> None:
    """Apply one additive column migration safely when workers start together."""
    if _column_exists(conn, table, column):
        return
    try:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
    except sqlite3.OperationalError as exc:
        # Two Uvicorn workers can import the app concurrently.  One may add
        # the column between PRAGMA and ALTER in the other; that is success,
        # while every different SQLite error must still fail loudly.
        if "duplicate column name" not in str(exc).lower():
            raise


def _migrate(conn) -> None:
    """Additive, idempotent column adds for tables that already shipped.
    New tables are handled by CREATE TABLE IF NOT EXISTS in SCHEMA; this only
    covers columns added to pre-existing tables (rollback-safe: old code ignores
    the extra column). See docs/IMPROVEMENT_PROTOCOL.md §3."""
    _add_column_if_missing(conn, "provenance", "locator", "TEXT DEFAULT ''")
    # Anonymous/public deployment boundary.  The columns are deliberately
    # additive: old SQLite files remain readable, while every newly-created
    # research asset can be scoped to its signed workspace cookie.  Empty
    # values are retained for legacy rows and are never treated as private
    # ownership; public legacy rows may still be read through is_public.
    for table, column, definition in (
        ("projects", "workspace_id", "TEXT DEFAULT ''"),
        ("watches", "workspace_id", "TEXT DEFAULT ''"),
        ("ai_ledger", "workspace_id", "TEXT DEFAULT ''"),
        ("ledgers", "is_public", "INTEGER DEFAULT 0"),
        ("ledgers", "workspace_id", "TEXT DEFAULT ''"),
    ):
        _add_column_if_missing(conn, table, column, definition)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_projects_workspace ON projects(workspace_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ledgers_workspace ON ledgers(workspace_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_watches_workspace ON watches(workspace_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ai_ledger_workspace ON ai_ledger(workspace_id)")
    # Preserve the pre-boundary local application.  A developer/operator who
    # has not opted into the public instance still owns the old rows as one
    # local workspace; the public deployment flag deliberately skips this
    # claim so legacy private rows are not silently exposed.
    public = str(os.environ.get("DIALEXIS_PUBLIC_INSTANCE", "")).lower() in {
        "1", "true", "yes", "on"
    }
    if not public:
        legacy = os.environ.get("DIALEXIS_LEGACY_WORKSPACE_ID", "single-user-local")
        for table in ("projects", "watches", "ai_ledger", "ledgers"):
            conn.execute(f"UPDATE {table} SET workspace_id=? WHERE workspace_id=''", (legacy,))


def init_db() -> None:
    conn = get_conn()
    conn.executescript(SCHEMA)
    _migrate(conn)
    conn.commit()
    conn.close()


def rows(cursor) -> list:
    return [dict(r) for r in cursor.fetchall()]
