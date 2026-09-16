"""
Test the logic from the utils module that finds records that are only
separated by breaks (series), merges notes, and plans merging records into
the longest record. These functions also run in JS, so the results are
compared against node.
"""

import json
import random
import subprocess

import pscript
from pscript import py2js, evaljs

from _common import run_tests
from timetagger.app import utils

try:
    subprocess.check_output([pscript.functions.get_node_exe(), "-v"])
    HAS_NODE = True
except Exception:  # pragma: no cover
    HAS_NODE = False


T = 1_700_000_000
DAY = 86400
DAYS = [T, T + DAY]
K = "#kancelaria Automatyzacja"
P = "#pumox Zadania GP"


def rec(key, t1, t2, ds=None, note=None):
    """Create a record dict with times relative to T."""
    record = {"key": key, "t1": T + t1, "t2": T + t2}
    if ds is not None:
        record["ds"] = ds
    if note is not None:
        record["note"] = note
    return record


def hm(h, m):
    return h * 3600 + m * 60


def series_keys(series_list):
    return [s["record_keys"] for s in series_list]


# %% Fixtures, as (name, func_name, args)


def get_note_fixtures():
    def notes(*texts):
        return [rec(f"n{i}", i, i + 1, "#a", text) for i, text in enumerate(texts)]

    return [
        ("notes_duplicates", "merge_notes", [notes("a", "a", "a\nb")]),
        ("notes_extended_first", "merge_notes", [notes("x\ny", "x")]),
        ("notes_order", "merge_notes", [notes("x", "y", "x")]),
        ("notes_empty", "merge_notes", [notes("", "  ", None)]),
        ("notes_prefix", "merge_notes", [notes("ticket 4", "ticket 42", " ticket 4 ")]),
        ("notes_none", "merge_notes", [[]]),
    ]


def get_series_fixtures():
    # The day from the screenshot: two threads with breaks, and a running record
    day = [
        rec("p1", hm(9, 26), hm(10, 18), P, "- scenarios for fetch\n-"),
        rec("p2", hm(10, 40), hm(11, 12), P, "- performance fixes\n- diagnostics"),
        rec("k1", hm(11, 49), hm(13, 30), K),
        rec("k2", hm(14, 35), hm(14, 45), K),
        rec("k3", hm(15, 0), hm(15, 16), K),
        rec("l1", hm(15, 27), hm(15, 27), "#liviere-studio"),
    ]
    day_now = T + hm(15, 28)

    def gap(extra):
        return [rec("k1", 0, 600, "#a"), rec("k2", 900, 1200, "#a")] + extra

    overlapping = [
        rec("a1", 0, 1800, "#a"),
        rec("a2", 300, 600, "#a"),
        rec("z", 700, 900, "#z"),
        rec("a3", 2000, 2100, "#a"),
    ]
    prototype = [
        rec("constructor", 0, 600, "toString"),
        rec("toString", 900, 1200, "toString"),
    ]
    before_first_day = [
        rec("y1", -900, -600, "#a"),
        rec("y2", -300, 100, "#a"),
        rec("t", 200, 300, "#a"),
    ]
    notes = [
        rec("n1", 0, 600, "#a", "ticket 4"),
        rec("n2", 900, 1200, "#a", "ticket 42"),
        rec("n3", 1300, 1400, "#a", " ticket 4 "),
    ]
    midnight = [rec("k1", 80000, 86000, "#a"), rec("k2", 87000, 88000, "#a")]
    return [
        ("series_day", "find_break_series", [day, DAYS, day_now]),
        ("series_gap_start", "find_break_series", [gap([rec("x", 600, 660)]), DAYS, T]),
        ("series_gap_end", "find_break_series", [gap([rec("y", 840, 900)]), DAYS, T]),
        ("series_gap_none", "find_break_series", [gap([rec("z", 300, 600)]), DAYS, T]),
        ("series_same_t1", "find_break_series", [gap([rec("b", 900, 960)]), DAYS, T]),
        ("series_same_t1_longer", "find_break_series", [gap([rec("b", 900, 1500)]), DAYS, T]),
        ("series_running", "find_break_series", [[rec("k1", 0, 600, "#a"), rec("k2", 900, 900, "#a")], DAYS, T + 1500]),
        ("series_running_gap", "find_break_series", [gap([rec("r", 650, 650)]), DAYS, T + 700]),
        ("series_midnight", "find_break_series", [midnight, DAYS, T]),
        ("series_overlapping", "find_break_series", [overlapping, DAYS, T]),
        ("series_no_ds", "find_break_series", [[rec("r1", 0, 600), rec("r2", 900, 1200, "")], DAYS, T]),
        ("series_prototype", "find_break_series", [prototype, DAYS, T]),
        ("series_before_first_day", "find_break_series", [before_first_day, DAYS, T]),
        ("series_notes", "find_break_series", [notes, DAYS, T]),
        ("series_empty", "find_break_series", [[], DAYS, T]),
    ]  # fmt: skip


