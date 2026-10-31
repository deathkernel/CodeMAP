"""Explainable static bug and risky-pattern checks.

The scanner parses source text only. It never imports or executes repository code.
"""
from __future__ import annotations

import ast
import re
from typing import Any

SECRET_PATTERN = re.compile(
    r"""(?i)\b(api[_-]?key|secret|password|access[_-]?token)\b\s*[:=]\s*["']([^"']{12,})["']"""
)
PLACEHOLDERS = {"your_api_key", "replace_me", "changeme", "example", "placeholder"}

JS_RISK_PATTERNS = (
    (re.compile(r"\beval\s*\("), "dynamic-code-execution", "Dynamic code execution", "high", "eval() executes a string as code and can create a code-injection risk.", "Avoid eval(); parse data as data and use explicit, allowlisted operations."),
    (re.compile(r"\bnew\s+Function\s*\("), "dynamic-function-constructor", "Dynamic function construction", "high", "The Function constructor compiles a string into executable code.", "Replace dynamically generated code with explicit functions or a safe expression parser."),
    (re.compile(r"\.innerHTML\s*="), "unsafe-innerhtml-assignment", "Potentially unsafe innerHTML assignment", "high", "Assigning to innerHTML parses a string as HTML; untrusted content can create cross-site scripting risk.", "Prefer textContent or sanitize HTML with a well-maintained allowlist-based sanitizer."),
    (re.compile(r"\bdangerouslySetInnerHTML\s*="), "react-dangerous-html", "React dangerouslySetInnerHTML", "high", "This React escape hatch inserts raw HTML and can create cross-site scripting risk if content is not sanitized.", "Avoid raw HTML where possible; otherwise sanitize content before rendering."),
    (re.compile(r"\brejectUnauthorized\s*:\s*false"), "tls-certificate-validation-disabled", "TLS certificate validation disabled", "high", "TLS certificate validation is disabled, making man-in-the-middle attacks easier.", "Keep certificate validation enabled and configure trusted certificates correctly."),
)


LANGUAGE_RISK_PATTERNS = {
    "php": (
        (re.compile(r"\beval\s*\("), "dynamic-code-execution", "Dynamic code execution", "high", "eval() executes a string as PHP code.", "Avoid eval(); use explicit, allowlisted operations."),
        (re.compile(r"\b(?:shell_exec|passthru|system|exec)\s*\("), "php-shell-execution", "PHP shell command execution", "high", "This function can execute operating-system commands; unsafe input can lead to command injection.", "Avoid shell execution or pass strictly validated arguments through a safe process API."),
        (re.compile(r"\bunserialize\s*\("), "php-unserialize-untrusted-data", "PHP unserialize call", "medium", "Unserializing untrusted data can instantiate objects and trigger unsafe magic methods.", "Use JSON for untrusted data or restrict allowed classes explicitly."),
    ),
    "java": (
        (re.compile(r"\bRuntime\s*\.\s*getRuntime\s*\(\s*\)\s*\.\s*exec\s*\("), "java-runtime-exec", "Java runtime command execution", "high", "Runtime.exec() launches operating-system processes and may be unsafe when arguments include untrusted input.", "Avoid shell command construction and validate each argument before process execution."),
    ),
    "go": (
        (re.compile(r"\bexec\s*\.\s*Command\s*\(\s*['\"](?:sh|bash|cmd|powershell)['\"]\s*,\s*['\"](?:-c|/c|/command)['\"]"), "go-shell-command", "Go shell command execution", "high", "Starting a shell with a command string can expose command injection when input is incorporated.", "Prefer direct executable invocation with separate, validated arguments."),
        (re.compile(r"\bInsecureSkipVerify\s*:\s*true\b"), "tls-certificate-validation-disabled", "TLS certificate validation disabled", "high", "Go TLS certificate verification is disabled.", "Keep certificate verification enabled and configure trusted certificates correctly."),
    ),
    "rb": (
        (re.compile(r"\b(?:eval|system|exec)\s*\("), "ruby-dynamic-or-shell-execution", "Ruby dynamic or shell execution", "high", "This call evaluates code or executes a system command and may be unsafe with untrusted input.", "Use explicit operations and avoid constructing executable strings from external input."),
    ),
    "cs": (
        (re.compile(r"\bProcess\s*\.\s*Start\s*\("), "dotnet-process-start", ".NET process execution", "medium", "Process.Start() launches another process; dynamically constructed arguments may introduce command or argument injection.", "Validate executable paths and arguments, and avoid shell execution."),
    ),
}


