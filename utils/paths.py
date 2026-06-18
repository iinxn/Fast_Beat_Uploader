"""Filesystem locations and path helpers shared across the app.

Centralises everything about *where things live* so the rest of the code does
not have to care whether the app runs from source or as a one-file .exe.
"""

import os
import sys


def app_base_dir() -> str:
    """Folder for user-supplied/editable files (client_secret.json, presets.json, settings.json).

    Frozen one-file build -> the folder that contains the .exe.
    Running from source    -> the project root (the folder above this package).

    Intentionally *not* ``sys._MEIPASS``: in a one-file build that is a temporary
    folder deleted on exit, so anything the user needs to see or edit must live
    next to the executable instead.
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    # This file is <project_root>/utils/paths.py -> go up two levels.
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def resource_path(relative: str) -> str:
    """Absolute path to a *bundled* resource (e.g. ffmpeg), PyInstaller-aware.

    Frozen -> inside the temporary ``_MEIPASS`` extraction folder.
    Source -> relative to the project root.
    """
    base = getattr(sys, "_MEIPASS", None) or app_base_dir()
    return os.path.join(base, relative)


def safe_filename(name: str) -> str:
    """Strip illegal characters and limit length so a string is safe as a filename."""
    name = name.strip()
    if not name:
        return "video"
    for ch in r'<>:"/\\|?*':
        name = name.replace(ch, "_")
    name = " ".join(name.split())
    return name[:120] or "video"


# ---------------------------------------------------------------------------
# Well-known file/folder locations
# ---------------------------------------------------------------------------

# Project root (source) or the .exe folder (frozen).
BASE_DIR = app_base_dir()

# Per-user data folder for things that must persist and stay private.
USER_DATA_DIR = os.path.join(os.path.expanduser("~"), ".fast_beats_render")
TOKEN_FILE = os.path.join(USER_DATA_DIR, "youtube_token.dat")

# Files that live next to the program so the user can find and edit them.
PRESETS_FILE = os.path.join(BASE_DIR, "presets.json")
SETTINGS_FILE = os.path.join(BASE_DIR, "settings.json")
CLIENT_SECRET_FILE = os.path.join(BASE_DIR, "client_secret.json")
