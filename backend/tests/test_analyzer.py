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



def test_code_intelligence_reports_bottlenecks_and_depth() -> None:
    from app.services.analyzer import code_intelligence

    graph = analyze_sources({
        "app/main.py": "import app.service",
        "app/service.py": "import app.shared",
        "app/other.py": "import app.shared",
        "app/shared.py": "value = 1",
        "docs/readme.md": "text",
    })
    result = code_intelligence(graph["nodes"], graph["edges"])
    assert result["dependency_depth"]["max_depth"] == 2
    assert result["dependency_depth"]["reachable_files"] == 4
    assert result["dependency_depth"]["unreachable_files"] == 1
    assert any(item["path"] == "app/shared.py" for item in result["bottleneck_files"])


def test_architecture_health_scores_cycles_and_module_risk() -> None:
    from app.services.analyzer import architecture_health

    graph = analyze_sources({
        "app/a.py": "import app.b\n" + "value = 1\n" * 30,
        "app/b.py": "import app.a\n",
        "app/service.py": "value = 1\n",
        "tests/test_app.py": "value = eval('1')\n",
    })
    findings = [{"path": "tests/test_app.py", "severity": "high", "rule_id": "dynamic-code-execution"}]
    health = architecture_health(graph["nodes"], graph["edges"], findings)
    assert health["health_score"] == 78
    assert health["health_grade"] == "watch"
    assert health["health_stats"]["circular_files"] == 2
    app_module = next(item for item in health["module_health"] if item["name"] == "app")
    assert app_module["circular_files"] == 2
    assert health["health_note"].startswith("Heuristic indicators")


def test_local_folder_response_includes_architecture_health() -> None:
    response = client.post("/api/repository/analyze-folder", json={
        "folder_name": "health-demo",
        "files": [
            {"path": "app/main.py", "content": "import app.service\n"},
            {"path": "app/service.py", "content": "value = eval('1')\n"},
        ],
    })
    assert response.status_code == 200
    payload = response.json()
    assert payload["architecture_health"]["health_stats"]["modules"] == 1
    assert "code_intelligence" in payload


def test_symbol_intelligence_extracts_python_symbols_and_resolves_unique_calls() -> None:
    from app.services.analyzer import symbol_intelligence

    report = symbol_intelligence({
        "app/main.py": "class Service:\n    def run(self):\n        helper()\n\ndef helper():\n    return 1\n",
        "app/other.py": "def unrelated():\n    return 2\n",
    })
    names = {(item["name"], item["kind"]) for item in report["symbols"]}
    assert ("Service", "class") in names
    assert ("run", "function") in names
    assert ("helper", "function") in names
    assert report["symbol_stats"]["functions"] == 3
    assert any(edge["callee"] == "helper" and edge["caller"] == "run" for edge in report["call_edges"])


def test_symbol_intelligence_omits_ambiguous_call_targets() -> None:
    from app.services.analyzer import symbol_intelligence

    report = symbol_intelligence({
        "a.py": "def helper():\n    return 1\n\ndef run():\n    helper()\n",
        "b.py": "def helper():\n    return 2\n",
    })
    assert report["call_edges"] == []


def test_symbol_intelligence_detects_inheritance_duplicates_and_dead_candidates() -> None:
    from app.services.analyzer import symbol_intelligence

    report = symbol_intelligence({
        "app/models.py": (
            "class Base:\n    pass\n\n"
            "class Child(Base):\n    pass\n\n"
            "def first():\n    return 42\n\n"
            "def second():\n    return 42\n\n"
            "def entry():\n    first()\n"
        ),
    })
    assert any(edge["child"] == "Child" and edge["parent"] == "Base" and edge["resolved"] for edge in report["inheritance_edges"])
    assert any({item["name"] for item in group} == {"first", "second"} for group in report["duplicate_function_groups"])
    assert any(item["name"] == "second" for item in report["dead_function_candidates"])
    assert report["symbol_stats"]["inheritance_links"] == 1
