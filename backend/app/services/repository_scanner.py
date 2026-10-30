"""Safe, bounded ingestion for public GitHub repositories."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

import httpx

GITHUB_API = "https://api.github.com"
MAX_FILES = 3000
MAX_FILE_BYTES = 256_000
SOURCE_SUFFIXES = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".java", ".go",
    ".rs", ".c", ".h", ".cpp", ".hpp", ".cs", ".php", ".rb", ".swift",
    ".kt", ".kts", ".vue", ".svelte", ".html", ".css", ".scss", ".json",
    ".yaml", ".yml", ".toml", ".md", ".sql", ".sh",
}
SKIP_PARTS = {".git", "node_modules", ".next", "dist", "build", "venv", ".venv", "__pycache__"}

class RepositoryError(ValueError):
    """Raised when a repository cannot be safely inspected."""


def parse_github_url(value: str) -> tuple[str, str]:
    parsed = urlparse(value.strip())
    if parsed.scheme != "https" or parsed.hostname not in {"github.com", "www.github.com"}:
        raise RepositoryError("Enter a valid https://github.com/owner/repository URL.")
    parts = [part for part in parsed.path.strip("/").split("/") if part]
    if len(parts) != 2:
        raise RepositoryError("Repository URL must contain an owner and repository name.")
    owner, name = parts
    if not re.fullmatch(r"[A-Za-z0-9-]{1,39}", owner) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", name):
        raise RepositoryError("Repository URL contains invalid characters.")
    return owner, name.removesuffix(".git")


async def scan_github_repository(url: str) -> dict[str, Any]:
    owner, name = parse_github_url(url)
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    async with httpx.AsyncClient(timeout=20, follow_redirects=False, headers=headers) as client:
        response = await client.get(f"{GITHUB_API}/repos/{owner}/{name}")
        if response.status_code == 404:
            raise RepositoryError("Repository not found or not public.")
        response.raise_for_status()
        metadata = response.json()
        branch = metadata["default_branch"]
        tree_response = await client.get(
            f"{GITHUB_API}/repos/{owner}/{name}/git/trees/{branch}",
            params={"recursive": "1"},
        )
        tree_response.raise_for_status()
        tree = tree_response.json()

    entries = []
    for item in tree.get("tree", []):
        path = item.get("path", "")
        if item.get("type") != "blob" or any(part in SKIP_PARTS for part in path.split("/")):
            continue
        if not any(path.lower().endswith(suffix) for suffix in SOURCE_SUFFIXES):
            continue
        entries.append({"path": path, "size": item.get("size", 0), "sha": item.get("sha")})
        if len(entries) >= MAX_FILES:
            break

    return {
        "repository": metadata["full_name"],
        "description": metadata.get("description"),
        "default_branch": branch,
        "stars": metadata.get("stargazers_count", 0),
        "files": entries,
        "file_count": len(entries),
        "tree_truncated": tree.get("truncated", False),
        "analysis_note": "File inventory only. No repository code was downloaded or executed.",
    }
