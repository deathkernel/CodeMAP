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
- Static potential-issue checks for Python plus selected JavaScript/TypeScript security patterns.
- Local Ollama explanations for source files, findings, and architecture summaries.
- Project-scoped codebase Q&A using a local SQLite retrieval index. Source files are split into overlapping chunks; SQLite FTS5/BM25 retrieves relevant excerpts before they are sent to the local Ollama model. A simple SQLite text-search fallback is used when FTS5 is unavailable. The UI can clear a project's indexed chunks.
- Graph exports: PNG and Mermaid.

The retrieval index is local keyword-based retrieval, not a semantic embedding/vector index. It reuses the configured Ollama generation model and does not require a separate embedding model.

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

Core workflows are implemented: GitHub/local-folder/ZIP ingestion, dependency visualization, architecture and static-issue analysis, local Ollama explanations, and project-scoped codebase Q&A. Backend tests and the frontend production build are being validated through GitHub Actions.

## Next improvements

- Add semantic embedding-based retrieval when a suitable local embedding model is selected; current SQLite FTS5/BM25 retrieval is keyword-based.
- Expand language-specific static checks and parser coverage.
- Improve incremental indexing and performance on very large repositories.

## Local setup

See [docs/development.md](docs/development.md) for the Windows-first setup instructions.

## License

MIT
