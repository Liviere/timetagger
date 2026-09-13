"""
Test the multitasking logic from the utils module: detecting chains (sessions)
of adjacent records, splitting them into blocks, and planning consolidation.
These functions also run in JS, so the results are compared against node.
"""

import json
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


def rec(key, t1, t2, ds=None, note=None):
    """Create a record dict with times relative to T."""
    record = {"key": key, "t1": T + t1, "t2": T + t2}
    if ds is not None:
        record["ds"] = ds
    if note is not None:
        record["note"] = note
    return record


def keys(records):
    return [r["key"] for r in records]


def block_times(plan):
    return [(b["key"], b["t1"] - T, b["t2"] - T) for b in plan["blocks"]]


# %% Fixtures, as (name, func_name, args)


def get_chain_fixtures():
    records1 = [
        rec("c", 1320, 1800),
        rec("a", 0, 600),
        rec("d", 1921, 2400),
        rec("b", 600, 1200),
    ]
    records2 = [
        rec("L", 0, 3600),
        rec("s1", 300, 600),
        rec("s2", 3000, 3300),
        rec("s3", 3720, 4200),
        rec("s4", 4321, 4800),
    ]
    records3 = [
        rec("r", 0, 0),  # running
        rec("x", 600, 1200),
        rec("v", -600, -120),
        rec("w", -1800, -721),
    ]
    return [
        ("chain_a", "get_record_chain", [records1, "a", 120, T]),
        ("chain_c", "get_record_chain", [records1, "c", 120, T]),
        ("chain_d", "get_record_chain", [records1, "d", 120, T]),
        ("chain_unknown", "get_record_chain", [records1, "zz", 120, T]),
        ("chain_s1", "get_record_chain", [records2, "s1", 120, T]),
        ("chain_s4", "get_record_chain", [records2, "s4", 120, T]),
        ("chain_r", "get_record_chain", [records3, "r", 120, T + 3600]),
        ("chain_w", "get_record_chain", [records3, "w", 120, T + 3600]),
    ]


def get_block_fixtures():
    names = "X A1 B1 A2 B2 Y C1 D1 C2".split(" ")
    records1 = []
    for i in range(len(names)):
        ds = "#" + names[i][0].lower()
        records1.append(rec(names[i], i * 600, (i + 1) * 600, ds))
    records2 = [
        rec("P", 0, 600, "#p"),
        rec("Q", 600, 1200, "#q"),
        rec("R", 900, 1500, "#r"),
    ]
    records3 = [
        rec("S", 0, 0, "#s"),  # running
        rec("U", 300, 600, "#u"),
    ]
    return [
        ("blocks_interleaved", "split_chain_into_blocks", [records1, T]),
        ("blocks_overlap", "split_chain_into_blocks", [records2, T]),
        ("blocks_running", "split_chain_into_blocks", [records3, T + 1800]),
    ]


K = "#kancelaria wdrozenie X"
P = "#pumox awaria Y"


def get_plan_fixtures():
    records_a = [
        rec("k1", 0, 3600, K, "etap 1"),
        rec("p1", 3600, 4800, P, "ticket 42"),
        rec("k2", 4800, 6000, K),
        rec("p2", 6000, 7200, P, "ticket 42"),
        rec("k3", 7200, 27000, K, "etap 2"),
    ]
    records_b = [
        rec("a1", 0, 600, "#a"),
        rec("b1", 600, 1500, "#b"),
        rec("a2", 1500, 2400, "#a"),
        rec("b2", 2400, 3000, "#b"),
    ]
    records_c = [rec("a", 0, 3600, "#a"), rec("b", 1200, 1800, "#b")]
    records_d = [rec("a1", 0, 1800, "#a"), rec("a2", 0, 1800, "#a")]
    records_e = [rec("x1", 0, 3600, "#x"), rec("y1", 0, 3600, "#y")]
    records_f = [
        rec("A1", 0, 600, "#a"),
        rec("B", 660, 1200, "#b"),
        rec("A2", 1200, 1800, "#a"),
    ]
    records_g = [
        rec("p1", 0, 2400, P, "ticket 42"),
        rec("k1", 2400, 27000, K, "etap 1\netap 2"),
    ]
    records_h = [
        rec("A1", 0, 600, "#a", "x"),
        rec("B1", 600, 1200, "#b"),
        rec("A2", 1200, 1800, "#a", " y \n"),
        rec("A3", 1800, 2400, "#a", "x"),
    ]
    records_i = [
        rec("r1", 0, 600),
        rec("a", 600, 1200, "#a"),
        rec("r2", 1200, 1800, ""),
    ]
    return [
        ("plan_a", "plan_consolidation", [records_a, 4095]),
        ("plan_b", "plan_consolidation", [records_b, 4095]),
        ("plan_c", "plan_consolidation", [records_c, 4095]),
        ("plan_d", "plan_consolidation", [records_d, 4095]),
        ("plan_e", "plan_consolidation", [records_e, 4095]),
        ("plan_f", "plan_consolidation", [records_f, 4095]),
        ("plan_g", "plan_consolidation", [records_g, 4095]),
        ("plan_h", "plan_consolidation", [records_h, 4095]),
        ("plan_h_truncated", "plan_consolidation", [records_h, 2]),
        ("plan_i", "plan_consolidation", [records_i, 4095]),
        ("plan_empty", "plan_consolidation", [[], 4095]),
    ]


