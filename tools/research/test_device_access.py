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


if __name__ == "__main__":
    test_a_literal_register_address_and_a_store_report_the_value_written()
    test_a_shifted_constant_base_is_followed()
    test_a_base_below_the_register_block_reports_nothing()
    test_a_body_that_reaches_another_entry_is_not_this_entry()
    print("PASS test_device_access")