def _finding(
    path: str,
    line: int,
    rule_id: str,
    title: str,
    severity: str,
    message: str,
    recommendation: str,
) -> dict[str, Any]:
    return {
        "id": f"{path}:{line}:{rule_id}",
        "path": path,
        "line": line,
        "rule_id": rule_id,
        "title": title,
        "severity": severity,
        "message": message,
        "recommendation": recommendation,
    }



def _advanced_python_findings(path: str, tree: ast.AST) -> list[dict[str, Any]]:
    """Find additional high-signal Python logic mistakes without executing code."""
    findings: list[dict[str, Any]] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            seen: dict[Any, int] = {}
            for key in node.keys:
                if not isinstance(key, ast.Constant):
                    continue
                try:
                    hash(key.value)
                except TypeError:
                    continue
                if key.value in seen:
                    findings.append(_finding(
                        path, key.lineno, "duplicate-dictionary-key",
                        "Duplicate dictionary key", "medium",
                        "A dictionary literal defines the same constant key more than once; the later value silently replaces the earlier one.",
                        "Remove the duplicate key or combine the values intentionally.",
                    ))
                else:
                    seen[key.value] = key.lineno

        if isinstance(node, ast.Compare):
            operands = [node.left, *node.comparators]
            for index, operator in enumerate(node.ops):
                if not isinstance(operator, (ast.Is, ast.IsNot)):
                    continue
                left, right = operands[index], operands[index + 1]
                literal = right if isinstance(right, ast.Constant) else left
                if isinstance(literal, ast.Constant) and literal.value is not None:
                    findings.append(_finding(
                        path, node.lineno, "identity-comparison-literal",
                        "Identity comparison with a literal", "medium",
                        "The is operator checks object identity, not value equality; using it with a non-None literal is usually unintended.",
                        "Use == or != for value comparison. Keep is None checks as they are.",
                    ))
                    break

        if isinstance(node, ast.Try) and node.finalbody:
            if any(isinstance(child, ast.Return) for statement in node.finalbody for child in ast.walk(statement)):
                findings.append(_finding(
                    path, node.lineno, "return-in-finally",
                    "Return inside finally block", "high",
                    "A return from a finally block can override an earlier return value or suppress an active exception.",
                    "Move the return outside finally; use finally only for cleanup.",
                ))

        for field_name, value in ast.iter_fields(node):
            if not isinstance(value, list) or not value or not all(isinstance(item, ast.stmt) for item in value):
                continue
            terminal_seen = False
            for statement in value:
                if terminal_seen:
                    findings.append(_finding(
                        path, statement.lineno, "unreachable-statement",
                        "Potentially unreachable statement", "medium",
                        "This statement follows an unconditional return, raise, break, or continue in the same block.",
                        "Remove the dead statement or correct the preceding control flow.",
                    ))
                if isinstance(statement, (ast.Return, ast.Raise, ast.Break, ast.Continue)):
                    terminal_seen = True

    return findings


