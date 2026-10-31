"""Helpers for turning API records into raw landing files."""

from __future__ import annotations

import json
from datetime import datetime, timezone


def new_run_id() -> str:
    """Timestamp ID for one extraction run. Dashes instead of colons so it's file-name safe."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")


def landing_path(source: str, entity: str, run_id: str) -> str:
    """One new file per run, partitioned by date. Raw data is never overwritten."""
    return f"{source}/{entity}/run_date={run_id[:10]}/{run_id}.json"


def to_ndjson(records: list[dict], source: str, entity: str, run_id: str) -> str:
    """Wrap each record in an envelope with lineage metadata, one JSON object per line."""
    extracted_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    lines = [
        json.dumps(
            {
                "_source": source,
                "_entity": entity,
                "_run_id": run_id,
                "_extracted_at": extracted_at,
                "payload": record,
            },
            default=str,
            sort_keys=True,
        )
        for record in records
    ]
    return "\n".join(lines) + ("\n" if lines else "")