from __future__ import annotations

import os
import struct
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import code_split

KICK = ((0x110, 0xE59F1030), (0x114, 0xE58010D4), (0x118, 0xE59F102C),
        (0x11C, 0xE58010D8), (0x120, 0xE59F1028), (0x124, 0xE1B01121),
        (0x128, 0xE3811484), (0x12C, 0x158010DC))


def image(size=0x400, code=b"", pointer=None, declared=0x13):
    data = bytearray(size)
    struct.pack_into("<I", data, 0x00, 0xE12FFF1E)
    struct.pack_into("<I", data, 0xC0, 0xE12FFF1E)
    for offset, value in KICK:
        struct.pack_into("<I", data, offset, value)
    struct.pack_into("<I", data, 0x148, 0x08000200)
    struct.pack_into("<I", data, 0x14C, 0x03000000)
    struct.pack_into("<I", data, 0x150, declared)
    data[0x200:0x210] = b"\xFF" * 0x10
    data[0x100:0x100 + len(code)] = code
    if pointer is not None:
        struct.pack_into("<I", data, 0x180, pointer)
    return bytes(data)


def walked(rom, entry, mode=code_split.MODE_THUMB):
    classes = bytearray(len(rom))
    modes = bytearray(len(rom))
    spans, pools, entries, _calls = code_split.walk(rom, [(entry, mode)], classes, modes,
                                                    code_split.PROVEN)
    return classes, modes, spans, pools, entries


def marked(classes, start, stop):
    return all(classes[index] == code_split.PROVEN for index in range(start, stop))


def test_a_conditional_branch_walks_its_target_and_the_fall_through():
    rom = bytearray(0x200)
    struct.pack_into("<HHHHH", rom, 0x100, 0xD001, 0x2100, 0x4770, 0x2200, 0x4770)
    classes, modes, spans, pools, entries = walked(rom, 0x08000100)
    assert marked(classes, 0x100, 0x10A)


def test_an_unconditional_branch_continues_at_its_target_and_skips_the_between():
    rom = bytearray(0x200)
    struct.pack_into("<HHH", rom, 0x100, 0xE000, 0xFFFF, 0x4770)
    classes, modes, spans, pools, entries = walked(rom, 0x08000100)
    assert marked(classes, 0x100, 0x102)
    assert not marked(classes, 0x102, 0x104)
    assert marked(classes, 0x104, 0x106)


def test_a_call_target_is_proven_and_the_caller_continues():
    rom = bytearray(0x200)
    struct.pack_into("<HHHH", rom, 0x100, 0xF000, 0xF800, 0x4770, 0x4770)
    classes, modes, spans, pools, entries = walked(rom, 0x08000100)
    assert marked(classes, 0x100, 0x106)
    assert (0x08000104, code_split.MODE_THUMB) in entries


def test_a_bx_of_a_pool_loaded_address_proves_its_target():
    rom = bytearray(0x200)
    struct.pack_into("<II", rom, 0xC0, 0xE59FC000, 0xE12FFF1C)
    struct.pack_into("<I", rom, 0xC8, 0x08000115)
    struct.pack_into("<HH", rom, 0x114, 0xB500, 0xBD00)
    classes, modes, spans, pools, entries = walked(rom, 0x080000C0, code_split.MODE_ARM)
    assert (0x08000114, code_split.MODE_THUMB) in entries
    assert marked(classes, 0x114, 0x118)
    assert modes[0x114] == code_split.MODE_THUMB


def test_an_arm_return_address_load_proves_its_target():
    rom = bytearray(0x200)
    struct.pack_into("<II", rom, 0xC0, 0xE59FE000, 0xEA000001)
    struct.pack_into("<III", rom, 0xC8, 0x08000101, 0xE1A00000, 0xE12FFF1E)
    classes, modes, spans, pools, entries = walked(rom, 0x080000C0, code_split.MODE_ARM)
    assert (0x08000100, code_split.MODE_THUMB) in entries


def test_an_arm_ldr_pc_proves_its_target_and_ends_the_path():
    rom = bytearray(0x200)
    struct.pack_into("<II", rom, 0xC0, 0xE59FF000, 0xE1A00000)
    struct.pack_into("<I", rom, 0xC8, 0x08000111)
    classes, modes, spans, pools, entries = walked(rom, 0x080000C0, code_split.MODE_ARM)
    assert (0x08000110, code_split.MODE_THUMB) in entries
    assert marked(classes, 0xC0, 0xC4)
    assert not marked(classes, 0xC4, 0xC8)


