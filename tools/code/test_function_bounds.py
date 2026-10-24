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


def classify(data, entries, rows, modes=None, calls=(), table=(), vectors=(), spans=(),
             pools=(), kept=()):
    return function_bounds.classify(bytes(data), entries, modes or {},
                                    [(BASE + start, BASE + stop) for start, stop in rows],
                                    set(BASE + value for value in calls),
                                    set(BASE + value for value in table),
                                    set(BASE + value for value in vectors),
                                    spans=set(BASE + value for value in spans),
                                    pools=[BASE + value for value in pools],
                                    kept=set(BASE + value for value in kept))


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
    put_half(data, BASE + 0x62, 0x2002)
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


def test_an_end_is_the_byte_after_the_return():
    data = image()
    put_half(data, BASE + 0x10, 0x2001)
    put_half(data, BASE + 0x12, 0xBD00)
    found = classify(data, [BASE + 0x10], [(0x10, 0x14)], calls=[0x10])
    assert found["ends"][BASE + 0x10] == (BASE + 0x14, "-")
    assert [row for row in function_bounds.ends_rows(found)
            if row[0] == BASE + 0x10] == [(BASE + 0x10, function_bounds.THUMB,
                                           "census", BASE + 0x14, "-")]


def test_the_next_start_bounds_an_end():
    data = image()
    for offset, half in ((0x10, 0x2001), (0x12, 0x2002), (0x14, 0x2003), (0x16, 0x2004)):
        put_half(data, BASE + offset, half)
    put_half(data, BASE + 0x18, 0xB510)
    put_half(data, BASE + 0x1A, 0xBD10)
    found = classify(data, [BASE + 0x10, BASE + 0x18], [(0x10, 0x1C)],
                     calls=[0x10, 0x18])
    assert found["ends"][BASE + 0x10] == (BASE + 0x18, "next-start")
    assert found["ends"][BASE + 0x18] == (BASE + 0x1C, "-")


def test_a_literal_pool_bounds_an_end():
    data = image()
    for offset, half in ((0x30, 0x2001), (0x32, 0x2002), (0x34, 0x2003),
                         (0x36, 0x2004), (0x38, 0xBD00)):
        put_half(data, BASE + offset, half)
    found = classify(data, [BASE + 0x30], [(0x30, 0x3C)], calls=[0x30], pools=[0x34])
    assert found["ends"][BASE + 0x30] == (BASE + 0x34, "pool")


def test_a_start_that_opens_no_function_is_corrected_to_its_prologue():
    data = image()
    put_half(data, BASE + 0x100, 0x2001)
    put_half(data, BASE + 0x102, 0xB510)
    put_half(data, BASE + 0x104, 0xBD10)
    found = classify(data, [BASE + 0x100], [(0x100, 0x106)], calls=[0x100])
    assert found["corrected"] == {BASE + 0x100: BASE + 0x102}
    assert function_bounds.ends_rows(found) == [
        (BASE + 0x100, function_bounds.THUMB, "census", BASE + 0x102, "next-start"),
        (BASE + 0x102, function_bounds.THUMB, "census", BASE + 0x106, "-")]
    assert function_bounds.flags_text(function_bounds.flag_rows(
        bytes(data), found)) == ("address,kind,limb,flags,entry,reason\n"
                                 "0x08000100,start,call+block,data,0x08000102,prefix\n")


def test_a_corrected_arm_start_is_walked_as_arm():
    data = image()
    put_word(data, BASE + 0x140, 0xE1A00000)
    put_word(data, BASE + 0x144, 0xE92D4010)
    put_word(data, BASE + 0x148, 0xE12FFF1E)
    found = classify(data, [BASE + 0x140], [(0x140, 0x14C)], {BASE + 0x140: 2},
                     calls=[0x140])
    assert found["corrected"] == {BASE + 0x140: BASE + 0x144}
    assert found["ends"][BASE + 0x144] == (BASE + 0x14C, "-")
    assert [row for row in function_bounds.ends_rows(found)
            if row[0] == BASE + 0x144] == [(BASE + 0x144, function_bounds.ARM, "census",
                                            BASE + 0x14C, "-")]


def test_a_start_that_opens_its_own_function_is_no_flag():
    data = image()
    put_half(data, BASE + 0x120, 0xB510)
    put_half(data, BASE + 0x122, 0xBD10)
    found = classify(data, [BASE + 0x120], [(0x120, 0x124)], calls=[0x120])
    assert found["corrected"] == {}
    assert function_bounds.flag_rows(bytes(data), found) == []


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