def get_merge_fixtures():
    def merge(records, keys, now=T, note_max=4095):
        return [records, "#a", keys, T, T + DAY, now, note_max]

    later = [
        rec("long", 28800, 43200, "#a"),
        rec("B", 43200, 61200, "#b"),
        rec("fix", 61200, 61500, "#a"),
        rec("C", 61500, 64800, "#c"),
    ]
    break_after_b = [
        rec("long", 28800, 43200, "#a"),
        rec("B", 43200, 45000, "#b"),
        rec("C", 46800, 61200, "#c"),
        rec("fix", 61200, 61500, "#a"),
    ]
    room = [
        rec("long", 0, 3600, "#a"),
        rec("fix", 3600, 3900, "#a"),
        rec("B", 3900, 4500, "#b"),
    ]
    earlier = [
        rec("fix", 0, 300, "#a"),
        rec("B", 300, 3600, "#b"),
        rec("long", 3600, 18000, "#a"),
    ]
    both = [
        rec("A1", 0, 600, "#a"),
        rec("B1", 600, 1200, "#b"),
        rec("long", 1200, 5000, "#a"),
        rec("B2", 5000, 5600, "#b"),
        rec("A2", 5600, 5900, "#a"),
        rec("C", 5900, 6500, "#c"),
        rec("A3", 6500, 6600, "#a"),
        rec("D", 6600, 7000, "#d"),
    ]
    unselected = [
        rec("long", 0, 3600, "#a"),
        rec("B", 3600, 4000, "#b"),
        rec("A2", 4000, 4300, "#a"),
        rec("C", 4300, 5000, "#c"),
        rec("A3", 5000, 5200, "#a"),
    ]
    running_after = [
        rec("long", 0, 3600, "#a"),
        rec("B", 3600, 4000, "#b"),
        rec("fix", 4000, 4100, "#a"),
        rec("R", 4100, 4100, "#r"),
    ]
    running_fix = [
        rec("long", 0, 3600, "#a"),
        rec("B", 3600, 4000, "#b"),
        rec("fix", 4000, 4000, "#a"),
    ]
    overlap = [
        rec("long", 0, 3600, "#a"),
        rec("C", 3600, 4200, "#c"),
        rec("D", 3900, 4500, "#d"),
        rec("fix", 4500, 4600, "#a"),
    ]
    overlap_elsewhere = running_after[:3] + [
        rec("X", 10000, 11000, "#x"),
        rec("Y", 10500, 11500, "#y"),
    ]
    anchor_selected = [
        rec("long", 0, 14400, "#a"),
        rec("B", 14400, 30000, "#b"),
        rec("fix", 30000, 30300, "#a"),
    ]
    tie = [
        rec("a1", 0, 600, "#a"),
        rec("B", 600, 900, "#b"),
        rec("a2", 900, 1500, "#a"),
    ]
    notes = [
        rec("w", 0, 60, "#a", "w"),
        rec("B", 60, 600, "#b"),
        rec("long", 600, 4200, "#a", "x"),
        rec("C", 4200, 5000, "#c"),
        rec("f", 5000, 5100, "#a", "x\ny"),
    ]
    previous_day = [
        rec("y", -600, 7200, "#a"),
        rec("B", 7200, 7500, "#b"),
        rec("fix", 7500, 7600, "#a"),
    ]
    midnight = [
        rec("long", 0, 36000, "#a"),
        rec("B", 36000, 86300, "#b"),
        rec("fix", 86300, 86700, "#a"),
    ]
    return [
        ("merge_later", "plan_record_merge", merge(later, ["fix"])),
        ("merge_break_absorbs", "plan_record_merge", merge(break_after_b, ["fix"])),
        ("merge_room", "plan_record_merge", merge(room, ["fix"])),
        ("merge_earlier", "plan_record_merge", merge(earlier, ["fix"])),
        ("merge_both", "plan_record_merge", merge(both, ["A1", "A2", "A3"])),
        ("merge_unselected", "plan_record_merge", merge(unselected, ["A3"])),
        ("merge_running_after", "plan_record_merge", merge(running_after, ["fix"], T + 5000)),
        ("merge_running_fix", "plan_record_merge", merge(running_fix, ["fix"], T + 4500)),
        ("merge_overlap", "plan_record_merge", merge(overlap, ["fix"])),
        ("merge_overlap_elsewhere", "plan_record_merge", merge(overlap_elsewhere, ["fix"])),
        ("merge_anchor_selected", "plan_record_merge", merge(anchor_selected, ["long", "fix"])),
        ("merge_tie", "plan_record_merge", merge(tie, ["a2"])),
        ("merge_notes", "plan_record_merge", merge(notes, ["w", "f"])),
        ("merge_notes_truncated", "plan_record_merge", merge(notes, ["w", "f"], T, 3)),
        ("merge_nothing", "plan_record_merge", merge(later, [])),
        ("merge_unknown", "plan_record_merge", merge(later, ["B", "nope"])),
        ("merge_previous_day", "plan_record_merge", merge(previous_day, ["y", "fix"])),
        ("merge_midnight", "plan_record_merge", merge(midnight, ["fix"])),
        ("merge_not_found", "plan_record_merge", merge([rec("B", 0, 60, "#b")], ["B"])),
    ]  # fmt: skip


