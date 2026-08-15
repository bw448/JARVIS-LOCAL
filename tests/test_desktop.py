from __future__ import annotations

import unittest
from unittest.mock import patch

from desktop import (
    FLOAT_HEIGHT,
    FLOAT_WIDTH,
    DesktopBridge,
    _cubic_bezier_progress,
    _clamp_main_opacity,
    _edge_targets,
    _floating_position,
)
from jarvis.native_floating import (
    _arc_points,
    clamp_floating_opacity,
    hud_wave_levels,
)


class FakeNative:
    def __init__(self) -> None:
        self.Opacity = 1.0
        self.InvokeRequired = False


class FakeWindow:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object | None]] = []
        self.x = 100
        self.y = 120
        self.width = FLOAT_WIDTH
        self.height = FLOAT_HEIGHT
        self.on_top = False
        self.native = None

    def show(self) -> None:
        self.calls.append(("show", None))

    def restore(self) -> None:
        self.calls.append(("restore", None))

    def hide(self) -> None:
        self.calls.append(("hide", None))

    def evaluate_js(self, script: str) -> None:
        self.calls.append(("evaluate_js", script))

    def move(self, x: int, y: int) -> None:
        self.x = x
        self.y = y
        self.calls.append(("move", (x, y)))

    def update_status(
        self,
        voice_state: str,
        voice_mode: bool,
        assistant_name: str,
        theme: str,
        opacity: float,
    ) -> None:
        self.calls.append(
            (
                "update_status",
                (voice_state, voice_mode, assistant_name, theme, opacity),
            )
        )

    def update_appearance(self, theme: str, opacity: float) -> None:
        self.calls.append(("update_appearance", (theme, opacity)))


