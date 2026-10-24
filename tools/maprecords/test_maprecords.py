from __future__ import annotations

import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))

import maprecords
import testkit

ROOT = os.path.dirname(os.path.dirname(HERE))


def retail():
    return testkit.rom_bytes(os.path.join(ROOT, "baserom.gba"), digest=maprecords.ROM_SHA256)


def test_the_table_reproduces_the_retail_bytes():
    result = maprecords.check(retail())
    assert result["mismatched_records"] == 0
    assert result["records"] == sum(maprecords.PINNED.values())


def test_the_table_accounts_for_the_census_class_exactly():
    result = maprecords.check(retail())
    assert result["emitted_bytes"] == maprecords.CENSUS_BYTES


def test_the_emitted_runs_are_inside_the_image_and_do_not_overlap():
    image = retail()
    previous = 0
    total = 0
    for start, end, _token in maprecords.tokens(image):
        assert 0x100 <= start < end <= 0x800000
        assert start >= previous
        previous = end
        total += end - start
    assert total == maprecords.CENSUS_BYTES


def test_a_doctored_field_changes_the_bytes_it_encodes():
    rows = maprecords.load_tables()
    entry = rows["entry"][0]
    labels = maprecords.labels_of(rows)
    before = maprecords.encode_row("entry", entry, labels)
    doctored = dict(entry)
    doctored["field_00"] = "%02x" % ((int(entry["field_00"], 16) + 1) & 0xFF)
    after = maprecords.encode_row("entry", doctored, labels)
    assert before != after
    assert before[1:] == after[1:]


def test_a_root_pointer_is_a_label_and_not_an_address():
    rows = maprecords.load_tables()
    words = maprecords.array_words(rows["array"][0])
    assert words
    assert all(maprecords.REFERENCE.match(word) for word in words)


def test_the_permuted_records_hold_no_record():
    counts = maprecords.null(retail())
    assert counts == {family: 0 for family in maprecords.PINNED}


def test_every_named_field_cites_a_load_site():
    text = open(os.path.join(HERE, "LAYOUT.md"), encoding="utf-8").read()
    missing = maprecords.uncited_fields(text)
    assert missing == []


def test_the_check_refuses_a_doctored_table(tmp_path):
    rows = maprecords.load_tables()
    doctored = dict(rows["entry"][0])
    doctored["field_01"] = "%02x" % ((int(doctored["field_01"], 16) + 1) & 0xFF)
    rows["entry"][0] = doctored
    result = maprecords.check(retail(), rows=rows)
    assert result["mismatched_records"] == 1
    assert result["records"] == sum(maprecords.PINNED.values())
