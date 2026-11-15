"""Start the Lakeflow pipeline and wait for it to finish.

Uses the Pipelines REST API: POST starts an update, GET polls its state.
Exits with an error if the update fails, so the workflow stops before dbt runs.
"""

from __future__ import annotations

import logging
import os
import time

import requests

log = logging.getLogger(__name__)

TERMINAL_STATES = {"COMPLETED", "FAILED", "CANCELED"}


def run(pipeline_id: str, poll_seconds: int = 30, timeout_seconds: int = 3600) -> None:
    host = os.environ["DATABRICKS_HOST"].rstrip("/")
    headers = {"Authorization": f"Bearer {os.environ['DATABRICKS_TOKEN']}"}

    resp = requests.post(
        f"{host}/api/2.0/pipelines/{pipeline_id}/updates", headers=headers, json={}, timeout=30
    )
    resp.raise_for_status()
    update_id = resp.json()["update_id"]
    log.info("Started pipeline update %s", update_id)

    deadline = time.monotonic() + timeout_seconds
    while True:
        status = requests.get(
            f"{host}/api/2.0/pipelines/{pipeline_id}/updates/{update_id}", headers=headers, timeout=30
        )
        status.raise_for_status()
        state = status.json()["update"]["state"]
        log.info("Pipeline state: %s", state)

        if state in TERMINAL_STATES:
            break
        if time.monotonic() > deadline:
            raise SystemExit(f"Pipeline update {update_id} still {state} after {timeout_seconds}s")
        time.sleep(poll_seconds)

    if state != "COMPLETED":
        raise SystemExit(f"Pipeline update {update_id} ended in state {state}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run(os.environ["DATABRICKS_PIPELINE_ID"])