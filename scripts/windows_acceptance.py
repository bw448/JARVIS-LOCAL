#!/usr/bin/env python3
"""Read-only release diagnostics for the JARVIS LOCAL Windows package.

The default checks never launch the application, load voice models, record audio,
or execute a computer-control action.  They are safe to run before manual GUI and
voice acceptance testing.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import platform
import shutil
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from jarvis import __version__  # noqa: E402
from jarvis.computer import ComputerToolService  # noqa: E402


@dataclass(frozen=True, slots=True)
class Check:
    name: str
    status: str
    detail: str
    category: str


PACKAGE_FILES = (
    ("JARVIS LOCAL.exe", 5 * 1024 * 1024),
    ("BUILD-INFO.json", 1),
    ("SELF-TEST.json", 1),
    ("KOKORO-MODEL-LICENSE.txt", 1),
    ("WHISPER-MODEL-LICENSE.txt", 1),
    ("_internal/models/tts/kokoro-multi-lang-v1_0/model.onnx", 250 * 1024 * 1024),
    ("_internal/models/tts/kokoro-multi-lang-v1_0/voices.bin", 1),
    ("_internal/models/tts/kokoro-multi-lang-v1_0/tokens.txt", 1),
    ("_internal/models/stt/faster-whisper-small/model.bin", 400 * 1024 * 1024),
    ("_internal/models/stt/faster-whisper-small/config.json", 1),
    ("_internal/models/stt/faster-whisper-small/tokenizer.json", 1),
)

DEPENDENCIES = (
    "sherpa_onnx",
    "faster_whisper",
    "webview",
    "numpy",
    "soundfile",
    "torch",
    "qwen_tts",
    "funasr",
)

ENDPOINTS = (
    ("文本模型", "http://127.0.0.1:8080/v1/models"),
    ("Qwen3-TTS", "http://127.0.0.1:9880/health"),
    ("SenseVoice", "http://127.0.0.1:50000/health"),
)

MANUAL_CHECKS = (
    "双击 EXE 后主窗口在 5 秒内出现，且没有后台异常弹窗",
    "将智能体改名为“贾维斯”后，主界面和悬浮 HUD 中央不出现“贾”字",
    "单次录音、识别、发送、回答、朗读形成完整闭环",
    "连续语音能在停顿后及时识别，朗读结束后恢复监听",
    "点击停止朗读后，当前音频和待合成句子立即取消",
    "情绪倾诉时先回应感受，再给建议；不武断判断用户情绪",
    "打开记事本/计算器会先显示确认框，取消后不执行，确认后只执行一次",
    "电脑控制关闭时，模型不能请求或执行任何电脑操作",
)


def _human_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KiB", "MiB", "GiB"):
        if value < 1024 or unit == "GiB":
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{size} B"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_package_version(package_dir: Path) -> str | None:
    info_path = package_dir / "BUILD-INFO.json"
    try:
        raw = json.loads(info_path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    value = raw.get("version") if isinstance(raw, dict) else None
    return str(value).strip() if value else None


def find_package_dir(explicit: str | None = None) -> Path | None:
    if explicit:
        return Path(explicit).expanduser().resolve()
    candidates = [
        PROJECT_ROOT / "dist" / f"JARVIS-LOCAL-{__version__}-Windows-x64-Offline",
        PROJECT_ROOT.parent / "JARVIS-LOCAL",
        Path("D:/JARVIS-LOCAL"),
        Path("/mnt/d/JARVIS-LOCAL"),
    ]
    for candidate in candidates:
        if (candidate / "JARVIS LOCAL.exe").is_file():
            return candidate.resolve()
    return None


def check_runtime() -> list[Check]:
    checks: list[Check] = []
    version = platform.python_version()
    supported = sys.version_info[:2] in {(3, 11), (3, 12), (3, 13)}
    checks.append(
        Check(
            "Python 运行版本",
            "PASS" if supported else "BLOCKED",
            f"Python {version}；项目要求 >=3.11,<3.14",
            "runtime",
        )
    )
    checks.append(
        Check(
            "操作系统",
            "PASS" if sys.platform == "win32" else "WARN",
            f"{platform.system()} {platform.release()}；GUI/麦克风验收必须在原生 Windows 完成",
            "runtime",
        )
    )
    available = [name for name in DEPENDENCIES if importlib.util.find_spec(name) is not None]
    missing = [name for name in DEPENDENCIES if name not in available]
    checks.append(
        Check(
            "当前解释器语音依赖",
            "PASS" if {"sherpa_onnx", "faster_whisper", "webview"}.issubset(available) else "WARN",
            f"可用：{', '.join(available) or '无'}；缺少：{', '.join(missing) or '无'}。"
            "该项检查开发环境，不代表 PyInstaller 离线包内部依赖",
            "runtime",
        )
    )
    return checks


def check_package(package_dir: Path | None) -> list[Check]:
    if package_dir is None:
        return [Check("Windows 离线包", "BLOCKED", "没有找到离线包目录", "package")]
    if not package_dir.is_dir():
        return [Check("Windows 离线包目录", "BLOCKED", f"目录不存在：{package_dir}", "package")]
    checks = [Check("Windows 离线包目录", "PASS", str(package_dir), "package")]
    package_version = read_package_version(package_dir)
    if package_version is None:
        checks.append(Check("离线包版本", "BLOCKED", "BUILD-INFO.json 缺失或无效", "package"))
    else:
        checks.append(
            Check(
                "离线包版本",
                "PASS" if package_version == __version__ else "BLOCKED",
                f"离线包 {package_version}；当前源码 {__version__}",
                "package",
            )
        )
    missing: list[str] = []
    undersized: list[str] = []
    total = 0
    for relative, minimum in PACKAGE_FILES:
        path = package_dir / relative
        if not path.is_file():
            missing.append(relative)
            continue
        size = path.stat().st_size
        total += size
        if size < minimum:
            undersized.append(f"{relative} ({_human_size(size)})")
    if missing or undersized:
        detail = []
        if missing:
            detail.append("缺失：" + ", ".join(missing))
        if undersized:
            detail.append("尺寸异常：" + ", ".join(undersized))
        checks.append(Check("离线语音文件", "BLOCKED", "；".join(detail), "package"))
    else:
        checks.append(
            Check("离线语音文件", "PASS", f"关键文件齐全，合计 {_human_size(total)}", "package")
        )
    exe = package_dir / "JARVIS LOCAL.exe"
    if exe.is_file():
        checks.append(
            Check(
                "主程序校验",
                "PASS",
                f"{_human_size(exe.stat().st_size)}；SHA-256 {_sha256(exe)}",
                "package",
            )
        )
    self_test = package_dir / "SELF-TEST.json"
    try:
        result = json.loads(self_test.read_text(encoding="utf-8-sig"))
        success = result.get("success") is True
        checks.append(
            Check(
                "打包时语音自检",
                "PASS" if success else "BLOCKED",
                f"SELF-TEST.json success={str(success).lower()}，版本 {result.get('version', '未知')}",
                "package",
            )
        )
    except (OSError, UnicodeError, json.JSONDecodeError, AttributeError):
        checks.append(Check("打包时语音自检", "BLOCKED", "SELF-TEST.json 缺失或无效", "package"))
    return checks


def probe_endpoint(name: str, url: str, timeout: float = 0.8) -> Check:
    started = time.perf_counter()
    request = Request(url, headers={"Accept": "application/json", "User-Agent": "JarvisAcceptance/1"})
    try:
        with urlopen(request, timeout=timeout) as response:
            response.read(4096)
            elapsed = round((time.perf_counter() - started) * 1000)
            return Check(name, "PASS", f"{url} 可用，GET {response.status}，{elapsed} ms", "services")
    except HTTPError as exc:
        elapsed = round((time.perf_counter() - started) * 1000)
        status = "PASS" if exc.code in {401, 403, 405} else "WARN"
        return Check(name, status, f"{url} 返回 HTTP {exc.code}，{elapsed} ms", "services")
    except (URLError, TimeoutError, OSError) as exc:
        return Check(name, "NOT_RUN", f"{url} 未就绪：{type(exc).__name__}", "services")


def check_gpu() -> Check:
    executable = shutil.which("nvidia-smi")
    if not executable:
        return Check("NVIDIA GPU", "INFO", "未找到 nvidia-smi；CPU 离线语音仍可使用", "hardware")
    try:
        result = subprocess.run(
            [executable, "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return Check("NVIDIA GPU", "WARN", f"nvidia-smi 无法运行：{type(exc).__name__}", "hardware")
    detail = (result.stdout or result.stderr).strip().replace("\n", "; ")
    return Check(
        "NVIDIA GPU",
        "PASS" if result.returncode == 0 else "WARN",
        detail or f"nvidia-smi 退出码 {result.returncode}",
        "hardware",
    )


def check_computer_tools() -> Check:
    """Exercise schema, proposal and cancellation without an OS mutation."""
    try:
        service = ComputerToolService()
        names = [item["function"]["name"] for item in service.schemas()]
        proposal = service.propose("open_application", {"application": "notepad"})
        cancelled = service.resolve(proposal["proposal_id"], False)
        if proposal.get("kind") != "proposal" or cancelled.get("executed") is not False:
            raise RuntimeError("提案取消链路返回异常")
        expected = {"get_system_status", "open_application", "open_folder", "lock_workstation"}
        if set(names) != expected:
            raise RuntimeError("工具白名单与验收预期不一致")
        return Check(
            "电脑控制安全链路",
            "PASS",
            "白名单、一次性提案和取消链路通过；未执行任何系统操作",
            "tools",
        )
    except Exception as exc:  # diagnostic boundary: report rather than crash
        return Check("电脑控制安全链路", "BLOCKED", str(exc), "tools")


def run_checks(package_dir: Path | None, *, probe_services: bool = True) -> list[Check]:
    checks = check_runtime()
    checks.extend(check_package(package_dir))
    checks.append(check_gpu())
    checks.append(check_computer_tools())
    if probe_services:
        checks.extend(probe_endpoint(name, url) for name, url in ENDPOINTS)
    checks.extend(Check(item, "MANUAL", "需要在原生 Windows 桌面观察", "manual") for item in MANUAL_CHECKS)
    return checks


def render_markdown(checks: Iterable[Check], package_dir: Path | None) -> str:
    rows = list(checks)
    counts = {status: sum(item.status == status for item in rows) for status in (
        "PASS", "BLOCKED", "WARN", "NOT_RUN", "MANUAL", "INFO"
    )}
    lines = [
        f"# JARVIS LOCAL {__version__} Windows 验收诊断",
        "",
        f"- 源码目录：`{PROJECT_ROOT}`",
        f"- 离线包目录：`{package_dir or '未找到'}`",
        f"- 平台：`{platform.platform()}`",
        f"- 汇总：PASS {counts['PASS']} / BLOCKED {counts['BLOCKED']} / "
        f"WARN {counts['WARN']} / NOT_RUN {counts['NOT_RUN']} / MANUAL {counts['MANUAL']}",
        "",
        "| 状态 | 类别 | 检查项 | 结果 |",
        "|---|---|---|---|",
    ]
    for item in rows:
        detail = item.detail.replace("|", "\\|").replace("\n", " ")
        name = item.name.replace("|", "\\|")
        lines.append(f"| {item.status} | {item.category} | {name} | {detail} |")
    lines.extend(
        (
            "",
            "## 建议性能门槛（需人工实测）",
            "",
            "- 热启动主窗口出现：≤ 5 秒；",
            "- 说完话到开始识别：≤ 1.0 秒；",
            "- 短句 STT：SenseVoice CPU ≤ 1.5 秒，Whisper small CPU ≤ 3.0 秒；",
            "- 文本模型首字：≤ 1.5 秒（取决于本地模型与硬件）；",
            "- 首句开始发声：Kokoro CPU ≤ 1.0 秒，Qwen3-TTS GPU 热态 ≤ 1.2 秒；",
            "- 连续对话过程中不重复弹麦克风授权，不出现上一轮残留朗读。",
            "",
            "以上是产品验收目标，不是模型在所有硬件上的性能保证。",
        )
    )
    return "\n".join(lines) + "\n"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="JARVIS LOCAL Windows 离线包只读验收诊断")
    parser.add_argument("--package-dir", help="离线包目录；省略时自动查找")
    parser.add_argument("--json", action="store_true", help="输出机器可读 JSON")
    parser.add_argument("--output", help="同时把 Markdown 或 JSON 写入指定文件")
    parser.add_argument("--skip-services", action="store_true", help="不探测三个本机服务端点")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    package_dir = find_package_dir(args.package_dir)
    checks = run_checks(package_dir, probe_services=not args.skip_services)
    if args.json:
        output = json.dumps(
            {
                "source_version": __version__,
                "package_dir": str(package_dir) if package_dir else None,
                "checks": [asdict(item) for item in checks],
            },
            ensure_ascii=False,
            indent=2,
        ) + "\n"
    else:
        output = render_markdown(checks, package_dir)
    if args.output:
        Path(args.output).expanduser().write_text(output, encoding="utf-8")
    print(output, end="")
    return 2 if any(item.status == "BLOCKED" for item in checks) else 0


if __name__ == "__main__":
    raise SystemExit(main())
