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
    """Calculate graph connectivity and dependency-depth indicators."""
    paths = [node["path"] for node in nodes]
    known = set(paths)
    incoming = {path: 0 for path in paths}
    outgoing = {path: 0 for path in paths}
    adjacency = {path: [] for path in paths}
    for edge in edges:
        source, target = edge.get("source"), edge.get("target")
        if source in known and target in known:
            outgoing[source] += 1
            incoming[target] += 1
            adjacency[source].append(target)
    bottlenecks = [
        {"path": path, "fan_in": incoming[path], "fan_out": outgoing[path],
         "connections": incoming[path] + outgoing[path]}
        for path in paths if incoming[path] >= 2 or outgoing[path] >= 3
    ]
    bottlenecks.sort(key=lambda item: (-item["connections"], item["path"]))
    roots = [path for path in paths if incoming[path] == 0]
    distances: dict[str, int] = {}
    queue = [(path, 0) for path in roots]
    while queue:
        current, depth = queue.pop(0)
        if current in distances and distances[current] <= depth:
            continue
        distances[current] = depth
        queue.extend((target, depth + 1) for target in adjacency[current])
    deepest = max(distances.values(), default=0)
    return {
        "bottleneck_files": bottlenecks[:10],
        "unreferenced_files": [
            {"path": path, "reason": "No incoming import edge in the analyzed graph"}
            for path in paths if incoming[path] == 0
        ],
        "dependency_depth": {
            "max_depth": deepest, "reachable_files": len(distances),
            "unreachable_files": len(paths) - len(distances),
            "deepest_files": sorted(path for path, depth in distances.items() if depth == deepest) if distances else [],
        },
        "code_intelligence_note": "Connectivity and depth use only locally resolved imports. Unreferenced files may still be used by frameworks, dynamic imports, tests, or external entry points.",
    }