def run_fixture(fixtures, name):
    for fixture_name, func_name, args in fixtures:
        if fixture_name == name:
            return getattr(utils, func_name)(*args)
    raise KeyError(name)


# %% Tests


def test_merge_notes():
    fixtures = get_note_fixtures()

    assert run_fixture(fixtures, "notes_duplicates") == "a\nb"
    # A note that was copied and then added to replaces the copy
    assert run_fixture(fixtures, "notes_extended_first") == "x\ny"
    assert run_fixture(fixtures, "notes_order") == "x\ny"
    assert run_fixture(fixtures, "notes_empty") == ""
    # A note that is a prefix of another note, but not of a line, is kept
    assert run_fixture(fixtures, "notes_prefix") == "ticket 4\nticket 42"
    assert run_fixture(fixtures, "notes_none") == ""


def test_find_break_series_day():
    series_list = run_fixture(get_series_fixtures(), "series_day")
    assert series_keys(series_list) == [["p1", "p2"], ["k1", "k2", "k3"], ["l1"]]

    p, k, studio = series_list
    assert p["ds"] == P
    assert p["key"] == "p2"
    assert (p["t1"], p["t2"]) == (T + hm(9, 26), T + hm(11, 12))
    assert p["total"] == hm(1, 24)
    assert p["breaks"] == hm(0, 22)
    assert p["note"] == "- scenarios for fetch\n-\n- performance fixes\n- diagnostics"
    assert p["running"] is False

    assert k["ds"] == K
    assert k["key"] == "k3"
    assert (k["t1"], k["t2"]) == (T + hm(11, 49), T + hm(15, 16))
    assert k["total"] == hm(2, 7)
    assert k["breaks"] == hm(1, 20)
    assert k["note"] == ""

    assert studio["running"] is True
    assert studio["key"] == "l1"
    assert (studio["t1"], studio["t2"]) == (T + hm(15, 27), T + hm(15, 28))
    assert studio["total"] == 60


def test_find_break_series_gaps():
    fixtures = get_series_fixtures()

    # A record that covers any part of the gap separates the records
    assert series_keys(run_fixture(fixtures, "series_gap_start")) == [
        ["k1"],
        ["x"],
        ["k2"],
    ]
    assert series_keys(run_fixture(fixtures, "series_gap_end")) == [
        ["k1"],
        ["y"],
        ["k2"],
    ]
    # A record that ends where the gap starts does not
    series_list = run_fixture(fixtures, "series_gap_none")
    assert series_keys(series_list) == [["k1", "k2"], ["z"]]
    assert series_list[0]["total"] == 900
    assert series_list[0]["breaks"] == 300
    # Neither does a record that starts where the gap ends, also if it is longer
    assert series_keys(run_fixture(fixtures, "series_same_t1")) == [
        ["k1", "k2"],
        ["b"],
    ]
    assert series_keys(run_fixture(fixtures, "series_same_t1_longer")) == [
        ["k1", "k2"],
        ["b"],
    ]


