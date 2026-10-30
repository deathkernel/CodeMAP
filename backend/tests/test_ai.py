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
