"""
Test other stores.
"""

import datetime

from _common import run_tests
from timetagger.app import stores


class Stub:
    def addEventListener(self, *args):
        pass

    def setTimeout(self, *args):
        pass

    def clearTimeout(self, *args):
        pass


stores.window = Stub()
stores.window.document = Stub()


def test_demo_record_store():
    ds = stores.DemoDataStore()

    # There are now records for only one year
    # Note that this test fails early januari :P
    if datetime.date.today().month > 1:
        assert len(ds.records.get_records(0, 1e15)) > 25
    assert len(ds.records.get_records(0, 1e15)) < 2000

    # Build other years
    for year in ds._years:
        ds._create_one_year_of_data(year)

    # Now we have the full demo. The demo generates the records async
    assert len(ds.records.get_records(0, 1e15)) > 2000

    stats = ds.records.get_stats(0, 1e15)
    assert len(stats.keys()) > 1
    print(stats)


def test_to_text():
    """The note converter keeps newlines (unlike to_str) but is still bounded."""
    assert stores.to_text("hello") == "hello"
    assert stores.to_text("a\nb") == "a\nb"
    assert stores.to_text("a\r\nb\rc") == "a\nb\nc"
    assert stores.to_text("a\tb") == "a b"
    assert len(stores.to_text("x" * 9999)) == stores.TEXT_MAX - 1
    # Note: to_str only flattens newlines in the js branch, where the client
    # actually runs; here it is the plain str stub, so there is nothing to assert.


def test_note_is_optional():
    """A record without a note must stay exactly as it was."""
    record = stores.RecordStore(None).create(100, 200, "#p1 header")
    assert "note" not in record

    items = stores.RecordStore(None)._validate_items([record])
    assert len(items) == 1
    assert "note" not in items[0]


def test_unknown_fields_survive_the_client():
    """An older client must not drop a field it does not know about."""
    record = stores.RecordStore(None).create(100, 200, "#p1")
    record["somefuturefield"] = "keep me"

    items = stores.RecordStore(None)._validate_items([record])
    assert items[0]["somefuturefield"] == "keep me"


def test_make_hidden_drops_the_note():
    """Deleting a record must not leave its prose behind."""
    record = stores.RecordStore(None).create(100, 200, "#p1 header")
    record["note"] = "context that should not outlive the record"

    stores.make_hidden(record)
    assert record["ds"].startswith("HIDDEN")
    assert "note" not in record


def test_make_hidden_stays_within_the_server_limit():
    """The server rejects ds of STR_MAX chars or more; a rejected hide would
    make the record come back on the next sync.
    """
    record = stores.RecordStore(None).create(100, 200, "#p1 " + "x" * 251)
    assert len(record["ds"]) == stores.STR_MAX - 1

    stores.make_hidden(record)
    assert record["ds"].startswith("HIDDEN ")
    assert len(record["ds"]) == stores.STR_MAX - 1

    # Hiding again changes nothing
    ds = record["ds"]
    stores.make_hidden(record)
    assert record["ds"] == ds


if __name__ == "__main__":
    run_tests(globals())
