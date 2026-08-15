from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

from jarvis import __version__
from jarvis.app import create_server
from jarvis.config import Settings, default_data_dir
from jarvis.native_floating import NativeFloatingWindow
from jarvis.runtime import bundle_root, bundled_path
from jarvis.speech import SpeechService, resolve_whisper_model


FLOAT_WIDTH = 196
FLOAT_HEIGHT = 196
FLOAT_MARGIN = 8
FLOAT_REVEAL_RATIO = 0.20
FLOAT_ANIMATION_SECONDS = 0.30


def _clamp_main_opacity(value: Any) -> float:
    try:
        opacity = float(value)
    except (TypeError, ValueError):
        opacity = 0.68
    return max(0.30, min(0.96, opacity))


def _set_native_window_opacity(window: Any, value: Any) -> bool:
    """Set whole-window opacity on the native pywebview host."""

    native = getattr(window, "native", None)
    if native is None:
        return False
    opacity = _clamp_main_opacity(value)

    if sys.platform == "win32":
        try:
            import ctypes

            handle = int(native.Handle.ToInt64())
            user32 = ctypes.windll.user32
            extended_style = int(user32.GetWindowLongW(handle, -20))
            user32.SetWindowLongW(handle, -20, extended_style | 0x00080000)
            alpha = max(1, min(255, round(opacity * 255)))
            if user32.SetLayeredWindowAttributes(handle, 0, alpha, 0x00000002):
                return True
        except Exception:
            pass

    def apply() -> None:
        native.Opacity = opacity

    try:
        if bool(getattr(native, "InvokeRequired", False)):
            from System import Func, Type

            native.Invoke(Func[Type](apply))
        else:
            apply()
        return True
    except Exception:
        return False


def _cubic_bezier_progress(
    progress: float,
    x1: float = 0.22,
    y1: float = 1.0,
    x2: float = 0.36,
    y2: float = 1.0,
) -> float:
    """Evaluate CSS cubic-bezier(.22, 1, .36, 1) at a time progress."""

    progress = max(0.0, min(1.0, float(progress)))

    def coordinate(t: float, first: float, second: float) -> float:
        inverse = 1.0 - t
        return (
            3.0 * inverse * inverse * t * first
            + 3.0 * inverse * t * t * second
            + t * t * t
        )

    low = 0.0
    high = 1.0
    parameter = progress
    for _ in range(14):
        parameter = (low + high) / 2.0
        if coordinate(parameter, x1, x2) < progress:
            low = parameter
        else:
            high = parameter
    return coordinate(parameter, y1, y2)


def _edge_targets(
    bounds: tuple[int, int, int, int],
    width: int,
    height: int,
    y: int,
    edge: str,
) -> tuple[int, int, int]:
    left, top, right, bottom = bounds
    reveal = max(26, round(width * FLOAT_REVEAL_RATIO))
    clamped_y = max(top + FLOAT_MARGIN, min(y, bottom - height - FLOAT_MARGIN))
    if edge == "left":
        expanded_x = left + FLOAT_MARGIN
        collapsed_x = left - width + reveal
    else:
        expanded_x = right - width - FLOAT_MARGIN
        collapsed_x = right - reveal
    return expanded_x, collapsed_x, clamped_y


def _windows_scale() -> float:
    if sys.platform != "win32":
        return 1.0
    try:
        import ctypes

        getter = getattr(ctypes.windll.user32, "GetDpiForSystem", None)
        dpi = int(getter()) if getter else 96
        return max(1.0, dpi / 96.0)
    except (AttributeError, OSError, TypeError, ValueError):
        return 1.0


