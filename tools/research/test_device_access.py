from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import device_access


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
    assert device_access.touches("thumb", lines, lambda address: 0x030038A0) == []


def test_a_body_that_reaches_another_entry_is_not_this_entry():
    lines = [(0x08000100, "MOV", "r0, #0x0"),
             (0x08000102, "BX", "lr")]
    assert device_access.unit(lines, {0x08000100}) == lines
    assert device_access.unit(lines, {0x08000102}) is None


def test_a_call_reports_the_address_it_branches_to():
    lines = [(0x08000100, "BL", "|loc_08022118|"),
             (0x08000104, "BX", "lr")]
    assert device_access.callees(lines) == [0x08022118]


def test_a_branch_that_is_not_a_call_reports_no_callee():
    lines = [(0x08000100, "B", "|loc_08022118|")]
    assert device_access.callees(lines) == []


def test_a_load_through_a_saved_register_reports_it_as_live_in():
    lines = [(0x08000100, "LDR", "r1, [r4, #0x18]"),
             (0x08000102, "BX", "lr")]
    assert device_access.live_in(lines) == ["r4"]


def test_a_saved_register_that_the_body_writes_first_is_not_live_in():
    lines = [(0x08000100, "PUSH", "{r4, lr}"),
             (0x08000102, "MOV", "r4, r0"),
             (0x08000104, "POP", "{r4, pc}")]
    assert device_access.live_in(lines) == []


if __name__ == "__main__":
    test_a_literal_register_address_and_a_store_report_the_value_written()
    test_a_shifted_constant_base_is_followed()
    test_a_base_below_the_register_block_reports_nothing()
    test_a_body_that_reaches_another_entry_is_not_this_entry()
    test_a_call_reports_the_address_it_branches_to()
    test_a_branch_that_is_not_a_call_reports_no_callee()
    test_a_load_through_a_saved_register_reports_it_as_live_in()
    test_a_saved_register_that_the_body_writes_first_is_not_live_in()
    print("PASS test_device_access")
