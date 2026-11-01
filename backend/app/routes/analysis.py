"""Static repository analysis endpoints."""
from __future__ import annotations

import asyncio
import base64
import binascii

import httpx
from fastapi import APIRouter, BackgroundTasks, File, HTTPException, UploadFile
from pydantic import BaseModel, HttpUrl, Field

from app.services.analyzer import analyze_sources_incremental, architecture_insights, architecture_health, code_intelligence, symbol_intelligence, advanced_architecture_intelligence
from app.services.bug_detector import scan_for_bugs_incremental
from app.services.repository_scanner import MAX_FILE_BYTES, RepositoryError, parse_github_url, scan_github_repository
from app.services.zip_scanner import ArchiveError, MAX_ARCHIVE_BYTES, read_zip_sources
from app.services.code_index import delete_project_index, index_project_sources_incremental, make_stable_project_id, create_embedding_job, run_embedding_job, get_index_job, count_project_embeddings, count_project_chunks

router = APIRouter(prefix="/api/repository", tags=["analysis"])
MAX_ANALYZED_FILES = 1000
MAX_FOLDER_FILE_BYTES = 256 * 1024
MAX_FOLDER_TOTAL_BYTES = 64 * 1024 * 1024
MAX_TOTAL_SOURCE_BYTES = 64 * 1024 * 1024
GITHUB_FETCH_BATCH_SIZE = 16
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
async def analyze_github(request: AnalyzeRequest, background_tasks: BackgroundTasks):
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
    total_source_bytes = 0
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}

    async def fetch_blob(client: httpx.AsyncClient, item: dict) -> tuple[str, str] | None:
        response = await client.get(
            f"https://api.github.com/repos/{owner}/{name}/git/blobs/{item['sha']}"
        )
        if response.status_code == 404:
            return None
        response.raise_for_status()
        payload = response.json()
        if payload.get("encoding") != "base64":
            return None
        try:
            raw = base64.b64decode(payload.get("content", ""), validate=False)
            if len(raw) > MAX_FILE_BYTES:
                return None
            return item["path"], raw.decode("utf-8", errors="replace")
        except (binascii.Error, ValueError):
            return None

    async with httpx.AsyncClient(timeout=20, follow_redirects=False, headers=headers) as client:
        for offset in range(0, len(selected), GITHUB_FETCH_BATCH_SIZE):
            batch = selected[offset:offset + GITHUB_FETCH_BATCH_SIZE]
            results = await asyncio.gather(*(fetch_blob(client, item) for item in batch))
            for result in results:
                if result is None:
                    continue
                path, source = result
                source_size = len(source.encode("utf-8"))
                if total_source_bytes + source_size > MAX_TOTAL_SOURCE_BYTES:
                    continue
                sources[path] = source
                total_source_bytes += source_size

    project_id = make_stable_project_id(inventory["repository"], inventory["default_branch"])
    index_update = index_project_sources_incremental(
        project_id, sources,
        prune_missing=(not inventory.get("tree_truncated", False) and len(sources) == inventory["file_count"]),
    )
    indexed_chunks = count_project_chunks(project_id)
    embedding_job = create_embedding_job(project_id)
    if embedding_job["created"]:
        background_tasks.add_task(run_embedding_job, embedding_job["job_id"], project_id)
    indexed_embeddings = count_project_embeddings(project_id)
    graph = analyze_sources_incremental(project_id, sources)
    bug_report = scan_for_bugs_incremental(project_id, sources)
    symbols = symbol_intelligence(sources)
    advanced_architecture = advanced_architecture_intelligence(sources, graph["nodes"], graph["edges"])
    return {
        "project_id": project_id,
        "indexed_chunks": indexed_chunks,
        "index_update": index_update,
        "indexed_embeddings": indexed_embeddings,
        "semantic_index_available": indexed_embeddings > 0,
        "embedding_job": {"job_id": embedding_job["job_id"], "status": embedding_job["status"]},
        "repository": inventory["repository"],
        "default_branch": inventory["default_branch"],
        **graph,
        "symbol_intelligence": symbols,
        "architecture_insights": architecture_insights(graph["nodes"], graph["edges"]),
        "advanced_architecture": advanced_architecture,
        "code_intelligence": code_intelligence(graph["nodes"], graph["edges"]),
        "architecture_health": architecture_health(graph["nodes"], graph["edges"], bug_report["findings"]),
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
async def analyze_local_folder(request: FolderAnalyzeRequest, background_tasks: BackgroundTasks):
    """Analyze browser-selected local folder contents without extracting or executing files."""
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
            raise HTTPException(status_code=413, detail="Selected source files exceed the 64 MB analysis limit.")
        sources[item.path] = item.content

    if not sources:
        raise HTTPException(status_code=400, detail="No supported source files were found in this folder.")

    project_id = make_stable_project_id(request.folder_name, "Local folder")
    index_update = index_project_sources_incremental(project_id, sources, prune_missing=True)
    indexed_chunks = count_project_chunks(project_id)
    embedding_job = create_embedding_job(project_id)
    if embedding_job["created"]:
        background_tasks.add_task(run_embedding_job, embedding_job["job_id"], project_id)
    indexed_embeddings = count_project_embeddings(project_id)
    graph = analyze_sources_incremental(project_id, sources)
    bug_report = scan_for_bugs_incremental(project_id, sources)
    symbols = symbol_intelligence(sources)
    advanced_architecture = advanced_architecture_intelligence(sources, graph["nodes"], graph["edges"])
    return {
        "project_id": project_id,
        "indexed_chunks": indexed_chunks,
        "index_update": index_update,
        "indexed_embeddings": indexed_embeddings,
        "semantic_index_available": indexed_embeddings > 0,
        "embedding_job": {"job_id": embedding_job["job_id"], "status": embedding_job["status"]},
        "repository": request.folder_name,
        "default_branch": "Local folder",
        **graph,
        "symbol_intelligence": symbols,
        "architecture_insights": architecture_insights(graph["nodes"], graph["edges"]),
        "advanced_architecture": advanced_architecture,
        "code_intelligence": code_intelligence(graph["nodes"], graph["edges"]),
        "architecture_health": architecture_health(graph["nodes"], graph["edges"], bug_report["findings"]),
        "bug_findings": bug_report["findings"],
        "bug_stats": bug_report["stats"],
        "bug_analysis_note": bug_report["note"],
        "stats": {
            **graph["stats"],
            "inventory_files": len(sources),
            "files_not_fetched": 0,
        },
        "source_files": len(sources),
        "analysis_note": "Local folder analysis. Files were not executed or copied as raw files; bounded source chunks are stored in the local SQLite retrieval index for project Q&A.",
    }


@router.post("/analyze-zip")
async def analyze_zip_upload(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    """Analyze supported source files from a ZIP entirely in memory."""
    if not file.filename or not file.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="Upload a .zip file.")

    try:
        data = await file.read(MAX_ARCHIVE_BYTES + 1)
        if len(data) > MAX_ARCHIVE_BYTES:
            raise HTTPException(status_code=413, detail="ZIP exceeds the 50 MB upload limit.")

        archive = read_zip_sources(data)
        sources = archive["sources"]
        project_id = make_stable_project_id(file.filename[:-4] or "Uploaded ZIP", "ZIP archive")
        index_update = index_project_sources_incremental(
            project_id, sources, prune_missing=(archive["files_skipped_by_limit"] == 0),
        )
        indexed_chunks = count_project_chunks(project_id)
        embedding_job = create_embedding_job(project_id)
        if embedding_job["created"]:
            background_tasks.add_task(run_embedding_job, embedding_job["job_id"], project_id)
        indexed_embeddings = count_project_embeddings(project_id)
        graph = analyze_sources_incremental(project_id, sources)
        bug_report = scan_for_bugs_incremental(project_id, sources)
        symbols = symbol_intelligence(sources)
        advanced_architecture = advanced_architecture_intelligence(sources, graph["nodes"], graph["edges"])
        return {
            "project_id": project_id,
            "indexed_chunks": indexed_chunks,
            "index_update": index_update,
            "indexed_embeddings": indexed_embeddings,
            "semantic_index_available": indexed_embeddings > 0,
            "embedding_job": {"job_id": embedding_job["job_id"], "status": embedding_job["status"]},
            "repository": file.filename[:-4] or "Uploaded ZIP",
            "default_branch": "ZIP archive",
            **graph,
            "symbol_intelligence": symbols,
            "architecture_insights": architecture_insights(graph["nodes"], graph["edges"]),
            "advanced_architecture": advanced_architecture,
            "code_intelligence": code_intelligence(graph["nodes"], graph["edges"]),
            "architecture_health": architecture_health(graph["nodes"], graph["edges"], bug_report["findings"]),
            "bug_findings": bug_report["findings"],
            "bug_stats": bug_report["stats"],
            "bug_analysis_note": bug_report["note"],
            "stats": {
                **graph["stats"],
                "inventory_files": archive["source_files"] + archive["files_skipped_by_limit"],
                "files_not_fetched": archive["files_skipped_by_limit"],
                "archive_entries": archive["archive_entries"],
                "source_bytes_analyzed": archive["source_bytes"],
            },
            "source_contents": sources,
            "source_files": archive["source_files"],
            "analysis_note": (
                "ZIP source files were analyzed in memory and never extracted or executed. Bounded source chunks are persisted in local SQLite for project Q&A. "
                f"{archive['files_skipped_by_limit']} supported files were skipped by analysis limits."
            ),
        }
    except ArchiveError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        await file.close()



@router.get("/jobs/{job_id}")
async def get_background_job(job_id: str):
    """Read the status of a persisted background indexing job."""
    import re

    if not re.fullmatch(r"[a-f0-9]{32}", job_id):
        raise HTTPException(status_code=400, detail="Invalid background job identifier.")
    job = get_index_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Background job not found.")
    return job



@router.delete("/index/{project_id}")
async def clear_project_index(project_id: str):
    """Delete only the local retrieval chunks associated with one project."""
    import re

    if not re.fullmatch(r"[a-f0-9]{24}", project_id):
        raise HTTPException(status_code=400, detail="Invalid project index identifier.")
    deleted_chunks = delete_project_index(project_id)
    return {"project_id": project_id, "deleted_chunks": deleted_chunks}
