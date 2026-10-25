from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))

import table_086f6d8c
import testkit

ROOT = os.path.dirname(os.path.dirname(HERE))


def retail():
    return testkit.rom_bytes(os.path.join(ROOT, "baserom.gba"),
                             digest=table_086f6d8c.ROM_SHA256)


def test_the_table_reproduces_the_retail_bytes():
    result = table_086f6d8c.check(retail())
    assert result["mismatched_records"] == 0
    assert result["records"] == sum(table_086f6d8c.PINNED.values())


def test_the_table_accounts_for_its_population_exactly():
    result = table_086f6d8c.check(retail())
    assert result["emitted_bytes"] == table_086f6d8c.CENSUS_BYTES == 4288


def test_the_emitted_runs_are_inside_the_image_and_do_not_overlap():
    image = retail()
    previous, total = 0, 0
    for start, end, _token in table_086f6d8c.tokens(image):
        assert 0x100 <= start < end <= 0x800000
        assert start >= previous
        previous = end
        total += end - start
    assert total == table_086f6d8c.CENSUS_BYTES


def test_every_pointer_slot_is_a_label_of_this_table():
    rows = table_086f6d8c.tables()
    labels = {row["label"] for family in rows for row in rows[family]}
    for row in rows["record"]:
        assert row["pointers_18"].split()
        assert set(row["pointers_18"].split()) <= labels
    assert set(rows["array"][0]["records"].split()) <= labels
    assert rows["table"][0]["records_04"] in labels


def test_a_doctored_entry_changes_the_bytes_it_encodes():
    rows = table_086f6d8c.tables()
    labels = dict((row["label"], int(row["address"], 16) - table_086f6d8c.ROM_BASE)
                  for family in rows for row in rows[family])
    entry = rows["entry"][0]
    before = table_086f6d8c.maprecords.encode_row("entry", entry, labels,
                                                  table_086f6d8c.SPECS)
    doctored = dict(entry)
    doctored["flag_02"] = "%04x" % (int(entry["flag_02"], 16) ^ 1)
    after = table_086f6d8c.maprecords.encode_row("entry", doctored, labels,
                                                 table_086f6d8c.SPECS)
    assert before != after and before[:2] == after[:2]


def test_the_permuted_table_holds_no_record():
    image = retail()
    counts = table_086f6d8c.null(image)
    assert counts == {family: 0 for family in table_086f6d8c.PINNED}
    assert all(value for value in table_086f6d8c.differing(image).values())


def test_every_named_field_cites_a_load_site():
    text = open(os.path.join(HERE, "LAYOUT.md"), encoding="utf-8").read()
    assert table_086f6d8c.uncited_fields(text) == []


def test_the_check_refuses_a_doctored_table():
    image = retail()
    rows = table_086f6d8c.tables()
    doctored = dict(rows["entry"][0])
    doctored["key_00"] = "%02x" % (int(doctored["key_00"], 16) ^ 0x40)
    rows["entry"][0] = doctored
    result = table_086f6d8c.check(image, rows=rows)
    assert result["mismatched_records"] == 1