def test_find_break_series_running_and_days():
    fixtures = get_series_fixtures()

    # A running record ends now
    series_list = run_fixture(fixtures, "series_running")
    assert series_keys(series_list) == [["k1", "k2"]]
    series = series_list[0]
    assert series["running"] is True
    assert series["key"] == "k2"
    assert series["t2"] == T + 1500
    assert series["total"] == 1200
    assert series["breaks"] == 300

    # A running record in the gap separates the records
    assert series_keys(run_fixture(fixtures, "series_running_gap")) == [
        ["k1"],
        ["r"],
        ["k2"],
    ]

    # Records on different days are not joined
    assert series_keys(run_fixture(fixtures, "series_midnight")) == [["k1"], ["k2"]]
    assert series_keys(run_fixture(fixtures, "series_before_first_day")) == [
        ["y1", "y2"],
        ["t"],
    ]


def test_find_break_series_details():
    fixtures = get_series_fixtures()

    # Overlapping records of the same thread: the end is the latest end, and
    # the key is of the record that ends last
    series_list = run_fixture(fixtures, "series_overlapping")
    assert series_keys(series_list) == [["a1", "a2", "a3"], ["z"]]
    series = series_list[0]
    assert (series["t1"], series["t2"]) == (T, T + 2100)
    assert series["key"] == "a3"
    assert series["total"] == 2200
    assert series["breaks"] == 200

    # Records without description are a thread too
    series_list = run_fixture(fixtures, "series_no_ds")
    assert series_keys(series_list) == [["r1", "r2"]]
    assert series_list[0]["ds"] == ""

    assert series_keys(run_fixture(fixtures, "series_prototype")) == [
        ["constructor", "toString"]
    ]
    assert run_fixture(fixtures, "series_notes")[0]["note"] == "ticket 4\nticket 42"
    assert run_fixture(fixtures, "series_empty") == []


def brute_force_series(records, day_starts, now):
    """A slow reference implementation, that checks the gaps second by second."""

    def end_of(r):
        return max(r["t1"], now) if r["t1"] == r["t2"] else r["t2"]

    def day_of(t):
        return len([d for d in day_starts if d <= t]) - 1

    series_list = []
    latest = {}
    for record in utils._sorted_records(records, now):
        ds = record.get("ds", "") or ""
        members = series_list[latest[ds]] if ds in latest else None
        if members is not None:
            end = max(end_of(r) for r in members)
            joined = day_of(members[0]["t1"]) == day_of(record["t1"])
            if joined and record["t1"] > end:
                for second in range(end, record["t1"]):
                    for other in records:
                        covers = other["t1"] <= second < end_of(other)
                        if covers and other is not record:
                            joined = False
            if joined:
                members.append(record)
                continue
        latest[ds] = len(series_list)
        series_list.append([record])

    result = []
    for members in series_list:
        end = None
        key = None
        running = False
        breaks = 0
        for r in members:
            if end is not None and r["t1"] > end:
                breaks += r["t1"] - end
            if r["t1"] == r["t2"]:
                running = True
                key = r["key"]
            elif not running and (end is None or end_of(r) >= end):
                key = r["key"]
            end = end_of(r) if end is None else max(end, end_of(r))
        result.append(
            {
                "ds": members[0].get("ds", "") or "",
                "record_keys": [r["key"] for r in members],
                "key": key,
                "t1": members[0]["t1"],
                "t2": end,
                "running": running,
                "total": sum(end_of(r) - r["t1"] for r in members),
                "breaks": breaks,
                "note": utils.merge_notes(members),
            }
        )
    return result


def test_find_break_series_random():
    rng = random.Random(42)
    day_starts = [T, T + 200]
    now = T + 450
    for _ in range(1000):
        records = []
        for i in range(rng.randint(0, 10)):
            t1 = rng.randint(-60, 400)
            t2 = t1 if rng.random() < 0.1 else t1 + rng.randint(1, 80)
            ds = rng.choice(["#a", "#a", "#b", "#c", ""])
            records.append(rec(f"r{i}", t1, t2, ds))
        expected = brute_force_series(records, day_starts, now)
        assert utils.find_break_series(records, day_starts, now) == expected, records