def _monitor_work_area(window: Any) -> tuple[int, int, int, int]:
    if sys.platform != "win32":
        return 0, 0, 1920, 1080
    try:
        import ctypes
        from ctypes import wintypes

        class Point(ctypes.Structure):
            _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]

        class Rect(ctypes.Structure):
            _fields_ = [
                ("left", wintypes.LONG),
                ("top", wintypes.LONG),
                ("right", wintypes.LONG),
                ("bottom", wintypes.LONG),
            ]

        class MonitorInfo(ctypes.Structure):
            _fields_ = [
                ("cbSize", wintypes.DWORD),
                ("rcMonitor", Rect),
                ("rcWork", Rect),
                ("dwFlags", wintypes.DWORD),
            ]

        native = getattr(window, "native", None)
        scale = float(getattr(native, "_scale", 0.0) or _windows_scale())
        center = Point(
            round((int(window.x) + int(window.width) / 2) * scale),
            round((int(window.y) + int(window.height) / 2) * scale),
        )
        monitor = ctypes.windll.user32.MonitorFromPoint(center, 2)
        info = MonitorInfo()
        info.cbSize = ctypes.sizeof(MonitorInfo)
        if not monitor or not ctypes.windll.user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
            raise OSError("GetMonitorInfoW failed")
        work = info.rcWork
        return (
            round(work.left / scale),
            round(work.top / scale),
            round(work.right / scale),
            round(work.bottom / scale),
        )
    except (AttributeError, OSError, TypeError, ValueError):
        scale = _windows_scale()
        try:
            import ctypes

            return (
                0,
                0,
                round(int(ctypes.windll.user32.GetSystemMetrics(0)) / scale),
                round(int(ctypes.windll.user32.GetSystemMetrics(1)) / scale),
            )
        except (AttributeError, OSError, TypeError, ValueError):
            return 0, 0, 1920, 1080


