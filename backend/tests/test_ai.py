from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_ollama_status_reports_unavailable_without_server(monkeypatch) -> None:
    class BrokenClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def get(self, *args, **kwargs):
            import httpx
            raise httpx.ConnectError("not running")

    monkeypatch.setattr("app.routes.ai.httpx.AsyncClient", BrokenClient)
    response = client.get("/api/ai/status")
    assert response.status_code == 200
    assert response.json()["available"] is False


def test_explain_rejects_empty_source() -> None:
    response = client.post("/api/ai/explain", json={
        "path": "main.py",
        "language": "python",
        "code": "",
    })
    assert response.status_code == 422


def test_bug_explainer_rejects_empty_source() -> None:
    response = client.post("/api/ai/explain-bug", json={
        "path": "main.py",
        "language": "python",
        "line": 3,
        "rule_id": "dynamic-code-execution",
        "title": "Dynamic code execution",
        "severity": "high",
        "message": "eval() executes a string.",
        "recommendation": "Avoid eval().",
        "code": "",
    })
    assert response.status_code == 422


def test_bug_explainer_rejects_invalid_severity() -> None:
    response = client.post("/api/ai/explain-bug", json={
        "path": "main.py",
        "language": "python",
        "line": 3,
        "rule_id": "dynamic-code-execution",
        "title": "Dynamic code execution",
        "severity": "critical",
        "message": "eval() executes a string.",
        "recommendation": "Avoid eval().",
        "code": "value = eval(user_input)",
    })
    assert response.status_code == 422


def test_bug_explainer_returns_local_model_result(monkeypatch) -> None:
    async def fake_generate(prompt: str):
        assert "dynamic-code-execution" in prompt
        assert "value = eval(user_input)" in prompt
        return "local-model", False, "Use a safe parser instead of eval."

    monkeypatch.setattr("app.routes.ai._generate_local", fake_generate)
    response = client.post("/api/ai/explain-bug", json={
        "path": "main.py",
        "language": "python",
        "line": 1,
        "rule_id": "dynamic-code-execution",
        "title": "Dynamic code execution",
        "severity": "high",
        "message": "eval() executes dynamic code.",
        "recommendation": "Avoid eval().",
        "code": "value = eval(user_input)",
    })
    assert response.status_code == 200
    assert response.json()["model"] == "local-model"
    assert "safe parser" in response.json()["explanation"]


def test_legacy_gguf_model_setting_maps_to_installed_tag(monkeypatch) -> None:
    monkeypatch.setenv(
        "OLLAMA_MODEL",
        "hf.co/bartowski/Qwen_Qwen3.5-9B-GGUF:Qwen3.5-9B-Q6_K.gguf",
    )
    _, model = __import__("app.routes.ai", fromlist=["_settings"])._settings()
    assert model == "hf.co/bartowski/Qwen_Qwen3.5-9B-GGUF:Q6_K"