def check_merge(name, anchor, shifted=(), hide=(), reason=""):
    plan = run_fixture(get_merge_fixtures(), name)
    assert plan["reason"] == reason, name
    if anchor is None:
        assert plan["anchor"] is None, name
    else:
        key, t1, t2 = anchor
        assert plan["anchor_key"] == key, name
        assert (plan["anchor"]["t1"] - T, plan["anchor"]["t2"] - T) == (t1, t2), name
    actual = [(s["key"], s["t1"] - T, s["t2"] - T) for s in plan["shifted"]]
    assert actual == list(shifted), name
    assert plan["hide"] == list(hide), name
    return plan


def test_plan_record_merge_moves():
    # The next record moves, the one after that fits
    plan = check_merge(
        "merge_later", ("long", 28800, 43500), [("B", 43500, 61500)], ["fix"]
    )
    assert plan["shifted"][0]["delta"] == 300
    assert plan["added"] == 300
    assert plan["max_shift"] == 300
    assert (plan["t1"], plan["t2"]) == (T + 28800, T + 61500)
    assert plan["candidate_keys"] == ["long", "fix"]

    # A break absorbs the shift
    check_merge(
        "merge_break_absorbs",
        ("long", 28800, 43500),
        [("B", 43500, 45300)],
        ["fix"],
    )
    # There is room, so nothing moves
    plan = check_merge("merge_room", ("long", 0, 3900), [], ["fix"])
    assert plan["max_shift"] == 0

    # A record before the anchor extends its start
    plan = check_merge(
        "merge_earlier", ("long", 3300, 18000), [("B", 0, 3300)], ["fix"]
    )
    assert plan["shifted"][0]["delta"] == -300

    # Both directions at once
    check_merge(
        "merge_both",
        ("long", 600, 5400),
        [("B1", 0, 600), ("B2", 5400, 6000), ("C", 6000, 6600)],
        ["A1", "A2", "A3"],
    )
    # A record of the same thread that is not selected moves like any other
    check_merge(
        "merge_unselected",
        ("long", 0, 3800),
        [("B", 3800, 4200), ("A2", 4200, 4500), ("C", 4500, 5200)],
        ["A3"],
    )


def test_plan_record_merge_checks():
    # A running record right after the range is fine
    check_merge("merge_running_after", ("long", 0, 3700), [("B", 3700, 4100)], ["fix"])
    plan = check_merge("merge_running_fix", None, [], ["fix"], "running")
    assert plan["anchor_key"] == "long"

    # Overlaps block the merge, but only within the range that changes
    check_merge("merge_overlap", None, [], ["fix"], "overlap")
    check_merge(
        "merge_overlap_elsewhere", ("long", 0, 3700), [("B", 3700, 4100)], ["fix"]
    )

    # Selecting the anchor has no effect; on a tie the earliest is the anchor
    check_merge(
        "merge_anchor_selected", ("long", 0, 14700), [("B", 14700, 30300)], ["fix"]
    )
    check_merge("merge_tie", ("a1", 0, 1200), [("B", 1200, 1500)], ["a2"])

    # Nothing to do
    plan = check_merge("merge_nothing", None, [], [], "nothing_selected")
    assert plan["anchor_key"] == "long"
    check_merge("merge_unknown", None, [], [], "nothing_selected")
    plan = check_merge("merge_previous_day", None, [], [], "nothing_selected")
    assert plan["candidate_keys"] == ["fix"]
    plan = check_merge("merge_not_found", None, [], [], "not_found")
    assert plan["anchor_key"] == ""

    # Records must not move into the next day
    check_merge("merge_midnight", None, [], ["fix"], "midnight")


def test_plan_record_merge_notes():
    plan = check_merge(
        "merge_notes",
        ("long", 540, 4300),
        [("B", 0, 540), ("C", 4300, 5100)],
        ["w", "f"],
    )
    assert plan["anchor"]["note"] == "w\nx\ny"
    assert plan["notes_truncated"] is False

    plan = run_fixture(get_merge_fixtures(), "merge_notes_truncated")
    assert plan["anchor"]["note"] == "w\nx"
    assert plan["notes_truncated"] is True


