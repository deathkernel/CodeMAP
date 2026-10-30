from fastapi.testclient import TestClient

from app.main import app
from app.services.analyzer import analyze_sources

client = TestClient(app)


def test_python_absolute_import_creates_edge() -> None:
    result = analyze_sources({
        "app/main.py": "from app.routes import repository\n",
        "app/routes/repository.py": "router = None\n",
    })
    assert any(edge["target"] == "app/routes/repository.py" for edge in result["edges"])


def test_typescript_relative_import_creates_edge() -> None:
    result = analyze_sources({
        "src/page.tsx": "import { Card } from './components/Card';\n",
        "src/components/Card.tsx": "export function Card() { return null; }\n",
    })
    assert len(result["edges"]) == 1
    assert result["edges"][0]["target"] == "src/components/Card.tsx"


def test_invalid_python_is_not_executed_or_crashing() -> None:
    result = analyze_sources({"broken.py": "this is not valid python !!!"})
    assert result["nodes"][0]["path"] == "broken.py"
    assert result["edges"] == []



def test_local_folder_analysis_builds_graph_and_bug_report() -> None:
    response = client.post("/api/repository/analyze-folder", json={
        "folder_name": "demo-app",
        "files": [
            {"path": "app/main.py", "content": "from app import utils\nvalue = eval('1')\n"},
            {"path": "app/utils.py", "content": "def helper():\n    return True\n"},
        ],
    })
    assert response.status_code == 200
    payload = response.json()
    assert payload["repository"] == "demo-app"
    assert payload["stats"]["files_analyzed"] == 2
    assert payload["stats"]["dependencies_found"] == 1
    assert any(item["rule_id"] == "dynamic-code-execution" for item in payload["bug_findings"])


def test_local_folder_analysis_rejects_traversal() -> None:
    response = client.post("/api/repository/analyze-folder", json={
        "files": [{"path": "../outside.py", "content": "print('no')"}],
    })
    assert response.status_code == 400


def test_local_folder_analysis_rejects_oversized_file() -> None:
    response = client.post("/api/repository/analyze-folder", json={
        "files": [{"path": "main.py", "content": "x" * (256 * 1024 + 1)}],
    })
    assert response.status_code == 413
