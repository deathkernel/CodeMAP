# API reference

The CodeMap backend is a FastAPI application. It serves interactive OpenAPI documentation at `http://127.0.0.1:8000/docs` while it is running. This page is a human-oriented summary of the same surface.

**Base URL:** `http://127.0.0.1:8000`
**Content types:** JSON for most endpoints. `multipart/form-data` for ZIP uploads. `application/x-ndjson` for the model-preparation stream.
**Authentication:** none. The API is designed to be bound to localhost. Do not expose it to a network (see [SECURITY.md](SECURITY.md)).

- [Summary](#summary)
- [Health](#health)
- [Repository inspection](#repository-inspection)
- [Analysis](#analysis)
- [Local AI](#local-ai)
- [Reports](#reports)
- [Error format](#error-format)

---

## Summary

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/health` | Liveness check. |
| `POST` | `/api/repository/github` | Inventory a public GitHub repository. No code is downloaded. |
| `POST` | `/api/repository/zip` | Inventory a ZIP. No code is extracted. |
| `POST` | `/api/repository/source` | Preview one file from a public GitHub repository (256 KB max). |
| `POST` | `/api/repository/analyze` | Full analysis of a public GitHub repository. |
| `POST` | `/api/repository/analyze-folder` | Full analysis of files sent from a local folder. |
| `POST` | `/api/repository/analyze-zip` | Full analysis of an uploaded ZIP. |
| `GET` | `/api/repository/jobs/{job_id}` | Status of a background embedding job. |
| `DELETE` | `/api/repository/index/{project_id}` | Delete one project's stored chunks, embeddings, and caches. |
| `GET` | `/api/ai/status` | Check whether the configured Ollama model is installed. |
| `POST` | `/api/ai/prepare` | Download the configured model if it is missing. Streams progress. |
| `POST` | `/api/ai/explain` | Explain a source file. |
| `POST` | `/api/ai/explain-bug` | Explain one static finding and suggest a fix. |
| `POST` | `/api/ai/explain-architecture` | Explain the architecture report. |
| `POST` | `/api/ai/ask-codebase` | Answer a question using retrieved project excerpts. |
| `POST` | `/api/reports/architecture.pdf` | Render an analysis result as a PDF. |
| `POST` | `/api/reports/snapshots` | Save a before/after snapshot of an analysis result. |
| `GET` | `/api/reports/compare/{project_id}` | Compare the two most recent snapshots for a project. |

---

## Health

### `GET /api/health`

```json
{ "status": "ok", "service": "codemap-api" }
```

---

## Repository inspection

These endpoints return inventories only. They never analyze or execute code.

### `POST /api/repository/github`

**Body**

```json
{ "url": "https://github.com/owner/repository" }
```

**Response** includes `repository`, `description`, `default_branch`, `stars`, `files` (`path`, `size`, `sha`), `file_count`, and `tree_truncated`.

**Errors:** `400` for an invalid or non-public URL. `502` if GitHub is unreachable or returns an unexpected response.

### `POST /api/repository/zip`

**Body:** `multipart/form-data` with field `file` (must end in `.zip`, maximum 50 MB).

**Response** includes `files` (`path`, `size`), `file_count`, `archive_entries`, and `uncompressed_bytes`.

**Errors:** `400` for an unsafe path, a symlink, an encrypted entry, a duplicate name, an oversized archive, or a corrupt ZIP.

### `POST /api/repository/source`

Returns the content of one file from the inventory of a public GitHub repository.

**Body**

```json
{ "url": "https://github.com/owner/repository", "path": "src/main.py" }
```

**Response**

```json
{ "path": "src/main.py", "content": "...", "truncated": false }
```

`path` must exactly match an entry in the inventory. Anything else returns `404`. Files over 256 KB return `413`.

---

## Analysis

Full analysis returns one large JSON document. Its main sections are listed below. The complete shape is defined in `frontend/lib/types.ts`.

| Section | Contents |
|---|---|
| `project_id` | Stable identifier for the project. Repository analyses use `repository` and `default_branch`. |
| `nodes`, `edges` | The dependency graph. |
| `stats` | `files_analyzed`, `dependencies_found`, `relative_imports_unresolved`, `files_not_fetched`, and more. |
| `indexed_chunks`, `indexed_embeddings`, `semantic_index_available` | Retrieval index state. |
| `embedding_job` | `job_id` and `status`. Poll it with `GET /api/repository/jobs/{job_id}`. |
| `bug_findings`, `bug_stats`, `bug_analysis_note` | Static findings. Each finding has `rule_id`, `severity`, `path`, `line`, `message`, and `recommendation`. |
| `symbol_intelligence` | Symbols, call edges, inheritance edges, dead-code candidates, duplicate groups. |
| `advanced_architecture` | Frameworks, entry points, API endpoints, database relations, cross-module dependencies. |
| `architecture_insights` | Entry points, circular dependency groups, module groups. |
| `architecture_health` | `health_score`, `health_grade`, `risk_factors`, and per-module health. |
| `code_intelligence` | Bottleneck files, unreferenced files, and dependency depth. |

### `POST /api/repository/analyze`

**Body:** `{ "url": "https://github.com/owner/repository" }`

Fetches up to 1,000 source files (256 KB each, 64 MB total), then runs the full pipeline described in [ARCHITECTURE.md §4](ARCHITECTURE.md#4-analysis-pipeline).

### `POST /api/repository/analyze-folder`

**Body**

```json
{
  "folder_name": "my-project",
  "files": [ { "path": "app/main.py", "content": "..." } ]
}
```

`files` holds 1 to 1,000 entries. Paths are relative to the selected folder.

### `POST /api/repository/analyze-zip`

**Body:** `multipart/form-data` with field `file` (a `.zip`, maximum 50 MB). The same limits as `/zip` apply, plus a per-file limit of 256 KB for analysis.

### `GET /api/repository/jobs/{job_id}`

Returns the status of a background embedding job. `404` if the ID is unknown.

### `DELETE /api/repository/index/{project_id}`

Deletes all stored data for one project. `project_id` must be 24 lowercase hexadecimal characters, or the endpoint returns `400`.

```json
{ "project_id": "…", "deleted_chunks": 412 }
```

---

## Local AI

All AI endpoints send data only to `OLLAMA_BASE_URL`. See [ollama-setup.md](ollama-setup.md).

### `GET /api/ai/status`

```json
{
  "models": ["…"],
  "configured_model": "hf.co/bartowski/Qwen_Qwen3.5-9B-GGUF:Q6_K",
  "model_installed": true
}
```

If Ollama cannot be reached, `models` is empty and `model_installed` is `false`.

### `POST /api/ai/prepare`

Downloads the configured model if it is missing. The response is `application/x-ndjson`, with one JSON object per line: `checking`, `downloading`, and `ready`.

### `POST /api/ai/explain`

**Body**

```json
{ "path": "app/main.py", "language": "py", "code": "…" }
```

`code` is limited to 20,000 characters.

**Response:** `{ "model": "…", "downloaded": false, "explanation": "…" }`

### `POST /api/ai/explain-bug`

**Body:** `path`, `language`, `line`, `rule_id`, `title`, `severity` (`high`, `medium`, or `low`), `message`, `recommendation`, and `code`.

**Response:** `{ "model": "…", "downloaded": false, "explanation": "…" }`

### `POST /api/ai/explain-architecture`

**Body:** the analysis sections `repository`, `stats`, `architecture_insights`, `advanced_architecture`, `architecture_health`, `code_intelligence`, `symbol_stats`, and `bug_stats`.

**Response:** `{ "model": "…", "downloaded": false, "explanation": "…" }`

### `POST /api/ai/ask-codebase`

**Body**

```json
{
  "project_id": "…",
  "repository": "owner/repository",
  "question": "Where is authentication handled?"
}
```

**Response**

```json
{
  "model": "…",
  "downloaded": false,
  "answer": "…",
  "retrieval_mode": "hybrid",
  "sources": [ { "path": "app/auth.py", "start_line": 12 } ]
}
```

`retrieval_mode` is `hybrid` when embeddings were used, or `keyword` when only BM25 or LIKE search was available. `404` is returned when no indexed chunk matches the question.

---

## Reports

### `POST /api/reports/architecture.pdf`

**Body:** `{ "result": { … } }`, where `result` is a full analysis response.

**Response:** `application/pdf`, with the architecture, quality, and security summary.

### `POST /api/reports/snapshots`

**Body:** `{ "result": { … } }`

Stores a snapshot in `code_report_snapshots` and returns its ID, the project ID, `created_at`, and a summary.

### `GET /api/reports/compare/{project_id}`

Compares the two most recent snapshots for a project. The response includes deltas for health score, dependencies, per-module risk, and finding counts.

---

## Error format

FastAPI errors use a consistent shape:

```json
{ "detail": "Human-readable message." }
```

| Status | Meaning |
|---|---|
| `400` | Invalid input or an unsafe archive. |
| `404` | Unknown job, file, or project. |
| `413` | File exceeds the preview limit. |
| `415` | Unsupported encoding from GitHub. |
| `422` | Schema validation failed. FastAPI returns the field-level error list. |
| `502` | Upstream failure (GitHub or Ollama) or an unexpected response. |
