from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))

import sprites
import testkit

ROOT = os.path.dirname(os.path.dirname(HERE))


def retail():
    return testkit.rom_bytes(os.path.join(ROOT, "baserom.gba"), digest=sprites.ROM_SHA256)


def test_the_table_reproduces_the_retail_bytes():
    result = sprites.check(retail())
    assert result["mismatched_records"] == 0
    assert result["records"] == sum(sprites.PINNED.values())


def test_the_table_accounts_for_the_census_class_exactly():
    result = sprites.check(retail())
    assert result["emitted_bytes"] == sprites.CENSUS_BYTES


def test_the_emitted_runs_are_inside_the_image_and_do_not_overlap():
    image = retail()
    previous = 0
    total = 0
    for start, end, _token in sprites.tokens(image):
        assert 0x100 <= start < end <= 0x800000
        assert start >= previous
        previous = end
        total += end - start
    assert total == sprites.CENSUS_BYTES


def test_a_doctored_piece_changes_the_bytes_it_encodes():
    rows = sprites.load_tables()
    piece = rows["piece"][0]
    labels = sprites.labels_of(rows)
    before = sprites.encode_row("piece", piece, labels)
    doctored = dict(piece)
    doctored["x"] = "%d" % (int(piece["x"]) + 1)
    after = sprites.encode_row("piece", doctored, labels)
    assert before != after
    assert before[1:] == after[1:]


def test_a_slot_is_a_label_and_not_an_address():
    rows = sprites.load_tables()
    slots = rows["definition"][0]["slots"].split()
    labels = [word for word in slots if sprites.REFERENCE.match(word)]
    assert labels
    assert all(word in sprites.labels_of(rows) for word in labels)


def test_the_permuted_records_hold_no_record():
    image = retail()
    counts = sprites.null(image)
    assert counts == {family: 0 for family in sprites.PINNED}
    kept = sprites.null(image, ("definition", "piece"))
    assert kept == {"directory": 1, "definition": 0, "piece": 0}


def test_every_named_field_cites_a_load_site():
    text = open(os.path.join(HERE, "LAYOUT.md"), encoding="utf-8").read()
    missing = sprites.uncited_fields(text)
    assert missing == []


def test_the_check_refuses_a_doctored_table():
    image = retail()
    rows = sprites.load_tables()
    doctored = dict(rows["piece"][0])
    doctored["w"] = "%d" % (int(doctored["w"]) + 1)
    rows["piece"][0] = doctored
    result = sprites.check(image, rows=rows)
    assert result["mismatched_records"] == 1
    assert result["records"] == sum(sprites.PINNED.values())
