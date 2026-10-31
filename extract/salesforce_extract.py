"""Extract Salesforce accounts into the landing volume.

v1: full pull every run. No watermark yet.
"""

from __future__ import annotations

import logging
import os

from simple_salesforce import Salesforce

from extract.records import landing_path, new_run_id, to_ndjson
from extract.volume import VolumeClient

log = logging.getLogger(__name__)

ACCOUNT_QUERY = (
    "SELECT Id, Name, Website, Phone, BillingCity, BillingState, Industry, "
    "CreatedDate, SystemModstamp FROM Account"
)


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
    run_id = new_run_id()

    records = [clean(r) for r in sf.query_all(ACCOUNT_QUERY)["records"]]
    if not records:
        return
    path = landing_path("salesforce", "account", run_id)
    volume.write_text(path, to_ndjson(records, "salesforce", "account", run_id))
    log.info("Landed %d accounts at %s", len(records), path)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run()