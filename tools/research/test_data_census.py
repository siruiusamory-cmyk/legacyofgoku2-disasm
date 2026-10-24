import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import data_census

IMAGE = [None]
RESULT = [None]
NULL = [None]


def image():
    if IMAGE[0] is None:
        IMAGE[0] = data_census.read_rom()
    return IMAGE[0]


def result():
    if RESULT[0] is None:
        RESULT[0] = data_census.census(image())
    return RESULT[0]


def null():
    if NULL[0] is None:
        NULL[0] = data_census.null_census(image())
    return NULL[0]


def test_the_region_is_the_measured_complement_of_the_containers():
    mask = data_census.region_mask(image())
    assert sum(mask) == data_census.REGION_BYTES


def test_the_classes_partition_the_region_exactly():
    rows = result()["rows"]
    assert sum(row["bytes"] for row in rows) == result()["total"]
    assert result()["total"] == data_census.REGION_BYTES
    assert len(data_census.region_extents(data_census.region_mask(image()))) == \
        result()["region_extents"]
    assert all(row["reader"] or row["name"].startswith(data_census.UNREAD)
               for row in rows)


def test_a_fill_run_of_eight_bytes_is_counted_and_seven_is_not():
    rom = bytes(8) + b"\x01" + bytes(7) + b"\xff" * 9
    mask = bytearray(b"\x01" * len(rom))
    assert data_census.fill_runs(rom, mask) == [(0, 8), (16, 25)]


def test_an_address_run_needs_two_consecutive_words():
    rom = bytearray(0x40)
    struct.pack_into("<II", rom, 0, 0x08000000, 0x08000004)
    struct.pack_into("<I", rom, 0x20, 0x08000008)
    mask = bytearray(b"\x01" * len(rom))
    assert data_census.address_runs(bytes(rom), mask) == [(0, 8)]


def test_every_reader_class_cites_a_site_inside_a_walked_code_extent():
    extents = data_census.code_extents(image())
    readers = [row for row in result()["rows"] if row["reader"]]
    assert readers
    for row in readers:
        site = row["reader"] - data_census.ROM_BASE
        assert data_census.contains(extents, site), row["name"]


def test_a_permuted_region_yields_no_reader_bytes():
    assert result()["reader_bytes"] > 0
    assert null()["reader_bytes"] == 0


def test_the_page_is_what_the_image_derives():
    expected = data_census.doc_text(result(), null())
    with open(data_census.DOC, encoding="utf-8", newline="") as handle:
        assert handle.read() == expected