@pytest.mark.parametrize("half", [0x4780, 0x47FF, 0xB100, 0xB200, 0xB300, 0xB600, 0xB650, 0xB800,
                                  0xBA00, 0xBE00, 0xBF00, 0xDE00, 0xE800, 0xEFFF, 0xF000, 0xFFFE])
def test_a_thumb_halfword_outside_armv4t_is_refused(half):
    rom = bytearray(0x200)
    struct.pack_into("<HH", rom, 0x100, half, 0x0000)
    assert code_split.thumb_length(rom, 0x08000100) is None


@pytest.mark.parametrize("half", [0x0000, 0x4770, 0xB000, 0xB080, 0xB400, 0xB500, 0xBC00,
                                  0xBD00, 0xD000, 0xDF00, 0xE000])
def test_a_thumb_halfword_inside_armv4t_is_an_instruction(half):
    rom = bytearray(0x200)
    struct.pack_into("<HH", rom, 0x100, half, 0x4770)
    assert code_split.thumb_length(rom, 0x08000100) == 2


def test_a_long_branch_is_a_pair_and_a_lone_halfword_is_refused():
    pair = bytearray(0x200)
    struct.pack_into("<HH", pair, 0x100, 0xF000, 0xF800)
    assert code_split.thumb_length(pair, 0x08000100) == 4
    lone = bytearray(0x200)
    struct.pack_into("<HH", lone, 0x100, 0xF000, 0x0000)
    assert code_split.thumb_length(lone, 0x08000100) is None
    low = bytearray(0x200)
    struct.pack_into("<H", low, 0x100, 0xF800)
    assert code_split.thumb_length(low, 0x08000100) is None


def test_the_cached_views_read_the_image_little_endian():
    found = code_split.views_of(bytearray([0x34, 0x12, 0x78, 0x56]))
    assert found[1][0] == 0x1234
    assert found[2][0] == 0x56781234


def test_a_big_endian_host_is_refused(monkeypatch):
    monkeypatch.setattr(code_split.sys, "byteorder", "big")
    with pytest.raises(SystemExit):
        code_split.views_of(bytearray(8))


def test_the_census_of_a_small_image_is_the_rows_and_runs_a_reader_gets():
    assert code_split.csv_text(code_split.measure(image())) == (
        "start,end,bytes,class\n"
        "0x08000000,0x08000004,4,proven code\n"
        "0x080000C0,0x080000C4,4,proven code\n"
        "0x08000200,0x08000210,16,IWRAM overlay\n")
    assert code_split.measure(image())["decodable"] == {1: 1000, 8: 1000, 32: 1000,
                                                        128: 812}
    pair = code_split.measure(image(code=struct.pack("<HH", 0xF000, 0xF800)))
    assert pair["decodable"] == {1: 998, 8: 998, 32: 936, 128: 496}
    undefined = code_split.measure(image(code=struct.pack("<HH", 0xB100, 0x2000)))
    assert undefined["decodable"] == {1: 998, 8: 998, 32: 938, 128: 496}


def test_the_probe_reports_a_return_and_its_branch_count():
    plain = bytearray(0x200)
    struct.pack_into("<H", plain, 0x100, 0x4770)
    assert code_split.probe(plain, 0x08000100) == (True, True, 0)
    branched = bytearray(0x200)
    struct.pack_into("<HHHHH", branched, 0x100, 0xD000, 0x4770, 0x4770, 0x4770, 0x4770)
    assert code_split.probe(branched, 0x08000100) == (True, True, 1)
    undefined = bytearray(0x200)
    struct.pack_into("<HH", undefined, 0x100, 0xB100, 0x4770)
    assert code_split.probe(undefined, 0x08000100) == (False, False, 0)
    no_return = bytearray(0x200)
    struct.pack_into("<HH", no_return, 0x100, 0xD000, 0xDF00)
    assert code_split.probe(no_return, 0x08000100) == (False, False, 0)


def test_the_permutation_reverses_each_block_and_keeps_its_halfwords():
    rom = bytes(range(0x100))
    shuffled = code_split.permute(rom)
    assert shuffled[:2] == rom[-2:]
    assert sorted(shuffled[index:index + 2] for index in range(0, len(rom), 2)) == \
        sorted(rom[index:index + 2] for index in range(0, len(rom), 2))


