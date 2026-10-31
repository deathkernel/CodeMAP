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