class DesktopBridge:
    def __init__(self) -> None:
        # pywebview recursively publishes public attributes on ``js_api``.
        # Native Window objects must stay private or their accessibility tree
        # is walked indefinitely when the floating window is created.
        self._main_window: Any = None
        self._floating_window: Any = None
        self._lock = threading.RLock()
        self._float_edge = "right"
        self._float_collapsed = False
        self._float_active = False
        self._float_animating = False
        self._float_animation_generation = 0
        self._float_ignore_moves_until = 0.0
        self._float_movement_timer: threading.Timer | None = None
        self._float_hover_monitor_started = False

    def _bind(self, main_window: Any, floating_window: Any) -> None:
        with self._lock:
            self._main_window = main_window
            self._floating_window = floating_window

    def _cancel_movement_timer(self) -> None:
        with self._lock:
            timer = self._float_movement_timer
            self._float_movement_timer = None
        if timer is not None:
            timer.cancel()

    def _start_edge_hover_monitor(self) -> None:
        if sys.platform != "win32":
            return
        with self._lock:
            if self._float_hover_monitor_started:
                return
            self._float_hover_monitor_started = True

        def monitor() -> None:
            try:
                import ctypes
                from ctypes import wintypes

                class Point(ctypes.Structure):
                    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]

                user32 = ctypes.windll.user32
                outside_since: float | None = None
                while True:
                    with self._lock:
                        window = self._floating_window
                        collapsed = self._float_collapsed
                        animating = self._float_animating
                        edge = self._float_edge
                        active = self._float_active
                    if window is None:
                        return
                    if collapsed and not animating:
                        point = Point()
                        if user32.GetCursorPos(ctypes.byref(point)):
                            native = getattr(window, "native", None)
                            scale = float(
                                getattr(native, "_scale", 0.0) or _windows_scale()
                            )
                            cursor_x = point.x / scale
                            cursor_y = point.y / scale
                            x = int(window.x)
                            y = int(window.y)
                            width = int(window.width)
                            height = int(window.height)
                            reveal = max(26, round(width * FLOAT_REVEAL_RATIO))
                            if edge == "left":
                                hit_left = x + width - reveal
                                hit_right = x + width
                            else:
                                hit_left = x
                                hit_right = x + reveal
                            if (
                                hit_left <= cursor_x <= hit_right
                                and y <= cursor_y <= y + height
                            ):
                                self.expand_floating()
                                outside_since = None
                                time.sleep(FLOAT_ANIMATION_SECONDS + 0.12)
                    elif not animating and not active:
                        native = getattr(window, "native", None)
                        scale = float(
                            getattr(native, "_scale", 0.0) or _windows_scale()
                        )
                        point = Point()
                        if user32.GetCursorPos(ctypes.byref(point)):
                            cursor_x = point.x / scale
                            cursor_y = point.y / scale
                            x = int(window.x)
                            y = int(window.y)
                            inside = (
                                x <= cursor_x <= x + int(window.width)
                                and y <= cursor_y <= y + int(window.height)
                            )
                            if inside:
                                outside_since = None
                            elif outside_since is None:
                                outside_since = time.monotonic()
                            elif time.monotonic() - outside_since >= 0.52:
                                self.collapse_floating()
                                outside_since = None
                                time.sleep(FLOAT_ANIMATION_SECONDS + 0.12)
                    time.sleep(0.06)
            except Exception:
                return

        threading.Thread(target=monitor, daemon=True).start()

    def _notify_floating(self) -> None:
        with self._lock:
            window = self._floating_window
            payload = {
                "edge": self._float_edge,
                "collapsed": self._float_collapsed,
                "active": self._float_active,
            }
        if window is None:
            return
        try:
            apply_host_state = getattr(window, "apply_host_state", None)
            if callable(apply_host_state):
                apply_host_state(payload)
                return
            window.evaluate_js(
                "window.jarvisFloating && window.jarvisFloating.applyHostState("
                + json.dumps(payload, ensure_ascii=False)
                + ")"
            )
        except Exception:
            # The first notification can race WebView initialization. The page
            # requests host state again as soon as its script is ready.
            return

    def _animate_floating(
        self,
        target_x: int,
        target_y: int,
        *,
        collapsed: bool,
    ) -> bool:
        with self._lock:
            window = self._floating_window
            if window is None:
                return False
            self._float_animation_generation += 1
            generation = self._float_animation_generation
            self._float_animating = True
            self._float_collapsed = collapsed
            self._float_ignore_moves_until = (
                time.monotonic() + FLOAT_ANIMATION_SECONDS + 0.18
            )
        self._cancel_movement_timer()
        self._notify_floating()
        try:
            start_x = int(window.x)
            start_y = int(window.y)
        except (AttributeError, TypeError, ValueError):
            start_x = target_x
            start_y = target_y
        if start_x == target_x and start_y == target_y:
            with self._lock:
                if generation == self._float_animation_generation:
                    self._float_animating = False
            self._notify_floating()
            return True

        def animate() -> None:
            steps = max(1, round(FLOAT_ANIMATION_SECONDS * 60))
            for index in range(1, steps + 1):
                with self._lock:
                    if generation != self._float_animation_generation:
                        return
                eased = _cubic_bezier_progress(index / steps)
                x = round(start_x + (target_x - start_x) * eased)
                y = round(start_y + (target_y - start_y) * eased)
                try:
                    window.move(x, y)
                except Exception:
                    with self._lock:
                        if generation == self._float_animation_generation:
                            self._float_animating = False
                    return
                if index < steps:
                    time.sleep(FLOAT_ANIMATION_SECONDS / steps)
            with self._lock:
                if generation != self._float_animation_generation:
                    return
                self._float_animating = False
            self._notify_floating()

        worker = threading.Thread(target=animate, daemon=True)
        worker.start()
        return True

    def _handle_floating_moved(self, x: int, y: int) -> None:
        del x, y
        with self._lock:
            if (
                self._float_animating
                or time.monotonic() < self._float_ignore_moves_until
                or self._floating_window is None
            ):
                return
            if self._float_movement_timer is not None:
                self._float_movement_timer.cancel()
            self._float_collapsed = False
            timer = threading.Timer(0.20, self.dock_floating)
            timer.daemon = True
            self._float_movement_timer = timer
            timer.start()

    def _handle_floating_loaded(self) -> None:
        self._notify_floating()
        if os.environ.get("JARVIS_FLOAT_AUTOCOLLAPSE", "0") == "1":
            self._start_edge_hover_monitor()
            timer = threading.Timer(1.2, self.collapse_floating)
            timer.daemon = True
            timer.start()

    def show_main(self) -> bool:
        with self._lock:
            window = self._main_window
        if window is None:
            return False
        window.show()
        window.restore()
        return True

    def open_settings(self) -> bool:
        if not self.show_main():
            return False
        with self._lock:
            window = self._main_window
        if window is None:
            return False
        window.evaluate_js(
            "window.jarvisDesktop && window.jarvisDesktop.openSettings()"
        )
        return True

    def toggle_voice_mode(self) -> bool:
        with self._lock:
            window = self._main_window
        if window is None:
            return False
        window.evaluate_js(
            "window.jarvisDesktop && window.jarvisDesktop.toggleVoiceMode()"
        )
        return True

    def set_main_opacity(self, opacity: float) -> bool:
        with self._lock:
            window = self._main_window
        if window is None:
            return False
        return _set_native_window_opacity(window, opacity)

    def update_floating_status(
        self,
        voice_state: str,
        voice_mode: bool,
        assistant_name: str,
        theme: str,
        opacity: float,
    ) -> bool:
        with self._lock:
            window = self._floating_window
        if window is None:
            return False
        updater = getattr(window, "update_status", None)
        if not callable(updater):
            return False
        updater(voice_state, voice_mode, assistant_name, theme, opacity)
        return True

    def preview_floating_appearance(self, theme: str, opacity: float) -> bool:
        with self._lock:
            window = self._floating_window
        if window is None:
            return False
        updater = getattr(window, "update_appearance", None)
        if not callable(updater):
            return False
        updater(theme, opacity)
        return True

    def set_floating_enabled(self, enabled: bool) -> bool:
        with self._lock:
            window = self._floating_window
        if window is None:
            return False
        if bool(enabled):
            window.show()
            self._notify_floating()
        else:
            window.hide()
        return True

    def hide_floating(self) -> bool:
        return self.set_floating_enabled(False)

    def get_floating_state(self) -> dict[str, object]:
        with self._lock:
            return {
                "edge": self._float_edge,
                "collapsed": self._float_collapsed,
                "active": self._float_active,
            }

    def set_floating_active(self, active: bool) -> bool:
        with self._lock:
            window = self._floating_window
            self._float_active = bool(active)
        if window is None:
            return False
        try:
            window.on_top = bool(active)
        except Exception:
            return False
        self._notify_floating()
        return True

    def expand_floating(self) -> bool:
        with self._lock:
            window = self._floating_window
            edge = self._float_edge
        if window is None:
            return False
        bounds = _monitor_work_area(window)
        expanded_x, _, y = _edge_targets(
            bounds, int(window.width), int(window.height), int(window.y), edge
        )
        return self._animate_floating(expanded_x, y, collapsed=False)

    def collapse_floating(self) -> bool:
        with self._lock:
            window = self._floating_window
            edge = self._float_edge
        if window is None:
            return False
        bounds = _monitor_work_area(window)
        _, collapsed_x, y = _edge_targets(
            bounds, int(window.width), int(window.height), int(window.y), edge
        )
        return self._animate_floating(collapsed_x, y, collapsed=True)

    def dock_floating(self) -> bool:
        with self._lock:
            window = self._floating_window
        if window is None:
            return False
        bounds = _monitor_work_area(window)
        x = int(window.x)
        width = int(window.width)
        left_distance = abs(x - bounds[0])
        right_distance = abs(bounds[2] - (x + width))
        edge = "left" if left_distance <= right_distance else "right"
        with self._lock:
            self._float_edge = edge
        self._start_edge_hover_monitor()
        _, collapsed_x, y = _edge_targets(
            bounds, width, int(window.height), int(window.y), edge
        )
        self._notify_floating()
        return self._animate_floating(collapsed_x, y, collapsed=True)


