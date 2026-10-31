"""Static dependency graph analysis for Python and JavaScript/TypeScript sources.

This module parses source text only. It never imports, evaluates, or executes repository code.
"""
from __future__ import annotations

import ast
import hashlib
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
    """Calculate graph connectivity and longest dependency depth for acyclic paths."""
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

    roots = [path for path in paths if incoming[path] == 0 and outgoing[path] > 0]
    reachable: set[str] = set()
    queue = list(roots)
    while queue:
        current = queue.pop(0)
        if current in reachable:
            continue
        reachable.add(current)
        queue.extend(adjacency[current])

    # Kahn's algorithm computes the longest path in the acyclic portion of the graph.
    remaining_indegree = dict(incoming)
    longest_depth = {path: 0 for path in roots}
    queue = list(roots)
    processed: set[str] = set()
    while queue:
        current = queue.pop(0)
        processed.add(current)
        for target in adjacency[current]:
            longest_depth[target] = max(
                longest_depth.get(target, 0),
                longest_depth[current] + 1,
            )
            remaining_indegree[target] -= 1
            if remaining_indegree[target] == 0:
                queue.append(target)

    # Nodes held back by a cycle are shown one layer beyond the deepest acyclic path.
    cyclic_or_blocked = (reachable - processed)
    if cyclic_or_blocked:
        cycle_depth = max(longest_depth.values(), default=0) + 1
        for path in cyclic_or_blocked:
            longest_depth[path] = cycle_depth

    deepest = max(longest_depth.values(), default=0)
    return {
        "bottleneck_files": bottlenecks[:10],
        "unreferenced_files": [
            {"path": path, "reason": "No incoming import edge in the analyzed graph"}
            for path in paths if incoming[path] == 0
        ],
        "dependency_depth": {
            "max_depth": deepest, "reachable_files": len(reachable),
            "unreachable_files": len(paths) - len(reachable),
            "deepest_files": sorted(path for path, depth in longest_depth.items() if depth == deepest) if longest_depth else [],
        },
        "code_intelligence_note": "Connectivity and depth use only locally resolved imports. Depth is the longest acyclic dependency chain; cycle-blocked reachable files are placed one layer after the deepest acyclic path. Unreferenced files may still be used by frameworks, dynamic imports, tests, or external entry points.",
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


def symbol_intelligence(sources: dict[str, str], max_symbols: int = 2000) -> dict[str, Any]:
    """Extract static declarations, local call links, inheritance, and code-quality candidates."""
    declarations: list[dict[str, Any]] = []
    raw_calls: list[dict[str, Any]] = []
    inheritance: list[dict[str, Any]] = []
    duplicate_groups: dict[str, list[dict[str, Any]]] = {}
    js_declaration = re.compile(
        r"^\s*(?:(?:export|default|async|public|private|protected|static|abstract)\s+)*"
        r"(function|class)\s+([A-Za-z_$][\w$]*)"
    )
    js_variable = re.compile(
        r"^\s*(?:(?:export|default|async)\s+)*(?:const|let|var)\s+"
        r"([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?(?:function\b|(?:\([^)]*\)|[A-Za-z_$][\w$]*)\s*=>)"
    )
    js_extends = re.compile(
        r"^\s*(?:(?:export|default|abstract)\s+)*class\s+([A-Za-z_$][\w$]*)\s+extends\s+([A-Za-z_$][\w$]*)"
    )
    call_pattern = re.compile(r"\b([A-Za-z_$][\w$]*)\s*\(")

    for path, source in sorted(sources.items()):
        suffix = PurePosixPath(path).suffix.lower()
        if suffix == ".py":
            try:
                tree = ast.parse(source)
            except (SyntaxError, ValueError):
                continue

            class Visitor(ast.NodeVisitor):
                def __init__(self) -> None:
                    self.scope: list[str] = []

                def visit_FunctionDef(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
                    qualified = ".".join(self.scope + [node.name])
                    declarations.append({
                        "id": f"{path}:{node.lineno}:{qualified}", "path": path,
                        "name": node.name, "qualified_name": qualified, "kind": "function",
                        "line": node.lineno, "end_line": getattr(node, "end_lineno", node.lineno),
                        "top_level": not self.scope,
                    })
                    if not self.scope:
                        body_dump = ast.dump(ast.Module(body=node.body, type_ignores=[]), include_attributes=False)
                        fingerprint = hashlib.sha256(body_dump.encode("utf-8")).hexdigest()
                        duplicate_groups.setdefault(fingerprint, []).append(
                            {"path": path, "name": node.name, "line": node.lineno}
                        )
                    self.scope.append(node.name)
                    for child in node.body:
                        self.visit(child)
                    self.scope.pop()

                visit_AsyncFunctionDef = visit_FunctionDef

                def visit_ClassDef(self, node: ast.ClassDef) -> None:
                    qualified = ".".join(self.scope + [node.name])
                    for base in node.bases:
                        base_name = base.id if isinstance(base, ast.Name) else base.attr if isinstance(base, ast.Attribute) else ""
                        if base_name:
                            inheritance.append({
                                "path": path, "child": node.name, "parent": base_name,
                                "line": node.lineno,
                            })
                    declarations.append({
                        "id": f"{path}:{node.lineno}:{qualified}", "path": path,
                        "name": node.name, "qualified_name": qualified, "kind": "class",
                        "line": node.lineno, "end_line": getattr(node, "end_lineno", node.lineno),
                        "top_level": not self.scope,
                    })
                    self.scope.append(node.name)
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
                            "caller": self.scope[-1] if self.scope else "(module)",
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
                    if kind == "class":
                        parent_match = js_extends.match(line)
                        if parent_match:
                            inheritance.append({
                                "path": path, "child": parent_match.group(1),
                                "parent": parent_match.group(2), "line": index,
                            })
                else:
                    variable = js_variable.match(line)
                    if not variable:
                        continue
                    kind, name = "function", variable.group(1)
                found.append({
                    "id": f"{path}:{index}:{name}", "path": path, "name": name,
                    "qualified_name": name, "kind": kind.lower(),
                    "line": index, "end_line": len(lines), "top_level": True,
                })
            for position, item in enumerate(found):
                item["end_line"] = found[position + 1]["line"] - 1 if position + 1 < len(found) else len(lines)
            declarations.extend(found)
            ranges = [(item["line"], item["end_line"], item["name"]) for item in found]
            for index, line in enumerate(lines, 1):
                caller = next((name for first, last, name in reversed(ranges) if first <= index <= last), "(module)")
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
    incoming_calls: dict[str, int] = {}
    for edge in unique_edges.values():
        for target in by_name.get(edge["callee"].split(".")[-1], []):
            if target["path"] == edge["target_path"]:
                incoming_calls[target["id"]] = incoming_calls.get(target["id"], 0) + 1

    dead_candidates = [
        {key: symbol[key] for key in ("id", "path", "name", "qualified_name", "line")}
        for symbol in declarations
        if symbol["kind"] == "function" and symbol.get("top_level")
        and incoming_calls.get(symbol["id"], 0) == 0
        and symbol["name"] not in {"main", "setup", "teardown"}
        and not symbol["name"].startswith("__")
    ]
    duplicates = [group for group in duplicate_groups.values() if len(group) > 1]
    class_names = {item["name"] for item in declarations if item["kind"] == "class"}
    inheritance_edges = [
        {**edge, "resolved": edge["parent"] in class_names}
        for edge in inheritance
    ]

    return {
        "symbols": declarations,
        "call_edges": list(unique_edges.values())[:5000],
        "inheritance_edges": inheritance_edges,
        "dead_function_candidates": dead_candidates[:500],
        "duplicate_function_groups": duplicates[:200],
        "symbol_stats": {
            "symbols": len(declarations),
            "functions": sum(1 for item in declarations if item["kind"] == "function"),
            "classes": sum(1 for item in declarations if item["kind"] == "class"),
            "resolved_call_links": min(len(unique_edges), 5000),
            "inheritance_links": len(inheritance_edges),
            "dead_function_candidates": len(dead_candidates),
            "duplicate_function_groups": len(duplicates),
        },
        "symbol_note": "Static symbol extraction. Python declarations and calls use AST; JavaScript/TypeScript uses line-based patterns. Dead functions are top-level candidates with no resolved incoming calls, not proof of unused code. Duplicate groups compare normalized Python function bodies only. Inheritance links are local name matches and may be incomplete.",
    }



def advanced_architecture_intelligence(
    sources: dict[str, str],
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
) -> dict[str, Any]:
    """Infer framework-aware entry points, API routes, data relations, and module coupling."""
    import json

    frameworks: set[str] = set()
    endpoints: list[dict[str, Any]] = []
    database_relations: list[dict[str, Any]] = []
    entry_points: list[dict[str, str]] = []
    known_paths = {node["path"] for node in nodes}

    package_data: dict[str, Any] = {}
    if "package.json" in sources:
        try:
            package_data = json.loads(sources["package.json"])
        except (ValueError, TypeError):
            package_data = {}
        dependencies = {
            **package_data.get("dependencies", {}),
            **package_data.get("devDependencies", {}),
        }
        for package, framework in (
            ("next", "Next.js"), ("express", "Express"), ("fastify", "Fastify"),
            ("@nestjs/core", "NestJS"), ("koa", "Koa"), ("hono", "Hono"),
            ("react", "React"),
        ):
            if package in dependencies:
                frameworks.add(framework)
        main_file = package_data.get("main")
        if isinstance(main_file, str) and main_file in known_paths:
            entry_points.append({"path": main_file, "framework": "Node.js", "reason": "package.json main field"})

    for manifest, patterns in (
        ("requirements.txt", (("fastapi", "FastAPI"), ("flask", "Flask"), ("django", "Django"))),
        ("pyproject.toml", (("fastapi", "FastAPI"), ("flask", "Flask"), ("django", "Django"))),
        ("Pipfile", (("fastapi", "FastAPI"), ("flask", "Flask"), ("django", "Django"))),
        ("go.mod", (("gin-gonic/gin", "Gin"), ("labstack/echo", "Echo"), ("gofiber/fiber", "Fiber"))),
        ("Cargo.toml", (("actix-web", "Actix Web"), ("axum", "Axum"), ("rocket", "Rocket"))),
    ):
        manifest_text = sources.get(manifest, "").lower()
        for needle, framework in patterns:
            if needle in manifest_text:
                frameworks.add(framework)

    if any(path.endswith("manage.py") for path in known_paths):
        frameworks.add("Django")
    if any(path.endswith(("next.config.js", "next.config.mjs", "next.config.ts")) for path in known_paths):
        frameworks.add("Next.js")

    for path in sorted(known_paths):
        name = PurePosixPath(path).name.lower()
        source = sources.get(path, "")
        suffix = PurePosixPath(path).suffix.lower()

        if name in {"manage.py", "wsgi.py", "asgi.py"}:
            entry_points.append({"path": path, "framework": "Django", "reason": "Django deployment or management entry point"})
        if name in {"main.py", "app.py"} and any(framework in frameworks for framework in ("FastAPI", "Flask")):
            framework = next(framework for framework in ("FastAPI", "Flask") if framework in frameworks)
            entry_points.append({"path": path, "framework": framework, "reason": "Conventional Python web application module"})
        if name in {"main.tsx", "main.jsx", "index.tsx", "index.jsx"} and any(framework in frameworks for framework in ("React", "Next.js")):
            framework = next(framework for framework in ("React", "Next.js") if framework in frameworks)
            entry_points.append({"path": path, "framework": framework, "reason": "Conventional frontend bootstrap file"})
        if path.endswith(("app/page.tsx", "app/page.jsx", "src/app/page.tsx", "src/app/page.jsx")) and "Next.js" in frameworks:
            entry_points.append({"path": path, "framework": "Next.js", "reason": "Next.js App Router page"})
        if path.endswith(("pages/index.tsx", "pages/index.jsx", "src/pages/index.tsx", "src/pages/index.jsx")) and "Next.js" in frameworks:
            entry_points.append({"path": path, "framework": "Next.js", "reason": "Next.js Pages Router page"})

        if suffix == ".py":
            route_pattern = re.compile(
                r"@(?:\w+\.)?(get|post|put|patch|delete|options|head|route)\s*\(\s*['""]([^'""]+)['""]([^)]*)\)",
                re.IGNORECASE,
            )
            for match in route_pattern.finditer(source):
                method = match.group(1).upper()
                methods_match = re.search(r"methods\s*=\s*\[([^]]+)\]", match.group(3), re.IGNORECASE)
                methods = re.findall(r"['""]([A-Z]+)['""]", methods_match.group(1)) if methods_match else []
                if method == "ROUTE":
                    methods = methods or ["GET"]
                for verb in methods or [method]:
                    endpoints.append({
                        "path": path, "line": source.count("\n", 0, match.start()) + 1,
                        "method": verb, "route": match.group(2),
                        "framework": "FastAPI" if "FastAPI" in frameworks else "Flask/Django",
                    })

            for match in re.finditer(r"ForeignKey\s*\(\s*['""]([^'""]+)['""]", source):
                database_relations.append({
                    "path": path, "line": source.count("\n", 0, match.start()) + 1,
                    "source_model": PurePosixPath(path).stem,
                    "target": match.group(1), "kind": "Python ForeignKey",
                })

        if suffix in {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"}:
            route_pattern = re.compile(
                r"\b(?:app|router|server|api)\.(get|post|put|patch|delete|options|head)\s*\(\s*['""]([^'""]+)['""]",
                re.IGNORECASE,
            )
            for match in route_pattern.finditer(source):
                endpoints.append({
                    "path": path, "line": source.count("\n", 0, match.start()) + 1,
                    "method": match.group(1).upper(), "route": match.group(2),
                    "framework": "Express-compatible router",
                })

            if name in {"route.ts", "route.js"}:
                for match in re.finditer(r"\bexport\s+(?:async\s+)?function\s+(GET|POST|PUT|PATCH|DELETE|OPTIONS|HEAD)\b", source):
                    route_path = "/" + path.split("/route.")[0].split("/app/")[-1].strip("/")
                    endpoints.append({
                        "path": path, "line": source.count("\n", 0, match.start()) + 1,
                        "method": match.group(1), "route": route_path,
                        "framework": "Next.js App Router",
                    })
                    entry_points.append({
                        "path": path, "framework": "Next.js",
                        "reason": "App Router API route handler",
                    })

        if suffix == ".prisma":
            current_model = ""
            for line_number, line in enumerate(source.splitlines(), 1):
                model_match = re.match(r"\s*model\s+(\w+)\s*\{", line)
                if model_match:
                    current_model = model_match.group(1)
                    continue
                relation_match = re.match(r"\s*([A-Za-z_]\w*)\s+([A-Za-z_]\w*)\??\s+@relation\b", line)
                if current_model and relation_match:
                    database_relations.append({
                        "path": path, "line": line_number,
                        "source_model": current_model, "target": relation_match.group(1),
                        "kind": "Prisma relation",
                    })
                if line.strip() == "}":
                    current_model = ""

        sql_pattern = re.compile(
            r"FOREIGN\s+KEY\s*\([^)]*\)\s*REFERENCES\s+[""]?(\w+)",
            re.IGNORECASE,
        )
        for match in sql_pattern.finditer(source):
            database_relations.append({
                "path": path, "line": source.count("\n", 0, match.start()) + 1,
                "source_model": "SQL table", "target": match.group(1), "kind": "SQL foreign key",
            })

    unique_entries = {
        (item["path"], item["framework"], item["reason"]): item
        for item in entry_points
    }
    unique_endpoints = {
        (item["path"], item["line"], item["method"], item["route"]): item
        for item in endpoints
    }
    unique_relations = {
        (item["path"], item["line"], item["source_model"], item["target"], item["kind"]): item
        for item in database_relations
    }

    def module_name(path: str) -> str:
        parts = PurePosixPath(path).parts
        return parts[0] if len(parts) > 1 else "(root)"

    module_edges: dict[tuple[str, str], int] = {}
    for edge in edges:
        source_path, target_path = edge.get("source"), edge.get("target")
        if source_path not in known_paths or target_path not in known_paths:
            continue
        source_module, target_module = module_name(source_path), module_name(target_path)
        if source_module != target_module:
            key = (source_module, target_module)
            module_edges[key] = module_edges.get(key, 0) + 1

    module_dependencies = [
        {"source": source, "target": target, "imports": count}
        for (source, target), count in sorted(module_edges.items(), key=lambda item: (-item[1], item[0]))
    ]

    return {
        "frameworks": sorted(frameworks),
        "entry_points": sorted(unique_entries.values(), key=lambda item: (item["path"], item["framework"])),
        "api_endpoints": sorted(unique_endpoints.values(), key=lambda item: (item["path"], item["line"], item["method"])),
        "database_relations": sorted(unique_relations.values(), key=lambda item: (item["path"], item["line"])),
        "module_dependencies": module_dependencies,
        "stats": {
            "frameworks_detected": len(frameworks),
            "entry_points": len(unique_entries),
            "api_endpoints": len(unique_endpoints),
            "database_relations": len(unique_relations),
            "cross_module_links": len(module_dependencies),
        },
        "note": "Framework, entry-point, endpoint, and database relationship results are static candidates inferred from manifests and source patterns. Dynamic registration, generated routes, ORM conventions, and files outside the analyzed set may be missed.",
    }
