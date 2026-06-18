import json
import os
from dataclasses import dataclass, field
from typing import Optional

from utils.consts import DEFAULT_CATEGORY, DEFAULT_LANGUAGE
from utils.paths import PRESETS_FILE


@dataclass
class UploadPreset:
    name: str
    title: str = ""
    description: str = ""
    tags: list[str] = field(default_factory=list)
    language: str = DEFAULT_LANGUAGE
    category: str = DEFAULT_CATEGORY

    @classmethod
    def from_dict(cls, data: dict) -> "UploadPreset":
        tags = data.get("tags", [])
        if isinstance(tags, str):
            tags = [t.strip() for t in tags.split(",") if t.strip()]
        return cls(
            name=str(data.get("name", "")).strip(),
            title=str(data.get("title", "")),
            description=str(data.get("description", "")),
            tags=[str(x).strip() for x in tags if str(x).strip()],
            language=str(data.get("language", DEFAULT_LANGUAGE)),
            category=str(data.get("category", DEFAULT_CATEGORY)),
        )

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "title": self.title,
            "description": self.description,
            "tags": self.tags,
            "language": self.language,
            "category": self.category,
        }


class PresetStore:
    """Loads, saves and manages upload presets from a JSON file."""

    def __init__(self, path: str = PRESETS_FILE):
        self.path = path
        self.data: dict = {}
        self.load()

    def load(self) -> None:
        if not os.path.exists(self.path):
            self.data = self._default_data()
            self.save()
            return
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                payload = json.load(f)
            if not isinstance(payload, dict):
                raise ValueError("invalid preset file")
            self.data = {
                "version": int(payload.get("version", 1)),
                "last_selected": str(payload.get("last_selected", "")),
                "presets": [
                    UploadPreset.from_dict(item).to_dict()
                    for item in payload.get("presets", [])
                    if isinstance(item, dict) and str(item.get("name", "")).strip()
                ],
            }
            if not self.data["presets"]:
                self.data = self._default_data()
                self.save()
        except Exception:
            self.data = self._default_data()
            self.save()

    def _default_data(self) -> dict:
        return {
            "version": 1,
            "last_selected": "Музыка по умолчанию",
            "presets": [
                UploadPreset(
                    name="Музыка по умолчанию",
                    language=DEFAULT_LANGUAGE,
                    category=DEFAULT_CATEGORY,
                ).to_dict()
            ],
        }

    def save(self) -> None:
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)

    def names(self) -> list[str]:
        return [item["name"] for item in self.data.get("presets", [])]

    def get(self, name: str) -> Optional[UploadPreset]:
        name = name.strip()
        for item in self.data.get("presets", []):
            if item.get("name", "").strip() == name:
                return UploadPreset.from_dict(item)
        return None

    def upsert(self, preset: UploadPreset) -> None:
        preset.name = preset.name.strip()
        if not preset.name:
            raise ValueError("Название пресета не может быть пустым")
        presets = self.data.setdefault("presets", [])
        for idx, item in enumerate(presets):
            if item.get("name", "").strip() == preset.name:
                presets[idx] = preset.to_dict()
                self.data["last_selected"] = preset.name
                self.save()
                return
        presets.append(preset.to_dict())
        self.data["last_selected"] = preset.name
        self.save()

    def delete(self, name: str) -> None:
        name = name.strip()
        self.data["presets"] = [
            item for item in self.data.get("presets", [])
            if item.get("name", "").strip() != name
        ]
        if self.data.get("last_selected") == name:
            remaining = self.data["presets"]
            self.data["last_selected"] = remaining[0]["name"] if remaining else ""
        if not self.data["presets"]:
            self.data = self._default_data()
        self.save()
