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



def test_architecture_explainer_uses_local_model(monkeypatch) -> None:
    async def fake_generate(prompt: str):
        assert "demo-app" in prompt
        assert "circular_dependencies" in prompt
        return "local-model", False, "The project has two main modules."

    monkeypatch.setattr("app.routes.ai._generate_local", fake_generate)
    response = client.post("/api/ai/explain-architecture", json={
        "repository": "demo-app",
        "stats": {"files_analyzed": 4, "dependencies_found": 3},
        "architecture_insights": {
            "entry_points": [{"path": "app/main.py"}],
            "circular_dependencies": [],
            "module_groups": [{"name": "app", "files": 4}],
        },
        "architecture_health": {"health_score": 90, "health_grade": "healthy"},
        "code_intelligence": {"dependency_depth": {"max_depth": 2}},
        "symbol_stats": {"symbols": 5, "functions": 4, "classes": 1},
        "bug_stats": {"total": 0},
    })
    assert response.status_code == 200
    assert response.json()["model"] == "local-model"
    assert "two main modules" in response.json()["explanation"]


def test_architecture_explainer_rejects_oversized_summary() -> None:
    response = client.post("/api/ai/explain-architecture", json={
        "repository": "large-demo",
        "stats": {"files_analyzed": 1},
        "architecture_insights": {"details": "x" * 25000},
        "architecture_health": {},
        "code_intelligence": {},
        "symbol_stats": {},
        "bug_stats": {},
    })
    assert response.status_code == 413



def test_codebase_qa_uses_retrieved_source_chunks(monkeypatch) -> None:
    def fake_search(project_id: str, query: str, limit: int = 6):
        assert project_id == "project123"
        assert "authentication" in query
        return [{
            "path": "app/auth.py",
            "start_line": 12,
            "content": "def authenticate(token): return validate(token)",
            "score": -1.2,
        }]

    async def fake_generate(prompt: str):
        assert "app/auth.py" in prompt
        assert "validate(token)" in prompt
        return "local-model", False, "Authentication is handled in app/auth.py."

    monkeypatch.setattr("app.routes.ai.search_project_sources", fake_search)
    monkeypatch.setattr("app.routes.ai._generate_local", fake_generate)
    response = client.post("/api/ai/ask-codebase", json={
        "project_id": "project123",
        "repository": "demo-app",
        "question": "How does authentication work?",
    })
    assert response.status_code == 200
    assert response.json()["sources"] == [{"path": "app/auth.py", "start_line": 12}]
    assert "app/auth.py" in response.json()["answer"]


def test_codebase_qa_returns_not_found_without_retrieved_context(monkeypatch) -> None:
    monkeypatch.setattr("app.routes.ai.search_project_sources", lambda *args, **kwargs: [])
    response = client.post("/api/ai/ask-codebase", json={
        "project_id": "project123",
        "repository": "demo-app",
        "question": "Where is authentication handled?",
    })
    assert response.status_code == 404
