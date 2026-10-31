# CodeMap

AI-powered codebase intelligence for understanding repositories locally.

CodeMap accepts a public GitHub repository URL or a ZIP upload, maps source files and dependencies, highlights potential issues, and explains code using a local Ollama model.

## Planned stack

- Frontend: Next.js, TypeScript, Tailwind CSS, React Flow
- Backend: FastAPI, Python
- Parsing: Tree-sitter (incremental language support)
- Local AI (current): Ollama
- Optional hosted AI (planned, explicit opt-in): BharatCode Qwen 3.8 27B API
- Persistence: SQLite


## AI model strategy

**Recommended hosted model for future CodeMAP integration:** BharatCode Qwen 3.8 27B (`qwen-3.8-27b`), for code explanation, repository Q&A, architecture discussion, and AI-assisted potential-issue explanations. BharatCode is the API platform; Qwen 3.8 27B is the model. This is a planned provider option, not an implemented feature in the current CodeMAP pipeline.

- **Free access:** verified eligible Indian students can use Qwen API access up to 10,000,000 total tokens per IST day. Input, cached input, output, and reasoning tokens all count; the allowance resets at midnight IST.
- **Paid access:** BharatCode Lite and Pro include Qwen API access. DeepSeek V4.1 Flash (`deepseek-v4.1-flash`) requires Pro and is not included in the free student Qwen allowance.
- **API base URL:** `https://bharatcode.ai/api/model/v1`; model ID: `qwen-3.8-27b`. The API is OpenAI-compatible and supports `/responses` and `/chat/completions`.
- **API constraints:** requests are stateless, so the client must send conversation history. Hosted tools, background jobs, `store:true`, `previous_response_id`, and audio/video/file input are unsupported. Tool calls are definitions returned to the application; the model provider does not execute CodeMAP tools.
- **Student allowance limits:** this is shared capacity, not guaranteed throughput. Requests may queue, time out, or be delayed during busy periods. The daily allowance is not unlimited.
- **Privacy boundary:** local Ollama remains the default and current implementation. A future hosted mode must be explicitly enabled, show the exact context to be transmitted, and obtain consent before sending code to BharatCode. Never send secrets or an entire repository by default.
- **Credential handling:** store `BHARATCODE_API_KEY` only in the backend environment/secret store. Never expose it to the browser or commit it.
- **Model choice:** use Qwen 3.8 27B as the first hosted model to benchmark. Consider DeepSeek only after measured tests justify a paid Pro plan; do not assume it is free.

Official references: [BharatCode API guide](https://auth.bharatcode.ai/build), [BharatCode pricing](https://www.bharatcode.ai/), and [BharatCode Terms](https://auth.bharatcode.ai/terms).

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
- Current behavior: source code is sent only to the configured local Ollama endpoint; no cloud AI provider is configured.
- Planned BharatCode support must be opt-in per workspace/request. Never upload a repository, source file, secrets, or full code context to a hosted provider by default. Show what will be sent and obtain user consent first.
- Keep BharatCode API credentials server-side in environment variables; never expose keys in frontend bundles or commit them.
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