def apply_merge(records, plan):
    """Apply a plan to a list of records, like the merge dialog does."""
    changes = {s["key"]: s for s in plan["shifted"]}
    changes[plan["anchor"]["key"]] = plan["anchor"]
    result = []
    for record in records:
        if record["key"] in plan["hide"]:
            continue
        record = dict(record)
        if record["key"] in changes:
            record["t1"] = changes[record["key"]]["t1"]
            record["t2"] = changes[record["key"]]["t2"]
        result.append(record)
    return result


def test_plan_record_merge_random():
    rng = random.Random(7)
    n_merged = n_shifted = 0
    for _ in range(2000):
        # A day of records that do not overlap, sometimes with breaks
        records = []
        t = rng.randint(0, 3600)
        for i in range(rng.randint(1, 12)):
            t += rng.choice([0, 0, 0, rng.randint(1, 1800)])
            duration = rng.randint(1, 7200)
            ds = rng.choice(["#a", "#a", "#b", "#c"])
            records.append(rec(f"r{i}", t, t + duration, ds))
            t += duration
        if rng.random() < 0.2:
            last = records[-1]
            last["t2"] = last["t1"]  # running
        if rng.random() < 0.2:
            t1 = rng.randint(0, t)
            records.append(rec("x", t1, t1 + rng.randint(1, 3600), "#x"))
        now = T + t + 60
        candidates = [r["key"] for r in records if r["ds"] == "#a"]
        keys = [key for key in candidates if rng.random() < 0.6]

        args = [records, "#a", keys, T, T + DAY, now, 4095]
        plan = utils.plan_record_merge(*args)
        if plan["reason"]:
            continue
        n_merged += 1
        n_shifted += len(plan["shifted"])

        result = apply_merge(records, plan)
        # No overlaps are added (overlaps outside the range are allowed)
        overlap_before = utils.find_overlaps(records, T - DAY, T + 3 * DAY, now, 1)
        overlap_after = utils.find_overlaps(result, T - DAY, T + 3 * DAY, now, 1)
        assert overlap_after["total"] == overlap_before["total"]
        # Every thread keeps its total, and the anchor gets the added time
        for ds in ["#a", "#b", "#c", "#x"]:
            before = sum(r["t2"] - r["t1"] for r in records if r["ds"] == ds)
            after = sum(r["t2"] - r["t1"] for r in result if r["ds"] == ds)
            assert before == after
        anchor = [r for r in records if r["key"] == plan["anchor_key"]][0]
        duration = plan["anchor"]["t2"] - plan["anchor"]["t1"]
        assert duration == anchor["t2"] - anchor["t1"] + plan["added"]
        # Only records within the range change, and the order stays the same
        for old, new in zip(
            [r for r in records if r["key"] not in plan["hide"]], result
        ):
            assert old["key"] == new["key"]
            if (old["t1"], old["t2"]) != (new["t1"], new["t2"]):
                assert plan["t1"] <= old["t1"] and old["t2"] <= plan["t2"]
                assert plan["t1"] <= new["t1"] and new["t2"] <= plan["t2"]
        moved = [r for r in result if r["key"] != "x"]
        order = [r["key"] for r in sorted(moved, key=lambda r: r["t1"])]
        assert order == [r["key"] for r in moved]
    assert n_merged > 500 and n_shifted > 500


def test_break_functions_in_js():
    """Check that the compiled JS produces the same results as Python."""
    if not HAS_NODE:
        print("skipping tests that use node")
        return

    funcs = [
        utils._record_end,
        utils._record_ds,
        utils._sorted_records,
        utils.find_overlaps,
        utils.merge_notes,
        utils.find_break_series,
        utils.plan_record_merge,
    ]
    js = "\n".join(py2js(func, docstrings=False) for func in funcs)

    fixtures = get_note_fixtures() + get_series_fixtures() + get_merge_fixtures()
    calls = []
    for name, func_name, args in fixtures:
        call = f"{func_name}(" + ", ".join(json.dumps(arg) for arg in args) + ")"
        calls.append(f"{json.dumps(name)}: {call}")
    code = js + "\nconsole.log(JSON.stringify({" + ", ".join(calls) + "}));"
    js_results = json.loads(evaljs(code, print_result=False))

    for name, func_name, args in fixtures:
        py_result = json.loads(json.dumps(getattr(utils, func_name)(*args)))
        assert js_results[name] == py_result, name


if __name__ == "__main__":
    run_tests(globals())
