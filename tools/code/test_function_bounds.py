from __future__ import annotations

import os
import struct
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import function_bounds

BASE = 0x08000000


def image(size=0x200):
    return bytearray(size)


def put_half(data, address, value):
    struct.pack_into("<H", data, address - BASE, value & 0xFFFF)


def put_word(data, address, value):
    struct.pack_into("<I", data, address - BASE, value & 0xFFFFFFFF)


def classify(data, entries, rows, modes=None, calls=(), table=(), vectors=(), spans=()):
    return function_bounds.classify(bytes(data), entries, modes or {},
                                    [(BASE + start, BASE + stop) for start, stop in rows],
                                    set(BASE + value for value in calls),
                                    set(BASE + value for value in table),
                                    set(BASE + value for value in vectors),
                                    spans=set(BASE + value for value in spans))


def row_of(found, address):
    return [line for line in function_bounds.rows_text(found).splitlines()
            if line.startswith("0x%08x," % address)][0]


def test_a_push_that_saves_lr_is_the_prologue_limb():
    data = image()
    put_half(data, BASE + 0x10, 0xB510)
    put_half(data, BASE + 0x12, 0xBD10)
    found = classify(data, [BASE + 0x10], [(0x10, 0x14)])
    assert "prologue" in found["starts"][BASE + 0x10]
    assert "block" in found["starts"][BASE + 0x10]


def test_a_push_that_does_not_save_lr_is_no_prologue_limb():
    data = image()
    put_half(data, BASE + 0x20, 0xB410)
    put_half(data, BASE + 0x22, 0xBD10)
    found = classify(data, [BASE + 0x20], [(0x20, 0x24)])
    assert found["starts"][BASE + 0x20] == ["block"]


def test_an_arm_stmfd_that_saves_lr_is_the_prologue_limb():
    data = image()
    put_word(data, BASE + 0x40, 0xE92D4030)
    put_word(data, BASE + 0x44, 0xE12FFF1E)
    found = classify(data, [BASE + 0x40], [(0x40, 0x48)], {BASE + 0x40: 2})
    assert "prologue" in found["starts"][BASE + 0x40]


def test_an_entry_with_no_limb_inside_a_proved_body_is_a_fragment():
    data = image()
    put_half(data, BASE + 0x60, 0x2001)
    put_half(data, BASE + 0x62, 0xBD00)
    put_half(data, BASE + 0x64, 0x2003)
    put_half(data, BASE + 0x66, 0xBD00)
    found = classify(data, [BASE + 0x60, BASE + 0x64], [(0x60, 0x68)])
    assert BASE + 0x64 in found["fragments"]
    assert found["fragments"][BASE + 0x64] == BASE + 0x60


def test_an_entry_that_opens_a_proved_code_run_is_a_start():
    data = image()
    put_half(data, BASE + 0x80, 0x2001)
    put_half(data, BASE + 0x82, 0xBD00)
    put_half(data, BASE + 0x84, 0x2002)
    put_half(data, BASE + 0x86, 0xBD00)
    found = classify(data, [BASE + 0x80, BASE + 0x84], [(0x80, 0x84), (0x84, 0x88)])
    assert BASE + 0x84 in found["starts"]
    assert found["starts"][BASE + 0x84] == ["block"]


def test_a_dispatch_table_word_is_the_table_limb():
    data = image()
    put_half(data, BASE + 0xA0, 0x4770)
    found = classify(data, [BASE + 0xA0], [(0xA0, 0xA4)], table=[0xA0])
    assert "table" in found["starts"][BASE + 0xA0]


