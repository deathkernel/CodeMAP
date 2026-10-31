"""Local SQLite-backed code retrieval index for retrieval-augmented explanations."""

from __future__ import annotations

import ast
import hashlib
import math
import os
import re
import sqlite3
import struct
import uuid

import httpx
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
    """Create a stable, content-aware local index key for one project snapshot."""
    digest = hashlib.sha256()
    digest.update(f"{name}\n{branch}\n".encode("utf-8"))
    for path, source in sorted(sources.items()):
        digest.update(path.encode("utf-8"))
        digest.update(hashlib.sha256(source.encode("utf-8")).digest())
    return digest.hexdigest()[:24]


def _text_chunks(source: str):
    """Split non-Python source into bounded, overlapping line-aware chunks."""
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


def _line_ranges(content: str, start_line: int):
    """Keep each logical unit bounded while preserving its source line."""
    lines = content.splitlines()
    chunk_lines: list[str] = []
    chunk_start = start_line
    current_size = 0

    for offset, line in enumerate(lines):
        line_size = len(line) + 1
        if chunk_lines and current_size + line_size > CHUNK_CHARS:
            yield chunk_start, "\n".join(chunk_lines)
            chunk_lines = []
            chunk_start = start_line + offset
            current_size = 0
        chunk_lines.append(line)
        current_size += line_size

    if chunk_lines:
        yield chunk_start, "\n".join(chunk_lines)


def _python_chunks(source: str):
    """Prefer top-level Python classes/functions as retrieval units."""
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        yield from _text_chunks(source)
        return

    lines = source.splitlines()
    definitions = [
        node for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        and hasattr(node, "end_lineno")
    ]
    if not definitions:
        yield from _text_chunks(source)
        return

    ranges: list[tuple[int, str]] = []
    cursor = 1
    for node in definitions:
        start_line = node.lineno
        end_line = node.end_lineno or node.lineno
        if start_line > cursor:
            gap = "\n".join(lines[cursor - 1:start_line - 1]).strip()
            if gap:
                ranges.extend(_line_ranges(gap, cursor))
        body = "\n".join(lines[start_line - 1:end_line]).strip()
        if body:
            ranges.extend(_line_ranges(body, start_line))
        cursor = end_line + 1

    if cursor <= len(lines):
        tail = "\n".join(lines[cursor - 1:]).strip()
        if tail:
            ranges.extend(_line_ranges(tail, cursor))

    if not ranges:
        yield from _text_chunks(source)
        return
    yield from ranges



JS_DEFINITION_PATTERN = re.compile(
    r"^\s*(?:(?:export|default|declare|abstract|async)\s+)*(?:"
    r"(?:function|class)\s+[A-Za-z_$][\w$]*|"
    r"(?:const|let|var)\s+[A-Za-z_$][\w$]*\s*=\s*(?:async\s*)?(?:function\b|\([^;\n]*\)\s*=>|[A-Za-z_$][\w$]*\s*=>)"
    r")",
)


def _matching_brace(source: str, opening: int) -> int | None:
    """Find a matching brace while ignoring braces inside strings and comments."""
    depth = 0
    state = "code"
    quote = ""
    index = opening

    while index < len(source):
        char = source[index]
        next_char = source[index + 1] if index + 1 < len(source) else ""

        if state == "line_comment":
            if char == "\n":
                state = "code"
        elif state == "block_comment":
            if char == "*" and next_char == "/":
                state = "code"
                index += 1
        elif state == "string":
            if char == "\\":
                index += 1
            elif char == quote:
                state = "code"
        elif state == "template":
            if char == "\\":
                index += 1
            elif ord(char) == 96:
                state = "code"
        else:
            if char == "/" and next_char == "/":
                state = "line_comment"
                index += 1
            elif char == "/" and next_char == "*":
                state = "block_comment"
                index += 1
            elif char in {"'", '"'}:
                state = "string"
                quote = char
            elif ord(char) == 96:
                state = "template"
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return index
        index += 1

    return None


def _javascript_chunks(source: str):
    """Prefer top-level JS/TS function and class declarations as retrieval units."""
    definitions: list[tuple[int, int]] = []
    offset = 0

    for line in source.splitlines(keepends=True):
        if JS_DEFINITION_PATTERN.match(line):
            search_end = min(len(source), offset + 5000)
            opening = source.find("{", offset, search_end)
            if opening >= 0:
                closing = _matching_brace(source, opening)
                if closing is not None:
                    definitions.append((offset, closing + 1))
        offset += len(line)

    if not definitions:
        yield from _text_chunks(source)
        return

    ranges: list[tuple[int, str]] = []
    cursor = 0
    for start, end in sorted(set(definitions)):
        if start < cursor:
            continue
        gap = source[cursor:start].strip()
        if gap:
            ranges.extend(_line_ranges(gap, source.count("\n", 0, cursor) + 1))
        body = source[start:end].strip()
        if body:
            ranges.extend(_line_ranges(body, source.count("\n", 0, start) + 1))
        cursor = end

    tail = source[cursor:].strip()
    if tail:
        ranges.extend(_line_ranges(tail, source.count("\n", 0, cursor) + 1))

    if not ranges:
        yield from _text_chunks(source)
        return
    yield from ranges


