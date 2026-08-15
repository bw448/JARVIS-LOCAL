from __future__ import annotations

import math
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any


def hud_wave_levels(state: str, voice_mode: bool, phase: float) -> tuple[float, ...]:
    """Return deterministic voice-bar levels for the native HUD animation."""

    activity = {
        "idle": 0.18,
        "listening": 0.72,
        "transcribing": 0.46,
        "thinking": 0.54,
        "speaking": 0.92,
        "error": 0.24,
    }.get(str(state), 0.18)
    if voice_mode and state == "idle":
        activity = 0.42

    profile = (0.38, 0.62, 0.84, 1.0, 0.84, 0.62, 0.38)
    speed = 1.2 if state == "idle" else 2.8
    levels = []
    for index, weight in enumerate(profile):
        motion = 0.64 + 0.36 * math.sin(phase * speed + index * 1.17)
        levels.append(max(0.12, min(1.0, 0.12 + weight * activity * motion)))
    return tuple(levels)


def clamp_floating_opacity(value: Any) -> float:
    try:
        opacity = float(value)
    except (TypeError, ValueError):
        opacity = 0.85
    return max(0.25, min(1.0, opacity))


def _arc_points(
    center_x: float,
    center_y: float,
    radius: float,
    start: float,
    extent: float,
) -> tuple[float, ...]:
    """Sample a circular arc for a smooth line with rounded endpoints."""

    steps = max(10, round(abs(extent) / 4))
    points: list[float] = []
    for index in range(steps + 1):
        angle = math.radians(start + extent * index / steps)
        points.extend(
            (
                center_x + math.cos(angle) * radius,
                center_y - math.sin(angle) * radius,
            )
        )
    return tuple(points)


