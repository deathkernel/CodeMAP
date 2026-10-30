"""Static repository analysis endpoints."""
from __future__ import annotations

import base64
import binascii

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, HttpUrl

from app.services.analyzer import analyze_sources
from app.services.bug_detector import scan_for_bugs
from app.services.repository_scanner import MAX_FILE_BYTES, RepositoryError, parse_github_url, scan_github_repository

router = APIRouter(prefix="/api/repository", tags=["analysis"])
MAX_ANALYZED_FILES = 120


class AnalyzeRequest(BaseModel):
    url: HttpUrl


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
        "bug_findings": bug_report["findings"],
        "bug_stats": bug_report["stats"],
        "bug_analysis_note": bug_report["note"],
        "stats": {
            **graph["stats"],
            "inventory_files": inventory["file_count"],
            "files_not_fetched": max(0, inventory["file_count"] - len(sources)),
        },
    }
