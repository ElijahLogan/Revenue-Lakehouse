"""Incremental Stripe extract via the Events API.

List endpoints filter on creation date,
they miss later changes like refunds on old charges. 
Events record every change. The watermark is the newest event's
`created` time  Unix timestamp).
"""

from __future__ import annotations

import logging
import os
from collections import defaultdict

import stripe

from extract.records import landing_path, new_run_id, to_ndjson
from extract.volume import VolumeClient
from extract.watermarks import WatermarkStore

log = logging.getLogger(__name__)

WATERMARK_KEY = "stripe.events"

# Event type prefix -> landing entity.
EVENT_ENTITY = {"customer.": "customer", "charge.": "charge"}


def entity_for(event_type: str) -> str | None:
    for prefix, entity in EVENT_ENTITY.items():
        if event_type.startswith(prefix):
            return entity
    return None


def group_events(events: list[dict]) -> dict[str, list[dict]]:
    """Group each event's object snapshot by entity, tagged with the event that produced it."""
    grouped: dict[str, list[dict]] = defaultdict(list)
    for event in events:
        entity = entity_for(event["type"])
        if entity is None:
            continue  # event types we don't land, e.g. payment_intent.*
        obj = dict(event["data"]["object"])
        obj["_event_id"] = event["id"]
        obj["_event_type"] = event["type"]
        obj["_event_created"] = event["created"]
        grouped[entity].append(obj)
    return grouped


def run() -> None:
    stripe.api_key = os.environ["STRIPE_API_KEY"]
    if not stripe.api_key.startswith("sk_test_"):
        raise SystemExit("Refusing to run: STRIPE_API_KEY must be a test-mode key.")

    volume = VolumeClient.from_env()
    watermarks = WatermarkStore(volume)
    run_id = new_run_id()

    stored = watermarks.get(WATERMARK_KEY)
    since = int(stored) if stored.isdigit() else 0  # default watermark is a date, not epoch

    events = [
        e.to_dict()
        for e in stripe.Event.list(created={"gt": since}, limit=100).auto_paging_iter()
    ]
    log.info("%d events since %s", len(events), since)
    if not events:
        return

    for entity, records in group_events(events).items():
        path = landing_path("stripe", entity, run_id)
        volume.write_text(path, to_ndjson(records, "stripe", entity, run_id))
        log.info("Landed %d %s records at %s", len(records), entity, path)

    # Only advance the watermark after every file has landed.
    watermarks.set(WATERMARK_KEY, str(max(e["created"] for e in events)))
    watermarks.save()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run()