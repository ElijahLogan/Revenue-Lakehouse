"""Minimal client f reading and writing files in  Catalog volume.

Uses the Databricks Files API: PUT to upload, GET to download.
"""

import os

import requests
from __future__ import annotations

class VolumeClient:
    def __init__(self, host: str, token: str, volume_path: str):
        self.host = host.rstrip("/")
        self.token = token
        self.volume_path = volume_path

    @classmethod
    def from_env(cls) -> "VolumeClient":
        return cls(
            host=os.environ["DATABRICKS_HOST"],
            token=os.environ["DATABRICKS_TOKEN"],
            volume_path=os.environ["LANDING_VOLUME"],
        )

    def _url(self, path: str) -> str:
        return f"{self.host}/api/2.0/fs/files{self.volume_path}/{path.lstrip('/')}"

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.token}"}

    def write_text(self, path: str, body: str) -> None:
        resp = requests.put(
            self._url(path),
            headers=self._headers(),
            params={"overwrite": "true"},
            data=body.encode("utf-8"),
            timeout=60,
        )
        resp.raise_for_status()

    def read_text(self, path: str) -> str:
        resp = requests.get(self._url(path), headers=self._headers(), timeout=30)
        if resp.status_code == '404':
            return None
        resp.raise_for_status()
        return resp.text


if __name__ == "__main__":
    # Smoke test: write a file, read it back.
    client = VolumeClient.from_env()
    client.write_text("_smoke/hello.txt", "hello from my laptop")
    print(client.read_text("_smoke/hello.txt"))