class DesktopBridgeTests(unittest.TestCase):
    def test_native_window_references_are_private(self) -> None:
        bridge = DesktopBridge()
        main = FakeWindow()
        floating = FakeWindow()
        bridge._bind(main, floating)

        self.assertIs(bridge._main_window, main)
        self.assertIs(bridge._floating_window, floating)
        self.assertNotIn("main_window", bridge.__dict__)
        self.assertNotIn("floating_window", bridge.__dict__)
        self.assertTrue(all(name.startswith("_") for name in bridge.__dict__))

    def test_main_and_floating_window_actions(self) -> None:
        bridge = DesktopBridge()
        main = FakeWindow()
        floating = FakeWindow()
        bridge._bind(main, floating)

        self.assertTrue(bridge.open_settings())
        self.assertEqual(main.calls[0:2], [("show", None), ("restore", None)])
        self.assertIn("openSettings", str(main.calls[2][1]))

        self.assertTrue(bridge.toggle_voice_mode())
        self.assertIn("toggleVoiceMode", str(main.calls[3][1]))

        self.assertTrue(bridge.set_floating_enabled(True))
        self.assertTrue(bridge.hide_floating())
        self.assertEqual(floating.calls[0], ("show", None))
        self.assertIn("applyHostState", str(floating.calls[1][1]))
        self.assertEqual(floating.calls[2], ("hide", None))

    def test_floating_active_state_controls_topmost(self) -> None:
        bridge = DesktopBridge()
        floating = FakeWindow()
        bridge._bind(FakeWindow(), floating)

        self.assertTrue(bridge.set_floating_active(True))
        self.assertTrue(floating.on_top)
        self.assertEqual(bridge.get_floating_state()["active"], True)
        self.assertTrue(bridge.set_floating_active(False))
        self.assertFalse(floating.on_top)

    def test_floating_status_is_forwarded_to_native_hud(self) -> None:
        bridge = DesktopBridge()
        floating = FakeWindow()
        bridge._bind(FakeWindow(), floating)

        self.assertTrue(
            bridge.update_floating_status(
                "listening", True, "Aivy", "emerald", 0.74
            )
        )
        self.assertEqual(
            floating.calls[-1],
            (
                "update_status",
                ("listening", True, "Aivy", "emerald", 0.74),
            ),
        )

        self.assertTrue(bridge.preview_floating_appearance("violet", 0.52))
        self.assertEqual(
            floating.calls[-1],
            ("update_appearance", ("violet", 0.52)),
        )

    def test_main_window_opacity_updates_native_host(self) -> None:
        bridge = DesktopBridge()
        main = FakeWindow()
        main.native = FakeNative()
        bridge._bind(main, FakeWindow())

        self.assertTrue(bridge.set_main_opacity(0.54))
        self.assertEqual(main.native.Opacity, 0.54)
        self.assertEqual(_clamp_main_opacity(0.01), 0.30)
        self.assertEqual(_clamp_main_opacity(2), 0.96)

    def test_dock_chooses_nearest_edge_and_collapses(self) -> None:
        bridge = DesktopBridge()
        floating = FakeWindow()
        floating.x = 1640
        bridge._bind(FakeWindow(), floating)

        with patch("desktop._monitor_work_area", return_value=(0, 0, 1920, 1080)):
            with patch.object(bridge, "_animate_floating", return_value=True) as animate:
                self.assertTrue(bridge.dock_floating())

        self.assertEqual(bridge.get_floating_state()["edge"], "right")
        animate.assert_called_once_with(1881, 120, collapsed=True)

    def test_unbound_bridge_actions_are_safe(self) -> None:
        bridge = DesktopBridge()
        self.assertFalse(bridge.show_main())
        self.assertFalse(bridge.open_settings())
        self.assertFalse(bridge.toggle_voice_mode())
        self.assertFalse(bridge.hide_floating())

    def test_non_windows_position_uses_platform_default(self) -> None:
        position = _floating_position(FLOAT_WIDTH, FLOAT_HEIGHT)
        self.assertEqual(len(position), 2)

    def test_edge_targets_hide_eighty_percent_and_clamp_height(self) -> None:
        bounds = (0, 0, 1920, 1080)
        self.assertEqual(
            _edge_targets(bounds, FLOAT_WIDTH, FLOAT_HEIGHT, 900, "right"),
            (1716, 1881, 876),
        )
        self.assertEqual(
            _edge_targets(bounds, FLOAT_WIDTH, FLOAT_HEIGHT, -50, "left"),
            (8, -157, 8),
        )

    def test_cubic_bezier_matches_requested_ease_out_curve(self) -> None:
        values = [_cubic_bezier_progress(index / 20) for index in range(21)]
        self.assertAlmostEqual(values[0], 0.0, places=3)
        self.assertAlmostEqual(values[-1], 1.0, places=3)
        self.assertTrue(all(left <= right for left, right in zip(values, values[1:])))
        self.assertGreater(_cubic_bezier_progress(0.5), 0.8)

    def test_native_hud_wave_reacts_to_voice_state(self) -> None:
        idle = hud_wave_levels("idle", False, 0.75)
        speaking = hud_wave_levels("speaking", False, 0.75)
        voice_mode = hud_wave_levels("idle", True, 0.75)

        self.assertEqual(len(idle), 7)
        self.assertTrue(all(0.0 < value <= 1.0 for value in speaking))
        self.assertGreater(sum(speaking), sum(idle))
        self.assertGreater(sum(voice_mode), sum(idle))
        self.assertEqual(clamp_floating_opacity(0.02), 0.25)
        self.assertEqual(clamp_floating_opacity(2), 1.0)

    def test_native_hud_arc_sampling_has_expected_endpoints(self) -> None:
        points = _arc_points(100.0, 100.0, 20.0, 0.0, 90.0)

        self.assertGreater(len(points), 20)
        self.assertAlmostEqual(points[0], 120.0, places=4)
        self.assertAlmostEqual(points[1], 100.0, places=4)
        self.assertAlmostEqual(points[-2], 100.0, places=4)
        self.assertAlmostEqual(points[-1], 80.0, places=4)


if __name__ == "__main__":
    unittest.main()