def test_the_class_totals_are_the_image_size():
    measured = code_split.measure(image())
    assert measured["totals"] == {"proven code": 8, "filtered pointer-entry code": 0,
                                  "table-held code": 0, "gap-fill code": 0,
                                  "literal pool": 0, "IWRAM overlay": 16,
                                  "unclassified": 0x400 - 24}


def test_a_filtered_entry_names_the_pool_word_its_load_reads():
    code = struct.pack("<HHHHHH", 0x2000, 0xD001, 0x4801, 0x4770, 0x4770, 0x0000)
    measured = code_split.measure(image(code=code, pointer=0x08000101))
    assert measured["accepted"] == [0x08000100]
    assert measured["classes"][0x10C:0x110] == bytes([code_split.POOL]) * 4


def test_the_overlay_length_is_the_dma_word_count_not_the_descriptor():
    measured = code_split.measure(image())
    assert measured["overlay"] == (0x08000200, 0x03000000, 0x10, 0x13)
    assert measured["totals"]["IWRAM overlay"] == 0x10


def test_a_descriptor_outside_iwram_is_refused():
    broken = bytearray(image())
    struct.pack_into("<I", broken, 0x14C, 0x02000000)
    with pytest.raises(ValueError):
        code_split.measure(bytes(broken))


def test_a_kick_that_is_not_the_dma_sequence_is_refused():
    broken = bytearray(image())
    struct.pack_into("<I", broken, 0x124, 0xE1B01122)
    with pytest.raises(ValueError):
        code_split.measure(bytes(broken))


def test_the_thunks_that_point_into_the_copy_are_named():
    rom = bytearray(image())
    struct.pack_into("<HHII", rom, 0x300, 0x4778, 0x46C0, 0xE51FF004, 0x03000008)
    measured = code_split.measure(bytes(rom))
    assert (0x08000300, 0x03000008) in measured["thunks"]


def test_a_jump_table_needs_its_bounds_check_and_base():
    rom = bytearray(image())
    struct.pack_into("<HHHHHHH", rom, 0x2FE, 0x3A1A, 0x2A0E, 0xD20D, 0xA301, 0x5C9B,
                     0x005B, 0x449F)
    struct.pack_into("<H", rom, 0x320, 0x4770)
    struct.pack_into("<I", rom, 0x180, 0x080002FF)
    measured = code_split.measure(bytes(rom))
    assert len(measured["tables"]) == 1
    table = measured["tables"][0]
    assert table["base"] == 0x0800030C
    assert table["count"] == 14
    assert table["scale"] == 2
    assert table["condition"] == "bhs"
    assert table["dispatch"] == 0x0800030A


def test_an_add_pc_ends_the_path_before_the_table():
    rom = bytearray(0x200)
    struct.pack_into("<HHHH", rom, 0x100, 0x2100, 0x448F, 0x4770, 0x4770)
    classes, _modes, _spans, _pools, _entries = walked(rom, 0x08000100)
    assert marked(classes, 0x100, 0x104)
    assert not marked(classes, 0x104, 0x108)


def test_a_call_from_a_filtered_entry_proves_its_callee():
    code = struct.pack("<HHHHH", 0xD000, 0x4770, 0xF000, 0xF82C, 0x4770)
    leaf = struct.pack("<HH", 0x2000, 0x4770)
    rom = bytearray(image(code=code, pointer=0x08000101))
    rom[0x160:0x160 + len(leaf)] = leaf
    measured = code_split.measure(bytes(rom))
    assert 0x08000100 in measured["accepted"]
    assert measured["classes"][0x160:0x164] == bytes([code_split.PROVEN]) * 4


def test_a_branchless_entry_that_nothing_calls_is_refused():
    code = struct.pack("<HH", 0x2000, 0x4770)
    measured = code_split.measure(image(code=code, pointer=0x08000101))
    assert 0x08000100 not in measured["accepted"]


def test_a_pointer_table_word_joins_a_run_that_holds_a_proven_entry():
    code = struct.pack("<HH", 0x2000, 0x4770)
    rom = bytearray(image(code=code, pointer=None))
    struct.pack_into("<II", rom, 0x1A0, 0x080000C1, 0x08000101)
    measured = code_split.measure(bytes(rom))
    assert 0x08000100 in measured["accepted"]
    assert measured["channels"]["function pointer table"] == 1
    assert measured["classes"][0x100:0x104] == bytes([code_split.TABLE]) * 4


