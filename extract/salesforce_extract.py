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

# WATERMARK_KEY = "salesforce.account"
# ACCOUNT_QUERY = (
#     "SELECT Id, Name, Website, Phone, BillingCity, BillingState, Industry, "
#     "CreatedDate, SystemModstamp FROM Account"
# )
ENTITIES = {
    "account": (
        "SELECT Id, Name, Website, Phone, BillingCity, BillingState, Industry, "
        "CreatedDate, SystemModstamp FROM Account"
    ),
    "opportunity": (
        "SELECT Id, AccountId, Name, StageName, Amount, CloseDate, IsWon, "
        "CreatedDate, SystemModstamp FROM Opportunity"
    ),
}
def build_query(base_query: str, watermark: str) -> str:
    return f"{base_query} WHERE SystemModstamp > {watermark} ORDER BY SystemModstamp ASC"
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


def extract_entity(sf, volume, watermarks, entity: str, base_query: str, run_id: str) -> None:
    key = f"salesforce.{entity}"
    watermark = watermarks.get(key)
    records = [clean(r) for r in sf.query_all(build_query(base_query, watermark))["records"]]
    log.info("%s: %d records changed since %s", entity, len(records), watermark)

    if not records:
        return

    path = landing_path("salesforce", entity, run_id)
    volume.write_text(path, to_ndjson(records, "salesforce", entity, run_id))
    watermarks.set(key, max_watermark(records, "SystemModstamp", watermark))
    log.info("Landed %d %s records at %s", len(records), entity, path)


def run() -> None:
    sf = connect()
    volume = VolumeClient.from_env()
    watermarks = WatermarkStore(volume)
    run_id = new_run_id()

    for entity, base_query in ENTITIES.items():
        extract_entity(sf, volume, watermarks, entity, base_query, run_id)

    # Save once, after every object has landed.
    watermarks.save()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run()