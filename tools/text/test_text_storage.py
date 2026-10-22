from __future__ import annotations

import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))

import testkit
import text_storage


def synthetic():
    image = bytearray(0x500)
    table = 0x200
    offsets = [0] * text_storage.FONT_CODES
    offsets[ord(" ")] = 0x100
    offsets[ord("A")] = 0x104
    for code, value in enumerate(offsets):
        struct.pack_into("<H", image, 0x200 + 2 * code, value)
    struct.pack_into("<HHH", image, 0x200 + 2 * 0x100, 2, 0x0001, 0x0002)
    struct.pack_into("<HHHHHH", image, 0x200 + 2 * 0x104, 4, 1, 1, 1, 1, 0)
    image[0x30:0x33] = b"He\0"
    image[0x38:0x3D] = b"Bad\x01\0"
    return bytes(image), table


def test_the_tracked_text_population_is_what_the_reader_check_pins():
    data = testkit.rom_bytes(text_storage.ROM, digest=text_storage.ROM_SHA256,
                             size=text_storage.ROM_SIZE)
    assert text_storage.check(data) == 0


def test_the_draw_routine_and_the_font_table_are_read_from_the_image():
    data = testkit.rom_bytes(text_storage.ROM, digest=text_storage.ROM_SHA256,
                             size=text_storage.ROM_SIZE)
    text_storage.check_reader(data)
    shapes = text_storage.font(data)
    assert shapes["codes"] == shapes["records"] == 221
    assert shapes["widths"][ord("A")] == 5


def test_a_string_ends_at_its_terminator():
    image, _table = synthetic()
    row = text_storage.string(image, text_storage.ROM_BASE + 0x30)
    assert row["bytes"] == b"He"
    assert row["length"] == 2


def test_a_byte_outside_the_printable_set_is_refused():
    image, _table = synthetic()
    assert testkit.refused(lambda: text_storage.string(image, text_storage.ROM_BASE + 0x38))


def test_the_synthetic_font_resolves_a_code_to_its_record_width():
    image, table = synthetic()
    shapes = text_storage.font(image, table)
    assert shapes["codes"] == 2
    assert shapes["widths"][ord("A")] == 4
    assert shapes["widths"][ord(" ")] == 2