def _python_findings(path: str, source: str) -> list[dict[str, Any]]:
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return []

    findings: list[dict[str, Any]] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            defaults = list(node.args.defaults) + [
                value for value in node.args.kw_defaults if value is not None
            ]
            for default in defaults:
                if isinstance(default, (ast.List, ast.Dict, ast.Set)):
                    findings.append(_finding(
                        path, default.lineno, "mutable-default-argument",
                        "Mutable default argument", "medium",
                        "A list, dictionary, or set is created once when the function is defined and may be shared between calls.",
                        "Use None as the default and create a new collection inside the function.",
                    ))

        if isinstance(node, ast.ExceptHandler):
            if node.type is None:
                findings.append(_finding(
                    path, node.lineno, "bare-except", "Bare except clause", "medium",
                    "This catches every exception, including system-exiting exceptions, and can hide important failures.",
                    "Catch the specific exception types the code can handle.",
                ))
            elif (
                isinstance(node.type, ast.Name)
                and node.type.id == "Exception"
            ):
                findings.append(_finding(
                    path, node.lineno, "broad-exception", "Broad exception handler", "low",
                    "Catching Exception may hide unrelated programming errors when the handler is too broad.",
                    "Catch narrower exception types where practical and preserve useful error details.",
                ))

            if node.body and all(isinstance(statement, ast.Pass) for statement in node.body):
                findings.append(_finding(
                    path, node.lineno, "swallowed-exception", "Exception silently ignored", "high",
                    "The exception handler discards the error without logging, re-raising, or recovering.",
                    "Log the exception, handle the failure explicitly, or re-raise it.",
                ))

        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in {"eval", "exec"}:
                findings.append(_finding(
                    path, node.lineno, "dynamic-code-execution",
                    "Dynamic code execution", "high",
                    f"{node.func.id}() executes dynamically supplied code and can create a code-injection risk.",
                    "Avoid evaluating source strings; use a safe parser or an explicit allowlist of operations.",
                ))

            if isinstance(node.func, ast.Attribute):
                if (
                    isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "os"
                    and node.func.attr == "system"
                ):
                    findings.append(_finding(
                        path, node.lineno, "os-system", "Shell command execution", "high",
                        "os.system() passes a command to the system shell.",
                        "Prefer subprocess.run() with an argument list and shell=False.",
                    ))

                if (
                    isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "subprocess"
                    and node.func.attr in {"run", "Popen", "call", "check_call", "check_output"}
                    and any(
                        keyword.arg == "shell"
                        and isinstance(keyword.value, ast.Constant)
                        and keyword.value.value is True
                        for keyword in node.keywords
                    )
                ):
                    findings.append(_finding(
                        path, node.lineno, "subprocess-shell-true",
                        "Subprocess uses shell=True", "high",
                        "The command is interpreted by a shell; unsafe string construction can allow command injection.",
                        "Pass an argument list and keep shell=False. Validate any external input.",
                    ))

    findings.extend(_advanced_python_findings(path, tree))
    return findings



def _cross_file_python_findings(sources: dict[str, str]) -> list[dict[str, Any]]:
    """Check explicit relative Python imports against files in the same source set."""
    module_paths: set[str] = set()
    parsed_files: list[tuple[str, ast.AST]] = []

    for path, source in sources.items():
        if not path.lower().endswith(".py"):
            continue
        parts = path.replace("\\\\", "/").split("/")
        filename = parts[-1]
        directories = parts[:-1]
        if filename == "__init__.py":
            module_parts = directories
        else:
            module_parts = directories + [filename[:-3]]
        module_name = ".".join(part for part in module_parts if part and part.isidentifier())
        if module_name:
            module_paths.add(module_name)
        try:
            parsed_files.append((path, ast.parse(source)))
        except (SyntaxError, ValueError):
            continue

    findings: list[dict[str, Any]] = []
    for path, tree in parsed_files:
        parts = path.replace("\\\\", "/").split("/")
        filename = parts[-1]
        package_parts = parts[:-1]
        if filename == "__init__.py":
            package_parts = parts[:-1]

        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom) or node.level <= 0 or not node.module:
                continue

            keep_count = len(package_parts) - node.level + 1
            if keep_count < 0:
                continue
            base_parts = package_parts[:keep_count]
            target_parts = base_parts + node.module.split(".")
            target_module = ".".join(part for part in target_parts if part)
            if target_module and target_module not in module_paths:
                findings.append(_finding(
                    path, node.lineno, "unresolved-relative-import",
                    "Relative import target not found", "medium",
                    f"The relative import target '{node.module}' does not match a Python module included in this analysis.",
                    "Check the import path, package layout, and whether the target file was included in the analyzed repository.",
                ))

    return findings



