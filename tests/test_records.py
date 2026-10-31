import json

from extract.records import landing_path, to_ndjson


def test_each_record_wrapped_with_lineage():
    body = to_ndjson([{"Id": "001"}, {"Id": "002"}], "salesforce", "account", "run-1")
    lines = [json.loads(line) for line in body.strip().split("\n")]
    assert len(lines) == 2
    assert lines[0]["_source"] == "salesforce"
    assert lines[1]["payload"] == {"Id": "002"}


def test_empty_input_gives_empty_file():
    assert to_ndjson([], "salesforce", "account", "run-1") == ""


def test_landing_path_partitioned_by_date():
    path = landing_path("salesforce", "account", "2026-10-30T20-00-00Z")
    assert path == "salesforce/account/run_date=2026-10-30/2026-10-30T20-00-00Z.json"