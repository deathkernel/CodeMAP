# Local Ollama setup

CodeMap sends code explanations only to the Ollama endpoint configured for the backend. It does not use a hosted AI provider.

1. Install Ollama for Windows from https://ollama.com/download/windows
2. Open PowerShell and run:

```powershell
ollama pull qwen2.5-coder:7b
ollama serve
```

3. In `backend/.env`, configure:

```env
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=qwen2.5-coder:7b
OLLAMA_REQUEST_TIMEOUT_SECONDS=120
```

4. Start the CodeMap backend and frontend. Open a repository, select a file, then choose **Explain with Ollama**.

Check the local model connection at `GET /api/ai/status`.

The default model can use several GB of RAM. Choose a smaller Ollama coder model if your PC has limited memory. Source previews are limited to 256 KB and explanation requests to 20,000 characters. Repository source is treated as untrusted input and is never executed by CodeMap.