class NativeFloatingWindow:
    """Small animated vector HUD with a real transparent native window."""

    _TRANSPARENT_KEY = "#010203"

    _STATUS_LABELS = {
        "idle": "系统待命",
        "listening": "正在聆听",
        "transcribing": "本地识别",
        "thinking": "正在思考",
        "speaking": "正在回应",
        "error": "需要处理",
    }
    _THEME_COLORS = {
        "cyan": ("#a2fff3", "#2be0ce", "#0a4b48", "#147c74", "#d9a94b"),
        "violet": ("#d5ceff", "#9185f2", "#35325e", "#554f91", "#d9a94b"),
        "emerald": ("#9affd5", "#2dd293", "#0b4938", "#176e53", "#d7a548"),
        "amber": ("#ffe7a8", "#dda943", "#59451f", "#8b6b2c", "#75ead7"),
    }

    def __init__(
        self,
        bridge: Any,
        asset_path: Path,
        *,
        width: int,
        height: int,
        x: int | None,
        y: int | None,
        scale: float,
        visible: bool,
        assistant_name: str,
        theme: str,
        opacity: float,
    ) -> None:
        self._bridge = bridge
        self._asset_path = Path(asset_path)
        self.width = int(width)
        self.height = int(height)
        self._scale = max(1.0, float(scale))
        self._x = int(x if x is not None else 24)
        self._y = int(y if y is not None else 24)
        self._visible = bool(visible)
        self._on_top = False
        self._assistant_name = assistant_name or "JARVIS"
        self._theme = theme or "cyan"
        self._base_opacity = clamp_floating_opacity(opacity)
        self._voice_state = "idle"
        self._voice_mode = False
        self._edge = "right"
        self._collapsed = False
        self._active = False
        self._lock = threading.RLock()
        self._ready = threading.Event()
        self._thread: threading.Thread | None = None
        self._startup_error: BaseException | None = None
        self._root: Any = None
        self._canvas: Any = None
        self._arc_items: list[dict[str, Any]] = []
        self._wave_items: list[tuple[Any, Any, Any]] = []
        self._guide_items: list[Any] = []
        self._status_dot_items: tuple[Any, Any] | None = None
        self._label_item: Any = None
        self._hud_center = (0.0, 0.0)
        self._hud_radius = 0.0
        self._animation_started = time.monotonic()
        self._hovered = False
        self._click_job: Any = None
        self._drag_origin: tuple[int, int, int, int] | None = None
        self._dragged = False
        self.native = SimpleNamespace(_scale=self._scale)

    @property
    def x(self) -> int:
        with self._lock:
            return self._x

    @property
    def y(self) -> int:
        with self._lock:
            return self._y

    @property
    def on_top(self) -> bool:
        with self._lock:
            return self._on_top

    @on_top.setter
    def on_top(self, value: bool) -> None:
        with self._lock:
            self._on_top = bool(value)
        self._dispatch(self._apply_topmost)

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(
            target=self._run,
            name="jarvis-native-floating",
            daemon=True,
        )
        self._thread.start()
        if not self._ready.wait(8.0):
            raise RuntimeError("原生悬浮窗启动超时")
        if self._startup_error is not None:
            raise RuntimeError(f"原生悬浮窗启动失败：{self._startup_error}")

    def _run(self) -> None:
        try:
            import tkinter as tk

            root = tk.Tk()
            self._root = root
            root.withdraw()
            root.title("JARVIS FLOAT")
            root.overrideredirect(True)
            root.configure(background=self._TRANSPARENT_KEY)
            root.wm_attributes("-transparentcolor", self._TRANSPARENT_KEY)
            root.wm_attributes("-alpha", self._base_opacity)
            try:
                root.wm_attributes("-toolwindow", True)
            except tk.TclError:
                pass

            pixel_width = round(self.width * self._scale)
            pixel_height = round(self.height * self._scale)
            root.geometry(self._geometry(pixel_width, pixel_height, self._x, self._y))

            canvas = tk.Canvas(
                root,
                width=pixel_width,
                height=pixel_height,
                background=self._TRANSPARENT_KEY,
                borderwidth=0,
                highlightthickness=0,
                relief="flat",
                cursor="hand2",
            )
            canvas.pack(fill="both", expand=True)
            self._canvas = canvas
            self._build_hud(tk, pixel_width, pixel_height)

            canvas.bind("<Enter>", self._on_enter)
            canvas.bind("<Leave>", self._on_leave)
            canvas.bind("<ButtonPress-1>", self._on_press)
            canvas.bind("<B1-Motion>", self._on_drag)
            canvas.bind("<ButtonRelease-1>", self._on_release)
            canvas.bind("<Double-Button-1>", self._on_double_click)
            canvas.bind("<Button-3>", self._show_menu)
            root.bind("<FocusIn>", lambda _event: self._set_active(True))
            root.bind("<FocusOut>", lambda _event: self._set_active(False))

            self._apply_topmost()
            self._refresh_visual()
            if self._visible:
                root.deiconify()
                root.lift()
            self._ready.set()
            root.after(0, self._bridge._handle_floating_loaded)
            root.after(0, self._animate_hud)
            root.after(1400, root.lift)
            root.mainloop()
        except BaseException as exc:
            self._startup_error = exc
            self._ready.set()
        finally:
            self._root = None

    def _display_name(self) -> str:
        return "".join(list(self._assistant_name)[:10]).upper() or "JARVIS"

    def _build_hud(self, tk: Any, pixel_width: int, pixel_height: int) -> None:
        canvas = self._canvas
        if canvas is None:
            return

        center_x = pixel_width / 2
        center_y = pixel_height / 2
        radius = min(pixel_width, pixel_height) * 0.385
        self._hud_center = (center_x, center_y)
        self._hud_radius = radius
        primary, secondary, dim, glow_color, accent = self._palette()

        guide_width = max(1, round(self._scale))
        for scale in (1.0, 0.72, 0.38):
            guide_radius = radius * scale
            item = canvas.create_oval(
                center_x - guide_radius,
                center_y - guide_radius,
                center_x + guide_radius,
                center_y + guide_radius,
                outline=dim,
                width=guide_width,
            )
            self._guide_items.append(item)

        arc_specs = (
            (1.00, 18.0, 62.0, 7.0, "secondary"),
            (1.00, 127.0, 42.0, 7.0, "primary"),
            (1.00, 218.0, 76.0, 7.0, "secondary"),
            (0.82, 54.0, 38.0, -11.0, "primary"),
            (0.82, 154.0, 68.0, -11.0, "secondary"),
            (0.82, 292.0, 34.0, -11.0, "accent"),
            (0.57, 8.0, 82.0, 15.0, "secondary"),
            (0.57, 188.0, 58.0, 15.0, "primary"),
        )
        role_colors = {
            "primary": primary,
            "secondary": secondary,
            "accent": accent,
        }
        for radius_scale, start, extent, speed, role in arc_specs:
            coordinates = _arc_points(
                center_x,
                center_y,
                radius * radius_scale,
                start,
                extent,
            )
            glow = canvas.create_line(
                *coordinates,
                fill=dim,
                width=max(5, round(6.2 * self._scale)),
                capstyle=tk.ROUND,
                joinstyle=tk.ROUND,
            )
            middle = canvas.create_line(
                *coordinates,
                fill=glow_color,
                width=max(3, round(3.35 * self._scale)),
                capstyle=tk.ROUND,
                joinstyle=tk.ROUND,
            )
            core = canvas.create_line(
                *coordinates,
                fill=role_colors[role],
                width=max(1, round(1.45 * self._scale)),
                capstyle=tk.ROUND,
                joinstyle=tk.ROUND,
            )
            self._arc_items.append(
                {
                    "glow": glow,
                    "middle": middle,
                    "core": core,
                    "radius": radius * radius_scale,
                    "start": start,
                    "extent": extent,
                    "speed": speed,
                    "role": role,
                }
            )

        spacing = radius * 0.105
        for index in range(7):
            x = center_x + (index - 3) * spacing
            glow = canvas.create_line(
                x,
                center_y - 4,
                x,
                center_y + 4,
                fill=dim,
                width=max(5, round(7.0 * self._scale)),
                capstyle=tk.ROUND,
            )
            middle = canvas.create_line(
                x,
                center_y - 4,
                x,
                center_y + 4,
                fill=secondary,
                width=max(3, round(3.5 * self._scale)),
                capstyle=tk.ROUND,
            )
            core = canvas.create_line(
                x,
                center_y - 4,
                x,
                center_y + 4,
                fill=primary,
                width=max(1, round(1.55 * self._scale)),
                capstyle=tk.ROUND,
            )
            self._wave_items.append((glow, middle, core))

        dot_radius = max(2.0, 2.25 * self._scale)
        halo_radius = dot_radius * 2.15
        orbit_x = center_x + radius * 0.9
        halo = canvas.create_oval(
            orbit_x - halo_radius,
            center_y - halo_radius,
            orbit_x + halo_radius,
            center_y + halo_radius,
            outline=dim,
            width=max(1, round(self._scale)),
        )
        dot = canvas.create_oval(
            orbit_x - dot_radius,
            center_y - dot_radius,
            orbit_x + dot_radius,
            center_y + dot_radius,
            fill=accent,
            outline="",
        )
        self._status_dot_items = (halo, dot)

        self._label_item = canvas.create_text(
            center_x,
            center_y + radius * 0.54,
            text=self._display_name(),
            fill=secondary,
            font=("Segoe UI", max(7, round(6.5 * self._scale)), "bold"),
            state="hidden",
        )

    def _palette(self) -> tuple[str, str, str, str, str]:
        palette = self._THEME_COLORS.get(self._theme, self._THEME_COLORS["cyan"])
        if self._voice_state == "error":
            return "#ffd0c5", "#ef8174", "#5b2b27", "#8b4038", "#ffad66"
        return palette

    def _animate_hud(self) -> None:
        root = self._root
        canvas = self._canvas
        if root is None or canvas is None:
            return

        elapsed = time.monotonic() - self._animation_started
        state = self._voice_state
        speed_factor = {
            "idle": 1.0,
            "listening": 1.55,
            "transcribing": 1.3,
            "thinking": 2.1,
            "speaking": 1.75,
            "error": 0.55,
        }.get(state, 1.0)
        if self._voice_mode and state == "idle":
            speed_factor = 1.35

        center_x, center_y = self._hud_center
        for spec in self._arc_items:
            start = spec["start"] + elapsed * spec["speed"] * speed_factor
            coordinates = _arc_points(
                center_x,
                center_y,
                spec["radius"],
                start,
                spec["extent"],
            )
            canvas.coords(spec["glow"], *coordinates)
            canvas.coords(spec["middle"], *coordinates)
            canvas.coords(spec["core"], *coordinates)

        levels = hud_wave_levels(state, self._voice_mode, elapsed)
        spacing = self._hud_radius * 0.105
        for index, ((glow, middle, core), level) in enumerate(
            zip(self._wave_items, levels)
        ):
            x = center_x + (index - 3) * spacing
            half_height = self._hud_radius * (0.055 + 0.18 * level)
            coordinates = (x, center_y - half_height, x, center_y + half_height)
            canvas.coords(glow, *coordinates)
            canvas.coords(middle, *coordinates)
            canvas.coords(core, *coordinates)

        if self._status_dot_items is not None:
            angle = math.radians(24 + elapsed * 13 * speed_factor)
            orbit = self._hud_radius * 0.9
            dot_x = center_x + math.cos(angle) * orbit
            dot_y = center_y - math.sin(angle) * orbit
            halo, dot = self._status_dot_items
            dot_radius = max(2.0, 2.25 * self._scale)
            halo_radius = dot_radius * 2.15
            canvas.coords(
                halo,
                dot_x - halo_radius,
                dot_y - halo_radius,
                dot_x + halo_radius,
                dot_y + halo_radius,
            )
            canvas.coords(
                dot,
                dot_x - dot_radius,
                dot_y - dot_radius,
                dot_x + dot_radius,
                dot_y + dot_radius,
            )

        root.after(40, self._animate_hud)

    def _geometry(self, width: int, height: int, x: int, y: int) -> str:
        pixel_x = round(x * self._scale)
        pixel_y = round(y * self._scale)
        return f"{width}x{height}{pixel_x:+d}{pixel_y:+d}"

    def _dispatch(self, callback: Any) -> None:
        root = self._root
        if root is None:
            return
        try:
            root.after(0, callback)
        except Exception:
            return

    def _background_call(self, callback: Any) -> None:
        threading.Thread(target=callback, daemon=True).start()

    def _apply_topmost(self) -> None:
        root = self._root
        if root is None:
            return
        try:
            root.wm_attributes("-topmost", self.on_top)
            if self.on_top:
                root.lift()
        except Exception:
            return

    def _refresh_visual(self) -> None:
        canvas = self._canvas
        if canvas is None:
            return
        primary, secondary, dim, glow_color, accent = self._palette()
        role_colors = {
            "primary": primary,
            "secondary": secondary,
            "accent": accent,
        }
        for item in self._guide_items:
            canvas.itemconfigure(item, outline=dim)
        for spec in self._arc_items:
            canvas.itemconfigure(spec["glow"], fill=dim)
            canvas.itemconfigure(spec["middle"], fill=glow_color)
            canvas.itemconfigure(spec["core"], fill=role_colors[spec["role"]])
        for glow, middle, core in self._wave_items:
            canvas.itemconfigure(glow, fill=dim)
            canvas.itemconfigure(middle, fill=secondary)
            canvas.itemconfigure(core, fill=primary)
        if self._status_dot_items is not None:
            halo, dot = self._status_dot_items
            canvas.itemconfigure(halo, outline=dim)
            canvas.itemconfigure(dot, fill=accent)

        label = self._STATUS_LABELS.get(self._voice_state, "系统待命")
        if self._voice_mode and self._voice_state == "idle":
            label = "语音模式"
        show_label = self._hovered or self._voice_state != "idle" or self._voice_mode
        canvas.itemconfigure(
            self._label_item,
            text=label if self._voice_state != "idle" or self._voice_mode else self._display_name(),
            fill=secondary,
            state="normal" if show_label else "hidden",
        )

    def _set_alpha(self, value: float) -> None:
        root = self._root
        if root is not None:
            try:
                root.wm_attributes("-alpha", value)
            except Exception:
                pass

    def _set_active(self, active: bool) -> None:
        self._background_call(
            lambda: self._bridge.set_floating_active(bool(active))
        )

    def _on_enter(self, _event: Any) -> None:
        self._hovered = True
        self._refresh_visual()
        self._set_alpha(1.0)
        self._background_call(self._bridge.expand_floating)

    def _on_leave(self, _event: Any) -> None:
        self._hovered = False
        self._refresh_visual()
        self._set_alpha(self._base_opacity)
        self._set_active(False)

    def _on_press(self, event: Any) -> None:
        if self._click_job is not None and self._root is not None:
            self._root.after_cancel(self._click_job)
            self._click_job = None
        with self._lock:
            origin_x = round(self._x * self._scale)
            origin_y = round(self._y * self._scale)
        self._drag_origin = (event.x_root, event.y_root, origin_x, origin_y)
        self._dragged = False
        self._set_active(True)

    def _on_drag(self, event: Any) -> None:
        if self._drag_origin is None or self._root is None:
            return
        pointer_x, pointer_y, origin_x, origin_y = self._drag_origin
        delta_x = event.x_root - pointer_x
        delta_y = event.y_root - pointer_y
        if abs(delta_x) + abs(delta_y) > 5:
            self._dragged = True
        pixel_x = origin_x + delta_x
        pixel_y = origin_y + delta_y
        with self._lock:
            self._x = round(pixel_x / self._scale)
            self._y = round(pixel_y / self._scale)
        pixel_width = round(self.width * self._scale)
        pixel_height = round(self.height * self._scale)
        self._root.geometry(
            f"{pixel_width}x{pixel_height}{pixel_x:+d}{pixel_y:+d}"
        )

    def _on_release(self, _event: Any) -> None:
        dragged = self._dragged
        self._drag_origin = None
        self._dragged = False
        if dragged:
            self._background_call(self._bridge.dock_floating)
            return
        root = self._root
        if root is not None:
            self._click_job = root.after(230, self._toggle_voice)

    def _toggle_voice(self) -> None:
        self._click_job = None
        self._background_call(self._bridge.toggle_voice_mode)

    def _on_double_click(self, _event: Any) -> None:
        root = self._root
        if self._click_job is not None and root is not None:
            root.after_cancel(self._click_job)
            self._click_job = None
        self._background_call(self._bridge.show_main)

    def _show_menu(self, event: Any) -> None:
        menu: Any = None
        try:
            import tkinter as tk

            menu = tk.Menu(self._root, tearoff=False)
            menu.add_command(
                label="打开主面板",
                command=lambda: self._background_call(self._bridge.show_main),
            )
            menu.add_command(
                label="切换连续语音",
                command=lambda: self._background_call(self._bridge.toggle_voice_mode),
            )
            menu.add_separator()
            menu.add_command(
                label="隐藏悬浮窗",
                command=lambda: self._background_call(self._bridge.hide_floating),
            )
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            try:
                if menu is not None:
                    menu.grab_release()
            except Exception:
                pass

    def move(self, x: int, y: int) -> None:
        with self._lock:
            self._x = int(x)
            self._y = int(y)

        def apply() -> None:
            if self._root is None:
                return
            pixel_width = round(self.width * self._scale)
            pixel_height = round(self.height * self._scale)
            self._root.geometry(
                self._geometry(pixel_width, pixel_height, int(x), int(y))
            )

        self._dispatch(apply)

    def show(self) -> None:
        self._visible = True

        def apply() -> None:
            if self._root is not None:
                self._root.deiconify()
                self._root.lift()

        self._dispatch(apply)

    def hide(self) -> None:
        self._visible = False
        self._dispatch(lambda: self._root.withdraw() if self._root is not None else None)

    def close(self) -> None:
        self._dispatch(lambda: self._root.destroy() if self._root is not None else None)

    def apply_host_state(self, payload: dict[str, object]) -> None:
        with self._lock:
            self._edge = "left" if payload.get("edge") == "left" else "right"
            self._collapsed = bool(payload.get("collapsed"))
            self._active = bool(payload.get("active"))
        self._dispatch(
            lambda: self._set_alpha(1.0 if self._active else self._base_opacity)
        )

    def update_status(
        self,
        voice_state: str,
        voice_mode: bool,
        assistant_name: str,
        theme: str,
        opacity: float,
    ) -> None:
        with self._lock:
            self._voice_state = str(voice_state or "idle")
            self._voice_mode = bool(voice_mode)
            self._assistant_name = str(assistant_name or "JARVIS")
            self._theme = str(theme or "cyan")
            self._base_opacity = clamp_floating_opacity(opacity)

        def apply() -> None:
            self._refresh_visual()
            if not self._hovered and not self._active:
                self._set_alpha(self._base_opacity)

        self._dispatch(apply)

    def update_appearance(self, theme: str, opacity: float) -> None:
        with self._lock:
            self._theme = str(theme or "cyan")
            self._base_opacity = clamp_floating_opacity(opacity)

        def apply() -> None:
            self._refresh_visual()
            if not self._hovered and not self._active:
                self._set_alpha(self._base_opacity)

        self._dispatch(apply)

    def evaluate_js(self, _script: str) -> None:
        # Compatibility shim for the bridge's WebView fallback path.
        return