def architecture_health(
    nodes: list[dict[str, Any]], edges: list[dict[str, Any]],
    bug_findings: list[dict[str, Any]],
) -> dict[str, Any]:
    """Produce transparent heuristic module complexity and risk indicators."""
    known = {node["path"] for node in nodes}
    node_by_path = {node["path"]: node for node in nodes}
    incoming = {path: 0 for path in known}
    outgoing = {path: 0 for path in known}
    for edge in edges:
        source, target = edge.get("source"), edge.get("target")
        if source in known and target in known:
            outgoing[source] += 1
            incoming[target] += 1

    cycles = architecture_insights(nodes, edges)["circular_dependencies"]
    cycle_files = {path for cycle in cycles for path in cycle}
    findings_by_module: dict[str, dict[str, int]] = {}
    for finding in bug_findings:
        path = finding.get("path", "")
        if path not in known:
            continue
        parts = PurePosixPath(path).parts
        module = parts[0] if len(parts) > 1 else "(root)"
        counts = findings_by_module.setdefault(module, {"high": 0, "medium": 0, "low": 0})
        severity = finding.get("severity", "low")
        if severity in counts:
            counts[severity] += 1

    grouped: dict[str, list[str]] = {}
    for path in sorted(known):
        parts = PurePosixPath(path).parts
        grouped.setdefault(parts[0] if len(parts) > 1 else "(root)", []).append(path)

    module_health = []
    for module, paths in grouped.items():
        path_set = set(paths)
        module_edges = [edge for edge in edges if edge.get("source") in path_set and edge.get("target") in known]
        internal = sum(1 for edge in module_edges if edge.get("target") in path_set)
        external = len(module_edges) - internal
        total_lines = sum(node_by_path[path].get("lines", 0) for path in paths)
        average_lines = total_lines / max(1, len(paths))
        average_connections = sum(incoming[path] + outgoing[path] for path in paths) / max(1, len(paths))
        cycle_count = sum(1 for path in paths if path in cycle_files)
        bugs = findings_by_module.get(module, {"high": 0, "medium": 0, "low": 0})
        complexity = min(100, round(average_lines / 2 + average_connections * 10 + external * 3))
        risk = min(100, bugs["high"] * 18 + bugs["medium"] * 8 + bugs["low"] * 3 + cycle_count * 12 + max(0, average_connections - 3) * 8)
        module_health.append({
            "name": module, "files": len(paths), "lines": total_lines,
            "dependencies": len(module_edges), "internal_dependencies": internal,
            "external_dependencies": external, "circular_files": cycle_count,
            "bug_counts": bugs, "complexity_score": complexity,
            "risk_score": round(risk),
            "risk_level": "high" if risk >= 45 else "medium" if risk >= 20 else "low",
        })
    module_health.sort(key=lambda item: (-item["risk_score"], -item["complexity_score"], item["name"]))
    total_bugs = {
        severity: sum(1 for finding in bug_findings if finding.get("severity") == severity)
        for severity in ("high", "medium", "low")
    }
    penalties = len(cycles) * 12 + total_bugs["high"] * 10 + total_bugs["medium"] * 4 + total_bugs["low"]
    score = max(0, 100 - min(100, penalties))
    factors = []
    if cycles:
        factors.append(f"{len(cycles)} circular dependency group(s)")
    if total_bugs["high"]:
        factors.append(f"{total_bugs['high']} high-severity static finding(s)")
    if total_bugs["medium"]:
        factors.append(f"{total_bugs['medium']} medium-severity static finding(s)")
    if not factors:
        factors.append("No circular groups or high/medium static findings detected")
    return {
        "health_score": score,
        "health_grade": "healthy" if score >= 85 else "watch" if score >= 65 else "needs_attention",
        "risk_factors": factors,
        "module_health": module_health,
        "health_stats": {
            "modules": len(module_health),
            "high_risk_modules": sum(1 for item in module_health if item["risk_level"] == "high"),
            "medium_risk_modules": sum(1 for item in module_health if item["risk_level"] == "medium"),
            "circular_files": len(cycle_files), "bug_findings": len(bug_findings),
        },
        "health_note": "Heuristic indicators based on analyzed lines, locally resolved imports, detected cycles, and static findings. Complexity is not cyclomatic complexity; the score is not a guarantee of code quality or runtime correctness.",
    }
}


