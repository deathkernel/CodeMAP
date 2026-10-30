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



def test_architecture_insights_detect_entry_points_and_folder_groups() -> None:
    from app.services.analyzer import architecture_insights

    graph = analyze_sources({
        "src/main.py": "from src import service",
        "src/service.py": "def run(): return True",
        "README.md": "demo",
        "tests/test_app.py": "pass",
    })
    insights = architecture_insights(graph["nodes"], graph["edges"])
    assert insights["entry_points"][0]["path"] == "src/main.py"
    assert {item["name"]: item["files"] for item in insights["module_groups"]} == {
        "src": 2, "tests": 1, "(root)": 1
    }


def test_architecture_insights_detect_circular_imports() -> None:
    from app.services.analyzer import architecture_insights

    graph = analyze_sources({
        "app/a.py": "import app.b",
        "app/b.py": "import app.a",
        "app/c.py": "value = 1",
    })
    insights = architecture_insights(graph["nodes"], graph["edges"])
    assert insights["circular_dependencies"] == [["app/a.py", "app/b.py"]]


def test_architecture_insights_handles_acyclic_graph() -> None:
    from app.services.analyzer import architecture_insights

    graph = analyze_sources({
        "app/main.py": "from . import service",
        "app/service.py": "value = 1",
    })
    assert architecture_insights(graph["nodes"], graph["edges"])["circular_dependencies"] == []



def test_code_intelligence_reports_graph_metrics() -> None:
    from app.services.analyzer import code_intelligence
    graph = analyze_sources({
        "app/main.py": "import app.service",
        "app/service.py": "import app.data",
        "app/data.py": "value = 1",
        "standalone.py": "value = 2",
    })
    insights = code_intelligence(graph["nodes"], graph["edges"])
    assert insights["dependency_depth"]["max_depth"] == 2
    assert insights["dependency_depth"]["reachable_files"] == 3
    assert insights["dependency_depth"]["unreachable_files"] == 1
    assert insights["dependency_depth"]["deepest_files"] == ["app/data.py"]
    assert {item["path"] for item in insights["unreferenced_files"]} == {"app/main.py", "standalone.py"}
    assert insights["bottleneck_files"] == []


def test_code_intelligence_detects_high_fan_in_bottleneck() -> None:
    from app.services.analyzer import code_intelligence
    graph = analyze_sources({
        "app/a.py": "import app.shared", "app/b.py": "import app.shared",
        "app/c.py": "import app.shared", "app/shared.py": "value = 1",
    })
    insights = code_intelligence(graph["nodes"], graph["edges"])
    shared = next(item for item in insights["bottleneck_files"] if item["path"] == "app/shared.py")
    assert shared["fan_in"] == 3 and shared["fan_out"] == 0


def test_analysis_endpoint_includes_code_intelligence() -> None:
    response = client.post("/api/repository/analyze-folder", json={"files": [
        {"path": "main.py", "content": "import service"},
        {"path": "service.py", "content": "value = 1"},
    ]})
    assert response.status_code == 200
    payload = response.json()
    assert "code_intelligence" in payload
    assert payload["code_intelligence"]["dependency_depth"]["max_depth"] == 1
