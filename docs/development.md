# Development setup (Windows)

## Prerequisites

- Windows 10/11
- Python 3.11+
- Node.js 20+
- Git
- Ollama (optional for the initial API skeleton)

## Clone

```powershell
git clone https://github.com/deathkernel/CodeMAP.git
cd CodeMAP
```

## Backend

```powershell
cd backend
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item ..\.env.example ..\.env
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

## Ollama

Install Ollama from https://ollama.com/download/windows, then pull the configured model:

```powershell
ollama pull qwen2.5-coder:7b
ollama serve
```

Model choice depends on available RAM/VRAM. You can choose a smaller model in `.env`.

## Safety notes

Never run code from an uploaded repository. ZIP extraction must validate every resolved path remains inside the extraction directory, reject symlinks, and enforce compressed and uncompressed size/count limits. Do not expose uploaded source files to public static hosting.
