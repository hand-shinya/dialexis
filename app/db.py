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
              "interpretation", "decision", "note", "source")
CONFIDENCE = ("confirmed", "high_probability", "unverified",
              "interpretive_hypothesis", "speculation")
ORIGINS = ("human", "ai", "external")
STATUSES = ("open", "adopted", "held", "rejected")
RELATIONS = ("supports", "contradicts", "answers", "refines", "derives_from",
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

SCHEMA = """
CREATE TABLE IF NOT EXISTS projects(
  id INTEGER PRIMARY KEY,
  title TEXT NOT NULL,
  description TEXT DEFAULT '',
  question TEXT DEFAULT '',
  is_public INTEGER DEFAULT 0,
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
  summary TEXT);

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


def _migrate(conn) -> None:
    """Additive, idempotent column adds for tables that already shipped.
    New tables are handled by CREATE TABLE IF NOT EXISTS in SCHEMA; this only
    covers columns added to pre-existing tables (rollback-safe: old code ignores
    the extra column). See docs/IMPROVEMENT_PROTOCOL.md §3."""
    if not _column_exists(conn, "provenance", "locator"):
        conn.execute("ALTER TABLE provenance ADD COLUMN locator TEXT DEFAULT ''")


def init_db() -> None:
    conn = get_conn()
    conn.executescript(SCHEMA)
    _migrate(conn)
    conn.commit()
    conn.close()


def rows(cursor) -> list:
    return [dict(r) for r in cursor.fetchall()]