def test_a_repeated_record_word_names_a_code_address_the_filter_does_not():
    rom = bytearray(image())
    for offset in (0x1C0, 0x1C4, 0x1C8, 0x1CC):
        struct.pack_into("<I", rom, offset, 0x08000301)
    rom[0x300:0x304] = struct.pack("<HH", 0x2000, 0x4770)
    measured = code_split.measure(bytes(rom))
    assert (0x08000300, code_split.MODE_THUMB) in measured["extra"]
    assert measured["classes"][0x300:0x304] == bytes([code_split.TABLE]) * 4


def test_a_record_word_below_the_repeat_threshold_names_nothing():
    rom = bytearray(image())
    for offset in (0x1C0, 0x1C8, 0x1D0):
        struct.pack_into("<I", rom, offset, 0x08000301)
    rom[0x300:0x304] = struct.pack("<HH", 0x2000, 0x4770)
    measured = code_split.measure(bytes(rom))
    assert (0x08000300, code_split.MODE_THUMB) not in measured["extra"]


def test_a_run_of_two_words_names_a_branchless_entry_that_no_call_proves():
    rom = bytearray(image())
    for offset in (0x300, 0x320):
        rom[offset:offset + 4] = struct.pack("<HH", 0x2000, 0x4770)
    struct.pack_into("<II", rom, 0x180, 0x08000301, 0x08000321)
    measured = code_split.measure(bytes(rom))
    assert measured["held"]["runfree"] == [(0x08000300, code_split.MODE_THUMB),
                                           (0x08000320, code_split.MODE_THUMB)]
    assert measured["classes"][0x300:0x304] == bytes([code_split.TABLE]) * 4


def test_pointer_words_reads_only_a_four_aligned_odd_in_image_word():
    rom = bytearray(0x1000)
    struct.pack_into("<IIII", rom, 0x100, 0x08000301, 0x08000300, 0x00000301, 0x08002001)
    assert code_split.pointer_words(bytes(rom), [0x08000100, 0x08000104, 0x08000108,
                                                 0x0800010A, 0x0800010C]) == {0x08000300}


def test_table_at_stops_at_the_first_word_that_is_not_a_pointer():
    rom = bytearray(0x1000)
    struct.pack_into("<III", rom, 0x100, 0x08000301, 0x08000101, 0)
    assert code_split.table_at(bytes(rom), 0x08000100) == [0x08000300, 0x08000100]


def test_a_register_that_still_holds_a_pool_word_is_proved_from_a_longer_window():
    rom = bytearray(image())
    struct.pack_into("<HHHHH", rom, 0x160, 0x2000, 0xD002, 0x4801, 0x2100, 0x4700)
    struct.pack_into("<H", rom, 0x16A, 0x4770)
    struct.pack_into("<I", rom, 0x16C, 0x08000171)
    struct.pack_into("<H", rom, 0x170, 0x4770)
    struct.pack_into("<I", rom, 0x180, 0x08000161)
    measured = code_split.measure(bytes(rom))
    assert 0x08000160 in measured["accepted"]
    assert (0x08000170, code_split.MODE_THUMB) in measured["extra"]
    assert measured["classes"][0x170:0x172] == bytes([code_split.PROVEN]) * 2


def test_a_prologue_that_decodes_to_a_return_is_measured_but_not_counted_as_code():
    rom = bytearray(image())
    struct.pack_into("<HHH", rom, 0x280, 0xB500, 0x2000, 0xBD00)
    measured = code_split.measure(bytes(rom))
    assert (0x08000280, code_split.MODE_THUMB) in measured["held"]["prologue"]
    assert measured["prologue_bytes"] == 6
    assert measured["classes"][0x280:0x286] == bytes([code_split.UNCLASSIFIED]) * 6
    assert 0x08000280 not in {address for address, _mode in measured["extra"]}


def test_a_prologue_whose_run_branches_before_it_returns_is_refused():
    rom = bytearray(image())
    struct.pack_into("<HHH", rom, 0x280, 0xB500, 0xE000, 0xBD00)
    measured = code_split.measure(bytes(rom))
    assert (0x08000280, code_split.MODE_THUMB) not in measured["held"]["prologue"]


def test_the_halfword_after_a_return_is_filled_when_it_walks():
    rom = bytearray(image())
    struct.pack_into("<HHHHH", rom, 0x100, 0x2000, 0xD001, 0x4770, 0x2000, 0x4770)
    struct.pack_into("<I", rom, 0x180, 0x08000101)
    measured = code_split.measure(bytes(rom))
    assert 0x08000100 in measured["accepted"]
    assert (0x08000106, code_split.MODE_THUMB) in measured["extra"]
    assert measured["classes"][0x106:0x108] == bytes([code_split.GAPFILL]) * 2


