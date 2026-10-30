"""Bounded source-file retrieval for public GitHub repositories."""
from __future__ import annotations

import base64
import binascii
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, HttpUrl, Field

from app.services.repository_scanner import MAX_FILE_BYTES, RepositoryError, parse_github_url, scan_github_repository

router = APIRouter(prefix="/api/repository", tags=["source"])


class SourceRequest(BaseModel):
    url: HttpUrl
    path: str = Field(min_length=1, max_length=500)


@router.post("/source")
async def get_source(request: SourceRequest) -> dict[str, Any]:
    try:
        owner, name = parse_github_url(str(request.url))
        inventory = await scan_github_repository(str(request.url))
    except RepositoryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail="GitHub repository could not be inspected.") from exc

    match = next((item for item in inventory["files"] if item["path"] == request.path), None)
    if not match:
        raise HTTPException(status_code=404, detail="File not found in the indexed source inventory.")
    if match.get("size", 0) > MAX_FILE_BYTES:
        raise HTTPException(status_code=413, detail="File is larger than the 256 KB preview limit.")

    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    async with httpx.AsyncClient(timeout=20, follow_redirects=False, headers=headers) as client:
        response = await client.get(f"https://api.github.com/repos/{owner}/{name}/git/blobs/{match['sha']}")
        if response.status_code == 404:
            raise HTTPException(status_code=404, detail="Source blob no longer exists.")
        response.raise_for_status()
        payload = response.json()

    if payload.get("encoding") != "base64":
        raise HTTPException(status_code=415, detail="GitHub returned an unsupported source encoding.")
    try:
        raw = base64.b64decode(payload.get("content", ""), validate=False)
        code = raw[:MAX_FILE_BYTES].decode("utf-8", errors="replace")
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(status_code=502, detail="Could not decode source file.") from exc

    return {"path": request.path, "content": code, "truncated": len(raw) > MAX_FILE_BYTES}