def get_thread_fixtures():
    records = [
        rec("A1", 0, 600, "#a", "n1"),
        rec("B1", 600, 1200, "#b"),
        rec("A2", 1200, 1200, "#a"),  # running
    ]
    return [
        ("threads", "list_session_threads", [records, T + 1500]),
        ("threads_empty", "list_session_threads", [[], T]),
    ]


def get_switch_fixtures():
    now = T + 1000
    r_a = rec("R", 0, 0, "#a")
    r_b = rec("R", 0, 0, "#b")
    young_b = rec("R", 995, 995, "#b")
    just_stopped_a = rec("P", 0, 995, "#a")
    stopped_a = rec("P", 0, 900, "#a")
    running_a = rec("Q", 990, 990, "#a")  # running records are not resumed
    r1_a = rec("R1", 0, 0, "#a")
    r2_b = rec("R2", 500, 500, "#b")
    r2_b_young = rec("R2", 999, 999, "#b")
    almost_young_b = rec("R", 990, 990, "#b")
    args = lambda running, recent, ds: [running, recent, ds, now, 10]
    return [
        ("switch_nothing_running", "plan_thread_switch", args([], [], "#b")),
        ("switch_new", "plan_thread_switch", args([r_a], [], "#b")),
        ("switch_same", "plan_thread_switch", args([r_b], [], "#b")),
        ("switch_retitle", "plan_thread_switch", args([young_b], [], "#c")),
        (
            "switch_resume",
            "plan_thread_switch",
            args([young_b], [stopped_a, just_stopped_a], "#a"),
        ),
        (
            "switch_no_resume",
            "plan_thread_switch",
            args([young_b], [stopped_a, running_a], "#a"),
        ),
        ("switch_keep", "plan_thread_switch", args([r1_a, r2_b], [], "#b")),
        ("switch_multi", "plan_thread_switch", args([r2_b_young, r1_a], [], "#c")),
        ("switch_not_young", "plan_thread_switch", args([almost_young_b], [], "#c")),
    ]


def get_overlap_fixtures():
    day = [T, T + 86400]
    touching = [rec("a", 0, 3600), rec("b", 3600, 7200)]
    simple = [rec("b", 1800, 5400), rec("a", 0, 3600)]
    triple = [rec("a", 0, 100), rec("b", 10, 20), rec("c", 15, 30)]
    clipped = [rec("a", -50, 50), rec("b", -40, -10), rec("c", 40, 60)]
    running = [rec("r", 0, 0), rec("b", 50, 60)]
    small = [rec("a", 0, 10), rec("b", 8, 20)]
    return [
        ("overlap_touching", "find_overlaps", [touching] + day + [T, 1]),
        ("overlap_simple", "find_overlaps", [simple] + day + [T, 1]),
        ("overlap_triple", "find_overlaps", [triple] + day + [T, 1]),
        ("overlap_clipped", "find_overlaps", [clipped, T, T + 100, T, 1]),
        ("overlap_running", "find_overlaps", [running] + day + [T + 100, 1]),
        ("overlap_small", "find_overlaps", [small] + day + [T, 5]),
        ("overlap_empty", "find_overlaps", [[]] + day + [T, 1]),
    ]


def run_fixture(fixtures, name):
    for fixture_name, func_name, args in fixtures:
        if fixture_name == name:
            return getattr(utils, func_name)(*args)
    raise KeyError(name)


# %% Tests


