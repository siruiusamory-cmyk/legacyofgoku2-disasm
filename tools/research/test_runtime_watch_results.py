from __future__ import annotations

import json
import os
import struct
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import runtime_watch_results

TARGETS = """kind,start,end,bytes,mode,runtime
candidate-code,0x08000100,0x08000108,8,thumb,
candidate-code,0x08000200,0x08000204,4,thumb,
bx-unresolved,0x08000300,0x08000302,2,thumb,
irq-slot,0x08000104,0x08000108,4,word,0x03000e3c
"""

LOG = """pc,elapsed,kind
0x08000100,0.5,target
0x08000104,0.6,target
0x08000200,0.7,target
0x03000824,0.8,liveness
"""

RUN = """run,seconds,bound,armed,targets,ranges,liveness,stops,executed,liveness_pc
1,120.0,120,4,4,3,60,63,3,0x03000824
"""

COPY = """[[code_copy]]
runtime_start = 0x03000000
source_start = 0x08000000
size = 0x100
"""


def fixture(tmp_path):
    targets = tmp_path / "targets.csv"
    targets.write_text(TARGETS, encoding="ascii")
    return targets


def copy_export(tmp_path):
    export = tmp_path / "export.toml"
    export.write_text(COPY, encoding="ascii")
    return str(export)


def image():
    rom = bytearray(0x100)
    struct.pack_into("<H", rom, 0x10, 0x46C0)
    struct.pack_into("<H", rom, 0x20, 0xDE00)
    return bytes(rom)


def test_a_log_line_names_its_program_counter(tmp_path):
    log = tmp_path / "hits.csv"
    log.write_text(LOG, encoding="ascii")
    addresses, lines = runtime_watch_results.executed(log)
    assert addresses == [0x03000824, 0x08000100, 0x08000104, 0x08000200]
    assert lines == 4


def test_every_target_folds_to_hit_or_silent(tmp_path):
    targets = fixture(tmp_path)
    log = tmp_path / "hits.csv"
    log.write_text(LOG, encoding="ascii")
    addresses, _lines = runtime_watch_results.executed(log)
    rows = runtime_watch_results.fold(runtime_watch_results.read_targets(str(targets)), addresses)
    assert [(row["kind"], row["status"], row["hits"]) for row in rows] == [
        ("candidate-code", "hit", 2), ("candidate-code", "hit", 1),
        ("bx-unresolved", "silent", 0), ("irq-slot", "hit", 1)]
    assert [row["first"] for row in rows] == ["0x08000100", "0x08000200", "", "0x08000104"]


def test_the_proposed_class_merges_the_hit_targets(tmp_path):
    targets = fixture(tmp_path)
    log = tmp_path / "hits.csv"
    log.write_text(LOG, encoding="ascii")
    addresses, _lines = runtime_watch_results.executed(log)
    rows = runtime_watch_results.fold(runtime_watch_results.read_targets(str(targets)), addresses)
    assert runtime_watch_results.proposed(rows) == [[0x08000100, 0x08000108],
                                                    [0x08000200, 0x08000204]]
    assert runtime_watch_results.totals(rows) == {
        "candidate-code": (2, 2, 12), "bx-unresolved": (1, 0, 0), "irq-slot": (1, 1, 4)}


def test_an_import_keeps_only_target_hits_and_one_run_row(tmp_path):
    targets = fixture(tmp_path)
    hits = tmp_path / "hits-out.csv"
    runs = tmp_path / "runs-out.csv"
    directory = tmp_path / "run"
    directory.mkdir()
    (directory / "watch-log.csv").write_text(LOG, encoding="ascii")
    (directory / "run.json").write_text(json.dumps(
        {"seconds": 120.0, "bound": 120, "armed": 5, "targets": 4, "ranges": 3,
         "liveness": 60, "stops": 63, "executed": 3, "liveness_pc": "0x03000824"}),
        encoding="ascii")
    rows = runtime_watch_results.import_run(str(directory), str(runs), str(hits),
                                            runtime_watch_results.read_targets(str(targets)))
    assert [row["start"] for row in rows] == [0x08000100, 0x08000200, 0x08000104]
    assert runtime_watch_results.read_runs(str(runs))[0]["liveness"] == "60"


def test_the_page_states_the_run_the_class_and_the_chance_score(tmp_path):
    targets = runtime_watch_results.read_targets(str(fixture(tmp_path)))
    hits = [{"kind": "candidate-code", "start": 0x08000100, "end": 0x08000108, "bytes": 8,
             "elapsed": "0.5"},
            {"kind": "irq-slot", "start": 0x08000104, "end": 0x08000108, "bytes": 4,
             "elapsed": "0.6"}]
    runs = [{"bound": "120", "seconds": "120.0", "targets": "4", "armed": "4", "ranges": "3",
             "liveness": "60", "stops": "62", "executed": "2", "liveness_pc": "0x03000824"}]
    text = runtime_watch_results.doc_text(targets, hits, runs)
    assert "| 120 | 120.0 | 4 | 4 | 3 | 60 | 62 | 2 |" in text
    assert "Liveness pc `0x03000824`" in text
    assert "1 extent(s) / 8 B" in text
    assert "`candidate-code`: 1 of 2 target(s) executed, 8 B." in text
    assert "`bx-unresolved`: 0 of 1 target(s) executed, 0 B." in text
    assert "The split is not edited" in text or "the split is not edited" in text


def test_a_recorded_entry_maps_through_the_copy_and_spans_its_instruction(tmp_path):
    rows = [{"region": "rom", "address": 0x08000010, "mode": "thumb"},
            {"region": "iwram", "address": 0x03000004, "mode": "arm"}]
    assert runtime_watch_results.label_spans(rows, image(), copy_export(tmp_path)) == [
        (0x08000010, 0x08000012), (0x08000004, 0x08000008)]


def test_an_address_that_is_not_an_instruction_start_is_refused(tmp_path):
    rows = [{"region": "rom", "address": 0x08000020, "mode": "thumb"}]
    with pytest.raises(SystemExit):
        runtime_watch_results.label_spans(rows, image(), copy_export(tmp_path))


def test_the_page_folds_the_recorded_entries_into_the_class(tmp_path):
    targets = runtime_watch_results.read_targets(str(fixture(tmp_path)))
    hits = [{"kind": "candidate-code", "start": 0x08000100, "end": 0x08000108, "bytes": 8,
             "elapsed": "0.5"}]
    runs = [{"bound": "120", "seconds": "120.0", "targets": "4", "armed": "4", "ranges": "3",
             "liveness": "60", "stops": "62", "executed": "2", "liveness_pc": "0x03000824"}]
    text = runtime_watch_results.doc_text(targets, hits, runs, [(0x0800ff00, 0x0800ff02)])
    assert "## Recorded label entries" in text
    assert "1 recorded entries" in text
    assert "2 extent(s) / 10 B" in text


def test_the_tracked_results_pass_their_check():
    if not os.path.exists(runtime_watch_results.RUNS):
        pytest.skip("no run has been imported, so there is no page to check")
    if not os.path.exists(runtime_watch_results.ROM):
        pytest.skip("no image, so the recorded entries cannot be checked")
    assert runtime_watch_results.main(["--check"]) == 0


if __name__ == "__main__":
    print("PASS test_runtime_watch_results")