def test_a_gap_fill_claim_on_a_prologue_halfword_keeps_the_sweep_from_counting_it():
    rom = bytearray(image())
    struct.pack_into("<HHHHH", rom, 0x100, 0x2000, 0xD001, 0x4770, 0xB500, 0xBD00)
    struct.pack_into("<I", rom, 0x180, 0x08000101)
    measured = code_split.measure(bytes(rom))
    assert measured["classes"][0x106] == code_split.GAPFILL
    assert (0x08000106, code_split.MODE_THUMB) not in measured["held"]["prologue"]
    assert measured["classes"][0x108] == code_split.FILTERED


def test_the_thumb_register_writer_sets_name_every_destination():
    assert code_split.thumb_dests(0x2000) == 1 << 0
    assert code_split.thumb_dests(0x2100) == 1 << 1
    assert code_split.thumb_dests(0x4805) == 1 << 0
    assert code_split.thumb_dests(0xA203) == 1 << 2
    assert code_split.thumb_dests(0x4687) == 1 << 15
    assert code_split.thumb_dests(0xBC10) == 0x10
    assert code_split.thumb_dests(0x4288) == 0
    assert code_split.thumb_dests(0xB500) == 0
    assert code_split.thumb_dests(0x4770) == 0


def test_the_arm_register_writer_sets_name_every_destination():
    assert code_split.arm_dests(0xE1A00000) == 1 << 0
    assert code_split.arm_dests(0xE59F0000) == 1 << 0
    assert code_split.arm_dests(0xE5800000) == 0
    assert code_split.arm_dests(0xE3500000) == 0
    assert code_split.arm_dests(0xE8BD8010) == 0x8010
    assert code_split.arm_dests(0xEAFFFFFE) == 0


def test_the_interrupt_vector_store_is_found_and_its_effects_decoded():
    rom = bytearray(0x200)
    struct.pack_into("<HHHHHHHH", rom, 0x100, 0x4804, 0x4905, 0x63C8, 0x2101, 0x4804,
                     0x0349, 0x8001, 0x4770)
    struct.pack_into("<III", rom, 0x114, 0x03000824, 0x03007FC0, 0x04000200)
    classes = bytearray(len(rom))
    modes = bytearray(len(rom))
    for offset in range(0x100, 0x110):
        classes[offset] = code_split.PROVEN
        modes[offset] = code_split.MODE_THUMB
    install = code_split.irq_install(bytes(rom), classes, modes, [(0x100, 0x110)])
    assert install["site"] == 0x08000104
    assert install["base"] == 0x03007FC0
    assert install["handler"] == 0x03000824
    assert install["immediate"] == 0x3C
    assert {item["address"]: item["value"] for item in install["effects"]}[0x04000200] == 0x2000


def test_the_doc_states_the_classes_a_reader_parses():
    measured = code_split.measure(image())
    doc = code_split.doc_text(measured, code_split.measure_null(image()))
    assert "| proven code | 2 | 8 |" in doc
    assert "| filtered pointer-entry code | 0 | 0 |" in doc
    assert "| IWRAM overlay | 1 | 16 |" in doc
    assert "| total |" in doc


def test_write_then_check_round_trips_and_a_changed_file_is_refused(monkeypatch, tmp_path):
    rom = image()
    source = tmp_path / "baserom.gba"
    source.write_bytes(rom)
    doc = tmp_path / "CODE_SPLIT.md"
    table = tmp_path / "CODE_SPLIT.csv"
    monkeypatch.setattr(code_split, "ROM", str(source))
    monkeypatch.setattr(code_split, "DOC", str(doc))
    monkeypatch.setattr(code_split, "CSV_OUT", str(table))
    assert code_split.main(["--write"]) == 0
    assert code_split.read_totals(str(doc), len(rom)) == code_split.measure(rom)["totals"]
    assert code_split.main(["--check"]) == 0
    doc.write_text(doc.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    assert code_split.main(["--check"]) == 1


def test_the_tracked_split_check_passes():
    if not os.path.exists(code_split.ROM):
        pytest.skip("baserom.gba is absent, so this check cannot run")
    assert code_split.main(["--check"]) == 0


if __name__ == "__main__":
    print("PASS test_code_split")
