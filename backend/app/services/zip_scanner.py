"""Safe ZIP inventory and in-memory source loading. Archives are never executed."""

from __future__ import annotations

import stat
import zipfile
from io import BytesIO
from pathlib import PurePosixPath
from typing import Any

MAX_ARCHIVE_BYTES = 50 * 1024 * 1024
MAX_EXTRACTED_BYTES = 250 * 1024 * 1024
MAX_FILES = 5000
MAX_ANALYZED_FILES = 1000
MAX_SOURCE_FILE_BYTES = 256 * 1024
MAX_ANALYZED_SOURCE_BYTES = 64 * 1024 * 1024

SOURCE_SUFFIXES = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".java", ".go", ".rs",
    ".c", ".h", ".cpp", ".hpp", ".cs", ".php", ".rb", ".swift", ".kt", ".kts",
    ".vue", ".svelte", ".html", ".css", ".scss", ".json", ".yaml", ".yml", ".toml",
    ".md", ".sql", ".sh",
}
SKIP_PARTS = {
    ".git", "node_modules", ".next", "dist", "build", "venv", ".venv",
    "__pycache__", ".idea", ".vscode",
}


class ArchiveError(ValueError):
    """Raised when an uploaded archive violates safety limits."""


def _open_archive(data: bytes) -> zipfile.ZipFile:
    if len(data) > MAX_ARCHIVE_BYTES:
        raise ArchiveError("ZIP exceeds the 50 MB upload limit.")
    try:
        archive = zipfile.ZipFile(BytesIO(data))
        infos = archive.infolist()
        if len(infos) > MAX_FILES:
            archive.close()
            raise ArchiveError("ZIP contains too many entries.")

        total_size = 0
        seen_paths: set[str] = set()
        for info in infos:
            filename = info.filename
            path = PurePosixPath(filename)
            mode = info.external_attr >> 16
            if (
                path.is_absolute()
                or ".." in path.parts
                or "\\" in filename
                or "\x00" in filename
                or (path.parts and ":" in path.parts[0])
            ):
                archive.close()
                raise ArchiveError("ZIP contains an unsafe file path.")
            if stat.S_ISLNK(mode):
                archive.close()
                raise ArchiveError("ZIP symlinks are not accepted.")
            if info.flag_bits & 0x1:
                archive.close()
                raise ArchiveError("Password-protected ZIP entries are not supported.")
            if not info.is_dir():
                if filename in seen_paths:
                    archive.close()
                    raise ArchiveError("ZIP contains duplicate file paths.")
                seen_paths.add(filename)
                total_size += info.file_size
                if total_size > MAX_EXTRACTED_BYTES:
                    archive.close()
                    raise ArchiveError("ZIP expands beyond the 250 MB extraction limit.")
        return archive
    except zipfile.BadZipFile as exc:
        raise ArchiveError("Uploaded file is not a valid ZIP archive.") from exc


def inspect_zip(data: bytes) -> dict[str, Any]:
    archive = _open_archive(data)
    try:
        files = []
        for info in archive.infolist():
            path = PurePosixPath(info.filename)
            if info.is_dir() or info.file_size > 2 * 1024 * 1024:
                continue
            if any(part in SKIP_PARTS for part in path.parts):
                continue
            if path.suffix.lower() in SOURCE_SUFFIXES:
                files.append({"path": info.filename, "size": info.file_size})

        return {
            "files": files,
            "file_count": len(files),
            "archive_entries": len(archive.infolist()),
            "uncompressed_bytes": sum(info.file_size for info in archive.infolist() if not info.is_dir()),
            "analysis_note": "Safe source-file inventory only. Files were not extracted to disk or executed.",
        }
    finally:
        archive.close()


def read_zip_sources(data: bytes) -> dict[str, Any]:
    """Read a bounded set of supported source files into memory without extracting to disk."""
    archive = _open_archive(data)
    sources: dict[str, str] = {}
    total_source_bytes = 0
    skipped_by_limit = 0
    archive_entries = len(archive.infolist())

    try:
        for info in archive.infolist():
            if info.is_dir():
                continue
            path = PurePosixPath(info.filename)
            if any(part in SKIP_PARTS for part in path.parts):
                continue
            if path.suffix.lower() not in SOURCE_SUFFIXES:
                continue
            if info.file_size > MAX_SOURCE_FILE_BYTES:
                skipped_by_limit += 1
                continue
            if len(sources) >= MAX_ANALYZED_FILES:
                skipped_by_limit += 1
                continue
            if total_source_bytes + info.file_size > MAX_ANALYZED_SOURCE_BYTES:
                skipped_by_limit += 1
                continue

            try:
                raw = archive.read(info)
            except (RuntimeError, zipfile.BadZipFile, OSError, NotImplementedError, EOFError) as exc:
                raise ArchiveError(f"Could not safely read ZIP entry: {info.filename}") from exc

            if len(raw) > MAX_SOURCE_FILE_BYTES:
                skipped_by_limit += 1
                continue
            total_source_bytes += len(raw)
            sources[info.filename] = raw.decode("utf-8", errors="replace")
    finally:
        archive.close()

    if not sources:
        raise ArchiveError("No supported source files were found within the analysis limits.")

    return {
        "sources": sources,
        "archive_entries": archive_entries,
        "source_files": len(sources),
        "source_bytes": total_source_bytes,
        "files_skipped_by_limit": skipped_by_limit,
    }