def _cross_file_js_findings(sources: dict[str, str]) -> list[dict[str, Any]]:
    """Resolve explicit relative JS/TS imports against files in the analyzed source set."""
    import posixpath

    source_paths = {
        path.replace("\\", "/")
        for path in sources
        if path.lower().endswith((".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".vue", ".svelte", ".json"))
    }
    extensions = (".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".vue", ".svelte", ".json")
    index_names = tuple("index" + extension for extension in extensions if extension != ".json")
    import_pattern = re.compile(
        r"""(?:\bfrom\s*|\bimport\s*|\brequire\s*\(\s*)['"](\.{1,2}/[^'"]+)['"]"""
    )
    findings: list[dict[str, Any]] = []

    for original_path, source in sources.items():
        path = original_path.replace("\\", "/")
        if not path.lower().endswith((".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".vue", ".svelte")):
            continue

        for match in import_pattern.finditer(source):
            import_path = match.group(1)
            target = posixpath.normpath(posixpath.join(posixpath.dirname(path), import_path))
            candidates = {target, *(target + extension for extension in extensions)}
            candidates.update(posixpath.join(target, index_name) for index_name in index_names)
            if any(candidate in source_paths for candidate in candidates):
                continue

            findings.append(_finding(
                original_path,
                source.count("\n", 0, match.start()) + 1,
                "unresolved-relative-js-import",
                "Relative import target not found",
                "medium",
                f"The relative import '{import_path}' does not match a supported source file included in this analysis.",
                "Check the import path, file extension, directory index, and whether the target was included in the analyzed repository.",
            ))

    return findings


def scan_for_bugs(sources: dict[str, str], max_findings: int = 500) -> dict[str, Any]:
    """Scan bounded source strings and return explainable static findings."""
    findings: list[dict[str, Any]] = []

    for path, source in sorted(sources.items()):
        suffix = path.lower().rsplit(".", 1)[-1] if "." in path else ""
        if suffix == "py":
            findings.extend(_python_findings(path, source))
        elif suffix in {"js", "jsx", "ts", "tsx", "mjs", "cjs", "vue", "svelte"}:
            for line_number, line in enumerate(source.splitlines(), 1):
                for pattern, rule_id, title, severity, message, recommendation in JS_RISK_PATTERNS:
                    if pattern.search(line):
                        findings.append(_finding(path, line_number, rule_id, title, severity, message, recommendation))
        elif suffix in LANGUAGE_RISK_PATTERNS:
            for line_number, line in enumerate(source.splitlines(), 1):
                for pattern, rule_id, title, severity, message, recommendation in LANGUAGE_RISK_PATTERNS[suffix]:
                    if pattern.search(line):
                        findings.append(_finding(path, line_number, rule_id, title, severity, message, recommendation))

        for match in SECRET_PATTERN.finditer(source):
            value = match.group(2).strip().lower()
            if value in PLACEHOLDERS or value.startswith(("your_", "example_", "test_")):
                continue
            line = source.count("\n", 0, match.start()) + 1
            findings.append(_finding(
                path, line, "possible-hardcoded-secret", "Possible hardcoded secret", "high",
                "A credential-like assignment contains a non-placeholder string. The value is intentionally not shown.",
                "Move credentials to environment variables or a secret manager, then rotate exposed credentials.",
            ))

    findings.extend(_cross_file_python_findings(sources))
    findings.extend(_cross_file_js_findings(sources))

    findings.sort(key=lambda item: (
        {"high": 0, "medium": 1, "low": 2}.get(item["severity"], 3),
        item["path"],
        item["line"],
        item["rule_id"],
    ))
    findings = findings[:max_findings]
    counts = {
        "high": sum(item["severity"] == "high" for item in findings),
        "medium": sum(item["severity"] == "medium" for item in findings),
        "low": sum(item["severity"] == "low" for item in findings),
    }
    return {
        "findings": findings,
        "stats": {
            "total": len(findings),
            "by_severity": counts,
            "files_scanned": len(sources),
            "truncated": len(findings) >= max_findings,
        },
        "note": "Static pattern checks only. Findings require human review and are not proof of an exploitable bug.",
    }