def symbol_intelligence(sources: dict[str, str], max_symbols: int = 2000) -> dict[str, Any]:
    """Extract static Python/JS/TS symbol declarations and unambiguous local call links."""
    declarations: list[dict[str, Any]] = []
    raw_calls: list[dict[str, Any]] = []
    js_declaration = re.compile(
        r"^\\s*(?:(?:export|default|async|public|private|protected|static)\\s+)*"
        r"(function|class)\\s+([A-Za-z_$][\\w$]*)"
    )
    js_variable = re.compile(
        r"^\\s*(?:(?:export|default|async)\\s+)*(?:const|let|var)\\s+"
        r"([A-Za-z_$][\\w$]*)\\s*=\\s*(?:async\\s*)?(?:function\\b|(?:\\([^)]*\\)|[A-Za-z_$][\\w$]*)\\s*=>)"
    )
    call_pattern = re.compile(r"\\b([A-Za-z_$][\\w$]*)\\s*\\(")

    for path, source in sorted(sources.items()):
        suffix = PurePosixPath(path).suffix.lower()
        if suffix == ".py":
            try:
                tree = ast.parse(source)
            except (SyntaxError, ValueError):
                continue

            class Visitor(ast.NodeVisitor):
                def __init__(self) -> None:
                    self.scope: list[tuple[str, int, int]] = []

                def visit_FunctionDef(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
                    qualified = ".".join([name for name, _, _ in self.scope] + [node.name])
                    declarations.append({
                        "id": f"{path}:{node.lineno}:{qualified}", "path": path,
                        "name": node.name, "qualified_name": qualified, "kind": "function",
                        "line": node.lineno, "end_line": getattr(node, "end_lineno", node.lineno),
                    })
                    self.scope.append((node.name, node.lineno, getattr(node, "end_lineno", node.lineno)))
                    for child in node.body:
                        self.visit(child)
                    self.scope.pop()

                visit_AsyncFunctionDef = visit_FunctionDef

                def visit_ClassDef(self, node: ast.ClassDef) -> None:
                    qualified = ".".join([name for name, _, _ in self.scope] + [node.name])
                    declarations.append({
                        "id": f"{path}:{node.lineno}:{qualified}", "path": path,
                        "name": node.name, "qualified_name": qualified, "kind": "class",
                        "line": node.lineno, "end_line": getattr(node, "end_lineno", node.lineno),
                    })
                    self.scope.append((node.name, node.lineno, getattr(node, "end_lineno", node.lineno)))
                    for child in node.body:
                        self.visit(child)
                    self.scope.pop()

                def visit_Call(self, node: ast.Call) -> None:
                    if isinstance(node.func, ast.Name):
                        name = node.func.id
                    elif isinstance(node.func, ast.Attribute):
                        name = node.func.attr
                    else:
                        name = ""
                    if name:
                        raw_calls.append({
                            "path": path, "name": name, "line": node.lineno,
                            "caller": self.scope[-1][0] if self.scope else "(module)",
                        })
                    self.generic_visit(node)

            Visitor().visit(tree)
        elif suffix in {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"}:
            lines = source.splitlines()
            found: list[dict[str, Any]] = []
            for index, line in enumerate(lines, 1):
                match = js_declaration.match(line)
                if match:
                    kind, name = match.groups()
                else:
                    variable = js_variable.match(line)
                    if not variable:
                        continue
                    kind, name = "function", variable.group(1)
                found.append({
                    "id": f"{path}:{index}:{name}", "path": path, "name": name,
                    "qualified_name": name, "kind": kind.lower(),
                    "line": index, "end_line": len(lines),
                })
            for position, item in enumerate(found):
                item["end_line"] = found[position + 1]["line"] - 1 if position + 1 < len(found) else len(lines)
            declarations.extend(found)
            ranges = [(item["line"], item["end_line"], item["name"]) for item in found]
            for index, line in enumerate(lines, 1):
                caller = next((name for start, end, name in reversed(ranges) if start <= index <= end), "(module)")
                for match in call_pattern.finditer(line):
                    raw_calls.append({"path": path, "name": match.group(1), "line": index, "caller": caller})

    declarations = declarations[:max_symbols]
    by_name: dict[str, list[dict[str, Any]]] = {}
    for symbol in declarations:
        by_name.setdefault(symbol["name"], []).append(symbol)

    call_edges: list[dict[str, Any]] = []
    for call in raw_calls:
        targets = by_name.get(call["name"], [])
        if len(targets) != 1:
            continue
        target = targets[0]
        if target["path"] == call["path"] and target["name"] == call["caller"]:
            continue
        call_edges.append({
            "id": f"{call['path']}:{call['line']}:{call['caller']}->{target['id']}",
            "source_path": call["path"], "target_path": target["path"],
            "caller": call["caller"], "callee": target["qualified_name"],
            "line": call["line"], "target_line": target["line"],
        })
    unique_edges = {edge["id"]: edge for edge in call_edges}
    return {
        "symbols": declarations,
        "call_edges": list(unique_edges.values())[:5000],
        "symbol_stats": {
            "symbols": len(declarations),
            "functions": sum(1 for item in declarations if item["kind"] == "function"),
            "classes": sum(1 for item in declarations if item["kind"] == "class"),
            "resolved_call_links": min(len(unique_edges), 5000),
        },
        "symbol_note": "Static symbol extraction. Python declarations and calls use AST; JavaScript/TypeScript uses line-based patterns. Call links are emitted only when a name resolves to exactly one analyzed declaration. This is not a complete language parser or proof of runtime calls.",
    }
