from __future__ import annotations

import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import device_access

BASE = 0x08000000


def image(size=0x300):
    return bytearray(size)


def put_half(data, address, value):
    struct.pack_into("<H", data, address - BASE, value & 0xFFFF)


def put_word(data, address, value):
    struct.pack_into("<I", data, address - BASE, value & 0xFFFFFFFF)


def test_a_literal_register_address_and_a_store_report_the_value_written():
    lines = [(0x08000100, "LDR", "r0, [pc, #0x0]"),
             (0x08000102, "MOV", "r1, #0x80"),
             (0x08000104, "STRH", "r1, [r0, #0x2]")]
    found = device_access.touches("thumb", lines, lambda address: 0x04000100)
    assert found == [(0x04000102, "STRH", 0x80)]


def test_a_shifted_constant_base_is_followed():
    lines = [(0x08000100, "MOV", "r1, #0x1"),
             (0x08000102, "LSL", "r1, r1, #0x1A"),
             (0x08000104, "STR", "r2, [r1, #0x4]")]
    assert device_access.touches("thumb", lines, lambda address: None) == [(0x04000004, "STR", None)]


def test_a_base_below_the_register_block_reports_nothing():
    lines = [(0x08000100, "LDR", "r0, [pc, #0x0]"),
             (0x08000102, "LDRH", "r1, [r0, #0x0]")]
    assert device_access.touches("thumb", lines, lambda address: 0x020038A0) == []


def test_a_store_through_an_iwram_base_reports_the_address_and_the_value_written():
    lines = [(0x08000100, "LDR", "r0, [pc, #0x0]"),
             (0x08000102, "LDR", "r1, [pc, #0x4]"),
             (0x08000104, "STR", "r1, [r0, #0x0]")]
    words = {0x08000104: 0x03007FFC, 0x08000108: 0x03000825}
    assert device_access.touches("thumb", lines, words.get) == [(0x03007FFC, "STR", 0x03000825)]


def test_a_call_keeps_the_callee_saved_registers_and_clears_the_scratch_ones():
    lines = [(0x08000100, "MOV", "r0, #0x1"),
             (0x08000102, "BL", "|loc_08022118|"),
             (0x08000106, "STR", "r0, [r4, #0x0]")]
    assert device_access.touches("thumb", lines, lambda address: None) == []


def test_an_epilogue_clears_only_the_registers_it_restores():
    lines = [(0x08000100, "MOV", "r0, #0x1"),
             (0x08000102, "POP", "{r4, pc}"),
             (0x08000104, "LSL", "r0, r0, #0x1A"),
             (0x08000106, "STR", "r1, [r0, #0x0]")]
    assert device_access.touches("thumb", lines, lambda address: None) == [(0x04000000, "STR", None)]


def test_an_effect_in_a_later_block_counts_and_one_past_another_start_does_not():
    data = image()
    put_half(data, BASE + 0x100, 0x4804)
    put_half(data, BASE + 0x102, 0x2101)
    put_half(data, BASE + 0x104, 0x2900)
    put_half(data, BASE + 0x106, 0xD001)
    put_half(data, BASE + 0x108, 0xBD00)
    put_half(data, BASE + 0x10A, 0x46C0)
    put_half(data, BASE + 0x10C, 0x6001)
    put_half(data, BASE + 0x10E, 0xBD00)
    put_word(data, BASE + 0x114, 0x04000100)
    put_half(data, BASE + 0x200, 0x2001)
    put_half(data, BASE + 0x202, 0x2102)
    put_half(data, BASE + 0x204, 0x0680)
    put_half(data, BASE + 0x206, 0x6001)
    put_half(data, BASE + 0x208, 0x4770)

    def word(address):
        at = address - BASE
        return struct.unpack_from("<I", data, at)[0]

    later = device_access.body(bytes(data), BASE + 0x100, "thumb", BASE + 0x112)
    assert device_access.touches("thumb", later, word) == [(0x04000100, "STR", 0x1)]

    starts = [BASE + 0x200, BASE + 0x204]
    assert device_access.limit(starts, BASE + 0x20A, BASE + 0x200) == BASE + 0x204
    assert device_access.limit(starts, BASE + 0x20A, BASE + 0x204) == BASE + 0x20A
    inside = device_access.body(bytes(data), BASE + 0x200, "thumb",
                               device_access.limit(starts, BASE + 0x20A, BASE + 0x200))
    assert device_access.touches("thumb", inside, word) == []
    past = device_access.body(bytes(data), BASE + 0x200, "thumb", BASE + 0x20A)
    assert device_access.touches("thumb", past, word) == [(0x04000000, "STR", 0x2)]


