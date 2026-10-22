from __future__ import annotations

import os
import struct
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))

import mapcontainer
import testkit

BANK_SITE = 0x4DF574
BANK_HEADER = 0x4C0000
ENTRY = mapcontainer.ENTRY_TABLE
ARRAY = 0x600
ROOT = 0x700
LAYER = 0x800
CHUNK = 0x900
ROOT_TABLE = 0xA00


def word(image, offset, value):
    struct.pack_into("<I", image, offset, value)


def image():
    data = bytearray(BANK_SITE + 0x100)
    for index in range(mapcontainer.TILE_BANK_COUNT):
        word(data, BANK_SITE + 4 * index, 0x08000000 + BANK_HEADER)
    struct.pack_into("<II", data, BANK_HEADER, 1, mapcontainer.TILE_BANK_DECLARED)
    word(data, ENTRY + mapcontainer.ENTRY_ROOT, 0x08000000 + ARRAY)
    word(data, ARRAY, 0x08000000 + ROOT)
    word(data, ROOT + mapcontainer.ROOT_TILE_BANKS, mapcontainer.TILE_BANK_TABLE)
    for slot in range(mapcontainer.SLOT_COUNT):
        word(data, ROOT + mapcontainer.SLOT_BASE + 4 * slot, 0x08000000 + LAYER)
    word(data, ROOT + mapcontainer.ROOT_TABLE_COUNT, 1)
    word(data, ROOT + mapcontainer.ROOT_TABLE_BASE, 0x08000000 + ROOT_TABLE)
    word(data, LAYER, mapcontainer.FACTORY)
    word(data, LAYER + 4, 0x400)
    data[LAYER + mapcontainer.ROW_FIELD] = 1
    data[LAYER + mapcontainer.COLUMN_FIELD] = 1
    word(data, LAYER + mapcontainer.CHUNK_FIELD, 0x08000000 + CHUNK)
    struct.pack_into("<II", data, CHUNK, 1, 0x400)
    return bytes(data)


def test_one_entry_one_root_one_layer_one_chunk_is_the_whole_population():
    result = mapcontainer.census(image())
    assert result == {"entries": 1, "roots": 1, "layers": 1, "factories": 1, "others": 0,
                      "record_bytes": 132, "chunks": 1, "chunk_headers": 1,
                      "declared_payload": 0x400, "root_table_rows": 1, "root_table_bytes": 24}


def test_a_slot_word_that_is_not_the_tile_bank_table_is_refused():
    data = bytearray(image())
    word(data, ROOT + mapcontainer.ROOT_TILE_BANKS, 0x08400000)
    assert testkit.refused(lambda: mapcontainer.map_roots(bytes(data)))


def test_a_tile_bank_that_is_not_a_kind_one_container_is_refused():
    data = bytearray(image())
    struct.pack_into("<II", data, BANK_HEADER, 0, mapcontainer.TILE_BANK_DECLARED)
    assert testkit.refused(lambda: mapcontainer.tile_banks(bytes(data)))


def test_a_permuted_image_holds_no_root():
    result = mapcontainer.null_census(mapcontainer.permuted(image()))
    assert (result["entries"], result["roots"], result["layers"]) == (0, 0, 0)


def test_a_layer_record_with_another_factory_counts_as_other_not_as_dominant():
    data = bytearray(image())
    word(data, LAYER, 0x08004FCD)
    result = mapcontainer.census(bytes(data))
    assert (result["factories"], result["others"], result["chunks"]) == (0, 1, 0)


def test_the_tracked_census_check_passes():
    root = os.path.dirname(os.path.dirname(HERE))
    testkit.rom_bytes(os.path.join(root, "baserom.gba"), digest=mapcontainer.ROM_SHA256)
    assert mapcontainer.main(["--check"]) == 0