def test_get_record_chain():
    fixtures = get_chain_fixtures()

    # Records within the gap belong to the chain, the order of input is irrelevant
    assert keys(run_fixture(fixtures, "chain_a")) == ["a", "b", "c"]
    assert keys(run_fixture(fixtures, "chain_c")) == ["a", "b", "c"]
    # A gap of 121s breaks the chain
    assert keys(run_fixture(fixtures, "chain_d")) == ["d"]
    assert run_fixture(fixtures, "chain_unknown") == []

    # A long record keeps the chain connected
    assert keys(run_fixture(fixtures, "chain_s1")) == ["L", "s1", "s2", "s3"]
    assert keys(run_fixture(fixtures, "chain_s4")) == ["s4"]

    # A running record ends now
    assert keys(run_fixture(fixtures, "chain_r")) == ["v", "r", "x"]
    assert keys(run_fixture(fixtures, "chain_w")) == ["w"]


def test_split_chain_into_blocks():
    fixtures = get_block_fixtures()

    blocks = run_fixture(fixtures, "blocks_interleaved")
    assert [keys(b) for b in blocks] == [
        ["X"],
        ["A1", "B1", "A2", "B2"],
        ["Y"],
        ["C1", "D1", "C2"],
    ]

    # No cut where records overlap
    blocks = run_fixture(fixtures, "blocks_overlap")
    assert [keys(b) for b in blocks] == [["P"], ["Q", "R"]]

    # A running record ends now
    blocks = run_fixture(fixtures, "blocks_running")
    assert [keys(b) for b in blocks] == [["S", "U"]]

    assert utils.split_chain_into_blocks([], T) == []


def test_plan_consolidation_design_example():
    fixtures = get_plan_fixtures()

    # The short interruptions go first, because that is closest to reality
    plan = run_fixture(fixtures, "plan_a")
    assert block_times(plan) == [("p1", 0, 2400), ("k1", 2400, 27000)]
    assert [b["note"] for b in plan["blocks"]] == ["ticket 42", "etap 1\netap 2"]
    assert [b["record_keys"] for b in plan["blocks"]] == [
        ["p1", "p2"],
        ["k1", "k2", "k3"],
    ]
    assert [b["ds"] for b in plan["blocks"]] == [P, K]
    assert plan["hide"] == ["k2", "p2", "k3"]
    assert plan["removed"] == []
    assert plan["n_before"] == 5
    assert plan["n_after"] == 2
    assert plan["n_threads"] == 2
    assert plan["t1"] == T and plan["t2"] == T + 27000
    assert plan["total"] == 27000
    assert plan["overlap_removed"] == 0
    assert plan["gaps_removed"] == 0
    assert plan["notes_truncated"] is False
    assert plan["is_noop"] is False
    assert plan["checkerboard"] is True

    # Consolidating the result again changes nothing
    plan = run_fixture(fixtures, "plan_g")
    assert block_times(plan) == [("p1", 0, 2400), ("k1", 2400, 27000)]
    assert plan["hide"] == []
    assert plan["is_noop"] is True
    assert plan["checkerboard"] is False


def test_plan_consolidation_keeps_totals():
    fixtures = get_plan_fixtures()

    plan = run_fixture(fixtures, "plan_b")
    assert block_times(plan) == [("a1", 0, 1500), ("b1", 1500, 3000)]
    assert plan["hide"] == ["a2", "b2"]
    assert plan["checkerboard"] is True

    # Gaps move to the end
    plan = run_fixture(fixtures, "plan_f")
    assert block_times(plan) == [("A1", 0, 1200), ("B", 1200, 1740)]
    assert plan["hide"] == ["A2"]
    assert plan["gaps_removed"] == 60
    assert plan["total"] == 1740

    for fixture_name, _, args in fixtures:
        plan = run_fixture(fixtures, fixture_name)
        blocks = plan["blocks"]
        # Blocks are contiguous and add up to the covered time
        for i in range(1, len(blocks)):
            assert blocks[i]["t1"] == blocks[i - 1]["t2"]
        assert sum(b["t2"] - b["t1"] for b in blocks) == plan["total"]
        raw = sum(r["t2"] - r["t1"] for r in args[0])
        assert plan["total"] + plan["overlap_removed"] == raw
        # Every record is either kept or hidden
        kept = [b["key"] for b in blocks]
        assert sorted(kept + plan["hide"]) == sorted(keys(args[0]))


def test_plan_consolidation_overlaps():
    fixtures = get_plan_fixtures()

    # The record that started later owns the overlapping time
    plan = run_fixture(fixtures, "plan_c")
    assert block_times(plan) == [("b", 0, 600), ("a", 600, 3600)]
    assert plan["hide"] == []
    assert plan["overlap_removed"] == 600
    assert plan["checkerboard"] is False

    # Duplicates of the same thread merge
    plan = run_fixture(fixtures, "plan_d")
    assert block_times(plan) == [("a1", 0, 1800)]
    assert plan["hide"] == ["a2"]
    assert plan["overlap_removed"] == 1800
    assert plan["checkerboard"] is False

    # A thread that is completely covered by another thread has no time left
    plan = run_fixture(fixtures, "plan_e")
    assert block_times(plan) == [("y1", 0, 3600)]
    assert plan["hide"] == ["x1"]
    assert plan["removed"] == ["#x"]
    assert plan["overlap_removed"] == 3600
    assert plan["n_threads"] == 2