def test_a_base_decrement_is_followed_to_the_register_it_names():
    lines = [(0x08000100, "LDR", "r1, [pc, #0x0]"),
             (0x08000102, "MOV", "r0, #0x0"),
             (0x08000104, "STRH", "r0, [r1, #0x2]"),
             (0x08000106, "SUB", "r1, #0x40"),
             (0x08000108, "STRH", "r0, [r1, #0x6]"),
             (0x0800010A, "STRH", "r0, [r1, #0x12]")]
    words = {0x08000104: 0x04000100}
    assert device_access.touches("thumb", lines, words.get) == [
        (0x04000102, "STRH", 0x0), (0x040000C6, "STRH", 0x0), (0x040000D2, "STRH", 0x0)]


def test_a_call_reports_the_address_it_branches_to():
    lines = [(0x08000100, "BL", "|loc_08022118|"),
             (0x08000104, "BX", "lr")]
    assert device_access.callees(lines) == [0x08022118]


def test_a_branch_that_is_not_a_call_reports_no_callee():
    lines = [(0x08000100, "B", "|loc_08022118|")]
    assert device_access.callees(lines) == []


def test_a_bios_call_reports_its_number():
    lines = [(0x08000100, "SWI", "0x0")]
    assert device_access.bios(lines) == [0]


def test_a_load_through_a_saved_register_reports_it_as_live_in():
    lines = [(0x08000100, "LDR", "r1, [r4, #0x18]"),
             (0x08000102, "BX", "lr")]
    assert device_access.live_in(lines) == ["r4"]


def test_a_saved_register_that_the_body_writes_first_is_not_live_in():
    lines = [(0x08000100, "PUSH", "{r4, lr}"),
             (0x08000102, "MOV", "r4, r0"),
             (0x08000104, "POP", "{r4, pc}")]
    assert device_access.live_in(lines) == []


def test_an_evidence_cell_quotes_only_the_addresses_it_names():
    assert device_access.quoted("DMA3 SAD (0x040000D4)=0x03003914, CNT_H (0x040000DE)=0x8000") \
        == [0x03003914, 0x040000D4, 0x040000DE]


if __name__ == "__main__":
    test_a_literal_register_address_and_a_store_report_the_value_written()
    test_a_shifted_constant_base_is_followed()
    test_a_base_below_the_register_block_reports_nothing()
    test_a_store_through_an_iwram_base_reports_the_address_and_the_value_written()
    test_a_call_keeps_the_callee_saved_registers_and_clears_the_scratch_ones()
    test_an_epilogue_clears_only_the_registers_it_restores()
    test_an_effect_in_a_later_block_counts_and_one_past_another_start_does_not()
    test_a_base_decrement_is_followed_to_the_register_it_names()
    test_a_call_reports_the_address_it_branches_to()
    test_a_branch_that_is_not_a_call_reports_no_callee()
    test_a_bios_call_reports_its_number()
    test_a_load_through_a_saved_register_reports_it_as_live_in()
    test_a_saved_register_that_the_body_writes_first_is_not_live_in()
    test_an_evidence_cell_quotes_only_the_addresses_it_names()
    print("PASS test_device_access")