def test_the_tracked_ends_and_allow_files_are_what_the_image_gives():
    root = os.path.dirname(os.path.dirname(HERE))
    rom = os.path.join(root, "baserom.gba")
    if not os.path.exists(rom):
        pytest.skip("the retail image is absent, so the bounds cannot be re-derived")
    data = open(rom, "rb").read()
    found = function_bounds.census(data)
    with open(function_bounds.ENDS, encoding="utf-8") as handle:
        assert handle.read() == function_bounds.ends_text(found)
    with open(function_bounds.ALLOW, encoding="utf-8") as handle:
        assert handle.read() == function_bounds.flags_text(
            function_bounds.flag_rows(data, found))


def test_every_census_start_or_its_corrected_entry_carries_an_end():
    root = os.path.dirname(os.path.dirname(HERE))
    rom = os.path.join(root, "baserom.gba")
    if not os.path.exists(rom):
        pytest.skip("the retail image is absent, so the bounds cannot be re-derived")
    found = function_bounds.census(open(rom, "rb").read())
    rows = dict((row[0], row) for row in function_bounds.ends_rows(found))
    missing = [address for address in found["starts"]
               if found["corrected"].get(address, address) not in rows]
    assert missing == []
    assert [row for row in rows.values() if not row[3]] == []


def test_every_flagged_start_names_a_real_entry():
    root = os.path.dirname(os.path.dirname(HERE))
    rom = os.path.join(root, "baserom.gba")
    if not os.path.exists(rom):
        pytest.skip("the retail image is absent, so the flags cannot be re-derived")
    data = open(rom, "rb").read()
    found = function_bounds.census(data)
    rows = function_bounds.flag_rows(data, found)
    assert rows
    assert [row for row in rows
            if row[4] is not None and row[4] != found["corrected"].get(row[0])] == []
    assert [row for row in rows if row[4] is not None and row[4] <= row[0]] == []
    assert [row for row in rows if (row[4] is None) != ("data" not in row[3].split("+"))] == []


def test_every_transcribed_code_span_start_is_classified():
    root = os.path.dirname(os.path.dirname(HERE))
    rom = os.path.join(root, "baserom.gba")
    if not os.path.exists(rom):
        pytest.skip("the retail image is absent, so the census cannot be re-derived")
    import code_split
    import emit_code
    data = open(rom, "rb").read()
    found = function_bounds.census(data)
    spans = [begin for begin, _end, name in emit_code.span_files(emit_code.fragments(data))
             if name.startswith("code_")]
    assert spans
    missing = [begin for begin in spans if begin not in found["starts"]]
    recorded = sorted(address for address in code_split.evidence()["data"] if address in spans)
    assert missing == [0x08000100] + recorded
    owners = [(address, mode) for address, mode, _origin, end, _reason
              in function_bounds.ends_rows(found)
              if address <= 0x08000100 < end]
    assert owners == [(0x080000C0, function_bounds.ARM)]


def test_a_pc_operand_that_is_not_the_destination_does_not_end_a_body():
    assert function_bounds.writes_pc("ADD", "r0, pc, #0x380") is False
    assert function_bounds.writes_pc("ADD", "pc, r0, #0x4") is True
    assert function_bounds.writes_pc("MOV", "r2, pc") is False
    assert function_bounds.writes_pc("POP", "{r4, pc}") is True
    assert function_bounds.writes_pc("LDMIA", "r0!, {r1, pc}") is True
    data = image()
    put_half(data, BASE + 0x140, 0xA001)
    put_half(data, BASE + 0x142, 0x2002)
    put_half(data, BASE + 0x144, 0xBD00)
    found = classify(data, [BASE + 0x140], [(0x140, 0x146)], calls=[0x140])
    assert function_bounds.ends_rows(found) == [
        (BASE + 0x140, function_bounds.THUMB, "census", BASE + 0x146, "-")]


def test_an_entry_the_rows_never_cover_is_a_start_of_its_own_mode():
    data = image()
    put_half(data, BASE + 0x1E0, 0x2001)
    put_half(data, BASE + 0x1E2, 0xBD00)
    found = classify(data, [BASE + 0x1E0], [])
    assert found["starts"][BASE + 0x1E0] == ["entry"]
    assert function_bounds.ends_rows(found) == [
        (BASE + 0x1E0, function_bounds.THUMB, "census", BASE + 0x1E4, "-")]


def test_a_start_inside_the_body_of_the_other_mode_is_no_row():
    data = image()
    put_word(data, BASE + 0x40, 0xE1A00000)
    put_word(data, BASE + 0x44, 0xE1A00000)
    found = classify(data, [BASE + 0x40, BASE + 0x44], [(0x40, 0x48)],
                     {BASE + 0x40: 2, BASE + 0x44: 1}, spans=[0x44])
    assert BASE + 0x44 not in found["starts"]
    assert found["fragments"][BASE + 0x44] == BASE + 0x40
    assert function_bounds.ends_rows(found) == [
        (BASE + 0x40, function_bounds.ARM, "census", BASE + 0x48, "no-return")]


