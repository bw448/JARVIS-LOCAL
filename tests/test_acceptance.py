from __future__ import annotations

import json
from pathlib import Path

from scripts.windows_acceptance import (
    check_computer_tools,
    check_package,
    read_package_version,
    render_markdown,
)


def test_read_package_version_accepts_utf8_bom(tmp_path: Path) -> None:
    (tmp_path / "BUILD-INFO.json").write_text(
        "\ufeff" + json.dumps({"version": "0.7.0"}), encoding="utf-8"
    )

    assert read_package_version(tmp_path) == "0.7.0"


def test_incomplete_package_is_blocked(tmp_path: Path) -> None:
    (tmp_path / "BUILD-INFO.json").write_text(
        json.dumps({"version": "0.7.0"}), encoding="utf-8"
    )

    checks = check_package(tmp_path)

    assert any(item.name == "离线语音文件" and item.status == "BLOCKED" for item in checks)


def test_missing_package_directory_is_blocked(tmp_path: Path) -> None:
    checks = check_package(tmp_path / "missing")

    assert checks[0].name == "Windows 离线包目录"
    assert checks[0].status == "BLOCKED"


def test_computer_tool_diagnostic_never_executes_action() -> None:
    result = check_computer_tools()

    assert result.status == "PASS"
    assert "未执行任何系统操作" in result.detail


def test_markdown_contains_status_summary() -> None:
    checks = [check_computer_tools()]

    report = render_markdown(checks, None)

    assert "PASS 1" in report
    assert "建议性能门槛" in report
