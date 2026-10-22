from __future__ import annotations

import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))

import testkit
import tilebank


def stored(image, offset, payload):
    image[offset:offset + 8] = struct.pack("<II", 0, len(payload))
    image[offset + 8:offset + 8 + len(payload)] = bytes(payload)


def test_the_tracked_bank_populations_are_what_the_reader_check_pins():
    data = testkit.rom_bytes(tilebank.ROM, digest=tilebank.ROM_SHA256,
                             size=tilebank.ROM_SIZE)
    assert tilebank.check(data) == 0


def test_the_map_loader_quotes_come_from_the_image():
    data = testkit.rom_bytes(tilebank.ROM, digest=tilebank.ROM_SHA256,
                             size=tilebank.ROM_SIZE)
    tilebank.check_reader(data)
    assert tilebank.table_banks(data)[0]["tiles"] == 512


def test_a_bank_declaring_another_size_is_refused():
    image = bytearray(0x200)
    stored(image, 0x40, bytes(64))
    table = 0x08000100
    image[0x100:0x104] = struct.pack("<I", tilebank.ROM_BASE + 0x40)
    assert tilebank.bank(bytes(image), tilebank.ROM_BASE + 0x40, 64)["tiles"] == 2
    assert testkit.refused(lambda: tilebank.bank(bytes(image), tilebank.ROM_BASE + 0x40, 32))


def test_a_table_entry_outside_the_image_is_refused():
    image = bytearray(0x200)
    image[0x100:0x104] = struct.pack("<I", tilebank.ROM_BASE + 0x1F0)
    assert testkit.refused(lambda: tilebank.bank(bytes(image), tilebank.ROM_BASE + 0x1F0, 64))


def test_the_permuted_region_keeps_the_table_and_loses_every_bank():
    image = bytearray(0x200)
    stored(image, 0x40, bytes(range(64)))
    stored(image, 0x100, bytes(range(64)))
    image[0x180:0x188] = struct.pack("<II", tilebank.ROM_BASE + 0x40,
                                     tilebank.ROM_BASE + 0x100)
    table = tilebank.ROM_BASE + 0x180
    assert tilebank.survivors(bytes(image), table, 2, 64) == 2
    scrambled = tilebank.permuted(bytes(image), 0x40, 0x140)
    assert tilebank.survivors(scrambled, table, 2, 64) == 0