def test_a_start_inside_a_32_bit_first_instruction_is_absorbed():
    data = image()
    put_half(data, BASE + 0x160, 0xF000)
    put_half(data, BASE + 0x162, 0xF800)
    put_half(data, BASE + 0x164, 0xBD00)
    found = classify(data, [BASE + 0x160, BASE + 0x162], [], calls=[0x160])
    assert sorted(found["starts"]) == [BASE + 0x160]
    assert function_bounds.ends_rows(found) == [
        (BASE + 0x160, function_bounds.THUMB, "census", BASE + 0x166, "-")]


def test_a_start_after_a_16_bit_first_instruction_is_no_fragment():
    data = image()
    put_half(data, BASE + 0x160, 0x2001)
    put_half(data, BASE + 0x162, 0x2002)
    put_half(data, BASE + 0x164, 0xBD00)
    found = classify(data, [BASE + 0x160, BASE + 0x162], [])
    assert sorted(found["starts"]) == [BASE + 0x160, BASE + 0x162]
    assert function_bounds.ends_rows(found) == [
        (BASE + 0x160, function_bounds.THUMB, "census", BASE + 0x162, "next-start"),
        (BASE + 0x162, function_bounds.THUMB, "census", BASE + 0x166, "-")]


def test_a_row_start_bounds_the_row_before_a_corrected_entry():
    data = image()
    put_half(data, BASE + 0x180, 0x2001)
    put_half(data, BASE + 0x182, 0x2002)
    put_half(data, BASE + 0x184, 0xB510)
    put_half(data, BASE + 0x186, 0xBD10)
    found = classify(data, [BASE + 0x180], [(0x180, 0x188)], calls=[0x180])
    assert found["corrected"] == {BASE + 0x180: BASE + 0x184}
    assert function_bounds.ends_rows(found) == [
        (BASE + 0x180, function_bounds.THUMB, "census", BASE + 0x184, "next-start"),
        (BASE + 0x184, function_bounds.THUMB, "census", BASE + 0x188, "-")]


def test_a_recorded_entry_keeps_the_body_it_walks_to():
    data = image()
    put_half(data, BASE + 0x100, 0x2001)
    put_half(data, BASE + 0x102, 0xB510)
    put_half(data, BASE + 0x104, 0xBD10)
    found = classify(data, [BASE + 0x100], [(0x100, 0x106)], calls=[0x100],
                     kept=[0x100])
    assert found["corrected"] == {}
    assert function_bounds.ends_rows(found) == [
        (BASE + 0x100, function_bounds.THUMB, "census", BASE + 0x106, "-")]
    assert function_bounds.flag_rows(bytes(data), found) == []


def test_a_recorded_entry_is_not_flagged_as_a_data_prefix():
    data = image()
    put_half(data, BASE + 0x100, 0x2001)
    put_half(data, BASE + 0x102, 0xB510)
    put_half(data, BASE + 0x104, 0xBD10)
    found = classify(data, [BASE + 0x100], [(0x100, 0x106)], calls=[0x100])
    assert found["corrected"] == {BASE + 0x100: BASE + 0x102}
    found = classify(data, [BASE + 0x100], [(0x100, 0x106)], calls=[0x100],
                     kept=[0x100])
    assert found["corrected"] == {}


def test_the_recorded_evidence_is_what_the_image_gives():
    root = os.path.dirname(os.path.dirname(HERE))
    rom = os.path.join(root, "baserom.gba")
    if not os.path.exists(rom):
        pytest.skip("the retail image is absent, so the evidence cannot be re-derived")
    data = open(rom, "rb").read()
    found = function_bounds.census(data)
    ends = dict((row[0], row) for row in function_bounds.ends_rows(found))
    assert ends[0x0800AFF0][3] == 0x0800B00C
    assert ends[0x0800E4D2][3] == 0x0800E54C
    assert 0x08003AFE not in found["starts"]
    assert 0x080042EA not in found["starts"]
    assert 0x0800AFF0 in found["starts"]
    assert 0x0800E4D2 in found["starts"]


def test_a_runtime_row_is_bounded_by_the_nearest_later_start(tmp_path, monkeypatch):
    path = tmp_path / "runtime.csv"
    path.write_text("region,address,mode\nrom,0x08000170,thumb\n", encoding="ascii")
    monkeypatch.setattr(function_bounds, "RUNTIME", str(path))
    data = image(0x400)
    for offset in range(0x170, 0x1C0, 2):
        put_half(data, BASE + offset, 0x2001)
    put_half(data, BASE + 0x1C0, 0xBD00)
    starts = {BASE + 0x200: ["call"], BASE + 0x180: ["call"]}
    assert function_bounds.folded(bytes(data), {"overlay": (0, 0, 0, 0)}, starts) == [
        (BASE + 0x170, function_bounds.THUMB, "runtime", BASE + 0x180, "next-start")]


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

