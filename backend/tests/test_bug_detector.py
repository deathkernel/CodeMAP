from app.services.bug_detector import scan_for_bugs


def test_detects_python_dynamic_execution() -> None:
    result = scan_for_bugs({"app.py": "value = eval(user_input)\n"})
    assert result["stats"]["total"] == 1
    assert result["findings"][0]["rule_id"] == "dynamic-code-execution"
    assert result["findings"][0]["line"] == 1


def test_detects_mutable_default_argument() -> None:
    result = scan_for_bugs({"app.py": "def add_item(item, values=[]):\n    values.append(item)\n"})
    assert any(item["rule_id"] == "mutable-default-argument" for item in result["findings"])


def test_detects_swallowed_exception() -> None:
    result = scan_for_bugs({"app.py": "try:\n    run()\nexcept Exception:\n    pass\n"})
    assert any(item["rule_id"] == "swallowed-exception" for item in result["findings"])


def test_detects_shell_true() -> None:
    source = "import subprocess\nsubprocess.run(command, shell=True)\n"
    result = scan_for_bugs({"app.py": source})
    assert any(item["rule_id"] == "subprocess-shell-true" for item in result["findings"])


def test_secret_value_is_never_returned() -> None:
    secret = "sk_live_12345678901234567890"
    result = scan_for_bugs({"settings.py": f'api_key = "{secret}"\n'})
    assert any(item["rule_id"] == "possible-hardcoded-secret" for item in result["findings"])
    assert secret not in str(result)


def test_invalid_python_is_skipped_without_execution() -> None:
    result = scan_for_bugs({"broken.py": "this is not valid python !!!"})
    assert result["findings"] == []


def test_detects_unsafe_javascript_html_and_dynamic_execution() -> None:
    source = (
        "const html = userInput;\n"
        "element.innerHTML = html;\n"
        "const run = new Function(userInput);\n"
        "root.dangerouslySetInnerHTML = { __html: html };\n"
    )
    result = scan_for_bugs({"src/view.tsx": source})
    rule_ids = {item["rule_id"] for item in result["findings"]}
    assert "unsafe-innerhtml-assignment" in rule_ids
    assert "dynamic-code-execution" not in rule_ids
    assert "dynamic-function-constructor" not in rule_ids
    assert "react-dangerous-html" in rule_ids


def test_detects_tls_validation_disabled_in_javascript() -> None:
    result = scan_for_bugs({"src/client.js": "const options = { rejectUnauthorized: false };\n"})
    assert any(item["rule_id"] == "tls-certificate-validation-disabled" for item in result["findings"])
