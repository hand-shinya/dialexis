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


def init_db() -> None:
    conn = get_conn()
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()


def rows(cursor) -> list:
    return [dict(r) for r in cursor.fetchall()]
