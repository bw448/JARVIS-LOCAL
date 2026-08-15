from __future__ import annotations

import sys
from pathlib import Path


def bundle_root() -> Path | None:
    """Return the read-only PyInstaller payload root when the app is frozen."""
    if not getattr(sys, "frozen", False):
        return None
    internal = getattr(sys, "_MEIPASS", "")
    if internal:
        return Path(internal).resolve()
    executable_root = Path(sys.executable).resolve().parent
    fallback = executable_root / "_internal"
    return fallback if fallback.is_dir() else executable_root


def bundled_path(*parts: str) -> Path | None:
    root = bundle_root()
    if root is None:
        return None
    candidate = root.joinpath(*parts)
    return candidate if candidate.exists() else None
