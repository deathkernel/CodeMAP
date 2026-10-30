import io
import zipfile

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.repository_scanner import RepositoryError, parse_github_url
from app.services.zip_scanner import ArchiveError, inspect_zip

client = TestClient(app)


def test_parse_github_url() -> None:
    assert parse_github_url("https://github.com/owner/project.git") == ("owner", "project")


@pytest.mark.parametrize("url", [
    "http://github.com/owner/project",
    "https://github.com/owner/project/issues",
    "https://evil.example/owner/project",
])
def test_reject_invalid_github_url(url: str) -> None:
    with pytest.raises(RepositoryError):
        parse_github_url(url)


def make_zip(name: str = "src/main.py", content: bytes = b"print('hello')") -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(name, content)
    return buffer.getvalue()


def test_zip_inventory_lists_source_files() -> None:
    result = inspect_zip(make_zip())
    assert result["file_count"] == 1
    assert result["files"][0]["path"] == "src/main.py"


def test_zip_rejects_path_traversal() -> None:
    with pytest.raises(ArchiveError):
        inspect_zip(make_zip("../outside.py"))


def test_zip_endpoint_rejects_non_zip() -> None:
    response = client.post("/api/repository/zip", files={"file": ("notes.txt", b"hello")})
    assert response.status_code == 400
