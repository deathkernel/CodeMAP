"""Safe ZIP inventory. Archives are never executed."""

from __future__ import annotations

import stat
import zipfile
from pathlib import PurePosixPath
from typing import Any

MAX_ARCHIVE_BYTES = 50 * 1024 * 1024
MAX_EXTRACTED_BYTES = 250 * 1024 * 1024
MAX_FILES = 5000
SOURCE_SUFFIXES = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".java", ".go", ".rs",
    ".c", ".h", ".cpp", ".cs", ".php", ".rb", ".swift", ".kt", ".vue",
    ".svelte", ".html", ".css", ".scss", ".json", ".yaml", ".yml", ".toml",
    ".md", ".sql", ".sh",
}
SKIP_PARTS = {".git", "node_modules", ".next", "dist", "build", "venv", ".venv", "__pycache__"}

class ArchiveError(ValueError):
    """Raised when an uploaded archive violates safety limits."""


def inspect_zip(data: bytes) -> dict[str, Any]:
    if len(data) > MAX_ARCHIVE_BYTES:
        raise ArchiveError("ZIP exceeds the 50 MB upload limit.")

    files = []
    total_size = 0
    try:
        from io import BytesIO
        with zipfile.ZipFile(BytesIO(data)) as archive:
            infos = archive.infolist()
            if len(infos) > MAX_FILES:
                raise ArchiveError("ZIP contains too many entries.")
            for info in infos:
                path = PurePosixPath(info.filename)
                mode = info.external_attr >> 16
                if path.is_absolute() or ".." in path.parts or "\\" in info.filename:
                    raise ArchiveError("ZIP contains an unsafe file path.")
                if stat.S_ISLNK(mode):
                    raise ArchiveError("ZIP symlinks are not accepted.")
                if info.is_dir():
                    continue
                total_size += info.file_size
                if total_size > MAX_EXTRACTED_BYTES:
                    raise ArchiveError("ZIP expands beyond the 250 MB extraction limit.")
                if info.file_size > 2 * 1024 * 1024:
                    continue
                if any(part in SKIP_PARTS for part in path.parts):
                    continue
                if path.suffix.lower() in SOURCE_SUFFIXES:
                    files.append({"path": info.filename, "size": info.file_size})
    except zipfile.BadZipFile as exc:
        raise ArchiveError("Uploaded file is not a valid ZIP archive.") from exc

    return {
        "files": files,
        "file_count": len(files),
        "archive_entries": len(infos),
        "uncompressed_bytes": total_size,
        "analysis_note": "Safe source-file inventory only. Files were not extracted to disk or executed.",
    }
