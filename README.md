# CodeMap

AI-powered codebase intelligence for understanding repositories locally.

CodeMap accepts a public GitHub repository URL or a ZIP upload, maps source files and dependencies, highlights potential issues, and explains code using a local Ollama model.

## Planned stack

- Frontend: Next.js, TypeScript, Tailwind CSS, React Flow
- Backend: FastAPI, Python
- Parsing: Tree-sitter (incremental language support)
- Local AI: Ollama
- Persistence: SQLite

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
- Source code is sent only to the configured local Ollama endpoint; no cloud AI provider is configured.
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
