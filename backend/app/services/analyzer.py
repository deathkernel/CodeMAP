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
            prefix = "." * node.level + node.module
            if node.names and node.names[0].name != "*":
                imports.extend(f"{prefix}.{alias.name}" for alias in node.names)
            else:
                imports.append(prefix)
    return imports


def _js_imports(source: str) -> list[str]:
    return JS_IMPORT.findall(source)


def _resolve_import(source_path: str, imported: str, known_paths: set[str], python: bool = False) -> str | None:
    if imported.startswith("."):
        candidate = str((PurePosixPath(source_path).parent / imported).as_posix())
        parts: list[str] = []
        for part in candidate.split("/"):
            if part == "..":
                if parts:
                    parts.pop()
            elif part not in {"", "."}:
                parts.append(part)
        candidate = "/".join(parts)
    elif python:
        candidate = imported.replace(".", "/")
    else:
        return None

    extensions = ("", ".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs")
    index_extensions = ("/__init__.py", "/index.js", "/index.jsx", "/index.ts", "/index.tsx")
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
        is_python = suffix == ".py"
        if is_python:
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
            target = _resolve_import(path, imported, known_paths, python=is_python)
            if target:
                edges.append({"id": f"{path}::{target}", "source": path, "target": target, "label": "imports"})
            elif imported.startswith(".") or is_python:
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



def architecture_insights(nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarize likely entry points, import cycles, and top-level modules."""
    paths = [node["path"] for node in nodes]
    known = set(paths)
    entry_names = {
        "__main__.py", "main.py", "app.py", "wsgi.py", "asgi.py",
        "index.js", "index.jsx", "index.ts", "index.tsx",
        "main.js", "main.jsx", "main.ts", "main.tsx",
        "server.js", "server.ts", "cli.py",
    }
    entry_points = [
        {"path": path, "reason": "Recognized application entry-point filename"}
        for path in paths if PurePosixPath(path).name.lower() in entry_names
    ]
    adjacency: dict[str, list[str]] = {path: [] for path in known}
    for edge in edges:
        source, target = edge.get("source"), edge.get("target")
        if source in known and target in known and target not in adjacency[source]:
            adjacency[source].append(target)

    # Tarjan strongly-connected components identify groups participating in cycles.
    index = 0
    stack: list[str] = []
    on_stack: set[str] = set()
    indices: dict[str, int] = {}
    lowlink: dict[str, int] = {}
    cycles: list[list[str]] = []

    def visit(node: str) -> None:
        nonlocal index
        indices[node] = lowlink[node] = index
        index += 1
        stack.append(node)
        on_stack.add(node)
        for target in adjacency[node]:
            if target not in indices:
                visit(target)
                lowlink[node] = min(lowlink[node], lowlink[target])
            elif target in on_stack:
                lowlink[node] = min(lowlink[node], indices[target])
        if lowlink[node] == indices[node]:
            component: list[str] = []
            while stack:
                member = stack.pop()
                on_stack.remove(member)
                component.append(member)
                if member == node:
                    break
            if len(component) > 1:
                cycles.append(sorted(component))

    for path in sorted(known):
        if path not in indices:
            visit(path)

    groups: dict[str, int] = {}
    for path in paths:
        parts = PurePosixPath(path).parts
        group = parts[0] if len(parts) > 1 else "(root)"
        groups[group] = groups.get(group, 0) + 1

    return {
        "entry_points": entry_points,
        "circular_dependencies": cycles,
        "module_groups": [
            {"name": name, "files": count}
            for name, count in sorted(groups.items(), key=lambda item: (-item[1], item[0]))
        ],
        "architecture_stats": {
            "entry_points": len(entry_points),
            "circular_dependency_groups": len(cycles),
            "top_level_modules": len(groups),
        },
        "architecture_note": "Entry points are filename-based candidates. Circular dependencies are detected only across locally resolved imports in the analyzed file set.",
    }


def code_intelligence(nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> dict[str, Any]:
    """Calculate import-graph metrics; these do not prove semantic usage."""
    paths = sorted({node["path"] for node in nodes})
    known = set(paths)
    outgoing = {path: set() for path in paths}
    incoming = {path: set() for path in paths}
    for edge in edges:
        source, target = edge.get("source"), edge.get("target")
        if source in known and target in known:
            outgoing[source].add(target)
            incoming[target].add(source)
    metrics = [
        {"path": path, "fan_in": len(incoming[path]), "fan_out": len(outgoing[path]),
         "connections": len(incoming[path]) + len(outgoing[path])}
        for path in paths
    ]
    bottlenecks = sorted(
        (item for item in metrics if item["fan_in"] >= 2 or item["fan_out"] >= 3),
        key=lambda item: (-(item["fan_in"] + item["fan_out"]), item["path"]),
    )[:10]
    unreferenced = [
        {"path": path, "reason": "No analyzed file imports this file"}
        for path in paths if not incoming[path]
    ]
    roots = [path for path in paths if not incoming[path]]
    depths = {path: 0 for path in roots}
    queue, cursor = list(roots), 0
    while cursor < len(queue):
        current = queue[cursor]
        cursor += 1
        for target in sorted(outgoing[current]):
            if target not in depths:
                depths[target] = depths[current] + 1
                queue.append(target)
    max_depth = max(depths.values(), default=0)
    deepest = sorted(path for path, depth in depths.items() if depth == max_depth)
    return {
        "bottleneck_files": bottlenecks,
        "unreferenced_files": unreferenced,
        "dependency_depth": {
            "max_depth": max_depth, "reachable_files": len(depths),
            "unreachable_files": max(0, len(paths) - len(depths)), "deepest_files": deepest[:10],
        },
        "code_intelligence_note": (
            "Metrics describe locally resolved imports in the analyzed file set. Unreferenced means "
            "zero incoming import edges, not proof that a file is unused; dynamic imports, framework "
            "conventions, and external entry points may be missed. Depth is shortest distance from "
            "files with zero incoming edges."
        ),
    }
