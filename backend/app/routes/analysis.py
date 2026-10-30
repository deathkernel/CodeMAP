"""Static repository analysis endpoints."""
from __future__ import annotations

import base64
import binascii

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, HttpUrl, Field

from app.services.analyzer import analyze_sources, architecture_insights, code_intelligence
from app.services.bug_detector import scan_for_bugs
from app.services.repository_scanner import MAX_FILE_BYTES, RepositoryError, parse_github_url, scan_github_repository

router = APIRouter(prefix="/api/repository", tags=["analysis"])
MAX_ANALYZED_FILES = 120
MAX_FOLDER_FILE_BYTES = 256 * 1024
MAX_FOLDER_TOTAL_BYTES = 8 * 1024 * 1024
FOLDER_SOURCE_SUFFIXES = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".java", ".go",
    ".rs", ".c", ".h", ".cpp", ".cs", ".php", ".rb", ".swift", ".kt",
    ".vue", ".svelte", ".html", ".css", ".scss", ".json", ".yaml", ".yml",
    ".toml", ".md", ".sql", ".sh",
}
FOLDER_SKIP_PARTS = {
    ".git", "node_modules", ".next", "dist", "build", "venv", ".venv",
    "__pycache__", ".idea", ".vscode",
}


class AnalyzeRequest(BaseModel):
    url: HttpUrl


class FolderFile(BaseModel):
    path: str = Field(min_length=1, max_length=1024)
    content: str


class FolderAnalyzeRequest(BaseModel):
    folder_name: str = Field(default="Local project", min_length=1, max_length=160)
    files: list[FolderFile] = Field(min_length=1, max_length=MAX_ANALYZED_FILES)


@router.post("/analyze")
async def analyze_github(request: AnalyzeRequest):
    try:
        inventory = await scan_github_repository(str(request.url))
        owner, name = parse_github_url(str(request.url))
    except RepositoryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail="GitHub repository could not be inspected.") from exc

    selected = [
        item for item in inventory["files"]
        if item.get("sha") and item.get("size", 0) <= MAX_FILE_BYTES
    ][:MAX_ANALYZED_FILES]
    sources: dict[str, str] = {}
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}

    async with httpx.AsyncClient(timeout=20, follow_redirects=False, headers=headers) as client:
        for item in selected:
            response = await client.get(
                f"https://api.github.com/repos/{owner}/{name}/git/blobs/{item['sha']}"
            )
            if response.status_code == 404:
                continue
            response.raise_for_status()
            payload = response.json()
            if payload.get("encoding") != "base64":
                continue
            try:
                raw = base64.b64decode(payload.get("content", ""), validate=False)
                sources[item["path"]] = raw[:MAX_FILE_BYTES].decode("utf-8", errors="replace")
            except (binascii.Error, ValueError):
                continue

    graph = analyze_sources(sources)
    bug_report = scan_for_bugs(sources)
    return {
        "repository": inventory["repository"],
        "default_branch": inventory["default_branch"],
        **graph,
        "architecture_insights": architecture_insights(graph["nodes"], graph["edges"]),
        "code_intelligence": code_intelligence(graph["nodes"], graph["edges"]),
        "bug_findings": bug_report["findings"],
        "bug_stats": bug_report["stats"],
        "bug_analysis_note": bug_report["note"],
        "stats": {
            **graph["stats"],
            "inventory_files": inventory["file_count"],
            "files_not_fetched": max(0, inventory["file_count"] - len(sources)),
        },
    }



@router.post("/analyze-folder")
async def analyze_local_folder(request: FolderAnalyzeRequest):
    """Analyze browser-selected local folder contents without storing or executing files."""
    from pathlib import PurePosixPath

    sources: dict[str, str] = {}
    total_bytes = 0

    for item in request.files:
        path = PurePosixPath(item.path)
        if path.is_absolute() or ".." in path.parts or "\\" in item.path:
            raise HTTPException(status_code=400, detail="Folder contains an unsafe file path.")
        if any(part in FOLDER_SKIP_PARTS for part in path.parts):
            continue
        if path.suffix.lower() not in FOLDER_SOURCE_SUFFIXES:
            continue

        encoded_size = len(item.content.encode("utf-8"))
        if encoded_size > MAX_FOLDER_FILE_BYTES:
            raise HTTPException(status_code=413, detail=f"File exceeds 256 KB limit: {item.path}")
        total_bytes += encoded_size
        if total_bytes > MAX_FOLDER_TOTAL_BYTES:
            raise HTTPException(status_code=413, detail="Selected source files exceed the 8 MB analysis limit.")
        sources[item.path] = item.content

    if not sources:
        raise HTTPException(status_code=400, detail="No supported source files were found in this folder.")

    graph = analyze_sources(sources)
    bug_report = scan_for_bugs(sources)
    return {
        "repository": request.folder_name,
        "default_branch": "Local folder",
        **graph,
        "architecture_insights": architecture_insights(graph["nodes"], graph["edges"]),
        "code_intelligence": code_intelligence(graph["nodes"], graph["edges"]),
        "bug_findings": bug_report["findings"],
        "bug_stats": bug_report["stats"],
        "bug_analysis_note": bug_report["note"],
        "stats": {
            **graph["stats"],
            "inventory_files": len(sources),
            "files_not_fetched": 0,
        },
        "source_files": len(sources),
        "analysis_note": "Local folder analysis. Selected source text was sent only to this local CodeMap backend; files were not written to disk or executed.",
    }
