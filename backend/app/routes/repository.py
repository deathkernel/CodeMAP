"""Repository ingestion endpoints."""

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel, HttpUrl

from app.services.repository_scanner import RepositoryError, scan_github_repository
from app.services.zip_scanner import ArchiveError, inspect_zip

router = APIRouter(prefix="/api/repository", tags=["repository"])


class RepositoryRequest(BaseModel):
    url: HttpUrl


@router.post("/github")
async def inspect_github(request: RepositoryRequest):
    try:
        return await scan_github_repository(str(request.url))
    except RepositoryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail="GitHub could not be reached or returned an invalid response.") from exc


@router.post("/zip")
async def inspect_zip_upload(file: UploadFile = File(...)):
    if not file.filename or not file.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="Upload a .zip file.")
    data = await file.read(50 * 1024 * 1024 + 1)
    try:
        return inspect_zip(data)
    except ArchiveError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        await file.close()
