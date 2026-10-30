"""Static dependency graph analysis for Python and JavaScript/TypeScript sources.

This module parses source text only. It never imports, evaluates, or executes repository code.
"""
from __future__ import annotations

import ast
import re
from pathlib import PurePosixPath
from typing import Any

JS_IMPORT = re.compile(
    r"""(?:import\s+(?:[^"'\n]*?\s+from\s+)?|export\s+[^"'\n]*?\s+from\s+|require\s*\()\s*['"]([^'"]+)['"]""",
    re.MULTILINE,
)


def _python_imports(source: str) -> list[str]:
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return []
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module)
    return imports


def _js_imports(source: str) -> list[str]:
    return JS_IMPORT.findall(source)


def _resolve_import(source_path: str, imported: str, known_paths: set[str]) -> str | None:
    if not imported.startswith("."):
        return None
    base = PurePosixPath(source_path).parent
    candidate = str((base / imported).as_posix())
    parts: list[str] = []
    for part in candidate.split("/"):
        if part == "..":
            if parts:
                parts.pop()
        elif part not in {"", "."}:
            parts.append(part)
    candidate = "/".join(parts)
    extensions = ("", ".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs")
    index_extensions = ("/index.js", "/index.jsx", "/index.ts", "/index.tsx")
    for suffix in extensions:
        target = candidate + suffix
        if target in known_paths:
            return target
    for suffix in index_extensions:
        target = candidate + suffix
        if target in known_paths:
            return target
    return None


def analyze_sources(sources: dict[str, str], max_files: int = 300) -> dict[str, Any]:
    """Create file nodes and locally-resolved import edges from bounded source strings."""
    paths = sorted(sources)[:max_files]
    known_paths = set(paths)
    nodes = []
    edges = []
    unresolved = 0

    for path in paths:
        source = sources[path]
        suffix = PurePosixPath(path).suffix.lower()
        if suffix == ".py":
            imports = _python_imports(source)
        elif suffix in {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"}:
            imports = _js_imports(source)
        else:
            imports = []

        nodes.append({
            "id": path,
            "type": "file",
            "label": PurePosixPath(path).name,
            "path": path,
            "lines": source.count("\n") + (1 if source else 0),
            "language": suffix.lstrip(".") or "unknown",
        })

        for imported in imports:
            target = _resolve_import(path, imported, known_paths)
            if target:
                edges.append({
                    "id": f"{path}::{target}",
                    "source": path,
                    "target": target,
                    "label": "imports",
                })
            elif imported.startswith("."):
                unresolved += 1

    return {
        "nodes": nodes,
        "edges": edges,
        "stats": {
            "files_analyzed": len(nodes),
            "dependencies_found": len(edges),
            "relative_imports_unresolved": unresolved,
            "files_skipped_by_limit": max(0, len(sources) - len(nodes)),
        },
        "analysis_note": "Static import analysis only; source code was not executed. External package imports are not graph edges.",
    }
