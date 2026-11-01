# Development setup

This guide gets a development environment running on Windows (PowerShell), macOS, or Linux, and explains how to run the test suite.

- [Prerequisites](#prerequisites)
- [Clone](#clone)
- [Backend](#backend)
- [Frontend](#frontend)
- [Ollama (optional)](#ollama-optional)
- [Running the tests](#running-the-tests)
- [How the local index works](#how-the-local-index-works)
- [Troubleshooting](#troubleshooting)
- [Safety notes](#safety-notes)

---

## Prerequisites

| Tool | Version | Notes |
|---|---|---|
| Python | 3.11 or newer | CI uses 3.11. Windows users can use the `py` launcher. |
| Node.js | 20 or newer | Includes `npm`. CI uses 20. |
| Git | any recent version | |
| Ollama | latest | **Optional.** Required only for AI explanations and Q&A. |

Everything except AI features runs without Ollama.

## Clone

```bash
git clone https://github.com/deathkernel/CodeMAP.git
cd CodeMAP
```

## Backend

### Windows (PowerShell)

```powershell
cd backend
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements-dev.txt
Copy-Item ..\.env.example ..\.env
uvicorn app.main:app --reload
```

> If PowerShell blocks the activation script, run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once, then try again.

### macOS and Linux

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements-dev.txt
cp ../.env.example ../.env
uvicorn app.main:app --reload
```

### Verify

- Health: <http://127.0.0.1:8000/api/health>, which should return `{"status": "ok", "service": "codemap-api"}`.
- Interactive API docs: <http://127.0.0.1:8000/docs>.

The backend loads `.env` with python-dotenv's default search, so the copy at the repository root (as shown above) is picked up. Keep secrets out of Git; `.env` is already ignored.

## Frontend

Open a second terminal.

```bash
cd frontend
npm install
npm run dev
```

The app runs at <http://localhost:3000>. Next.js reads environment files from the `frontend/` folder, not the repository root. If you need a different backend URL, create `frontend/.env.local` with `NEXT_PUBLIC_API_URL=http://127.0.0.1:8000`. The variable is read at build time, so restart `npm run dev` after changing it. Without it, the app defaults to `http://localhost:8000`.

To produce a production build, which also type-checks the whole app:

```bash
npm run build
```

## Ollama (optional)

1. Install Ollama from <https://ollama.com/download> and start it. It listens on `http://127.0.0.1:11434`.
2. Pull the generation model that CodeMap is configured to use:

   ```bash
   ollama pull hf.co/bartowski/Qwen_Qwen3.5-9B-GGUF:Q6_K
   ```

3. For semantic code search, pull the embedding model:

   ```bash
   ollama pull nomic-embed-text
   ```

   Without it, Q&A still works through keyword search, and the response reports `retrieval_mode: keyword`.

You can change the models in `.env` with `OLLAMA_MODEL` and `CODEMAP_EMBEDDING_MODEL`. The configured generation model must match `ollama list` exactly. When you request an AI explanation, CodeMap checks for the model and can ask Ollama to download it through `POST /api/ai/prepare`. See [ollama-setup.md](ollama-setup.md).

## Running the tests

The backend test suite lives in `backend/tests/` and is configured by `backend/pytest.ini`.

```bash
cd backend
python -m pytest              # full suite
python -m pytest -q tests/test_ingestion.py   # one file
python -m pytest -k zip       # tests whose names match a keyword
```

CI runs the same command on pushes and pull requests to `main`. The frontend is validated by `npm run build` in CI. There are no frontend unit tests yet.

Lint: `npm run lint` requires an ESLint configuration file, which is on the roadmap. Until it is added, rely on `npm run build`, which type-checks the code.

## How the local index works

When a repository, folder, or ZIP is analyzed, CodeMap stores bounded source chunks in the SQLite database set by `CODEMAP_DATABASE_URL` (default `./data/codemap.db`, relative to the backend working directory).

- **Keyword retrieval is always on.** It uses SQLite FTS5 with BM25 ranking. If FTS5 is unavailable in your SQLite build, CodeMap falls back to a plain table with `LIKE` search.
- **Semantic retrieval is optional.** If `nomic-embed-text` (or your configured embedding model) is installed, CodeMap stores an embedding for each chunk in a background job. Keyword and vector results are combined with reciprocal-rank fusion.
- **Clearing the index** removes one project's chunks, embeddings, and caches. Use **Clear index** in the project Q&A panel, or call `DELETE /api/repository/index/{project_id}`.

The `data/` directory and the database files are excluded from Git.

## Troubleshooting

| Symptom | Likely cause and fix |
|---|---|
| `Activate.ps1 cannot be loaded because running scripts is disabled` | Run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once. |
| `ModuleNotFoundError` when starting Uvicorn | The virtual environment is not active. Activate it, then run `pip install -r requirements-dev.txt` again. |
| Analysis requests fail immediately | Confirm the backend is running on port 8000, and that `NEXT_PUBLIC_API_URL` matches it (see the Frontend section). Restart `npm run dev` after changing it. |
| GitHub analysis returns `502` | GitHub is unreachable, or the unauthenticated rate limit (60 requests per hour) was reached. Wait and retry. |
| AI features show "Could not reach local Ollama." | Confirm Ollama is running on `OLLAMA_BASE_URL`, then check `GET /api/ai/status`. |
| AI explanation fails with a missing model | Run `ollama list` and confirm the name matches `OLLAMA_MODEL` exactly. |
| Q&A says `retrieval_mode: keyword` | The embedding model is not installed. This is expected without `nomic-embed-text`. |

## Safety notes

- **Never run code from an analyzed repository.** CodeMap parses source as text. Do not add features that import or execute repository files.
- ZIP extraction must validate that every resolved path stays inside the target directory, reject symlinks, and enforce compressed and uncompressed size and count limits. The current implementation does not extract to disk at all.
- Do not expose uploaded source files through static hosting.
- AI prompts and source snippets are sent only to the configured local Ollama endpoint. No hosted AI provider is configured.
- Keep the backend bound to `127.0.0.1`. The API has no authentication. See [SECURITY.md](SECURITY.md).
