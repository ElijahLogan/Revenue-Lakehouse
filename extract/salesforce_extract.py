"""Extract Salesforce accounts into the landing volume.

v1: full pull every run. No watermark yet.
"""

from __future__ import annotations

import logging
import os

from simple_salesforce import Salesforce

from extract.records import landing_path, new_run_id, to_ndjson
from extract.volume import VolumeClient
from extract.watermarks import WatermarkStore, max_watermark

log = logging.getLogger(__name__)

WATERMARK_KEY = "salesforce.account"
ACCOUNT_QUERY = (
    "SELECT Id, Name, Website, Phone, BillingCity, BillingState, Industry, "
    "CreatedDate, SystemModstamp FROM Account"
)
def build_query(watermark: str) -> str:
    return f"{ACCOUNT_QUERY} WHERE SystemModstamp > {watermark} ORDER BY SystemModstamp ASC"

def connect() -> Salesforce:
    """Log in with OAuth client credentials via an External Client App.

    The org disables SOAP username/password login, which Salesforce is retiring.
    """
    return Salesforce(
        consumer_key=os.environ["SF_CLIENT_ID"],
        consumer_secret=os.environ["SF_CLIENT_SECRET"],
        domain=os.environ["SF_DOMAIN"],
    )


def clean(record: dict) -> dict:
    """Drop Salesforce's 'attributes' metadata; keep only the fields we asked for."""
    return {k: v for k, v in record.items() if k != "attributes"}


def run() -> None:
    sf = connect()
    volume = VolumeClient.from_env()
    watermarks = WatermarkStore(volume)
    run_id = new_run_id()

    watermark = watermarks.get(WATERMARK_KEY)
    records = [clean(r) for r in sf.query_all(build_query(watermark))["records"]]
    log.info("%d accounts changed since %s", len(records), watermark)

    if not records:
        return

    path = landing_path("salesforce", "account", run_id)
    volume.write_text(path, to_ndjson(records, "salesforce", "account", run_id))

    # Only advance the watermark after the data has landed.
    watermarks.set(WATERMARK_KEY, max_watermark(records, "SystemModstamp", watermark))
    watermarks.save()
    log.info("Landed %d accounts at %s", len(records), path)