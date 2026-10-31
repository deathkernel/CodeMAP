"""Local SQLite-backed code retrieval index for retrieval-augmented explanations."""

from __future__ import annotations

import hashlib
import os
import re
import sqlite3
from pathlib import Path
from typing import Any

CHUNK_CHARS = 12_000
CHUNK_OVERLAP = 1_000
DEFAULT_RESULTS = 6


def _database_path() -> Path:
    url = os.getenv("CODEMAP_DATABASE_URL", "sqlite:///./data/codemap.db")
    if not url.startswith("sqlite:///"):
        raise ValueError("CodeMap's local code index requires a SQLite database URL.")
    path = Path(url.removeprefix("sqlite:///"))
    if not path.is_absolute():
        path = Path.cwd() / path
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _connect() -> tuple[sqlite3.Connection, bool]:
    connection = sqlite3.connect(_database_path(), timeout=30)
    connection.execute("PRAGMA journal_mode=WAL")
    try:
        connection.execute(
            "CREATE VIRTUAL TABLE IF NOT EXISTS code_chunks USING fts5("
            "project_id UNINDEXED, path UNINDEXED, start_line UNINDEXED, content, "
            "tokenize='unicode61')"
        )
        return connection, True
    except sqlite3.OperationalError:
        connection.execute(
            "CREATE TABLE IF NOT EXISTS code_chunks_plain ("
            "project_id TEXT NOT NULL, path TEXT NOT NULL, start_line INTEGER NOT NULL, "
            "content TEXT NOT NULL)"
        )
        return connection, False


def make_project_id(name: str, branch: str, sources: dict[str, str]) -> str:
    """Create a stable local index key for a repository snapshot's file inventory."""
    inventory = "\n".join(sorted(sources))
    digest = hashlib.sha256(f"{name}\n{branch}\n{inventory}".encode("utf-8")).hexdigest()
    return digest[:24]


def _chunks(source: str):
    start = 0
    while start < len(source):
        end = min(start + CHUNK_CHARS, len(source))
        if end < len(source):
            boundary = source.rfind("\n", start + CHUNK_CHARS // 2, end)
            if boundary > start:
                end = boundary
        content = source[start:end].strip()
        if content:
            yield source.count("\n", 0, start) + 1, content
        if end >= len(source):
            break
        start = max(start + 1, end - CHUNK_OVERLAP)


def index_project_sources(project_id: str, sources: dict[str, str]) -> int:
    """Replace a project's local text index with bounded overlapping source chunks."""
    connection, has_fts = _connect()
    table = "code_chunks" if has_fts else "code_chunks_plain"
    try:
        connection.execute(f"DELETE FROM {table} WHERE project_id = ?", (project_id,))
        rows = []
        for path, source in sources.items():
            for start_line, content in _chunks(source):
                rows.append((project_id, path, start_line, content))
        connection.executemany(
            f"INSERT INTO {table} (project_id, path, start_line, content) VALUES (?, ?, ?, ?)",
            rows,
        )
        connection.commit()
        return len(rows)
    finally:
        connection.close()


def search_project_sources(project_id: str, query: str, limit: int = DEFAULT_RESULTS) -> list[dict[str, Any]]:
    """Retrieve relevant source chunks for a single project using local BM25 or LIKE fallback."""
    terms = re.findall(r"[A-Za-z0-9_]+", query.lower())[:12]
    if not terms:
        return []
    limit = max(1, min(limit, 12))
    connection, has_fts = _connect()
    try:
        if has_fts:
            match_query = " OR ".join(f'"{term}"' for term in terms)
            rows = connection.execute(
                "SELECT path, CAST(start_line AS INTEGER), content, bm25(code_chunks) "
                "FROM code_chunks WHERE project_id = ? AND code_chunks MATCH ? "
                "ORDER BY bm25(code_chunks) LIMIT ?",
                (project_id, match_query, limit),
            ).fetchall()
        else:
            clauses = " OR ".join("content LIKE ?" for _ in terms)
            params = [project_id, *(f"%{term}%" for term in terms), limit]
            rows = connection.execute(
                f"SELECT path, start_line, content, 0 FROM code_chunks_plain "
                f"WHERE project_id = ? AND ({clauses}) LIMIT ?",
                params,
            ).fetchall()
        return [
            {"path": row[0], "start_line": row[1], "content": row[2], "score": row[3]}
            for row in rows
        ]
    finally:
        connection.close()


def delete_project_index(project_id: str) -> int:
    """Delete all locally stored source chunks for one project."""
    connection, has_fts = _connect()
    table = "code_chunks" if has_fts else "code_chunks_plain"
    try:
        cursor = connection.execute(f"DELETE FROM {table} WHERE project_id = ?", (project_id,))
        connection.commit()
        return cursor.rowcount
    finally:
        connection.close()
