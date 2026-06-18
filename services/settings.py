import json
import os
from typing import Any

from utils.paths import SETTINGS_FILE


class SettingsStore:
    """Persists simple app preferences (key/value) to a JSON file next to the program.

    Currently used to remember the default output folder so it survives restarts.
    The store is generic, so new preferences can be added without changing it.
    """

    DEFAULTS: dict = {
        "default_output_dir": "",
    }

    def __init__(self, path: str = SETTINGS_FILE):
        self.path = path
        self.data: dict = dict(self.DEFAULTS)
        self.load()

    def load(self) -> None:
        if not os.path.exists(self.path):
            return
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                payload = json.load(f)
            if isinstance(payload, dict):
                self.data.update(payload)
        except Exception:
            # Corrupt/unreadable file -> keep defaults and carry on.
            pass

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self.data[key] = value

    def save(self) -> None:
        try:
            os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
        except Exception:
            # Saving preferences must never crash the app.
            pass
