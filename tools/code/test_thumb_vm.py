from __future__ import annotations

import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "tools"))

import pytest

import testkit
import thumb_vm

BASE = 0x08000100


def snippet(halfwords, base=BASE):
    image = bytearray(0x2000)
    for index, value in enumerate(halfwords):
        struct.pack_into("<H", image, base - thumb_vm.ROM_BASE + 2 * index, value)
    return bytes(image), set(base + 2 * index for index in range(len(halfwords)))


def test_an_added_register_pair_is_stored_and_the_result_returned():
    image, body = snippet([0x2005, 0x2103, 0x1840, 0x6010, 0x4770])
    memory = thumb_vm.Memory(image)
    result = thumb_vm.run_function(image, BASE, registers={1: 3, 2: 0x02000000}, memory=memory, body=body)
    assert result["registers"][0] == 8
    assert result["written"] == [(0x02000000, 4, 8)]
    assert result["calls"] == []


def test_a_conditional_branch_loops_until_the_count_reaches_three():
    image, body = snippet([0x2000, 0x3001, 0x2803, 0xDBFC, 0x4770])
    result = thumb_vm.run_function(image, BASE, body=body)
    assert result["registers"][0] == 3
    assert result["steps"] == 11


def test_a_pc_relative_load_reads_the_literal_after_the_code():
    image, body = snippet([0x4800, 0x4770, 0x1234, 0x5678])
    result = thumb_vm.run_function(image, BASE, body=body)
    assert result["registers"][0] == 0x56781234


def test_a_call_is_recorded_and_stubbed_and_the_instruction_after_it_runs():
    image, body = snippet([0xF000, 0xF97E, 0x2007, 0x4770])
    result = thumb_vm.run_function(image, BASE, body=body)
    assert result["calls"] == [(BASE, 0x08000400)]
    assert result["registers"][0] == 7


def test_a_stub_supplies_the_callee_return_values():
    image, body = snippet([0xF000, 0xF97E, 0x4770])
    result = thumb_vm.run_function(image, BASE, body=body, stubs={0x08000400: {0: 0x40}})
    assert result["registers"][0] == 0x40


def test_a_branch_outside_the_body_is_refused():
    image, body = snippet([0xE020, 0x4770])
    with pytest.raises(ValueError, match="left the body"):
        thumb_vm.run_function(image, BASE, body=body)


def test_a_run_past_the_step_budget_is_refused():
    image, body = snippet([0xE7FE])
    with pytest.raises(ValueError, match="step budget"):
        thumb_vm.run_function(image, BASE, body=body, budget=16)


def test_a_push_and_pop_restore_the_stack_and_return_through_the_popped_pc():
    image, body = snippet([0x2401, 0xB510, 0x2402, 0xBD10])
    result = thumb_vm.run_function(image, BASE, body=body, registers={13: 0x03007F00, 14: 0x08000201})
    assert result["registers"][4] == 1
    assert result["registers"][13] == 0x03007F00
    assert result["registers"][15] == 0x08000200


def test_a_halfword_and_a_byte_move_through_the_register_offset_and_immediate_forms():
    image, body = snippet([0x8808, 0x7088, 0x4770])
    memory = thumb_vm.Memory(image)
    memory.half(0x02000010, 0xBEEF)
    result = thumb_vm.run_function(image, BASE, registers={0: 0x02000020, 1: 0x02000010},
                          memory=memory, body=body)
    assert result["registers"][0] == 0xBEEF
    assert (0x02000012, 1, 0xEF) in result["written"]


def test_a_store_multiple_writes_every_listed_register_above_the_base():
    image, body = snippet([0xC00E, 0x4770])
    memory = thumb_vm.Memory(image)
    result = thumb_vm.run_function(image, BASE, registers={0: 0x02000040, 1: 1, 2: 2, 3: 3},
                          memory=memory, body=body)
    assert result["written"] == [(0x02000040, 4, 1), (0x02000044, 4, 2),
                                 (0x02000048, 4, 3)]
    assert result["registers"][0] == 0x0200004C


def test_a_word_load_through_a_register_offset_reads_the_address():
    image, body = snippet([0x6808, 0x4770])
    memory = thumb_vm.Memory(image)
    memory.word(0x02000000, 0xCAFEBABE)
    result = thumb_vm.run_function(image, BASE, registers={1: 0x02000000}, memory=memory, body=body)
    assert result["registers"][0] == 0xCAFEBABE


def test_an_add_of_a_register_and_the_immediate_zero_adds_and_does_not_subtract():
    image, body = snippet([0x2003, 0x2507, 0x1C28, 0x4770])
    result = thumb_vm.run_function(image, BASE, body=body)
    assert result["registers"][0] == 7


def test_a_shift_of_zero_sets_the_zero_flag_for_the_branch_after_it():
    image, body = snippet([0x2500, 0x07ED, 0x2001, 0xD000, 0x2002, 0x4770])
    result = thumb_vm.run_function(image, BASE, body=body)
    assert result["registers"][0] == 1


def test_a_switch_to_arm_state_is_refused():
    image, body = snippet([0x4778])
    with pytest.raises(ValueError, match="switches to ARM"):
        thumb_vm.run_function(image, BASE, body=body)


def test_a_branch_through_a_register_returns_through_its_address():
    image, body = snippet([0x2001, 0x4708])
    result = thumb_vm.run_function(image, BASE, body=body, registers={1: 0x08000401})
    assert result["registers"][0] == 1
    assert result["returned"] == 0x08000400


def test_the_body_of_a_function_comes_from_the_function_bounds_rows():
    image = testkit.rom_bytes(os.path.join(ROOT, "baserom.gba"), size=0x800000)
    body = thumb_vm.body_of(image, 0x0801F08C)
    assert 0x0801F08C in body
    assert 0x0801F0AA in body
    assert 0x0801F110 not in body