def _chunks(source: str, path: str):
    suffix = path.lower().rsplit(".", 1)[-1] if "." in path else ""
    if suffix == "py":
        yield from _python_chunks(source)
    elif suffix in {"js", "jsx", "ts", "tsx", "mjs", "cjs"}:
        yield from _javascript_chunks(source)
    else:
        yield from _text_chunks(source)


def make_stable_project_id(name: str, branch: str) -> str:
    """Create a stable local index key that survives source-file changes."""
    digest = hashlib.sha256(f"{name}\n{branch}".encode("utf-8")).hexdigest()
    return digest[:24]


def _ensure_file_manifest(connection: sqlite3.Connection) -> None:
    connection.execute(
        "CREATE TABLE IF NOT EXISTS code_index_files ("
        "project_id TEXT NOT NULL, path TEXT NOT NULL, content_hash TEXT NOT NULL, "
        "updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, "
        "PRIMARY KEY (project_id, path))"
    )


def index_project_sources_incremental(
    project_id: str,
    sources: dict[str, str],
    prune_missing: bool = True,
) -> dict[str, int]:
    """Update changed files; prune absent paths only when the supplied snapshot is complete."""
    connection, has_fts = _connect()
    table = "code_chunks" if has_fts else "code_chunks_plain"
    try:
        _ensure_file_manifest(connection)
        _ensure_embedding_table(connection)
        existing_rows = connection.execute(
            "SELECT path, content_hash FROM code_index_files WHERE project_id = ?",
            (project_id,),
        ).fetchall()
        existing = {path: content_hash for path, content_hash in existing_rows}
        current = {
            path: hashlib.sha256(source.encode("utf-8")).hexdigest()
            for path, source in sources.items()
        }

        removed = (set(existing) - set(current)) if prune_missing else set()
        changed = {
            path for path, digest in current.items()
            if existing.get(path) != digest
        }
        for path in removed | changed:
            connection.execute(
                f"DELETE FROM {table} WHERE project_id = ? AND path = ?",
                (project_id, path),
            )
            connection.execute(
                "DELETE FROM code_embeddings WHERE project_id = ? AND path = ?",
                (project_id, path),
            )

        indexed_chunks = 0
        batch: list[tuple[str, str, int, str]] = []
        for path in sorted(changed):
            for start_line, chunk in _chunks(sources[path], path):
                batch.append((project_id, path, start_line, chunk))
                if len(batch) >= 500:
                    connection.executemany(
                        f"INSERT INTO {table} (project_id, path, start_line, content) VALUES (?, ?, ?, ?)",
                        batch,
                    )
                    indexed_chunks += len(batch)
                    batch.clear()
            connection.execute(
                "INSERT OR REPLACE INTO code_index_files "
                "(project_id, path, content_hash, updated_at) VALUES (?, ?, ?, CURRENT_TIMESTAMP)",
                (project_id, path, current[path]),
            )

        if batch:
            connection.executemany(
                f"INSERT INTO {table} (project_id, path, start_line, content) VALUES (?, ?, ?, ?)",
                batch,
            )
            indexed_chunks += len(batch)

        for path in removed:
            connection.execute(
                "DELETE FROM code_index_files WHERE project_id = ? AND path = ?",
                (project_id, path),
            )

        connection.commit()
        total_files = len(current)
        return {
            "changed_files": len(changed),
            "removed_files": len(removed),
            "unchanged_files": max(0, total_files - len(changed)),
            "indexed_chunks": indexed_chunks,
            "total_files": total_files,
        }
    finally:
        connection.close()


def index_project_sources(project_id: str, sources: dict[str, str]) -> int:
    """Replace a project's local text index with bounded overlapping source chunks."""
    connection, has_fts = _connect()
    table = "code_chunks" if has_fts else "code_chunks_plain"
    try:
        connection.execute(f"DELETE FROM {table} WHERE project_id = ?", (project_id,))
        rows = []
        for path, source in sources.items():
            for start_line, content in _chunks(source, path):
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



def _embedding_settings() -> tuple[str, str]:
    base_url = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
    model = os.getenv("CODEMAP_EMBEDDING_MODEL", "nomic-embed-text")
    return base_url, model