def _floating_position(width: int, height: int) -> tuple[int | None, int | None]:
    if sys.platform != "win32":
        return None, None
    try:
        import ctypes

        scale = _windows_scale()
        screen_width = round(int(ctypes.windll.user32.GetSystemMetrics(0)) / scale)
        screen_height = round(int(ctypes.windll.user32.GetSystemMetrics(1)) / scale)
        return max(16, screen_width - width - 28), max(16, screen_height - height - 72)
    except (AttributeError, OSError, TypeError, ValueError):
        return None, None


def run_self_test(report_path: Path) -> int:
    report: dict[str, object] = {
        "app": "JARVIS LOCAL",
        "version": __version__,
        "bundle_root": str(bundle_root() or ""),
        "success": False,
    }
    try:
        settings = Settings()
        settings.tts.browser_fallback = False
        service = SpeechService()
        report["capabilities"] = service.capabilities(settings)
        report["stt_model"] = resolve_whisper_model(settings.stt.model)

        phrase = "主人你好，我是贾维斯，很高兴陪伴你，今天也要开心呀。"
        generated = service.synthesize(settings, phrase)
        if generated is None or not generated.data.startswith(b"RIFF"):
            raise RuntimeError("离线语音合成没有返回有效 WAV")
        report["tts_wav_bytes"] = len(generated.data)

        transcript = service.transcribe(settings, generated.data, generated.content_type)
        if not transcript:
            raise RuntimeError("离线语音识别没有返回文字")
        report["stt_transcript"] = transcript
        report["success"] = True
    except Exception as exc:  # pragma: no cover - exercised by the frozen build
        report["error_type"] = type(exc).__name__
        report["error"] = str(exc)

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return 0 if report["success"] else 1


