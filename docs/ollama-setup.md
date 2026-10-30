# Local Ollama setup

CodeMap sends code explanations only to the Ollama endpoint configured for the backend. It does not use a hosted AI provider.

1. Install Ollama for Windows from https://ollama.com/download/windows
2. Start the Ollama app. Keep its local service running at `http://127.0.0.1:11434`.
3. In `backend/.env`, configure:

```env
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=qwen2.5-coder:3b
OLLAMA_REQUEST_TIMEOUT_SECONDS=180
```

4. Start CodeMap. Open a repository, select a file, then choose **Explain with Ollama**.

## Automatic model download

CodeMap checks the configured model when an explanation is requested. If it is missing, CodeMap automatically asks the local Ollama service to download it, then generates the explanation. The first request can take several minutes and requires an internet connection and enough disk space. Later requests reuse the downloaded model.

The default is `qwen2.5-coder:3b`. To use another Ollama model, change `OLLAMA_MODEL`; CodeMap will automatically pull that model if it is not installed.

Check the local model connection at `GET /api/ai/status`. The response includes `model_installed`.

Source previews are limited to 256 KB and explanation requests to 20,000 characters. Repository source is treated as untrusted input and is never executed by CodeMap. Model downloads happen only when the user requests an AI explanation, not silently at application startup.