def _ensure_embedding_table(connection: sqlite3.Connection) -> None:
    connection.execute(
        "CREATE TABLE IF NOT EXISTS code_embeddings ("
        "project_id TEXT NOT NULL, path TEXT NOT NULL, start_line INTEGER NOT NULL, "
        "content TEXT NOT NULL, vector BLOB NOT NULL, dimensions INTEGER NOT NULL, "
        "PRIMARY KEY (project_id, path, start_line, content))"
    )


async def _ollama_embeddings(texts: list[str]) -> list[list[float]] | None:
    """Create local embeddings only when the separately configured model is installed."""
    base_url, model = _embedding_settings()
    try:
        async with httpx.AsyncClient(timeout=120, trust_env=False) as client:
            tags = await client.get(f"{base_url}/api/tags")
            tags.raise_for_status()
            installed = {item.get("name", "") for item in tags.json().get("models", [])}
            if model not in installed and f"{model}:latest" not in installed:
                return None

            response = await client.post(
                f"{base_url}/api/embed",
                json={"model": model, "input": texts},
            )
            response.raise_for_status()
            embeddings = response.json().get("embeddings", [])
            if len(embeddings) != len(texts):
                return None
            if not embeddings or not all(isinstance(value, (int, float)) for value in embeddings[0]):
                return None
            return embeddings
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        return None


async def index_project_embeddings(project_id: str, batch_size: int = 24) -> int:
    """Embed only chunks that do not already have a matching local vector."""
    connection, has_fts = _connect()
    table = "code_chunks" if has_fts else "code_chunks_plain"
    try:
        _ensure_embedding_table(connection)
        rows = connection.execute(
            f"SELECT c.path, CAST(c.start_line AS INTEGER), c.content "
            f"FROM {table} c LEFT JOIN code_embeddings e "
            "ON e.project_id = c.project_id AND e.path = c.path "
            "AND e.start_line = c.start_line AND e.content = c.content "
            "WHERE c.project_id = ? AND e.project_id IS NULL",
            (project_id,),
        ).fetchall()
        connection.execute(
            f"DELETE FROM code_embeddings WHERE project_id = ? AND NOT EXISTS "
            f"(SELECT 1 FROM {table} c WHERE c.project_id = code_embeddings.project_id "
            "AND c.path = code_embeddings.path AND c.start_line = code_embeddings.start_line "
            "AND c.content = code_embeddings.content)",
            (project_id,),
        )
        connection.commit()
    finally:
        connection.close()

    stored = 0
    for offset in range(0, len(rows), max(1, batch_size)):
        batch = rows[offset:offset + max(1, batch_size)]
        vectors = await _ollama_embeddings([row[2] for row in batch])
        if vectors is None:
            break

        connection, _ = _connect()
        try:
            _ensure_embedding_table(connection)
            payload = []
            for row, vector in zip(batch, vectors):
                packed = struct.pack(f"<{len(vector)}f", *vector)
                payload.append((project_id, row[0], row[1], row[2], packed, len(vector)))
            connection.executemany(
                "INSERT OR REPLACE INTO code_embeddings "
                "(project_id, path, start_line, content, vector, dimensions) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                payload,
            )
            connection.commit()
            stored += len(payload)
        finally:
            connection.close()
    connection, _ = _connect()
    try:
        _ensure_embedding_table(connection)
        total = connection.execute(
            "SELECT COUNT(*) FROM code_embeddings WHERE project_id = ?",
            (project_id,),
        ).fetchone()[0]
        return total
    finally:
        connection.close()



def _ensure_jobs_table(connection: sqlite3.Connection) -> None:
    connection.execute(
        "CREATE TABLE IF NOT EXISTS code_index_jobs ("
        "job_id TEXT PRIMARY KEY, project_id TEXT NOT NULL, job_type TEXT NOT NULL, "
        "status TEXT NOT NULL, result_count INTEGER NOT NULL DEFAULT 0, "
        "error TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, "
        "updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"
    )


def create_embedding_job(project_id: str) -> dict[str, str]:
    """Create or reuse a queued/running embedding job for a project."""
    connection, _ = _connect()
    try:
        _ensure_jobs_table(connection)
        existing = connection.execute(
            "SELECT job_id, status FROM code_index_jobs "
            "WHERE project_id = ? AND job_type = 'embeddings' "
            "AND status IN ('queued', 'running') ORDER BY created_at DESC LIMIT 1",
            (project_id,),
        ).fetchone()
        if existing:
            return {"job_id": existing[0], "status": existing[1], "created": False}

        job_id = uuid.uuid4().hex
        connection.execute(
            "INSERT INTO code_index_jobs (job_id, project_id, job_type, status) "
            "VALUES (?, ?, 'embeddings', 'queued')",
            (job_id, project_id),
        )
        connection.commit()
        return {"job_id": job_id, "status": "queued", "created": True}
    finally:
        connection.close()