def test_plan_consolidation_notes_and_ties():
    fixtures = get_plan_fixtures()

    # Notes are stripped, deduplicated and kept in chronological order
    plan = run_fixture(fixtures, "plan_h")
    assert block_times(plan) == [("B1", 0, 600), ("A1", 600, 2400)]
    assert [b["note"] for b in plan["blocks"]] == ["", "x\ny"]
    assert plan["hide"] == ["A2", "A3"]
    assert plan["notes_truncated"] is False

    plan = run_fixture(fixtures, "plan_h_truncated")
    assert [b["note"] for b in plan["blocks"]] == ["", "x"]
    assert plan["notes_truncated"] is True

    # Records without description form a thread too; on a tie, first come first
    plan = run_fixture(fixtures, "plan_i")
    assert block_times(plan) == [("r1", 0, 1200), ("a", 1200, 1800)]
    assert [b["ds"] for b in plan["blocks"]] == ["", "#a"]
    assert plan["hide"] == ["r2"]
    assert plan["checkerboard"] is True

    plan = run_fixture(fixtures, "plan_empty")
    assert plan["blocks"] == [] and plan["hide"] == []
    assert plan["is_noop"] is True


def test_list_session_threads():
    fixtures = get_thread_fixtures()

    threads = run_fixture(fixtures, "threads")
    assert threads == [
        {
            "ds": "#a",
            "note": "n1",
            "total": 900,
            "n_records": 2,
            "last_end": T + 1500,
            "last_key": "A2",
        },
        {
            "ds": "#b",
            "note": "",
            "total": 600,
            "n_records": 1,
            "last_end": T + 1200,
            "last_key": "B1",
        },
    ]
    assert run_fixture(fixtures, "threads_empty") == []


def test_plan_thread_switch():
    fixtures = get_switch_fixtures()

    def check(name, action, key="", stop=(), hide=()):
        plan = run_fixture(fixtures, name)
        assert plan["action"] == action, name
        assert plan["key"] == key, name
        assert plan["stop"] == [[k, T + t] for k, t in stop], name
        assert plan["hide"] == list(hide), name

    check("switch_nothing_running", "new")
    check("switch_new", "new", stop=[("R", 1000)])
    check("switch_same", "noop", "R")
    # A young record (e.g. an accidental switch) is renamed ...
    check("switch_retitle", "retitle", "R")
    # ... or when going back, the record that just stopped continues
    check("switch_resume", "resume", "P", hide=["R"])
    check("switch_no_resume", "retitle", "R")
    # Multiple running records: keep the one that matches, stop the others
    check("switch_keep", "keep", "R2", stop=[("R1", 1000)])
    check("switch_multi", "new", stop=[("R1", 1000), ("R2", 1001)])
    check("switch_not_young", "new", stop=[("R", 1000)])


def test_find_overlaps():
    fixtures = get_overlap_fixtures()

    def check(name, total, pairs):
        result = run_fixture(fixtures, name)
        assert result == {"total": total, "pairs": pairs}, name

    check("overlap_touching", 0, [])
    check("overlap_simple", 1800, [["a", "b", 1800]])
    check("overlap_triple", 25, [["a", "b", 10], ["a", "c", 15], ["b", "c", 5]])
    # Only the time within the range counts
    check("overlap_clipped", 10, [["a", "c", 10]])
    # A running record ends now
    check("overlap_running", 10, [["r", "b", 10]])
    # Small overlaps are not listed, but do count
    check("overlap_small", 2, [])
    check("overlap_empty", 0, [])


def test_multitask_functions_in_js():
    """Check that the compiled JS produces the same results as Python."""
    if not HAS_NODE:
        print("skipping tests that use node")
        return

    funcs = [
        utils._record_end,
        utils._record_ds,
        utils._sorted_records,
        utils.get_record_chain,
        utils.split_chain_into_blocks,
        utils.plan_consolidation,
        utils.list_session_threads,
        utils.plan_thread_switch,
        utils.find_overlaps,
    ]
    js = "\n".join(py2js(func, docstrings=False) for func in funcs)

    fixtures = get_chain_fixtures() + get_block_fixtures() + get_plan_fixtures()
    fixtures += get_thread_fixtures() + get_switch_fixtures()
    fixtures += get_overlap_fixtures()
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
