from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))

import testkit
import transform_slots

ROOT = os.path.dirname(os.path.dirname(HERE))


def retail():
    return testkit.rom_bytes(os.path.join(ROOT, "baserom.gba"),
                             digest=transform_slots.ROM_SHA256)


def test_the_descriptor_table_reproduces_the_retail_bytes():
    result = transform_slots.check(retail())
    assert result["mismatched_records"] == 0
    assert result["records"] == transform_slots.PINNED["slot"]


def test_the_records_are_the_census_population():
    result = transform_slots.check(retail())
    assert result["emitted_bytes"] == transform_slots.CENSUS_BYTES == 408


def test_every_record_is_twelve_bytes_and_the_gap_never_smaller():
    image = retail()
    places = [offset for offset, width in transform_slots.walk(image)["slot"]]
    assert all(width == transform_slots.WIDTH for _offset, width in transform_slots.walk(image)["slot"])
    assert min(later - earlier for earlier, later in zip(places, places[1:])) >= 12


def test_the_initialiser_carries_every_cited_read():
    image = retail()
    window = image[0x0801FA18 - transform_slots.ROM_BASE:0x0801FA34 - transform_slots.ROM_BASE]
    for cited in ("826a", "1368", "8360", "d388", "9b03", "1389", "5389", "1279", "4274"):
        assert bytes.fromhex(cited) in window


def test_a_doctored_step_changes_the_bytes_it_encodes():
    rows = transform_slots.tables()
    labels = dict((row["label"], int(row["address"], 16) - transform_slots.ROM_BASE)
                  for family in rows for row in rows[family])
    row = rows["slot"][0]
    before = transform_slots.maprecords.encode_row("slot", row, labels, transform_slots.SPECS)
    doctored = dict(row)
    doctored["step_0a"] = "%04x" % (int(row["step_0a"], 16) ^ 1)
    after = transform_slots.maprecords.encode_row("slot", doctored, labels, transform_slots.SPECS)
    assert before != after and len(before) == len(after) == 12


def test_the_permuted_records_hold_no_slot():
    image = retail()
    assert transform_slots.null(image)["slot"] == 0
    assert transform_slots.differing(image)["slot"] == transform_slots.PINNED["slot"]


def test_every_named_field_cites_a_load_site():
    text = open(os.path.join(HERE, "TRANSFORM_SLOTS.md"), encoding="utf-8").read()
    assert transform_slots.uncited_fields(text) == []


def test_the_check_refuses_a_doctored_row():
    image = retail()
    rows = transform_slots.tables()
    doctored = dict(rows["slot"][3])
    doctored["clip_end_08"] = "%04x" % (int(doctored["clip_end_08"], 16) ^ 0x100)
    rows["slot"][3] = doctored
    assert transform_slots.check(image, rows=rows)["mismatched_records"] == 1
