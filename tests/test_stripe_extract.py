from extract.stripe_extract import entity_for, group_events


def test_events_grouped_by_entity():
    events = [
        {"id": "evt_1", "type": "customer.created", "created": 1, "data": {"object": {"id": "cus_1"}}},
        {"id": "evt_2", "type": "charge.succeeded", "created": 2, "data": {"object": {"id": "ch_1"}}},
        {"id": "evt_3", "type": "payment_intent.created", "created": 3, "data": {"object": {"id": "pi_1"}}},
    ]
    grouped = group_events(events)
    assert set(grouped) == {"customer", "charge"}
    assert grouped["charge"][0]["_event_type"] == "charge.succeeded"


def test_unknown_event_types_are_skipped():
    assert entity_for("payment_intent.created") is None