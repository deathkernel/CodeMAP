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

This is the Phase 1 repository foundation. The analysis pipeline and UI are being built incrementally.

## Planned milestones

1. Foundation: API skeleton, configuration, health check, dashboard shell.
2. Ingestion: validated GitHub URL and safe ZIP upload.
3. Analysis: source inventory, imports and dependency graph.
4. Visualization: interactive architecture and dependency explorer.
5. Local AI: Ollama explanations and contextual analysis.
6. Findings: static checks and AI-assisted potential bug explanations.

## Local setup

See [docs/development.md](docs/development.md) for the Windows-first setup instructions.

## License

MIT
