from __future__ import annotations

import os
import struct
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))

import opcode_stream
import testkit


def stream_bytes(*items):
    blob = bytearray()
    for item in items:
        blob += bytes([item[0]])
        blob += item[1]
    return bytes(blob)


def test_a_byte_none_and_end_stream_decodes_and_re_emits_its_bytes():
    blob = stream_bytes((0x00, b"\x2a"), (0x04, b""), (0x11, b""))
    instructions, stop, problem = opcode_stream.decode(blob, 0, len(blob))
    assert problem is None and stop == len(blob)
    assert [item[1] for item in instructions] == [0x00, 0x04, 0x11]
    assert opcode_stream.encode(instructions) == blob


def test_a_varint_survives_a_round_trip():
    blob = stream_bytes((0x01, b"\x81\x02"), (0x11, b""))
    instructions, stop, problem = opcode_stream.decode(blob, 0, len(blob))
    assert problem is None and stop == len(blob)
    assert instructions[0][3] == 0x82
    assert opcode_stream.encode(instructions) == blob


def test_a_counted_opcode_reads_one_count_byte_then_that_many_varints():
    blob = stream_bytes((0x1D, b"\x02\x05\x81\x01"), (0x11, b""))
    instructions, stop, problem = opcode_stream.decode(blob, 0, len(blob))
    assert problem is None and stop == len(blob)
    assert (instructions[0][3], instructions[0][4]) == (2, [5, 0x81])
    assert opcode_stream.encode(instructions) == blob


def test_a_stream_without_an_end_is_reported_not_decoded():
    blob = stream_bytes((0x00, b"\x01"), (0x04, b""))
    _instructions, stop, problem = opcode_stream.decode(blob, 0, len(blob))
    assert stop is None and problem == "no end"


def test_an_absent_opcode_is_reported():
    blob = bytes([0x1E, 0x11])
    _instructions, stop, problem = opcode_stream.decode(blob, 0, len(blob))
    assert stop is None and problem == "opcode 0x1e"


def test_a_short_operand_is_reported():
    blob = bytes([0x00])
    _instructions, stop, problem = opcode_stream.decode(blob, 0, len(blob))
    assert stop is None and problem == "operand"


def test_the_tracked_census_check_passes():
    root = os.path.dirname(os.path.dirname(HERE))
    testkit.rom_bytes(os.path.join(root, "baserom.gba"), digest=opcode_stream.ROM_SHA256)
    assert opcode_stream.main(["--check"]) == 0