def test_a_proof_inside_another_body_is_reported_and_not_a_start():
    data = image()
    put_half(data, BASE + 0xC0, 0xB510)
    put_half(data, BASE + 0xC2, 0xE000)
    put_half(data, BASE + 0xC4, 0xBD10)
    put_half(data, BASE + 0xC6, 0x2003)
    put_half(data, BASE + 0xC8, 0xBD00)
    found = classify(data, [BASE + 0xC0, BASE + 0xC6], [(0xC0, 0xCC)], calls=[0xC6])
    assert found["contained"] == 1
    assert BASE + 0xC6 not in found["starts"]
    assert found["fragments"][BASE + 0xC6] == BASE + 0xC0


def test_a_body_stops_at_the_end_of_its_run():
    data = image()
    put_half(data, BASE + 0xE0, 0x2001)
    found = classify(data, [BASE + 0xE0, BASE + 0xF0], [(0xE0, 0xE2), (0xF0, 0xF2)])
    assert found["bodies"][BASE + 0xE0] == BASE + 0xE0
    assert BASE + 0xF0 in found["starts"]


def test_a_transcribed_span_start_that_no_rule_reaches_is_unreferenced():
    data = image()
    put_half(data, BASE + 0x110, 0x2001)
    put_half(data, BASE + 0x112, 0xBD00)
    found = classify(data, [], [(0x110, 0x114)], spans=[0x110])
    assert found["starts"][BASE + 0x110] == ["block"]
    assert row_of(found, BASE + 0x110) == "0x08000110,unreferenced,block"


def test_a_transcribed_span_start_that_saves_lr_is_a_referenced_start():
    data = image()
    put_half(data, BASE + 0x120, 0xB510)
    put_half(data, BASE + 0x122, 0xBD10)
    found = classify(data, [], [(0x120, 0x124)], spans=[0x120])
    assert row_of(found, BASE + 0x120) == "0x08000120,start,prologue+block"


def test_an_unreferenced_span_start_does_not_swallow_an_evidence_start():
    data = image()
    put_half(data, BASE + 0x20, 0x2001)
    put_half(data, BASE + 0x22, 0x2002)
    put_half(data, BASE + 0x24, 0x2003)
    put_half(data, BASE + 0x26, 0xBD00)
    found = classify(data, [BASE + 0x24], [(0x20, 0x28)], spans=[0x20], calls=[0x24])
    assert found["contained"] == 0
    assert found["starts"][BASE + 0x24] == ["call"]
    assert BASE + 0x24 not in found["fragments"]


def test_the_tracked_bounds_file_is_what_the_image_gives():
    root = os.path.dirname(os.path.dirname(HERE))
    rom = os.path.join(root, "baserom.gba")
    if not os.path.exists(rom):
        pytest.skip("the retail image is absent, so the census cannot be re-derived")
    found = function_bounds.census(open(rom, "rb").read())
    with open(function_bounds.BOUNDS, encoding="utf-8") as handle:
        assert handle.read() == function_bounds.rows_text(found)


def test_every_transcribed_code_span_start_is_classified():
    root = os.path.dirname(os.path.dirname(HERE))
    rom = os.path.join(root, "baserom.gba")
    if not os.path.exists(rom):
        pytest.skip("the retail image is absent, so the census cannot be re-derived")
    import emit_code
    data = open(rom, "rb").read()
    found = function_bounds.census(data)
    spans = [begin for begin, _end, name in emit_code.span_files(emit_code.fragments(data))
             if name.startswith("code_")]
    assert spans
    assert [begin for begin in spans if begin not in found["starts"]] == []


if __name__ == "__main__":
    test_a_push_that_saves_lr_is_the_prologue_limb()
    test_a_push_that_does_not_save_lr_is_no_prologue_limb()
    test_an_arm_stmfd_that_saves_lr_is_the_prologue_limb()
    test_an_entry_with_no_limb_inside_a_proved_body_is_a_fragment()
    test_an_entry_that_opens_a_proved_code_run_is_a_start()
    test_a_dispatch_table_word_is_the_table_limb()
    test_a_proof_inside_another_body_is_reported_and_not_a_start()
    test_a_body_stops_at_the_end_of_its_run()
    print("PASS test_function_bounds")