async def run_embedding_job(job_id: str, project_id: str) -> None:
    """Run embedding work after the HTTP response and persist its lifecycle."""
    connection, _ = _connect()
    try:
        _ensure_jobs_table(connection)
        connection.execute(
            "UPDATE code_index_jobs SET status = 'running', updated_at = CURRENT_TIMESTAMP "
            "WHERE job_id = ?",
            (job_id,),
        )
        connection.commit()
    finally:
        connection.close()

    try:
        result_count = await index_project_embeddings(project_id)
        status = "completed"
        error = None
    except Exception:
        result_count = 0
        status = "failed"
        error = "Embedding indexing failed. Check the local Ollama service and application logs."

    connection, _ = _connect()
    try:
        _ensure_jobs_table(connection)
        connection.execute(
            "UPDATE code_index_jobs SET status = ?, result_count = ?, error = ?, "
            "updated_at = CURRENT_TIMESTAMP WHERE job_id = ?",
            (status, result_count, error, job_id),
        )
        connection.commit()
    finally:
        connection.close()


def get_index_job(job_id: str) -> dict[str, Any] | None:
    """Return a persisted background index job without exposing local paths."""
    connection, _ = _connect()
    try:
        _ensure_jobs_table(connection)
        row = connection.execute(
            "SELECT job_id, project_id, job_type, status, result_count, error, created_at, updated_at "
            "FROM code_index_jobs WHERE job_id = ?",
            (job_id,),
        ).fetchone()
        if not row:
            return None
        return {
            "job_id": row[0], "project_id": row[1], "job_type": row[2],
            "status": row[3], "indexed_embeddings": row[4], "error": row[5],
            "created_at": row[6], "updated_at": row[7],
        }
    finally:
        connection.close()



def count_project_embeddings(project_id: str) -> int:
    """Count stored vectors for one project without loading their payloads."""
    connection, _ = _connect()
    try:
        _ensure_embedding_table(connection)
        return connection.execute(
            "SELECT COUNT(*) FROM code_embeddings WHERE project_id = ?",
            (project_id,),
        ).fetchone()[0]
    finally:
        connection.close()


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    if len(left) != len(right) or not left:
        return 0.0
    dot = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if not left_norm or not right_norm:
        return 0.0
    return dot / (left_norm * right_norm)


async def search_project_sources_hybrid(
    project_id: str,
    query: str,
    limit: int = DEFAULT_RESULTS,
) -> tuple[list[dict[str, Any]], str]:
    """Combine local BM25 and cosine similarity using reciprocal-rank fusion."""
    keyword_results = search_project_sources(project_id, query, limit=max(limit * 2, 8))
    query_vectors = await _ollama_embeddings([query])
    if not query_vectors:
        return keyword_results[:limit], "keyword"

    connection, _ = _connect()
    try:
        _ensure_embedding_table(connection)
        rows = connection.execute(
            "SELECT path, start_line, content, vector, dimensions "
            "FROM code_embeddings WHERE project_id = ?",
            (project_id,),
        ).fetchall()
    finally:
        connection.close()

    if not rows:
        return keyword_results[:limit], "keyword"

    query_vector = query_vectors[0]
    semantic_results = []
    for row in rows:
        if row[4] != len(query_vector):
            continue
        vector = list(struct.unpack(f"<{row[4]}f", row[3]))
        semantic_results.append({
            "path": row[0],
            "start_line": row[1],
            "content": row[2],
            "score": _cosine_similarity(query_vector, vector),
        })
    semantic_results.sort(key=lambda item: item["score"], reverse=True)

    fused: dict[tuple[str, int, str], dict[str, Any]] = {}
    for rank, item in enumerate(keyword_results, 1):
        key = (item["path"], item["start_line"], item["content"])
        fused.setdefault(key, {**item, "hybrid_score": 0.0})
        fused[key]["hybrid_score"] += 1 / (60 + rank)
    for rank, item in enumerate(semantic_results[:max(limit * 2, 8)], 1):
        key = (item["path"], item["start_line"], item["content"])
        fused.setdefault(key, {**item, "hybrid_score": 0.0})
        fused[key]["hybrid_score"] += 1 / (60 + rank)
        fused[key]["semantic_score"] = item["score"]

    results = sorted(fused.values(), key=lambda item: item["hybrid_score"], reverse=True)
    return results[:limit], "hybrid"



def delete_project_index(project_id: str) -> int:
    """Delete all locally stored source chunks for one project."""
    connection, has_fts = _connect()
    table = "code_chunks" if has_fts else "code_chunks_plain"
    try:
        cursor = connection.execute(f"DELETE FROM {table} WHERE project_id = ?", (project_id,))
        _ensure_embedding_table(connection)
        connection.execute("DELETE FROM code_embeddings WHERE project_id = ?", (project_id,))
        connection.commit()
        return cursor.rowcount
    finally:
        connection.close()
