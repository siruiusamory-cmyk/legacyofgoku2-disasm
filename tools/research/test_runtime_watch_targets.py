from __future__ import annotations

import csv
import os
import struct
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import runtime_watch_targets


def tracked_rows():
    with open(runtime_watch_targets.CSV_OUT, newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    for row in rows:
        row["start"] = int(row["start"], 16)
        row["end"] = int(row["end"], 16)
    return rows


def test_a_missing_image_is_refused(tmp_path):
    with pytest.raises(SystemExit):
        runtime_watch_targets.targets(rom_path=str(tmp_path / "absent.gba"))


def test_a_code_extent_outside_the_image_is_not_decoded():
    rom = bytearray(0x40)
    struct.pack_into("<I", rom, 0, 0xE12FFF13)
    sites = runtime_watch_targets.register_sites(bytes(rom), [(0x08000000, 4, "arm"),
                                                              (0x03000000, 4, "arm")])
    assert sites == [(0x08000000, "arm")]


def test_the_interrupt_slots_follow_the_exported_handler_copy():
    rows = runtime_watch_targets.irq_rows()
    assert len(rows) == 14
    assert [at for at, _runtime in rows] == list(range(0x087FE4F8, 0x087FE530, 4))
    assert rows[0][1] == "0x03000e3c"
    assert rows[-1][1] == "0x03000e70"


def test_the_tracked_targets_pass_their_check_and_are_ordered():
    if not os.path.exists(runtime_watch_targets.ROM):
        pytest.skip("the image is absent, so the targets cannot be derived")
    assert runtime_watch_targets.main(["--check"]) == 0
    rows = tracked_rows()
    assert {row["kind"] for row in rows} == set(runtime_watch_targets.KINDS)
    order = {kind: index for index, kind in enumerate(runtime_watch_targets.KINDS)}
    assert rows == sorted(rows, key=lambda row: (order[row["kind"]], row["start"]))
    assert all(0x08000000 <= row["start"] < row["end"] <= 0x08800000 for row in rows)
    assert [row["start"] for row in rows if row["kind"] == "irq-slot"] == list(
        range(0x087FE4F8, 0x087FE530, 4))
    candidates = [{"start": row["start"], "end": row["end"]} for row in rows
                  if row["kind"] == "candidate-code"]
    assert len(candidates) == 808
    assert runtime_watch_targets.merged_bytes(candidates) == 26062
    for kind in ("bx-unresolved", "irq-slot"):
        mine = [row for row in rows if row["kind"] == kind]
        assert all(left["end"] <= right["start"] for left, right in zip(mine, mine[1:]))


if __name__ == "__main__":
    print("PASS test_runtime_watch_targets")
