from extract.watermarks import DEFAULT_WATERMARK, WatermarkStore, max_watermark


class FakeVolume:
    """In-memory stand-in for VolumeClient."""

    def __init__(self):
        self.files = {}

    def read_text(self, path):
        return self.files.get(path)

    def write_text(self, path, body):
        self.files[path] = body


def test_first_run_uses_default_watermark():
    assert WatermarkStore(FakeVolume()).get("salesforce.account") == DEFAULT_WATERMARK


def test_saved_watermark_survives_a_new_run():
    volume = FakeVolume()
    store = WatermarkStore(volume)
    store.set("salesforce.account", "2026-10-31T04:00:00Z")
    store.save()
    assert WatermarkStore(volume).get("salesforce.account") == "2026-10-31T04:00:00Z"


def test_unsaved_watermark_is_lost():
    volume = FakeVolume()
    WatermarkStore(volume).set("salesforce.account", "2026-10-31T04:00:00Z")
    assert WatermarkStore(volume).get("salesforce.account") == DEFAULT_WATERMARK


def test_watermark_never_moves_backwards():
    records = [{"SystemModstamp": "2026-01-01T00:00:00Z"}]
    assert max_watermark(records, "SystemModstamp", "2026-06-01T00:00:00Z") == "2026-06-01T00:00:00Z"