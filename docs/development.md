# Development setup (Windows)

## Prerequisites

- Windows 10/11
- Python 3.11+
- Node.js 20+
- Git
- Ollama (required for local AI features; the API skeleton can start without it)

## Clone

```powershell
git clone https://github.com/deathkernel/CodeMAP.git
cd CodeMAP
```

## Ollama

Install Ollama from https://ollama.com/download/windows and start the Ollama app.

CodeMap's default model is configured in `.env.example`:

```text
hf.co/bartowski/Qwen_Qwen3.5-9B-GGUF:Q6_K
```

Pull that exact model tag:

```powershell
ollama pull hf.co/bartowski/Qwen_Qwen3.5-9B-GGUF:Q6_K
ollama list
```

If Ollama is not already running as a Windows app/service, start it with:

```powershell
ollama serve
```

You can change `OLLAMA_BASE_URL` or `OLLAMA_MODEL` in the backend `.env` file. The configured model must be available to the Ollama instance. CodeMap's AI prepare endpoint can also pull the configured model when it is missing.

## Backend

```powershell
cd backend
py -3 -m venv .venv
.\\.venv\\Scripts\\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item ..\\.env.example ..\\.env
uvicorn app.main:app --reload
```

Backend health endpoint: http://127.0.0.1:8000/api/health

API docs: http://127.0.0.1:8000/docs

## Frontend

Open a second terminal:

```powershell
cd frontend
npm install
npm run dev
```

Frontend: http://localhost:3000

## Local code retrieval index

When a repository, folder, or ZIP is analyzed, CodeMap stores bounded source chunks in the local SQLite database configured by `CODEMAP_DATABASE_URL` (default: `./data/codemap.db`, relative to the backend working directory). Codebase Q&A retrieves relevant chunks locally with SQLite FTS5/BM25; a SQLite text-search fallback is used if FTS5 is unavailable. This is keyword retrieval, not semantic vector embeddings. Use **Clear index** in the project Q&A panel to remove that project’s stored chunks. The database and `data/` directory are excluded from Git.

## Safety notes

Never run code from an uploaded repository. ZIP extraction must validate every resolved path remains inside the extraction directory, reject symlinks, and enforce compressed and uncompressed size/count limits. Do not expose uploaded source files to public static hosting. AI prompts and source snippets are sent only to the configured local Ollama endpoint; no hosted AI provider is configured.
