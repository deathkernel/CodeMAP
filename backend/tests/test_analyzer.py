from app.services.analyzer import analyze_sources


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
