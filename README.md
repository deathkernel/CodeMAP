# CodeMap

AI-powered codebase intelligence for understanding repositories locally.

CodeMap accepts a public GitHub repository URL or a ZIP upload, maps source files and dependencies, highlights potential issues, and explains code using a local Ollama model.

## Planned stack

- Frontend: Next.js, TypeScript, Tailwind CSS, React Flow
- Backend: FastAPI, Python
- Parsing: Tree-sitter (incremental language support)
- Local AI: Ollama
- Persistence: SQLite

## AI model strategy

CodeMap uses Ollama for local AI features, including code explanation and AI-assisted explanations of potential issues.

- **Runtime:** Ollama running on the user's machine.
- **Configuration:** Set `OLLAMA_BASE_URL` and `OLLAMA_MODEL` in the backend environment.
- **Default model:** `hf.co/bartowski/Qwen_Qwen3.5-9B-GGUF:Q6_K`.
- **Privacy:** AI prompts and source snippets are sent to the configured local Ollama endpoint. No hosted AI provider is configured.
- **Model management:** CodeMap can check whether the configured model is installed and prepare it through Ollama.

## Implemented capabilities

- GitHub repository analysis, local folder analysis, and ZIP upload analysis.
- ZIP files are inspected and read in memory; repository code is never extracted to disk or executed.
- Static dependency graph, folder navigation, architecture insights, architecture health, and code intelligence.
- Framework-aware architecture intelligence: candidate entry points, API route mapping, Python/Prisma/SQL relationship hints, and cross-module dependency summaries.
- Static bug detection includes Python AST logic checks, cross-file Python and JavaScript/TypeScript import resolution, dynamic SQL construction checks, and high-signal command-execution/TLS patterns for PHP, Java, Go, Ruby, and C#.
- Large-repository engine: stable project IDs, per-file content hashes, changed/removed-file-only SQLite chunk updates, cached per-file import extraction for incremental dependency graphs, changed-file-only bug rescans with cached findings, incremental local embeddings, persisted background embedding jobs (`GET /api/repository/jobs/{job_id}`), bounded batch writes, concurrent GitHub blob fetching, and up to 1,000 source files / 64 MB per analysis where the ingestion path supports it.
- Static potential-issue checks for Python plus selected JavaScript/TypeScript security patterns.
- Local Ollama explanations for source files, findings, and architecture summaries.
- Project-scoped codebase Q&A using a local SQLite retrieval index. Python and JavaScript/TypeScript functions and classes are indexed as focused chunks where recognized; other files use bounded text chunks. Retrieval combines SQLite FTS5/BM25 keyword ranking with local Ollama vector embeddings using reciprocal-rank fusion. If the embedding model is unavailable, Q&A falls back to BM25/SQLite text search. The UI can clear a project's indexed chunks and embeddings.
- Graph exports: PNG and Mermaid.
- Advanced reporting: downloadable architecture/quality/security PDF reports, complete JSON analysis export, and SQLite-backed before/after snapshots with health, dependency, module-risk, and finding-count deltas. Reporting API: `POST /api/reports/architecture.pdf`, `POST /api/reports/snapshots`, and `GET /api/reports/compare/{project_id}`.

## Local semantic retrieval

- **Generation model:** remains `OLLAMA_MODEL` (default Qwen 3.5 9B Q6_K); this is not changed by semantic indexing.
- **Embedding model:** `CODEMAP_EMBEDDING_MODEL` (default `nomic-embed-text`), used only through the local Ollama `/api/embed` endpoint.
- **Install once:** run `ollama pull nomic-embed-text` on the same machine as Ollama. CodeMap does not automatically download this embedding model.
- **Storage:** vectors and source chunks are stored in the local SQLite database and removed together when a project's index is cleared.
- **Fallback:** if the embedding model is not installed or the local embedding endpoint is unavailable, indexing/Q&A continue with keyword retrieval; the analysis response reports `semantic_index_available` and Q&A reports its `retrieval_mode`.
- **Privacy:** embedding requests go only to the configured local Ollama endpoint; no hosted embedding API is used.

## Repository layout

```
CodeMAP/
├── frontend/              # Next.js web application
├── backend/
│   └── app/
│       ├── routes/        # API endpoints
│       ├── services/      # scanners, parser, graph, findings, Ollama
│       └── models/        # API/domain schemas
├── tests/
├── docs/
├── .env.example
└── README.md
```

## Safety principles

- Uploaded archives are treated as untrusted input.
- ZIP extraction must reject path traversal and enforce file/count/size limits.
- Repository code is analyzed as data and is never executed.
- AI prompts and retrieved source excerpts are sent only to the configured local Ollama endpoint; no cloud AI provider is configured. Bounded source chunks are persisted locally in SQLite for codebase Q&A and can be cleared per project from the UI.
- Keep local service configuration on the backend. Do not expose private configuration in frontend bundles.
- Findings are labelled as potential issues unless independently confirmed.

## Development status

All five planned major feature areas are implemented: advanced static bug detection, semantic RAG, advanced architecture intelligence, large-repository processing, and advanced reporting. Testing and validation are intentionally pending.

## Local setup

See [docs/development.md](docs/development.md) for the Windows-first setup instructions.

## License

MIT