def _show_startup_error(exc: BaseException) -> None:
    log_dir = default_data_dir() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "startup-error.log"
    log_path.write_text(f"{type(exc).__name__}: {exc}\n", encoding="utf-8")
    if sys.platform == "win32":
        try:
            import ctypes

            ctypes.windll.user32.MessageBoxW(
                0,
                f"JARVIS LOCAL 无法启动。\n\n{exc}\n\n诊断日志：{log_path}",
                "JARVIS LOCAL",
                0x10,
            )
            return
        except Exception:
            pass
    raise SystemExit(f"JARVIS LOCAL 无法启动：{exc}\n诊断日志：{log_path}")


def main() -> None:
    if len(sys.argv) >= 2 and sys.argv[1] == "--self-test":
        target = (
            Path(sys.argv[2]).resolve()
            if len(sys.argv) >= 3
            else Path(tempfile.gettempdir()) / "jarvis-offline-self-test.json"
        )
        raise SystemExit(run_self_test(target))

    try:
        import webview
    except ImportError as exc:
        raise SystemExit("请先执行：pip install -e '.[desktop]'") from exc

    server = create_server("127.0.0.1", 0)
    port = server.server_address[1]
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    floating_window: NativeFloatingWindow | None = None
    try:
        bridge = DesktopBridge()
        main_window = webview.create_window(
            "JARVIS LOCAL",
            f"http://127.0.0.1:{port}/",
            js_api=bridge,
            width=1240,
            height=800,
            min_size=(900, 620),
            hidden=os.environ.get("JARVIS_MAIN_HIDDEN", "0") == "1",
            background_color="#0c0e0b",
        )
        float_width = FLOAT_WIDTH
        float_height = FLOAT_HEIGHT
        float_x, float_y = _floating_position(float_width, float_height)
        hud_asset = bundled_path("jarvis", "static", "jarvis-hud-logo.png")
        if hud_asset is None:
            hud_asset = (
                Path(__file__).resolve().parent
                / "jarvis"
                / "static"
                / "jarvis-hud-logo.png"
            )
        settings = server.application.settings
        floating_window = NativeFloatingWindow(
            bridge,
            hud_asset,
            width=float_width,
            height=float_height,
            x=float_x,
            y=float_y,
            scale=_windows_scale(),
            visible=settings.appearance.floating_window,
            assistant_name=settings.identity.assistant_name,
            theme=settings.appearance.theme,
            opacity=settings.appearance.floating_opacity,
        )
        bridge._bind(main_window, floating_window)
        floating_window.start()
        if os.environ.get("JARVIS_FLOAT_TEST_TOPMOST", "0") == "1":
            bridge.set_floating_active(True)
        webview.start(gui="edgechromium", private_mode=True)
    finally:
        if floating_window is not None:
            floating_window.close()
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except BaseException as error:  # pragma: no cover - desktop safety boundary
        _show_startup_error(error)
