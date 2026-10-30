# Local Ollama setup

CodeMap sends code explanations only to the Ollama endpoint configured for the backend. It does not use a hosted AI provider.

1. Install Ollama for Windows from https://ollama.com/download/windows
2. Start the Ollama app. Keep its local service running at `http://127.0.0.1:11434`.
3. In `backend/.env`, configure:

```env
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=hf.co/bartowski/Qwen_Qwen3.5-9B-GGUF:Qwen3.5-9B-Q6_K.gguf
OLLAMA_REQUEST_TIMEOUT_SECONDS=240
```

4. Start CodeMap. Open a repository, select a file, then choose **Explain with Ollama**.

## Automatic model download

CodeMap checks the configured model when an explanation is requested. If it is missing, CodeMap asks the local Ollama service to download it, then generates the explanation. The first request can take several minutes and requires an internet connection and enough disk space. Later requests reuse the downloaded model.

The default is the locally hosted Qwen3.5 9B GGUF Q6_K model shown above. If you already ran it with `ollama run`, CodeMap should reuse that installed model instead of downloading it again, provided the model name in `ollama list` matches exactly. To use another Ollama model, change `OLLAMA_MODEL`.

Check the local model connection at `GET /api/ai/status`. The response includes `model_installed`.

Source previews are limited to 256 KB and explanation requests to 20,000 characters. Repository source is treated as untrusted input and is never executed by CodeMap. Model downloads happen only when the user requests an AI explanation, not silently at application startup.
