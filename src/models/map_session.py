from dataclasses import dataclass, field
from typing import Any


@dataclass
class MapSession:
    filename: str | None = None
    data: dict[str, Any] = field(default_factory=dict)
    dirty: bool = False

    @property
    def is_loaded(self) -> bool:
        return bool(self.filename and self.data)

    def set_loaded_map(self, filename: str, data: dict[str, Any]) -> None:
        self.filename = filename
        self.data = data
        self.dirty = False

    def mark_dirty(self) -> None:
        self.dirty = True

    def mark_clean(self) -> None:
        self.dirty = False
