from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))

import text_rows
import testkit

ROOT = os.path.dirname(os.path.dirname(HERE))


def retail():
    return testkit.rom_bytes(os.path.join(ROOT, "baserom.gba"), digest=text_rows.ROM_SHA256)


def test_the_table_reproduces_the_retail_bytes():
    result = text_rows.check(retail())
    assert result["mismatched_records"] == 0
    assert result["records"] == sum(text_rows.PINNED.values())


def test_the_table_accounts_for_the_census_class_exactly():
    result = text_rows.check(retail())
    assert result["emitted_bytes"] == text_rows.CENSUS_BYTES
    assert result["bytes"] - result["emitted_bytes"] == 0


def test_the_emitted_runs_are_inside_the_image_and_do_not_overlap():
    image = retail()
    previous = 0
    total = 0
    for start, end, _token in text_rows.tokens(image):
        assert 0x100 <= start < end <= 0x800000
        assert start >= previous
        previous = end
        total += end - start
    assert total == text_rows.CENSUS_BYTES


def test_a_doctored_character_changes_only_its_own_byte():
    rows = text_rows.tables()
    labels = text_rows.maprecords.labels_of(rows)
    row = rows["roster_string"][0]
    before = text_rows.maprecords.encode_row("roster_string", row, labels, text_rows.SPECS)
    doctored = dict(row, text=row["text"][:-1] + row["text"][-1].upper())
    after = text_rows.maprecords.encode_row("roster_string", doctored, labels, text_rows.SPECS)
    assert len(before) == len(after)
    assert before != after
    assert before[:-2] == after[:-2]


def test_a_text_field_is_a_label_and_not_an_address():
    rows = text_rows.tables()
    labels = text_rows.maprecords.labels_of(rows)
    words = rows["roster"][0]["text_00"].split() + rows["roster"][0]["text_04"].split()
    assert words
    assert all(text_rows.maprecords.REFERENCE.match(word) for word in words)
    assert all(word in labels for word in words)


def test_an_objective_row_names_the_record_that_carries_it():
    image = retail()
    rows = text_rows.tables()
    for index, row in enumerate(rows["objective"]):
        offset = text_rows.u32(image, text_rows.text_storage.OBJECTIVES + 16 * index + 12)
        assert "%08x" % offset == row["address"]


def test_the_permuted_extents_hold_no_record_of_any_family():
    image = retail()
    assert text_rows.null(image) == {family: 0 for family in text_rows.PINNED}
    assert text_rows.counts(image) == text_rows.COUNTS
    assert text_rows.differing(image) == text_rows.PINNED


def test_every_named_field_cites_a_load_site():
    text = open(os.path.join(HERE, "LAYOUT.md"), encoding="utf-8").read()
    assert text_rows.uncited_fields(text) == []


def test_the_check_refuses_a_doctored_table():
    image = retail()
    rows = text_rows.tables()
    rows["roster_string"][0] = dict(rows["roster_string"][0], text="AlligatoR")
    result = text_rows.check(image, rows=rows)
    assert result["mismatched_records"] == 1
    assert result["records"] == sum(text_rows.PINNED.values())
