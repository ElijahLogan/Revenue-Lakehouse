"""Remember where each extract left off, so the next run only pulls changes."""

from __future__ import annotations

import json

from extract.volume import VolumeClient

DEFAULT_WATERMARK = "1970-01-01T00:00:00Z"  # first run: pull everything


class WatermarkStore:
    """Watermarks per source/entity, stored as JSON in the landing volume."""

    STATE_FILE = "_state/watermarks.json"

    def __init__(self, volume: VolumeClient):
        self.volume = volume
        raw = volume.read_text(self.STATE_FILE)
        self.state = json.loads(raw) if raw else {}

    def get(self, key: str) -> str:
        return self.state.get(key, DEFAULT_WATERMARK)

    def set(self, key: str, value: str) -> None:
        self.state[key] = value  # in memory only, until save()

    def save(self) -> None:
        self.volume.write_text(self.STATE_FILE, json.dumps(self.state, indent=2, sort_keys=True))


def max_watermark(records: list[dict], field: str, current: str) -> str:
    """Newest value of `field` across records. Never moves backwards."""
    values = [str(r[field]) for r in records if r.get(field) is not None]
    return max([current, *values])