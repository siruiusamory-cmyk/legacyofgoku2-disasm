from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))

import opcode_rows
import testkit

ROOT = os.path.dirname(os.path.dirname(HERE))


def retail():
    return testkit.rom_bytes(os.path.join(ROOT, "baserom.gba"), digest=opcode_rows.ROM_SHA256)


def test_the_table_reproduces_the_retail_bytes():
    result = opcode_rows.check(retail())
    assert result["mismatched_records"] == 0
    assert result["records"] == sum(opcode_rows.PINNED.values())


def test_the_table_accounts_for_the_reader_backed_class_exactly():
    result = opcode_rows.check(retail())
    assert result["emitted_bytes"] == opcode_rows.CENSUS_BYTES == 1227


def test_the_emitted_runs_are_inside_the_image_and_do_not_overlap():
    image = retail()
    previous, total = 0, 0
    for start, end, _token in opcode_rows.tokens(image):
        assert 0x100 <= start < end <= 0x800000
        assert start >= previous
        previous = end
        total += end - start
    assert total == opcode_rows.CENSUS_BYTES


def test_every_record_names_two_streams_the_table_carries():
    rows = opcode_rows.tables()
    starts = {int(row["address"], 16) for row in rows["instruction"]}
    for row in rows["quest_record"]:
        assert int(row["stream_04"], 16) in starts
        assert int(row["stream_08"], 16) in starts


def test_a_doctored_operand_changes_the_stream_it_encodes():
    rows = opcode_rows.tables()
    for row in rows["instruction"]:
        item = opcode_rows.stream_item(None, row)[2]
        if len(opcode_rows.operand_tokens(item)) == 1 and item[1] != opcode_rows.opcode_stream.END:
            break
    before = opcode_rows.encode_row("instruction", item, {})
    tokens = opcode_rows.operand_tokens(item)
    doctored = list(item)
    doctored[2] = bytes([item[2][0] ^ 0xff])
    after = opcode_rows.encode_row("instruction", tuple(doctored), {})
    assert before != after and before[0] == after[0]
    assert tokens


def test_the_permuted_table_holds_no_record():
    counts = opcode_rows.null(retail())
    assert counts == {family: 0 for family in opcode_rows.PINNED}


def test_every_named_field_cites_a_load_site():
    text = open(os.path.join(HERE, "LAYOUT.md"), encoding="utf-8").read()
    assert opcode_rows.uncited_fields(text) == []


def test_the_check_refuses_a_doctored_table():
    image = retail()
    rows = opcode_rows.tables()
    changed = 0
    for row in rows["instruction"]:
        item = opcode_rows.stream_item(None, row)[2]
        if len(opcode_rows.operand_tokens(item)) == 1 and item[1] != opcode_rows.opcode_stream.END:
            doctored = dict(row)
            doctored["operands"] = "%02x" % (int(row["operands"], 16) ^ 0xff)
            rows["instruction"][rows["instruction"].index(row)] = doctored
            changed += 1
            break
    assert changed
    result = opcode_rows.check(image, rows=rows)
    assert result["mismatched_records"] == 1
