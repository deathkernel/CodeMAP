from app.services.code_index import index_project_sources, make_project_id, search_project_sources


def test_project_index_chunks_and_retrieves_relevant_source(tmp_path, monkeypatch) -> None:
    database = tmp_path / "codemap-index.db"
    monkeypatch.setenv("CODEMAP_DATABASE_URL", f"sqlite:///{database.as_posix()}")
    sources = {
        "app/database.py": "def connect_database():\n    return create_connection()\n",
        "app/ui.py": "def render_page():\n    return '<main />'\n",
    }
    project_id = make_project_id("demo", "main", sources)

    count = index_project_sources(project_id, sources)
    results = search_project_sources(project_id, "database connection", limit=4)

    assert count == 2
    assert results
    assert results[0]["path"] == "app/database.py"
    assert results[0]["start_line"] == 1


def test_project_indexes_are_isolated(tmp_path, monkeypatch) -> None:
    database = tmp_path / "codemap-index.db"
    monkeypatch.setenv("CODEMAP_DATABASE_URL", f"sqlite:///{database.as_posix()}")
    first = make_project_id("first", "main", {"a.py": "def first_project(): pass"})
    second = make_project_id("second", "main", {"a.py": "def second_project(): pass"})

    index_project_sources(first, {"a.py": "def first_project(): pass"})
    index_project_sources(second, {"a.py": "def second_project(): pass"})

    first_results = search_project_sources(first, "first_project")
    second_results = search_project_sources(second, "second_project")

    assert first_results and first_results[0]["content"].find("first_project") >= 0
    assert second_results and second_results[0]["content"].find("second_project") >= 0
    assert search_project_sources(first, "second_project") == []
